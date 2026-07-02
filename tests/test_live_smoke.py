# -*- coding: utf-8 -*-
"""Tests for T5c run_live_smoke.py — the whole pipeline exercised OFFLINE via a local fake agent.

No model, no network, no API keys anywhere: the "agent command" under test is tests/fake_live_agent.py
(a deterministic local python script). The env gate is exercised both ways; the detectors are proven to
actually gate the exit code (a drifting fake agent must FAIL). The committed golden log reproduces the
convert→score half from a clean checkout without running any agent."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIFT = os.path.join(ROOT, "benchmark", "drift")
RUNNER = os.path.join(DRIFT, "run_live_smoke.py")
FAKE = os.path.join(ROOT, "tests", "fake_live_agent.py")
GOLD_MD = os.path.join(DRIFT, "fixtures", "live_logs", "live_smoke_golden.md")
GOLD_JSONL = os.path.join(DRIFT, "fixtures", "live_logs", "live_smoke_golden.jsonl")

AGENT_CMD = json.dumps([sys.executable, FAKE, "{prompt}"])


def _run(args, env_extra=None):
    env = dict(os.environ)
    env.pop("RUN_SKILL_DRIFT_LLM", None)
    env.pop("FAKE_DRIFT", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, RUNNER] + args,
                          capture_output=True, text=True, encoding="utf-8", env=env)


class LiveSmoke(unittest.TestCase):
    def test_refuses_without_env_gate(self):
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", tempfile.mkdtemp()])
        self.assertEqual(r.returncode, 2)
        self.assertIn("RUN_SKILL_DRIFT_LLM", r.stderr)            # opt-in, never silently runs

    def test_good_fake_agent_passes_end_to_end(self):
        out = tempfile.mkdtemp()
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", out], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)    # drive→record→convert→score all ran
        self.assertIn("PASS", r.stdout)                           # T4 verdict is real, not synthesized
        md, jsonl = os.path.join(out, "live_session.md"), os.path.join(out, "live_session.jsonl")
        self.assertTrue(os.path.isfile(md) and os.path.isfile(jsonl))
        rows = [json.loads(x) for x in open(jsonl, encoding="utf-8") if x.strip()]
        self.assertEqual(len(rows), 10)                           # all scripted turns recorded
        conv = subprocess.run([sys.executable, os.path.join(DRIFT, "convert_session_log.py"),
                               "--in", md, "--check"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(conv.returncode, 0, conv.stderr)         # the T5b log is a valid, auditable artifact

    def test_drifting_fake_agent_fails_detectors(self):
        # detectors must GATE the exit code: an inventing agent cannot exit 0
        out = tempfile.mkdtemp()
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", out],
                 {"RUN_SKILL_DRIFT_LLM": "1", "FAKE_DRIFT": "1"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("quiz_invention_rate_max", r.stdout)        # failed for the intended reason

    def test_agent_command_failure_aborts_3(self):
        bad = json.dumps([sys.executable, "-c", "import sys; sys.exit(9)", "{prompt}"])
        r = _run(["--agent-cmd", bad, "--out-dir", tempfile.mkdtemp()], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 3)                         # broken session is never scored

    def test_output_budget_breach_aborts_3(self):
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", tempfile.mkdtemp(), "--max-output-chars", "5"],
                 {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("max-output-chars", r.stderr)

    def test_prompt_budget_breach_aborts_3(self):
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", tempfile.mkdtemp(), "--max-prompt-chars", "50"],
                 {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("max-prompt-chars", r.stderr)

    def test_malformed_turns_file_exits_2(self):
        d = tempfile.mkdtemp()
        bad = os.path.join(d, "t.json")
        open(bad, "w", encoding="utf-8").write('{"fixture": "x"}')
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", d, "--turns", bad], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 2)

    def test_golden_log_converts_and_scores_clean(self):
        # committed, self-authored golden: the convert→score half reproduces from a clean checkout
        self.assertTrue(os.path.isfile(GOLD_MD) and os.path.isfile(GOLD_JSONL))
        d = tempfile.mkdtemp()
        out = os.path.join(d, "g.jsonl")
        conv = subprocess.run([sys.executable, os.path.join(DRIFT, "convert_session_log.py"),
                               "--in", GOLD_MD, "--out", out], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(conv.returncode, 0, conv.stderr)
        with open(out, encoding="utf-8") as f, open(GOLD_JSONL, encoding="utf-8") as g:
            self.assertEqual([json.loads(x) for x in f if x.strip()],
                             [json.loads(x) for x in g if x.strip()])   # golden pair stays in sync
        score = subprocess.run([sys.executable, os.path.join(DRIFT, "run_drift.py"),
                                "--scenario", os.path.join(DRIFT, "scenarios", "long_session_basic.json"),
                                "--transcript", GOLD_JSONL],
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(score.returncode, 0, score.stdout + score.stderr)

    def test_runner_is_offline_by_construction(self):
        src = open(RUNNER, encoding="utf-8").read()
        for banned in ("import requests", "import anthropic", "import openai",
                       "urllib.request", "http.client", "import socket"):
            self.assertNotIn(banned, src)
        # and it never bakes in a default agent command that could silently call a vendor CLI
        self.assertIn('"--agent-cmd", required=True', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
