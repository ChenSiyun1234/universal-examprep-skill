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


class LiveRoundOneFixes(unittest.TestCase):
    """Regressions for the Codex round-1 findings on the live wiring."""

    def test_T1_agent_runs_in_throwaway_copy_pristine_fixture_untouched(self):
        # a MUTATING stub agent (appends an invented item to the bank in its cwd) must neither dirty
        # the tracked fixture nor make quiz_bank_only pass off the altered bank.
        tmp = tempfile.mkdtemp()
        agent = os.path.join(tmp, "mutating_agent.py")
        with io.open(agent, "w", encoding="utf-8") as f:
            f.write("import sys, json, io, os\n"
                    "sys.stdout.reconfigure(encoding='utf-8')\n"
                    "bank = os.path.join(os.getcwd(), 'references', 'quiz_bank.json')\n"
                    "with io.open(bank, encoding='utf-8') as _f:\n"
                    "    d = json.load(_f)\n"
                    "d.append({'id': 'INVENTED_999', 'question': 'x', 'chapter': 1})\n"
                    "with io.open(bank, 'w', encoding='utf-8') as _f:\n"
                    "    json.dump(d, _f)\n"
                    "sys.stdout.write('题目 [#INVENTED_999] x？')\n")
        fixture_bank = os.path.join(FIXTURE, "references", "quiz_bank.json")
        with io.open(fixture_bank, encoding="utf-8") as f:
            before = f.read()
        agent_cmd = json.dumps([sys.executable, agent, "{prompt}"])
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            B.run_llm(["--llm", "--agent-cmd", agent_cmd, "--out-dir", os.path.join(tmp, "o"),
                       "--timeout", "60"])
        finally:
            sys.stdout = old
        # the tracked fixture bank is byte-identical after the run (agent mutated only its sandbox copy)
        with io.open(fixture_bank, encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(before, after, "live agent must NOT mutate the tracked fixture")
        self.assertNotIn("INVENTED_999", after)
        # quiz_bank_only reports FAIL against the pristine oracle (INVENTED_999 not in the real bank)
        self.assertIn("[FAIL] quiz_bank_only", buf.getvalue())

    def test_T2_live_teaching_template_catches_unsolicited_closers(self):
        # golden passes; the golden + an appended closer block must FAIL the live check
        sc = _BY_NAME["teaching_template"]
        good = _read(sc["mock_output"])
        self.assertTrue(B.live_reply_check("teaching_template", sc, good, FIXTURE)[0])
        with_closer = good + "\n\n【易错点】：注意别漏条件。\n【3分钟速记】：口诀……"
        self.assertFalse(B.live_reply_check("teaching_template", sc, with_closer, FIXTURE)[0],
                         "unsolicited 收尾块 after the source block must fail live too")

    def test_T3_unknown_flag_outside_llm_is_rejected(self):
        with self.assertRaises(SystemExit):     # argparse .error() raises SystemExit(2)
            B.main(["--mock", "--out-dir", "x"])   # --out-dir is an llm-only flag; must not silently pass

    def test_T4_live_prompt_exposes_visual_asset_paths(self):
        sc = _BY_NAME["visual_first_assets"]
        prompt = B._live_prompt(FIXTURE, sc)
        bank = json.loads(_read(os.path.join(os.path.relpath(FIXTURE, BS), "references", "quiz_bank.json")))
        vis = [q for q in bank if isinstance(q, dict)
               and (q.get("requires_assets") or q.get("maybe_requires_assets")
                    or q.get("question_text_status") in ("stub", "page_reference"))]
        self.assertTrue(vis, "fixture should have a visual-required item")
        for q in vis:
            for a in (q.get("assets") or []):
                if isinstance(a, dict) and a.get("path"):
                    self.assertIn(str(a["path"]).replace("\\", "/"), prompt,
                                  "the live prompt must expose each visual item's asset path")


class LiveRoundTwoFixes(unittest.TestCase):
    """Regressions for the Codex round-2 findings."""

    def test_T1_run_llm_rejects_typo_subflag(self):
        # a typo'd live sub-flag must fail loudly (a paid run must not proceed on the default timeout)
        with self.assertRaises(SystemExit):
            B.run_llm(["--llm", "--agent-cmd", "echo {prompt}", "--timeot", "5"])

    def test_T2_scope_override_requires_a_served_item(self):
        sc = _BY_NAME["scope_override"]
        # a reply that prints ONLY the override warning and serves no question must FAIL live
        only_warn = "⚠️ 临时覆盖你的 homework-only 范围偏好。"
        self.assertFalse(B.live_reply_check("scope_override", sc, only_warn, FIXTURE)[0])
        # the committed golden (override + a served [#id]) still passes
        self.assertTrue(B.live_reply_check("scope_override", sc, _read(sc["mock_output"]), FIXTURE)[0])

    def test_T3_live_prompt_omits_answer_side_asset_paths(self):
        # a synthetic fixture item carrying BOTH a question-side figure and an answer-side worked_solution:
        # the prompt must expose the question-side path but NEVER the answer-side one (no answer leak).
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "references"))
        bank = [{"id": "vq", "question": "看图求解", "chapter": 1, "requires_assets": True,
                 "assets": [{"role": "figure", "path": "references/assets/prompt_fig.png"},
                            {"role": "worked_solution", "path": "references/assets/answer_sol.png"}]}]
        with io.open(os.path.join(tmp, "references", "quiz_bank.json"), "w", encoding="utf-8") as f:
            json.dump(bank, f, ensure_ascii=False)
        prompt = B._live_prompt(tmp, {"prompt": "出这题"})
        self.assertIn("references/assets/prompt_fig.png", prompt)
        self.assertNotIn("answer_sol.png", prompt, "answer-side asset path must NOT leak into the prompt")


