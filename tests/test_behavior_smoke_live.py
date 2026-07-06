# -*- coding: utf-8 -*-
"""B2 — behavior_smoke LIVE single-turn smoke is WIRED (no longer a skeleton).

The live path (`run_behavior_smoke.py --llm`) drives a real agent per scenario and applies the SAME
deterministic detectors as `--mock` to each reply. These tests exercise the wiring WITHOUT a paid LLM:
  (1) live_reply_check reuses the mock detectors — the committed golden passes, the negative fails;
  (2) the full run_llm pipe runs end-to-end against a STUB agent (a tiny local script that returns each
      scenario's golden reply), so every reply-verifiable scenario PASSES and transcripts are written.
Opt-in gating stays: no env + no --agent-cmd → refuses (returns 2), never runs `claude` in CI."""
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BS = os.path.join(ROOT, "benchmark", "behavior_smoke")
sys.path.insert(0, BS)
import run_behavior_smoke as B  # noqa: E402

SCEN = json.loads(io.open(os.path.join(BS, "scenarios.json"), encoding="utf-8").read())
FIXTURE = os.path.join(BS, SCEN.get("fixture", "fixtures/mini_course"))
_BY_NAME = {s["name"]: s for s in SCEN["scenarios"]}
REPLY_VERIFIABLE = ["quiz_bank_only", "scope_override", "provenance_labels", "zero_basic_key_question",
                    "teaching_template", "time_budget_no_questions", "knowledge_window_recheck",
                    "language_first_ask", "visual_first_assets"]


def _read(rel):
    with io.open(os.path.join(BS, rel), encoding="utf-8") as f:
        return f.read()


class LiveReplyCheckReusesMockDetectors(unittest.TestCase):
    """live_reply_check runs the SAME positive detectors --mock uses (no logic drift)."""

    def test_golden_reply_passes_each_scenario(self):
        for name in REPLY_VERIFIABLE:
            sc = _BY_NAME[name]
            res = B.live_reply_check(name, sc, _read(sc["mock_output"]), FIXTURE)
            self.assertIsNotNone(res, name)
            ok, detail = res
            self.assertTrue(ok, f"{name}: golden reply should pass live detector — {detail}")

    def test_negative_reply_fails_where_a_negative_exists(self):
        for name in REPLY_VERIFIABLE:
            sc = _BY_NAME[name]
            if not sc.get("mock_negative"):
                continue
            ok, _detail = B.live_reply_check(name, sc, _read(sc["mock_negative"]), FIXTURE)
            self.assertFalse(ok, f"{name}: negative reply must fail the live detector")

    def test_state_mutation_scenarios_are_skipped_not_faked(self):
        # a one-shot `claude -p` can only TALK — file/state scenarios must return None (SKIP), never PASS
        for name in ("hint_skip_mistake_archive", "confusion_tracking", "checkpoint_recovery",
                     "no_python_fallback"):
            self.assertIsNone(B.live_reply_check(name, _BY_NAME[name], "anything", FIXTURE), name)


class RunLlmGating(unittest.TestCase):
    def test_optin_refused_without_env_or_agent_cmd(self):
        old = os.environ.pop("RUN_SKILL_BEHAVIOR_LLM", None)
        try:
            self.assertEqual(B.run_llm(["--llm"]), 2)
        finally:
            if old is not None:
                os.environ["RUN_SKILL_BEHAVIOR_LLM"] = old


class RunLlmEndToEndWithStubAgent(unittest.TestCase):
    """The full pipe drives an agent per scenario and applies detectors — proven with a stub agent
    (returns each scenario's golden reply) so it's deterministic and paid-LLM-free."""

    def _stub_path(self, tmp):
        # a tiny agent: given the prompt (argv[1]), find the scenario whose student turn it contains,
        # print that scenario's golden mock_output. Emulates a perfectly-compliant agent.
        p = os.path.join(tmp, "stub_agent.py")
        src = (
            "import sys, json, io, os\n"
            "prompt = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "BS = %r\n"
            "d = json.load(io.open(os.path.join(BS, 'scenarios.json'), encoding='utf-8'))\n"
            "for sc in d['scenarios']:\n"
            "    if sc.get('prompt') and sc['prompt'] in prompt and sc.get('mock_output'):\n"
            "        sys.stdout.reconfigure(encoding='utf-8')\n"
            "        sys.stdout.write(io.open(os.path.join(BS, sc['mock_output']), encoding='utf-8').read())\n"
            "        break\n"
        ) % BS
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(src)
        return p

    def test_pipe_runs_and_all_reply_scenarios_pass(self):
        tmp = tempfile.mkdtemp()
        stub = self._stub_path(tmp)
        out = os.path.join(tmp, "out")
        # JSON-array agent-cmd is the cross-platform exact form call_agent accepts (no shell parsing);
        # {prompt} is substituted as a single argv element even though it is huge/multiline.
        agent_cmd = json.dumps([sys.executable, stub, "{prompt}"])
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = B.run_llm(["--llm", "--agent-cmd", agent_cmd, "--out-dir", out, "--timeout", "60"])
        finally:
            sys.stdout = old
        report = buf.getvalue()
        self.assertEqual(rc, 0, "all reply-verifiable scenarios should PASS against a compliant stub\n" + report)
        # every reply-verifiable scenario ran and wrote a transcript; state ones were SKIPped
        for name in REPLY_VERIFIABLE:
            self.assertTrue(os.path.isfile(os.path.join(out, "live_%s.md" % name)), name)
        self.assertIn("passed,", report)
        self.assertEqual(report.count("[FAIL]"), 0, report)

    def test_noncompliant_stub_makes_scenarios_fail(self):
        # a stub that returns an empty/irrelevant reply → detectors fail → run_llm returns 1 (not a
        # silent pass): proves the pipe actually applies the detectors to the live reply.
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "empty_agent.py")
        # ASCII-only reply so call_agent accepts it as valid UTF-8; it is simply non-compliant, so the
        # DETECTORS (not call_agent's byte guard) are what must reject it.
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.stdout.write('irrelevant reply, not compliant')\n")
        agent_cmd = json.dumps([sys.executable, p, "{prompt}"])
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = B.run_llm(["--llm", "--agent-cmd", agent_cmd, "--out-dir", os.path.join(tmp, "o"),
                            "--timeout", "60"])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 1, "a non-compliant agent must make the live smoke FAIL, not pass")


if __name__ == "__main__":
    unittest.main()
