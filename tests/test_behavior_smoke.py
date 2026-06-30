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
        ok, errors, warnings, _ = H.validate_fixture_workspace(H.FIXTURE)
        self.assertTrue(ok, f"mini-course fixture 未通过校验: {[e['msg'] for e in errors]}")
        # the documented fixture must be 0-error AND 0-warning (a warning = a lost recommended field)
        self.assertEqual(warnings, [], f"fixture 不应有告警（会削弱 6 题型 smoke）: {[w['msg'] for w in warnings]}")

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
        # an UNTAGGED invented question among tagged bank items must ALSO fail (no false confidence)
        self.assertFalse(
            H.assert_quiz_ids_in_bank("1. [#mc_q1] 合法题\n2. 这是没标号的 AI 编造题", bank_ids),
            "未标号的编造题应被判不合格（不能只看已标号的题）",
        )
        # a good output where EVERY numbered item is bank-tagged still passes
        self.assertTrue(H.assert_quiz_ids_in_bank("1. [#mc_q1] a\n2. [#mc_q2] b", bank_ids))
        # an invented tag on a NON-numbered (bullet) line must ALSO fail — scan all tags, any format
        self.assertFalse(H.assert_quiz_ids_in_bank("1. [#mc_q1] 合法\n- [#mc_q99] 项目符号编造", bank_ids),
                         "非编号行（项目符号）上的编造题号也应被抓")
        # an UNTAGGED bullet QUESTION (ends with ？) must fail...
        self.assertFalse(H.assert_quiz_ids_in_bank("1. [#mc_q1] 合法\n- 红黑树怎么删除？", bank_ids),
                         "未标号的项目符号问题（以？结尾）也应被抓")
        # ...but an instruction bullet (no ？) and option bullets (A./B.) must NOT be flagged as questions
        self.assertTrue(H.assert_quiz_ids_in_bank("1. [#mc_q1] 栈的顺序？\n- 请直接回复答案", bank_ids),
                        "非问题的指令项目符号不应被误判为未标号问题")
        self.assertTrue(H.assert_quiz_ids_in_bank("1. [#mc_q1] 栈的顺序？\n- A. LIFO\n- B. FIFO", bank_ids),
                        "选项行(A./B.)不应被误判为未标号问题")

    def test_quiz_detector_content_and_chapter_scope(self):
        qmap = H.load_quiz_bank_map(H.FIXTURE)
        ch1 = {i: v["question"] for i, v in qmap.items() if str(v["chapter"]) == "1"}
        # a valid tag slapped on INVENTED content must fail the content check
        self.assertFalse(H.assert_quiz_ids_in_bank("1. [#mc_q1] 请证明红黑树删除算法的复杂度", ch1),
                         "把合法题号贴到编造题面上应被内容校验抓住")
        # a chapter-2 id used in a chapter-1 quiz must fail the scope check
        self.assertFalse(H.assert_quiz_ids_in_bank("1. [#mc_q4] 二叉树最多多少节点？", ch1),
                         "第1章测验里抽到第2章题号应被章节范围抓住")
        # the matching bank content within scope passes
        self.assertTrue(H.assert_quiz_ids_in_bank("1. [#mc_q1] " + qmap["mc_q1"]["question"], ch1))
        # a TAGGED BULLET with invented content must be content-checked too (not skipped)
        self.assertFalse(H.assert_quiz_ids_in_bank("- [#mc_q1] 请证明红黑树删除算法", ch1),
                         "项目符号格式的『合法题号 + 编造题面』也应被内容校验抓住")
        # tag on its OWN line + invented content on the next line must fail (no vacuous empty-text match)
        self.assertFalse(H.assert_quiz_ids_in_bank("[#mc_q1]\n请证明红黑树删除算法的复杂度。", ch1),
                         "题号单独一行、下一行是编造题面，也应被内容校验抓住")

    # 6
    def test_provenance_detector_recognizes_all_canonical_labels(self):
        text = _read("mock/sample_outputs/provenance_answer.txt")
        self.assertTrue(H.has_canonical_provenance_labels(text))
        # must require ALL three: dropping any one canonical label makes it fail
        for lbl in H.CANON_LABELS:
            self.assertFalse(H.has_canonical_provenance_labels(text.replace(lbl, "")),
                             f"缺少标注「{lbl}」时仍判通过，说明未检查全部 canonical 标注")
        # a mere LEGEND listing the labels (no labelled answer content) must NOT pass
        legend = "可用标签：🟢 来自资料 / 🟡 AI补充，可能与你老师讲的不完全一致 / ⚠️ AI生成答案，非老师/教材提供\n答案是栈。"
        self.assertFalse(H.has_canonical_provenance_labels(legend),
                         "只罗列标签图例、答案却不带标注，不应判通过")
        # labels used AFTER content (skill style: 结论……（🟢 来自资料）) must pass
        suffix = ("栈是 LIFO（🟢 来自资料）。红黑树较复杂（🟡 AI补充，可能与你老师讲的不完全一致）。"
                  "以下为伪代码（⚠️ AI生成答案，非老师/教材提供）。")
        self.assertTrue(H.has_canonical_provenance_labels(suffix), "标签放在内容之后（括注）也应判通过")
        # a MULTI-LINE legend (labels each on their own line, answer unlabelled) must also fail
        ml_legend = ("标签说明：\n🟢 来自资料\n🟡 AI补充，可能与你老师讲的不完全一致\n"
                     "⚠️ AI生成答案，非老师/教材提供\n答案：栈是 LIFO。")
        self.assertFalse(H.has_canonical_provenance_labels(ml_legend),
                         "多行图例（标签各自成行、答案不带标注）也不应判通过")

    # 7
    def test_zero_basic_detector_recognizes_sections(self):
        self.assertTrue(H.has_zero_basic_sections(_read("mock/sample_outputs/zero_basic_explain.txt")))
        self.assertFalse(H.has_zero_basic_sections("## 考点拆解\n只有一个小节"), "缺少其余小节时不应判通过")
        # a one-line checklist that merely NAMES the sections (no real headings) must not pass
        self.assertFalse(H.has_zero_basic_sections("请包含：考点拆解、标准答题步骤、易错点、3分钟速记"),
                         "仅罗列小节名（无实际小节标题）不应判通过")
        # ordered-list headings (1. 考点拆解 / 2. 标准答题步骤 …) are valid section headings
        ordered = "1. 考点拆解\n讲解\n2. 标准答题步骤\n步骤\n3. 易错点\n注意\n4. 3分钟速记\n口诀"
        self.assertTrue(H.has_zero_basic_sections(ordered), "有序列表小节标题(1. 考点拆解)也应判通过")

    # 8
    def test_hint_skip_detector_recognizes_recovery_offer(self):
        self.assertTrue(H.has_hint_skip_offer(_read("mock/sample_outputs/hint_skip_offer.txt")))
        self.assertFalse(H.has_hint_skip_offer("继续加油，你能答对的。"), "无逃生通道时不应判通过")
        # an output that explicitly DENIES the escape hatch must not pass on keyword presence alone
        self.assertFalse(H.has_hint_skip_offer("没有提示，不能跳过，也不会归档到错题本"),
                         "明确否定『提示/跳过/归档』的文案应判不合格")
        # negation with intervening words must also be caught
        self.assertFalse(H.has_hint_skip_offer("可以提示、可以跳过，但不会把它归档到错题本"),
                         "中间夹词的否定（『不会把它归档』）也应判不合格")
        self.assertFalse(H.has_hint_skip_offer("可以给提示，也可以跳过，但不会写入错题本"),
                         "『不会写入错题本』的归档否定也应判不合格")
        self.assertFalse(H.has_hint_skip_offer("可以提示、跳过，但不会把这道题自动记录进错题档案"),
                         "夹词较长的归档否定（…记录进错题档案）也应判不合格")

    # 9
    def test_mistake_archive_detector(self):
        self.assertTrue(H.progress_has_mistake_archive(_read("mock/sample_outputs/progress_after_mistake.md")))
        # base fixture progress has an empty 错题档案 -> no archived row
        self.assertFalse(H.progress_has_mistake_archive(_read("fixtures/mini_course/study_progress.md")))
        # accept BOTH the standard template header (错题档案) and legacy mini wording (错题本)
        std = "## ❌ 错题档案记录\n| ID | 章节 | 状态 |\n| --- | --- | --- |\n| mc_q1 | 1 | 已归档 |"
        legacy = "## 错题本\n| 题号 | 状态 |\n| --- | --- |\n| mc_q2 | 已归档 |"
        self.assertTrue(H.progress_has_mistake_archive(std), "应识别标准模板表头『错题档案记录』")
        self.assertTrue(H.progress_has_mistake_archive(legacy), "应兼容旧表头『错题本』")
        # an empty-state placeholder rendered AS a table row must NOT count as an archived mistake
        empty = "## ❌ 错题档案记录\n| 错题ID | 章节 | 状态 |\n| --- | --- | --- |\n| 暂无错题 | - | - |"
        self.assertFalse(H.progress_has_mistake_archive(empty), "空状态占位行不应被当成已归档错题")
        # scenario-specific: the archived row must mention the SIMULATED wrong item, not just any row
        m = _read("mock/sample_outputs/progress_after_mistake.md")
        self.assertTrue(H.progress_has_mistake_archive(m, expect="mc_q2"))
        self.assertFalse(H.progress_has_mistake_archive(m, expect="mc_q1"),
                         "归档了错误的题（非本场景模拟的 mc_q2）不应判通过")
        # exact ID match: a row about mc_q20 must NOT satisfy expect=mc_q2 (prefix collision)
        m20 = "## ❌ 错题档案记录\n| 错题ID | 章节 | 状态 |\n| --- | --- | --- |\n| mc_q20 | 2 | 已归档 |"
        self.assertFalse(H.progress_has_mistake_archive(m20, expect="mc_q2"),
                         "mc_q20 的行不应满足 expect=mc_q2（前缀相同不算命中）")

    # 10
    def test_confusion_tracker_detector(self):
        self.assertTrue(H.progress_has_confusion_row(_read("mock/sample_outputs/progress_after_confusion.md")))
        self.assertFalse(H.progress_has_confusion_row(_read("fixtures/mini_course/study_progress.md")))

    # 11
    def test_checkpoint_recovery_reads_current_phase(self):
        phase = H.progress_current_phase(_read("fixtures/mini_course/study_progress.md"))
        self.assertEqual(phase, 2, "断点恢复探测器未能从进度读到当前阶段 2")
        # completed phases listed BEFORE the current marker must not be misread as the current phase
        reordered = "## 当前复习断点\n- 已完成：阶段 1\n- 当前进行阶段：阶段 2"
        self.assertEqual(H.progress_current_phase(reordered), 2,
                         "已完成阶段排在当前标记之前时，仍应读出当前阶段 2（而非 1）")

    # 11b — resume must point at the current phase, not restart at phase 1 (direct +/- coverage)
    def test_checkpoint_resume_refers_to_current_phase(self):
        self.assertTrue(H.resume_refers_to_phase(_read("mock/sample_outputs/resume_message.txt"), 2))
        # mentions 阶段 2 but STILL restarts at 阶段 1 → must be rejected (the exact gap Codex flagged)
        self.assertFalse(H.resume_refers_to_phase("当前在阶段 2，但先从阶段 1 重新开始", 2),
                         "虽提到阶段 2 但仍从阶段 1 重启，应判不合格")
        self.assertFalse(H.resume_refers_to_phase("从头开始复习，先看阶段 2 的目录", 2),
                         "『从头开始』的续跑文案应判不合格")
        self.assertFalse(H.resume_refers_to_phase("当前在阶段 2，但先从阶段1开始", 2),
                         "紧凑写法『从阶段1开始』（无空格）也应判重启不合格")
        # spacing / word-order variants of the CURRENT phase still count as a correct resume
        self.assertTrue(H.resume_refers_to_phase("当前在阶段2：二叉树，我们继续", 2),
                        "紧凑『阶段2』（无空格）应判为指向当前阶段")
        self.assertTrue(H.resume_refers_to_phase("从第2阶段接着复习", 2),
                        "『第2阶段』写法应判为指向当前阶段")
        # negating the current phase must be rejected even though 阶段2 is mentioned
        self.assertFalse(H.resume_refers_to_phase("你现在不是阶段2，而是阶段1。", 2),
                         "否定当前阶段（『不是阶段2』）应判不合格")
        self.assertFalse(H.resume_refers_to_phase("你现在不是第2阶段，而是第1阶段。", 2),
                         "否定『第2阶段』形式也应判不合格")

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
