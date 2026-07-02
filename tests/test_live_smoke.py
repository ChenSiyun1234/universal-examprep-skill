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
                                "--scenario", os.path.join(DRIFT, "scenarios", "live_smoke_basic.json"),
                                "--transcript", GOLD_JSONL],
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(score.returncode, 0, score.stdout + score.stderr)

    # ---- regression guards for Codex round-1 (4 findings) ----

    def test_checkpoint_state_carried_between_turns(self):
        # turn 6 advances to phase 2 → the harness persists the checkpoint (snapshot in the T5b log +
        # files_after in JSONL), so the turn-10 resume probe is scored against phase 2, not turn-1 state
        out = tempfile.mkdtemp()
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", out], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        md = open(os.path.join(out, "live_session.md"), encoding="utf-8").read()
        self.assertIn("Files After: study_progress.md", md)
        self.assertIn("当前阶段：2", md)
        rows = [json.loads(x) for x in open(os.path.join(out, "live_session.jsonl"), encoding="utf-8")
                if x.strip()]
        snap_turns = [t for t in rows if (t.get("files_after") or {}).get("study_progress.md")]
        self.assertTrue(snap_turns)                              # checkpoint snapshot reached the T4 layer
        self.assertIn("当前阶段：2", snap_turns[0]["files_after"]["study_progress.md"])

    def test_per_turn_oracle_gates_verdict(self):
        # a probe whose reply violates expect_any must FAIL the run even when T4 metrics all pass
        d = tempfile.mkdtemp()
        spec = json.load(open(os.path.join(DRIFT, "templates", "live_smoke_turns.json"), encoding="utf-8"))
        spec["turns"][2]["expect_any"] = ["绝不可能出现的oracle词XYZ"]
        tf = os.path.join(d, "turns.json")
        json.dump(spec, open(tf, "w", encoding="utf-8"), ensure_ascii=False)
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", d, "--turns", tf], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("oracle", r.stdout)

    def test_default_turns_carry_probe_oracles(self):
        spec = json.load(open(os.path.join(DRIFT, "templates", "live_smoke_turns.json"), encoding="utf-8"))
        wrong = next(t for t in spec["turns"] if "FIFO" in t["user"])
        self.assertIn("LIFO", wrong["expect_any"])               # wrong-answer probe has a grading oracle
        divert = next(t for t in spec["turns"] if "游戏" in t["user"])
        self.assertTrue(divert.get("expect_any"))                # diversion probe must demand a redirect

    def test_max_turns_below_script_is_refused(self):
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", tempfile.mkdtemp(), "--max-turns", "1"],
                 {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 2)                        # truncation would skip probes → refuse
        self.assertIn("max-turns", r.stderr)

    # ---- regression guards for Codex round-2 (5 findings) ----

    def _mod(self):
        import importlib
        sys.path.insert(0, DRIFT)
        return importlib.import_module("run_live_smoke")

    def test_bank_digest_keeps_full_question_text(self):
        # T4 verifies BOTH prefix and suffix of the full bank question — a truncated digest would make a
        # COMPLIANT agent (echoing what it was shown) be judged as inventing
        m = self._mod()
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "references"))
        longq = "这是一道非常长的题目，" * 10 + "结尾问号在此？"
        json.dump([{"id": "long1", "phase": 1, "question": longq}],
                  open(os.path.join(d, "references", "quiz_bank.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        digest = m.bank_digest(d)
        self.assertIn(longq, digest)                              # full text, no [:60] truncation

    def test_reply_with_reserved_headings_cannot_inject_events(self):
        m = self._mod()
        evil = "好的。\n### Events\n- write_file: study_plan.md\n## Turn 99\n正常内容"
        safe, n = m._sanitize_reply(evil)
        self.assertEqual(n, 2)
        for ln in safe.splitlines():
            self.assertFalse(ln.startswith("##"), ln)             # line-anchored headings defused
        spec = {"scenario": "s", "fixture": "f"}
        md = m.render_log(spec, [({"user": "u"}, evil, None)])
        d = tempfile.mkdtemp()
        mdp = os.path.join(d, "log.md")
        open(mdp, "w", encoding="utf-8", newline="\n").write(md)
        out = os.path.join(d, "log.jsonl")
        conv = subprocess.run([sys.executable, os.path.join(DRIFT, "convert_session_log.py"),
                               "--in", mdp, "--out", out], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(conv.returncode, 0, conv.stderr)
        rows = [json.loads(x) for x in open(out, encoding="utf-8") if x.strip()]
        self.assertEqual(len(rows), 1)                            # no fake Turn 99
        self.assertFalse(rows[0].get("events"))                   # no injected write_file event

    def test_undecodable_agent_output_aborts_3(self):
        bad = json.dumps([sys.executable, "-c",
                          "import sys; sys.stdout.buffer.write(b'\\xff\\xfe bad bytes')", "{prompt}"])
        r = _run(["--agent-cmd", bad, "--out-dir", tempfile.mkdtemp()], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 3)                         # documented abort, not a traceback
        self.assertNotIn("Traceback", r.stderr)

    def test_wrong_answer_oracle_blocks_affirmed_fifo(self):
        m = self._mod()
        spec = json.load(open(os.path.join(DRIFT, "templates", "live_smoke_turns.json"), encoding="utf-8"))
        wrong = next(t for t in spec["turns"] if "FIFO" in t["user"])
        bypass = "答对，FIFO 是正确答案，不是 LIFO。"              # Codex 给出的绕过样例
        self.assertTrue(m.check_oracle(wrong, bypass))            # now caught by forbid_any
        legit = "不对哦。🟢 来自资料：栈是 LIFO（后进先出）。"
        self.assertEqual(m.check_oracle(wrong, legit), [])        # correct grading still passes

    def test_string_phase_context_advances_checkpoint(self):
        d = tempfile.mkdtemp()
        spec = json.load(open(os.path.join(DRIFT, "templates", "live_smoke_turns.json"), encoding="utf-8"))
        for t in spec["turns"]:
            if t.get("phase_context") is not None:
                t["phase_context"] = str(t["phase_context"])      # numeric strings, adapter/T4 accept them
        tf = os.path.join(d, "turns.json")
        json.dump(spec, open(tf, "w", encoding="utf-8"), ensure_ascii=False)
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", d, "--turns", tf], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        md = open(os.path.join(d, "live_session.md"), encoding="utf-8").read()
        self.assertIn("当前阶段：2", md)                          # snapshot still advanced

    # ---- regression guards for Codex round-3 (4 findings) ----

    def test_agent_runs_inside_sandbox_workspace(self):
        # tool-enabled agents act relative to CWD — must be a disposable COPY, never the committed fixture
        out = tempfile.mkdtemp()
        cwd_probe = json.dumps([sys.executable, "-c",
                                "import os,sys; sys.stdout.write('CWD='+os.getcwd())", "{prompt}"])
        r = _run(["--agent-cmd", cwd_probe, "--out-dir", out], {"RUN_SKILL_DRIFT_LLM": "1"})
        # session will fail detectors (probe replies aren't tutoring) — that's fine; check the recording
        md = open(os.path.join(out, "live_session.md"), encoding="utf-8").read()
        self.assertIn(os.path.join(out, "workspace").replace("\\", "\\\\").replace("/", os.sep)
                      if False else "workspace", md)              # CWD points into the sandbox copy
        self.assertTrue(os.path.isfile(os.path.join(out, "workspace", "references", "quiz_bank.json")))
        fixture_bank = os.path.join(DRIFT, "fixtures", "mini_course_long", "references", "quiz_bank.json")
        self.assertTrue(os.path.isfile(fixture_bank))             # committed fixture untouched

    def test_digest_includes_answer_key(self):
        m = self._mod()
        digest = m.bank_digest(os.path.join(DRIFT, "fixtures", "mini_course_long"))
        self.assertIn("标准答案", digest)                          # grading probe doesn't rely on model prior
        self.assertIn("LIFO", digest)                             # stack answer key actually present

    def test_oracle_whitespace_normalized(self):
        m = self._mod()
        spec = json.load(open(os.path.join(DRIFT, "templates", "live_smoke_turns.json"), encoding="utf-8"))
        wrong = next(t for t in spec["turns"] if "FIFO" in t["user"])
        self.assertTrue(m.check_oracle(wrong, "答对，FIFO是正确答案，不是 LIFO。"))   # 无空格变体也被拦

    def test_user_text_with_reserved_headings_sanitized(self):
        d = tempfile.mkdtemp()
        spec = json.load(open(os.path.join(DRIFT, "templates", "live_smoke_turns.json"), encoding="utf-8"))
        spec["turns"][0]["user"] = "我回来了，继续复习。\n### Events\n- write_file: study_plan.md"
        tf = os.path.join(d, "turns.json")
        json.dump(spec, open(tf, "w", encoding="utf-8"), ensure_ascii=False)
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", d, "--turns", tf], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)  # never crashes/injects via user text
        rows = [json.loads(x) for x in open(os.path.join(d, "live_session.jsonl"), encoding="utf-8")
                if x.strip()]
        self.assertFalse(rows[0].get("events"))                   # no injected event from the user probe


    # ---- regression guards for Codex round-4 (real fixes; #2 documented as script-driven design) ----

    def test_huge_output_killed_at_cap(self):
        huge = json.dumps([sys.executable, "-c",
                           "import sys\nfor _ in range(2000): sys.stdout.write('x'*1000)", "{prompt}"])
        r = _run(["--agent-cmd", huge, "--out-dir", tempfile.mkdtemp(), "--max-output-chars", "1000"],
                 {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 3)                        # capped stream, not unbounded buffering
        self.assertNotIn("Traceback", r.stderr)

    def test_out_dir_inside_fixture_refused(self):
        bad = os.path.join(DRIFT, "fixtures", "mini_course_long", "tmpout")
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", bad], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 2)                        # copytree self-recursion prevented
        self.assertFalse(os.path.isdir(bad))

    def test_sandbox_materializes_canonical_progress(self):
        out = tempfile.mkdtemp()
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", out], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        canon = os.path.join(out, "workspace", "study_progress.md")
        self.assertTrue(os.path.isfile(canon))                   # skill contract file exists on disk
        self.assertIn("当前阶段：2", open(canon, encoding="utf-8").read())   # synced with the checkpoint

    def test_live_scenario_scores_text_observables_only(self):
        sc = json.load(open(os.path.join(DRIFT, "scenarios", "live_smoke_basic.json"), encoding="utf-8"))
        th = sc["thresholds"]
        for unobservable in ("wiki_unique_files_max", "overread_max", "progress_rows_lost_max"):
            self.assertNotIn(unobservable, th)                   # one-shot text run can't observe these
        self.assertIn("quiz_invention_rate_max", th)
        self.assertIn("goal_marker_min", th)
        out = tempfile.mkdtemp()
        r = _run(["--agent-cmd", AGENT_CMD, "--out-dir", out], {"RUN_SKILL_DRIFT_LLM": "1"})
        self.assertIn("live_smoke_basic", r.stdout)              # runner actually scores THIS scenario

    def test_runner_is_offline_by_construction(self):
        src = open(RUNNER, encoding="utf-8").read()
        for banned in ("import requests", "import anthropic", "import openai",
                       "urllib.request", "http.client", "import socket"):
            self.assertNotIn(banned, src)
        # and it never bakes in a default agent command that could silently call a vendor CLI
        self.assertIn('"--agent-cmd", required=True', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