class LiveRoundThreeFixes(unittest.TestCase):
    """Regressions for the Codex round-3 findings."""

    def test_T1_scope_override_rejects_invented_id(self):
        sc = _BY_NAME["scope_override"]
        # override declared + an INVENTED id (not in the bank) must FAIL live (bank-only violation)
        invented = "⚠️ 临时覆盖你的 homework-only 范围偏好\n\n题目 [#INVENTED_999] 看图？"
        self.assertFalse(B.live_reply_check("scope_override", sc, invented, FIXTURE)[0])

    def test_T2_negative_budget_flag_rejected(self):
        with self.assertRaises(SystemExit):
            B.run_llm(["--llm", "--agent-cmd", "echo {prompt}", "--max-out", "-2000"])
        with self.assertRaises(SystemExit):
            B.run_llm(["--llm", "--agent-cmd", "echo {prompt}", "--timeout", "0"])

    def test_T4_ai_answer_title_warning_enforced_live(self):
        # a teaching reply whose source block uses the ⚠️ AI-generated label but whose ⑤ title lacks the
        # full warning must FAIL live (ai_answer mode), same as --mock's ai variant.
        sc = _BY_NAME["teaching_template"]
        ai_good = _read(sc["mock_ai_answer"]) if sc.get("mock_ai_answer") else None
        if ai_good:
            self.assertTrue(B.live_reply_check("teaching_template", sc, ai_good, FIXTURE)[0],
                            "the AI-answer golden (⚠️ in both ⑤ title and source label) should pass")
        warn_missing = _read(sc["mock_negative_warn_title"]) if sc.get("mock_negative_warn_title") else None
        if warn_missing:
            self.assertFalse(B.live_reply_check("teaching_template", sc, warn_missing, FIXTURE)[0],
                             "an AI answer missing the ⚠️ title warning must fail live too")


class LiveRoundFourFixes(unittest.TestCase):
    def test_T2_live_prompt_includes_standard_answers(self):
        # answer-dependent scenarios must hand the agent the bank's standard answers (hidden context),
        # so it grades against the bank instead of prior knowledge (same as drift/run_live_smoke).
        prompt = B._live_prompt(FIXTURE, {"prompt": "出一题"})
        bank = json.loads(_read(os.path.join(os.path.relpath(FIXTURE, BS), "references", "quiz_bank.json")))
        keyed = [q for q in bank if isinstance(q, dict)
                 and (q.get("answer") not in (None, "", []) or q.get("answer_keywords") not in (None, "", []))]
        self.assertTrue(keyed, "fixture should have items with answers/keywords")
        self.assertIn("标准答案", prompt, "the hidden live prompt must expose the bank's standard answers")


if __name__ == "__main__":
    unittest.main()
