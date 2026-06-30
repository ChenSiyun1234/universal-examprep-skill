# -*- coding: utf-8 -*-
"""PR T2 — Tier 2 behavioral smoke (deterministic, stdlib-only, no network/LLM/API key).

These tests exercise the behavior_smoke harness + detectors against the self-authored mini-course
fixture and mock outputs. They prove the DEFAULT path is CI-safe; the real-LLM smoke is opt-in only.
"""
import io
import os
import sys
import json
import contextlib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BSDIR = os.path.join(ROOT, "benchmark", "behavior_smoke")
if BSDIR not in sys.path:
    sys.path.insert(0, BSDIR)
import run_behavior_smoke as H  # noqa: E402

SIX_TYPES = {"choice", "subjective", "diagram", "fill_blank", "true_false", "code"}


def _bs(rel):
    return os.path.join(BSDIR, rel)


def _read(rel):
    with open(_bs(rel), encoding="utf-8") as f:
        return f.read()


def _silent(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a, **k)


class BehaviorSmokeTest(unittest.TestCase):
    # 1
    def test_fixture_passes_validate_workspace(self):
        ok, errors, _, _ = H.validate_fixture_workspace(H.FIXTURE)
        self.assertTrue(ok, f"mini-course fixture 未通过校验: {[e['msg'] for e in errors]}")

    # 2
    def test_fixture_quiz_bank_covers_all_six_types(self):
        bank = json.loads(_read("fixtures/mini_course/references/quiz_bank.json"))
        types = {q["type"] for q in bank}
        self.assertEqual(types, SIX_TYPES, f"题库未覆盖全部 6 种题型，实际: {sorted(types)}")

    # 3
    def test_scenario_spec_valid_and_references_exist(self):
        spec = H.load_scenarios()
        self.assertIn("scenarios", spec)
        self.assertTrue(os.path.isdir(_bs(spec["fixture"])), "scenarios.json 的 fixture 路径不存在")
        file_keys = ("mock_output", "mock_negative", "progress_after", "transcript")
        for sc in spec["scenarios"]:
            for k in file_keys:
                if k in sc:
                    self.assertTrue(os.path.isfile(_bs(sc[k])), f"{sc['name']}.{k} 指向不存在的文件: {sc[k]}")
            if "fallback_workspace" in sc:
                self.assertTrue(os.path.isdir(_bs(sc["fallback_workspace"])), f"{sc['name']}.fallback_workspace 不存在")

    # 4
    def test_quiz_output_only_uses_bank_ids(self):
        bank_ids = H.load_quiz_bank_ids(H.FIXTURE)
        self.assertTrue(H.assert_quiz_ids_in_bank(_read("mock/sample_outputs/quiz_output_good.txt"), bank_ids))

    # 5
    def test_detector_fails_on_invented_id(self):
        bank_ids = H.load_quiz_bank_ids(H.FIXTURE)
        self.assertFalse(
            H.assert_quiz_ids_in_bank(_read("mock/sample_outputs/quiz_output_invented.txt"), bank_ids),
            "探测器未能识别题库中不存在的 AI 即兴题号",
        )

    # 6
    def test_provenance_detector_recognizes_all_canonical_labels(self):
        text = _read("mock/sample_outputs/provenance_answer.txt")
        self.assertTrue(H.has_canonical_provenance_labels(text))
        # must require ALL three: dropping any one canonical label makes it fail
        for lbl in H.CANON_LABELS:
            self.assertFalse(H.has_canonical_provenance_labels(text.replace(lbl, "")),
                             f"缺少标注「{lbl}」时仍判通过，说明未检查全部 canonical 标注")

    # 7
    def test_zero_basic_detector_recognizes_sections(self):
        self.assertTrue(H.has_zero_basic_sections(_read("mock/sample_outputs/zero_basic_explain.txt")))
        self.assertFalse(H.has_zero_basic_sections("## 考点拆解\n只有一个小节"), "缺少其余小节时不应判通过")

    # 8
    def test_hint_skip_detector_recognizes_recovery_offer(self):
        self.assertTrue(H.has_hint_skip_offer(_read("mock/sample_outputs/hint_skip_offer.txt")))
        self.assertFalse(H.has_hint_skip_offer("继续加油，你能答对的。"), "无逃生通道时不应判通过")

    # 9
    def test_mistake_archive_detector(self):
        self.assertTrue(H.progress_has_mistake_archive(_read("mock/sample_outputs/progress_after_mistake.md")))
        # base fixture progress has an empty 错题本 -> no archived row
        self.assertFalse(H.progress_has_mistake_archive(_read("fixtures/mini_course/study_progress.md")))

    # 10
    def test_confusion_tracker_detector(self):
        self.assertTrue(H.progress_has_confusion_row(_read("mock/sample_outputs/progress_after_confusion.md")))
        self.assertFalse(H.progress_has_confusion_row(_read("fixtures/mini_course/study_progress.md")))

    # 11
    def test_checkpoint_recovery_reads_current_phase(self):
        phase = H.progress_current_phase(_read("fixtures/mini_course/study_progress.md"))
        self.assertEqual(phase, 2, "断点恢复探测器未能从进度读到当前阶段 2")

    # 11b — resume must point at the current phase, not restart at phase 1 (direct +/- coverage)
    def test_checkpoint_resume_refers_to_current_phase(self):
        self.assertTrue(H.resume_refers_to_phase(_read("mock/sample_outputs/resume_message.txt"), 2))
        self.assertFalse(H.resume_refers_to_phase("从阶段 1 重新开始，欢迎新同学", 2),
                         "从阶段 1 重启的续跑文案不应被判为『指向当前阶段 2』")

    # 12
    def test_no_python_fallback_workspace_is_complete(self):
        # the mini-course is HAND-AUTHORED (not produced by ingest.py) — i.e. exactly the shape the
        # agent writes by hand when Python is unavailable; it must validate as a complete workspace.
        ok = H.validate_fixture_workspace(H.FIXTURE)[0]
        self.assertTrue(ok, "无 Python 手写产出的工作区未能校验为完整工作区")

    # 13
    def test_run_mock_exits_zero(self):
        self.assertEqual(_silent(H.main, ["--mock"]), 0)

    # 14
    def test_check_fixture_exits_zero(self):
        self.assertEqual(_silent(H.main, ["--check-fixture"]), 0)

    # 15
    def test_llm_is_refused_without_env_optin(self):
        saved = os.environ.pop("RUN_SKILL_BEHAVIOR_LLM", None)
        try:
            self.assertEqual(_silent(H.main, ["--llm"]), 2, "未设置 env 时 --llm 应被拒绝（返回 2）")
            os.environ["RUN_SKILL_BEHAVIOR_LLM"] = "1"
            self.assertEqual(_silent(H.main, ["--llm"]), 0, "设 env 后 --llm 应进入 skeleton（不调用模型，返回 0）")
        finally:
            os.environ.pop("RUN_SKILL_BEHAVIOR_LLM", None)
            if saved is not None:
                os.environ["RUN_SKILL_BEHAVIOR_LLM"] = saved

    # 16
    def test_no_api_keys_required_or_read(self):
        src = _read("run_behavior_smoke.py")
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "API_KEY"):
            self.assertNotIn(key, src, f"harness 不应引用 API key: {key}")
        # with every *_API_KEY removed from the env, the default path still works
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.endswith("API_KEY")}
        try:
            self.assertEqual(_silent(H.main, ["--mock"]), 0)
            self.assertEqual(_silent(H.main, ["--check-fixture"]), 0)
        finally:
            os.environ.update(saved)

    # 17
    def test_no_network_or_paid_benchmark_by_default(self):
        src = _read("run_behavior_smoke.py")
        for net in ("requests", "urllib", "http.client", "socket."):
            self.assertNotIn(net, src, f"默认路径不应引入网络库: {net}")
        # FUNCTIONAL + transitive guard: break subprocess AND sockets/urlopen, then prove the default
        # paths (which transitively import scripts/validate_workspace.py) still pass without any of them.
        import subprocess
        import socket
        import urllib.request
        def _boom(msg):
            def f(*a, **k):
                raise AssertionError(msg)
            return f
        saved = (subprocess.run, socket.socket, urllib.request.urlopen)
        subprocess.run = _boom("默认路径不应调用 subprocess（无 claude -p / 付费真跑）")
        socket.socket = _boom("默认路径不应建立 socket（无网络）")
        urllib.request.urlopen = _boom("默认路径不应发起 HTTP 请求（无网络）")
        try:
            self.assertEqual(_silent(H.main, ["--mock"]), 0)
            self.assertEqual(_silent(H.main, ["--check-fixture"]), 0)
        finally:
            subprocess.run, socket.socket, urllib.request.urlopen = saved


if __name__ == "__main__":
    unittest.main()
