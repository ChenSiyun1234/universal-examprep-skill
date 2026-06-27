# -*- coding: utf-8 -*-
"""Tests for devflow's guarded GitHub WRITE integration + bounded polling + approval gating.
All gh calls are mocked. No network, no real mutations.

    python -m unittest tests.test_devflow_github_write
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from devflow.tools import github_cli as G
from devflow.tools.github_cli import (
    GitHubWriter, GhError, bounded_poll, _assert_write_allowed,
)
from devflow.graph import build_graph
from devflow.state import new_state, APPROVED, APPROVAL_GATES, GATE_ADVISORY
from devflow.nodes import advisory as advisory_nodes
from devflow.nodes import pr_review as pr_nodes


def quiet(*_a, **_k):
    pass


class TestWriteGuard(unittest.TestCase):
    def test_refuses_merge_delete_force(self):
        for bad in (["pr", "merge", "1"], ["issue", "delete", "1"], ["branch", "-D", "x"],
                    ["pr", "create", "--force"], ["repo", "delete"]):
            with self.assertRaises(GhError):
                _assert_write_allowed(bad)

    def test_allows_create_comment(self):
        for ok in (["issue", "create"], ["issue", "comment"], ["pr", "create"], ["pr", "comment"]):
            _assert_write_allowed(ok)

    def test_writer_has_no_merge_capability(self):
        w = GitHubWriter("o/r", logger=quiet)
        self.assertFalse(hasattr(w, "merge_pr"))
        self.assertFalse(hasattr(w, "merge"))


class TestDryRunWrites(unittest.TestCase):
    def test_dry_run_does_not_spawn_gh(self):
        with mock.patch.object(G.subprocess, "run", side_effect=AssertionError("no subprocess!")):
            w = GitHubWriter("o/r", live=False, logger=quiet)
            r1 = w.create_advisory_issue("t", "b", labels=["x"])
            r2 = w.comment_on_issue(5, "@codex hi")
            r3 = w.create_draft_pr("t", "b", "main", "feat")
            r4 = w.comment_on_pr(5, "@codex review")
        for r in (r1, r2, r3, r4):
            self.assertFalse(r["executed"])
            self.assertTrue(r.get("dry_run"))
        self.assertTrue(all(c["executed"] is False for c in w.calls))


class TestRealWrites(unittest.TestCase):
    def _fake_run(self, recorder, stdout=""):
        def fake(cmd, **kw):
            recorder.append(cmd)
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return fake

    def test_real_mode_calls_intended_commands_only(self):
        calls = []
        with mock.patch.object(G.shutil, "which", return_value="gh"), \
             mock.patch.object(G.subprocess, "run",
                               side_effect=self._fake_run(calls, "https://github.com/o/r/issues/7")):
            w = GitHubWriter("o/r", live=True, logger=quiet)
            res = w.create_advisory_issue("Title", "Body")
            w.comment_on_issue(7, "@codex advise")
            w.create_draft_pr("PR", "body", "main", "feat")
            w.comment_on_pr(8, "@codex review")
        self.assertTrue(res["executed"])
        self.assertEqual(res["number"], 7)  # parsed from URL
        allowed = {("issue", "create"), ("issue", "comment"), ("pr", "create"), ("pr", "comment")}
        forbidden = {"merge", "delete", "--force", "-D", "push", "close"}
        self.assertTrue(calls)
        for cmd in calls:
            args = cmd[1:]                       # drop "gh"
            self.assertEqual(cmd[0], "gh")
            self.assertIn(tuple(args[:2]), allowed)
            self.assertFalse(set(a.lower() for a in args) & forbidden)
            self.assertIn("--draft", args) if args[:2] == ["pr", "create"] else None

    def test_real_write_fails_safely(self):
        def boom(cmd, **kw):
            return SimpleNamespace(returncode=1, stdout="", stderr="gh: something broke")
        with mock.patch.object(G.shutil, "which", return_value="gh"), \
             mock.patch.object(G.subprocess, "run", side_effect=boom):
            res = GitHubWriter("o/r", live=True, logger=quiet).create_advisory_issue("t", "b")
        self.assertFalse(res["executed"])
        self.assertIn("something broke", res["error"])


class TestBoundedPolling(unittest.TestCase):
    def test_stops_when_never_found(self):
        seen = {"n": 0, "sleeps": 0}
        def fetch():
            seen["n"] += 1
            return None
        res = bounded_poll(fetch, max_attempts=4, sleep_seconds=99,
                           sleep_fn=lambda s: seen.__setitem__("sleeps", seen["sleeps"] + 1))
        self.assertFalse(res["found"])
        self.assertEqual(res["attempts"], 4)
        self.assertEqual(seen["n"], 4)
        self.assertEqual(seen["sleeps"], 3)  # no sleep after the final attempt

    def test_stops_early_when_found(self):
        vals = [None, None, {"ok": 1}]
        res = bounded_poll(lambda: vals.pop(0), max_attempts=9, sleep_seconds=0, sleep_fn=quiet)
        self.assertTrue(res["found"])
        self.assertEqual(res["attempts"], 3)


class TestWaitNodesRealMode(unittest.TestCase):
    def _state(self):
        s = new_state("docs-advisory", "t", real_github=True, max_polls=3, poll_seconds=0)
        s["issue_number"] = 7
        s["pr_number"] = 8
        s["_sleep_fn"] = quiet  # don't actually sleep in tests
        return s

    def test_advisory_timeout_reported(self):
        with mock.patch.object(G.ReadOnlyGitHub, "find_latest_codex_advisory", return_value=None):
            out = advisory_nodes.wait_for_codex_advisory(self._state())
        self.assertEqual(out["codex_advisory_status"], "timeout")
        self.assertTrue(out["errors"])
        self.assertTrue(any("TIMEOUT" in e for e in out["event_log"]))

    def test_advisory_found(self):
        packet = {"author": "codex", "body": "## Advisory\n- do x", "created_at": "z"}
        with mock.patch.object(G.ReadOnlyGitHub, "find_latest_codex_advisory", return_value=packet):
            out = advisory_nodes.wait_for_codex_advisory(self._state())
        self.assertEqual(out["codex_advisory_status"], "ready")
        self.assertEqual(out["advisory_packet"], packet)

    def test_review_timeout_reported(self):
        with mock.patch.object(G.ReadOnlyGitHub, "find_latest_codex_review", return_value=None):
            out = pr_nodes.wait_for_codex_review(self._state())
        self.assertEqual(out["codex_review_status"], "timeout")
        self.assertTrue(out["errors"])


class TestApprovalBeforeEdits(unittest.TestCase):
    def test_interrupt_happens_before_applying_changes(self):
        # nothing seeded -> pause at the advisory gate, before any implementation node runs
        state = new_state("docs-advisory", "t", approvals={})
        final = build_graph(prefer_fallback=True).invoke(state)
        self.assertEqual(final["status"], "paused")
        self.assertEqual(final["paused_at_gate"], GATE_ADVISORY)
        log = " ".join(final["event_log"])
        self.assertNotIn("apply_approved_changes", log)
        self.assertNotIn("create_draft_pr", log)
        self.assertNotIn("claude_execute_merge", log)

    def test_dry_run_graph_never_spawns_gh(self):
        # full dry-run run (auto-approve) must not spawn any gh subprocess
        with mock.patch.object(G.subprocess, "run", side_effect=AssertionError("no subprocess!")):
            state = new_state("docs-advisory", "t",
                              approvals={g: APPROVED for g in APPROVAL_GATES})
            final = build_graph(prefer_fallback=True).invoke(state)
        self.assertEqual(final["status"], "done")


class TestNoMergeInGraph(unittest.TestCase):
    def test_merge_node_is_noop(self):
        from devflow.nodes.merge import claude_execute_merge
        out = claude_execute_merge(new_state("t", "t"))
        self.assertTrue(any("merge NOT executed" in e for e in out["event_log"]))


if __name__ == "__main__":
    unittest.main()
