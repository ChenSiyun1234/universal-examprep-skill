# -*- coding: utf-8 -*-
"""A3 tests — homework/solution ingest: file classification, Q/A pairing across separate PDFs,
inline solutions, provenance, source_type tagging, visual dependence, fail-loud orphans."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_raw_input_from_workspace as B   # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nfakepng"


class FakeBackend(object):
    name = "fake"

    def __init__(self, texts_by_name):
        self.texts = texts_by_name

    def can_text(self):
        return True

    def can_render(self):
        return True

    def page_texts(self, pdf_path):
        return self.texts[os.path.basename(pdf_path)]

    def render_page_png(self, pdf_path, page_index):
        return PNG


HW1 = ["Problem 1\n求栈的出栈顺序。\n\nProblem 2\n给出队列复杂度并证明。",
       "Problem 3\nShade the region shown at right in the Venn diagram."]
HW1_SOL = ["Problem 1\n答案：LIFO 顺序。\n\nProblem 2\n答案：O(1)，证明略。"]
HW2_INLINE = ["第1题\n解释二叉搜索树。\nSolution\n中序遍历有序。\n\n第2题\n无答案的题。"]
ORPHAN_SOL = ["Problem 1\n这是找不到题面的答案。"]


def _mk(tmp, names_texts):
    mat = os.path.join(tmp, "mat")
    os.makedirs(os.path.join(mat, "homework"), exist_ok=True)
    fake = {}
    for name, pages in names_texts.items():
        path = os.path.join(mat, "homework", name)
        with open(path, "wb") as f:
            f.write(b"%PDF-fake")
        fake[name] = pages
    return mat, FakeBackend(fake)


def _run(mat, backend, extra=None):
    argv = ["--materials", mat, "--out", os.path.join(mat, "..", "raw.json"),
            "--report", os.path.join(mat, "..", "rep.json")] + (extra or [])
    args = B.build_arg_parser().parse_args(argv)
    code, payload, report = B.run(args, backend=backend)
    return code, payload, report


class HomeworkIngest(unittest.TestCase):
    def test_separate_solution_pdf_paired(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": HW1, "hw1_sol.pdf": HW1_SOL})
        code, payload, report = _run(mat, be)
        self.assertEqual(code, 0, report)
        bank = {q["id"]: q for q in payload["quiz_bank"]}
        q1 = bank["hw_homework_hw1_1"]
        self.assertEqual(q1["source_type"], "homework")
        self.assertIn("出栈顺序", q1["question"])
        self.assertIn("LIFO", q1["answer"])                       # 题答分离 PDF 自动配对
        self.assertEqual(q1["answer_source_file"], "homework/hw1_sol.pdf")
        self.assertEqual(q1["source_file"], "homework/hw1.pdf")
        self.assertEqual(q1["source_pages"], [1])
        self.assertEqual(report["homework_pairs"], [["homework/hw1_sol.pdf", "homework/hw1.pdf"]])
        self.assertEqual(report["homework_problems"], 3)
        self.assertEqual(report["homework_answered"], 2)

    def test_unanswered_problem_fail_loud(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": HW1, "hw1_sol.pdf": HW1_SOL})
        code, payload, report = _run(mat, be)
        q3 = next(q for q in payload["quiz_bank"] if q["id"] == "hw_homework_hw1_3")
        self.assertNotIn("answer", q3)
        self.assertEqual(q3["answer_status"], "unknown")
        self.assertTrue(any(w.startswith("hw_unanswered: hw_homework_hw1_3") for w in report["warnings"]))

    def test_inline_solution_and_cn_markers(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"作业2.pdf": HW2_INLINE})
        code, payload, report = _run(mat, be)
        self.assertEqual(code, 0, report)
        bank = {q["id"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        q1 = next(q for q in bank.values() if q["id"].endswith("_1"))
        self.assertIn("二叉搜索树", q1["question"])
        self.assertIn("中序遍历有序", q1["answer"])                # inline Solution 归属前一题
        self.assertNotIn("Solution", q1["question"].split("Solution")[0] + "")  # 题面在 Solution 前截断
        q2 = next(q for q in bank.values() if q["id"].endswith("_2"))
        self.assertEqual(q2["answer_status"], "unknown")

    def test_unpaired_solution_file_warns_and_skips(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw9_solutions.pdf": ORPHAN_SOL})
        code, payload, report = _run(mat, be)
        self.assertTrue(any(w.startswith("hw_unpaired_solution_file") for w in report["warnings"]))
        self.assertFalse([q for q in payload["quiz_bank"] if q.get("source_type") == "homework"])

    def test_visual_dependent_homework_renders_assets(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": HW1, "hw1_sol.pdf": HW1_SOL})
        asset_root = os.path.join(tmp, "ws", "references", "assets")
        code, payload, report = _run(mat, be, ["--asset-root", asset_root])
        q3 = next(q for q in payload["quiz_bank"] if q["id"] == "hw_homework_hw1_3")
        self.assertIs(q3["requires_assets"], True)                # Venn/shown at right → 图依赖
        self.assertTrue(q3["assets"])
        self.assertEqual(q3["assets"][0]["role"], "question_context")
        self.assertTrue(os.path.isfile(os.path.join(asset_root, os.path.basename(q3["assets"][0]["path"]))))

    def test_extract_homework_never_disables(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": HW1, "hw1_sol.pdf": HW1_SOL})
        code, payload, report = _run(mat, be, ["--extract-homework", "never"])
        self.assertFalse([q for q in payload["quiz_bank"] if q.get("source_type") == "homework"])

    def test_lecture_extraction_unaffected(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": HW1,
                            "lec_ch01.pdf": ["Example 1.1 Problem\n求和。\nExample 1.1 Solution\n答案 3。"]})
        code, payload, report = _run(mat, be)
        ids = [q["id"] for q in payload["quiz_bank"]]
        self.assertTrue(any(i.startswith("lecture_example_1_1") for i in ids))   # lecture 管线原样
        self.assertIn("hw_homework_hw1_1", ids)

    def test_duplicate_problem_number_kept_first(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw3.pdf": ["Problem 1\n第一处。\n\nProblem 1\n重复标记。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 1)
        self.assertIn("第一处", hw[0]["question"])
        self.assertTrue(any(w.startswith("hw_duplicate_problem") for w in report["warnings"]))

    def test_output_passes_ingest_and_validator(self):
        # e2e: builder → ingest.py → validate_workspace.py（真 CLI），homework 项带标签通过校验
        import subprocess
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": HW1, "hw1_sol.pdf": HW1_SOL})
        raw = os.path.join(tmp, "raw.json")
        ws = os.path.join(tmp, "ws")
        args = B.build_arg_parser().parse_args(["--materials", mat, "--out", raw,
                                                "--report", os.path.join(tmp, "rep.json"),
                                                "--asset-root", os.path.join(ws, "references", "assets")])
        code, payload, report = B.run(args, backend=be)
        json.dump(payload, open(raw, "w", encoding="utf-8"), ensure_ascii=False)
        r1 = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "ingest.py"),
                             "-i", raw, "-o", ws], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        bank = json.load(open(os.path.join(ws, "references", "quiz_bank.json"), encoding="utf-8"))
        hw = [q for q in bank if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 3)                              # source_type 穿 ingest 存活
        r2 = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "validate_workspace.py"), ws],
                            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_classifier_pairs_variants(self):
        hw, pairing = B.classify_homework_files(
            ["homework/hw1.pdf", "homework/hw1_sol.pdf", "homework/HW2.pdf",
             "homework/HW2_Answers.pdf", "homework/作业3.pdf", "homework/作业3答案.pdf",
             "lectures/ch01.pdf"])
        self.assertEqual(sorted(hw), ["homework/HW2.pdf", "homework/hw1.pdf", "homework/作业3.pdf"])
        self.assertEqual(pairing["homework/hw1_sol.pdf"], "homework/hw1.pdf")
        self.assertEqual(pairing["homework/HW2_Answers.pdf"], "homework/HW2.pdf")
        self.assertEqual(pairing["homework/作业3答案.pdf"], "homework/作业3.pdf")

    # ---- regression guards for Codex round-1 (7 findings) ----

    def test_bare_answer_word_not_a_marker(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw4.pdf": ["Problem 1\nAnswer the following questions about stacks.\n更多题面内容在此。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("Answer the following", q["question"])      # 没被裁成 inline 答案
        self.assertEqual(q["answer_status"], "unknown")

    def test_subdir_files_get_distinct_ids(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        for sub in ("week1", "week2"):
            os.makedirs(os.path.join(mat, sub), exist_ok=True)
            with open(os.path.join(mat, sub, "hw1.pdf"), "wb") as f:
                f.write(b"%PDF-fake")
        be = FakeBackend({"hw1.pdf": ["Problem 1\n本周题面内容足够长了吧。"]})
        code, payload, report = _run(mat, be)
        ids = sorted(q["id"] for q in payload["quiz_bank"] if q.get("source_type") == "homework")
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1])                       # week1/week2 不同 id

    def test_chapter_only_when_stated(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw5.pdf": ["Problem 1\n本题考察第 3 章 的内容，请作答完整过程。",
                                        "Problem 2\n没有章节线索的题面文字内容。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(hw[1]["chapter"], 3)                     # 题文明说 → 标 chapter
        self.assertNotIn("chapter", hw[2])                        # 不硬编（作业号 ≠ 章节号）

    def test_hw1_solution_never_pairs_hw10(self):
        hw, pairing = B.classify_homework_files(["homework/hw10.pdf", "homework/hw1_sol.pdf"])
        self.assertIsNone(pairing["homework/hw1_sol.pdf"])        # 数字边界：hw1 ≠ hw10

    def test_solution_file_prefers_answer_slice(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw6.pdf": ["Problem 1\n题面：求栈顺序的完整过程。"],
                            "hw6_sol.pdf": ["Problem 1\n题面复述而已。\nAnswer 1: 真正的答案是 LIFO。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("LIFO", q["answer"])                        # 答案段优先于题面复述
        self.assertFalse(q["answer"].startswith("Problem 1"))

    def test_marker_only_prompt_becomes_page_reference(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw7.pdf": ["Problem 1\n"]})          # 只有标题，真题面是页上的图
        asset_root = os.path.join(tmp, "ws", "references", "assets")
        code, payload, report = _run(mat, be, ["--asset-root", asset_root])
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertEqual(q["question_text_status"], "page_reference")
        self.assertIs(q["requires_assets"], True)
        self.assertTrue(q["assets"])                              # 原页已渲染挂上

    def test_solutions_directory_companion(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        os.makedirs(os.path.join(mat, "homework"), exist_ok=True)
        os.makedirs(os.path.join(mat, "solutions"), exist_ok=True)
        with open(os.path.join(mat, "homework", "hw1.pdf"), "wb") as f:
            f.write(b"%PDF-fake")
        with open(os.path.join(mat, "solutions", "hw1.pdf"), "wb") as f:
            f.write(b"%PDF-fake")

        class DirBackend(FakeBackend):
            def page_texts(self, pdf_path):
                if "solutions" in pdf_path.replace("\\", "/"):
                    return ["Problem 1\nAnswer 1: 目录版答案在此。"]
                return ["Problem 1\n目录版题面内容足够长。"]
        be = DirBackend({})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("目录版答案", q["answer"])                   # solutions/ 目录伴随被识别配对

    # ---- regression guards for Codex round-2 (6 findings) ----

    def test_same_basename_pairs_within_directory(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        for sub in ("week1", "week2"):
            os.makedirs(os.path.join(mat, sub), exist_ok=True)
            with open(os.path.join(mat, sub, "hw1.pdf"), "wb") as f:
                f.write(b"%PDF-fake")
            with open(os.path.join(mat, sub, "hw1_sol.pdf"), "wb") as f:
                f.write(b"%PDF-fake")

        class WeekBackend(FakeBackend):
            def page_texts(self, pdf_path):
                p = pdf_path.replace("\\", "/")
                week = "week1" if "week1" in p else "week2"
                if "sol" in p:
                    return ["Problem 1\nAnswer 1: %s 的答案。" % week]
                return ["Problem 1\n%s 的题面内容足够长。" % week]
        code, payload, report = _run(mat, WeekBackend({}))
        hw = {q["source_file"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("week1 的答案", hw["week1/hw1.pdf"]["answer"])   # 同目录配对，不跨目录串
        self.assertIn("week2 的答案", hw["week2/hw1.pdf"]["answer"])

    def test_long_stem_ids_stay_unique(self):
        base = "very_long_lms_export_name_" + "x" * 50
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        os.makedirs(os.path.join(mat, "hw"), exist_ok=True)
        names = [base + "_alpha.pdf", base + "_beta.pdf"]
        for n in names:
            with open(os.path.join(mat, "hw", n), "wb") as f:
                f.write(b"%PDF-fake")

        class LongBackend(FakeBackend):
            def page_texts(self, pdf_path):
                return ["Problem 1\n长文件名题面内容足够长。"]
        code, payload, report = _run(mat, LongBackend({}))
        ids = [q["id"] for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)                        # 截断后哈希后缀保唯一

    def test_short_but_complete_prompt_stays_full(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw8.pdf": ["Problem 1\n2+2=?\n\nProblem 2\n求导 x^2。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(hw[1]["question_text_status"], "full")   # 短而完整 ≠ 图片题
        self.assertNotIn("requires_assets", hw[1])
        self.assertEqual(hw[2]["question_text_status"], "full")

    def test_long_question_not_silently_truncated(self):
        long_q = "Problem 1\n" + "很长的编程大作业题面。" * 300
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw9.pdf": [long_q]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertGreater(len(q["question"]), 2000)              # 保留全文，不静默截断

    def test_separated_ps_number_classified(self):
        hw, pairing = B.classify_homework_files(["exports/ps 1.pdf", "exports/PS-2.pdf", "exports/ps_3.pdf"])
        self.assertEqual(len(hw), 3)                              # ps 1 / PS-2 / ps_3 都识别为作业

    def test_answer_blank_line_not_official_answer(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw10a.pdf": ["Problem 1\n计算 2+2。\nAnswer: ________\n\nProblem 2\n下一题题面。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertNotIn("answer", hw[1])                         # 填空线不是官方答案
        self.assertEqual(hw[1]["answer_status"], "unknown")

    # ---- regression guards for Codex round-3 (4 findings) ----

    def test_numbered_answer_key_headings_pair(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw11.pdf": ["Problem 1\n第一题题面内容。\n\nProblem 2\n第二题题面内容。"],
                            "hw11_sol.pdf": ["1. Answer: 第一题的官方答案。\n\n2) Solution: 第二题的官方答案。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("第一题的官方答案", hw[1]["answer"])          # 「1. Answer:」编号在标记前也能配上
        self.assertIn("第二题的官方答案", hw[2]["answer"])          # 「2) Solution:」同理

    def test_zero_padded_stem_pairs(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"HW01.pdf": ["Problem 1\n零填充作业的题面内容。"],
                            "HW1_sol.pdf": ["Problem 1\nAnswer 1: 零填充也要配上的答案。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("零填充也要配上", q["answer"])                # HW01 ↔ HW1_sol
        hw, pairing = B.classify_homework_files(["homework/hw1.pdf", "homework/hw10.pdf",
                                                 "homework/hw1_sol.pdf"])
        self.assertTrue(pairing["homework/hw1_sol.pdf"].endswith("hw1.pdf"))   # hw1/hw10 边界不受影响

    def test_same_line_prompt_stays_full(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw12.pdf": ["Problem 1 Compute 2+2.\n\nProblem 2: 求 x^2 的导数。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(hw[1]["question_text_status"], "full")   # 标题同行的完整题面 ≠ 图片题
        self.assertNotIn("requires_assets", hw[1])
        self.assertEqual(hw[2]["question_text_status"], "full")

    def test_decimal_problem_numbers_kept_distinct(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw13.pdf": ["Problem 1.1\n第一小题题面内容。\nAnswer 1.1: 第一小题答案。\n\n"
                                         "Problem 1.2\n第二小题题面内容。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        nums = sorted(str(q["homework_number"]) for q in hw)
        self.assertEqual(nums, ["1.1", "1.2"])                    # 小数题号不再折叠成同一个 1
        self.assertEqual(len({q["id"] for q in hw}), 2)
        by_num = {str(q["homework_number"]): q for q in hw}
        self.assertIn("第一小题答案", by_num["1.1"]["answer"])     # 小数号 inline 答案配对
        self.assertEqual(by_num["1.2"]["answer_status"], "unknown")

    def test_download_copy_suffix_and_synonym_pair(self):
        hw, pairing = B.classify_homework_files(["hw2 (4)(1).pdf", "homework2solutions.pdf"])
        self.assertEqual(pairing["homework2solutions.pdf"], "hw2 (4)(1).pdf")   # 下载副本后缀 + homework≡hw

    def test_true_duplicate_copies_stay_failloud(self):
        hw, pairing = B.classify_homework_files(["hw2 (1).pdf", "hw2 (2).pdf", "hw2solutions.pdf"])
        self.assertIsNone(pairing["hw2solutions.pdf"])            # 真重名副本歧义时拒绝配对，不串答案

    # ---- regression guards for Codex round-4 (5 findings) ----

    def test_sibling_week_directories_pair(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        for wk in ("week1", "week2"):
            os.makedirs(os.path.join(mat, wk, "homework"), exist_ok=True)
            os.makedirs(os.path.join(mat, wk, "solutions"), exist_ok=True)
            for sub in ("homework", "solutions"):
                with open(os.path.join(mat, wk, sub, "hw1.pdf"), "wb") as f:
                    f.write(b"%PDF-fake")

        class WkBackend(FakeBackend):
            def page_texts(self, pdf_path):
                p = pdf_path.replace("\\", "/")
                wk = "week1" if "week1" in p else "week2"
                if "solutions" in p:
                    return ["Problem 1\nAnswer 1: %s 的官方答案。" % wk]
                return ["Problem 1\n%s 的题面内容。" % wk]
        code, payload, report = _run(mat, WkBackend({}))
        hw = {q["source_file"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("week1 的官方答案", hw["week1/homework/hw1.pdf"]["answer"])   # 同父家族层各配各的
        self.assertIn("week2 的官方答案", hw["week2/homework/hw1.pdf"]["answer"])

    def test_toc_line_not_recorded_as_answer(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw14.pdf": ["Problem 1\n题面内容在此。"],
                            "hw14_sol.pdf": ["目录\n1. Answer ........ 5", "Problem 1\n真答案内容。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("真答案内容", q["answer"])                   # 目录行被过滤，答案取真实解答页
        self.assertNotIn("........", q["answer"])

    def test_problem_n_solution_heading_is_inline_answer(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw15.pdf": ["Problem 1\n题面文字内容。\n\nProblem 1 Solution\n官方解答内容。\n\n"
                                         "Problem 2\n下一题题面。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(len(hw), 2)                              # 解答段标题不是新题也不是重复
        self.assertIn("官方解答内容", hw[1]["answer"])
        self.assertEqual(hw[2]["answer_status"], "unknown")
        self.assertFalse([w for w in report["warnings"] if "hw_duplicate_problem" in w])

    def test_answer_key_after_all_problems_pairs(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw16.pdf": ["Problem 1\n题面一内容。\n\nProblem 2\n题面二内容。\n\n"
                                         "Answer 1: 答案一内容。\nAnswer 2: 答案二内容。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("答案一内容", hw[1]["answer"])                # 题目区与答案区分离也能按号配
        self.assertIn("答案二内容", hw[2]["answer"])
        self.assertNotIn("答案二内容", hw[1]["answer"])            # 各答案切片互不越界

    def test_continued_problem_keeps_all_pages(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw17.pdf": ["Problem 1\n第一页题面内容。",
                                         "Problem 1 (Continued)\n第二页续文内容。\n\nProblem 2\n下一题题面。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(len(hw), 2)                              # 续页标题不产生新题
        self.assertIn("第二页续文内容", hw[1]["question"])          # 续页文字并入本题
        self.assertEqual(hw[1]["source_pages"], [1, 2])            # 页码覆盖续页
        self.assertFalse([w for w in report["warnings"] if "hw_duplicate_problem" in w])

    # ---- regression guards for Codex round-5 (5 findings) ----

    def test_same_line_answer_verb_stays_problem(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw18.pdf": ["Problem 1: Answer the following questions about stacks.\n"
                                         "更多题面内容在此。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 1)                              # 题面动词 Answer 不翻成解答段
        self.assertIn("Answer the following", hw[0]["question"])
        self.assertEqual(hw[0]["answer_status"], "unknown")
        self.assertFalse([w for w in report["warnings"] if "hw_no_markers" in w])

    def test_verb_answer_filenames_are_homework(self):
        hw, pairing = B.classify_homework_files(["unanswered_hw1.pdf", "answer_questions_hw2.pdf"])
        self.assertEqual(len(hw), 2)                              # 都是作业文件，不是解答
        self.assertEqual(pairing, {})
        hw2, pairing2 = B.classify_homework_files(["hw1.pdf", "hw1_answers.pdf"])
        self.assertEqual(pairing2["hw1_answers.pdf"], "hw1.pdf")  # 真解答记号（hw 之后）照常配

    def test_lettered_subparts_kept_distinct(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw19.pdf": ["Problem 1(a)\n第一小问题面。\nAnswer 1(a): 第一小问答案。\n\n"
                                         "Problem 1(b)\n第二小问题面。"]})
        code, payload, report = _run(mat, be)
        hw = {str(q["homework_number"]): q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(sorted(hw), ["1a", "1b"])                # 字母小问不折叠成同一个 1
        self.assertIn("第一小问答案", hw["1a"]["answer"])
        self.assertEqual(hw["1b"]["answer_status"], "unknown")
        self.assertEqual(len({q["id"] for q in hw.values()}), 2)

    def test_sanitize_collision_ids_stay_unique(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        os.makedirs(os.path.join(mat, "a", "b"), exist_ok=True)
        os.makedirs(os.path.join(mat, "a_b"), exist_ok=True)
        for sub in (("a", "b"), ("a_b",)):
            with open(os.path.join(mat, *sub, "hw1.pdf"), "wb") as f:
                f.write(b"%PDF-fake")
        be = FakeBackend({"hw1.pdf": ["Problem 1\n消毒撞名的题面内容。"]})
        code, payload, report = _run(mat, be)
        ids = [q["id"] for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)                        # a/b 与 a_b 消毒同串也不撞 id

    def test_mirrored_subtrees_pair(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        for wk in ("week1", "week2"):
            os.makedirs(os.path.join(mat, "homework", wk), exist_ok=True)
            os.makedirs(os.path.join(mat, "solutions", wk), exist_ok=True)
            for top in ("homework", "solutions"):
                with open(os.path.join(mat, top, wk, "hw1.pdf"), "wb") as f:
                    f.write(b"%PDF-fake")

        class MirBackend(FakeBackend):
            def page_texts(self, pdf_path):
                p = pdf_path.replace("\\", "/")
                wk = "week1" if "week1" in p else "week2"
                if "solutions" in p:
                    return ["Problem 1\nAnswer 1: %s 的镜像答案。" % wk]
                return ["Problem 1\n%s 的镜像题面。" % wk]
        code, payload, report = _run(mat, MirBackend({}))
        hw = {q["source_file"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("week1 的镜像答案", hw["homework/week1/hw1.pdf"]["answer"])   # 镜像子树各配各的
        self.assertIn("week2 的镜像答案", hw["homework/week2/hw1.pdf"]["answer"])

    # ---- regression guards for Codex round-6 (4 findings) ----

    def test_blank_plus_instructions_not_an_answer(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw20.pdf": ["Problem 1\n计算 2+2。\nAnswer: ________\nShow your work carefully.\n\n"
                                         "Problem 2\n下一题题面。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertNotIn("answer", hw[1])                         # 填空线+指示语不是官方答案
        self.assertEqual(hw[1]["answer_status"], "unknown")

    def test_lettered_prefix_answer_keys_pair(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw21.pdf": ["Problem 1(a)\n第一小问题面。\n\nProblem 1(b)\n第二小问题面。\n\n"
                                         "1(a). Answer: 甲小问答案。\n1b. Answer: 乙小问答案。"]})
        code, payload, report = _run(mat, be)
        hw = {str(q["homework_number"]): q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("甲小问答案", hw["1a"]["answer"])            # 1(a). Answer: 形式配上
        self.assertIn("乙小问答案", hw["1b"]["answer"])            # 1b. Answer: 形式配上

    def test_compact_sol_suffix_classified(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": ["Problem 1\n紧凑后缀的题面内容。"],
                            "hw1sol.pdf": ["Problem 1\nAnswer 1: 紧凑后缀的官方答案。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 1)                              # hw1sol 是解答文件，不是第二份作业
        self.assertIn("紧凑后缀的官方答案", hw[0]["answer"])
        hw2, pairing2 = B.classify_homework_files(["hw2.pdf", "hw2ans.pdf"])
        self.assertEqual(pairing2["hw2ans.pdf"], "hw2.pdf")

    def test_ambiguous_local_match_is_terminal(self):
        hw, pairing = B.classify_homework_files(["week1/hw1a.pdf", "week1/hw1b.pdf",
                                                 "week1/hw1_sol.pdf", "week2/hw1.pdf"])
        self.assertIsNone(pairing["week1/hw1_sol.pdf"])           # 本层歧义就地放弃，绝不配到 week2

    # ---- regression guards for Codex round-7 (4 findings) ----

    def test_prefixed_blank_answer_key_stays_unknown(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw22.pdf": ["Problem 1(a)\n第一小问题面。\n\nProblem 1(b)\n第二小问题面。\n\n"
                                         "1(a). Answer: ________\n1(b). Answer: 真实答案内容。"]})
        code, payload, report = _run(mat, be)
        hw = {str(q["homework_number"]): q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertNotIn("answer", hw["1a"])                      # 带号前缀的填空线不是官方答案
        self.assertEqual(hw["1a"]["answer_status"], "unknown")
        self.assertIn("真实答案内容", hw["1b"]["answer"])

    def test_solution_prefix_filenames_are_companions(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": ["Problem 1\n前缀式解答的题面。"],
                            "solutions_hw1.pdf": ["Problem 1\nAnswer 1: 前缀式解答的答案。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 1)                              # solutions_hw1 是伴随解答不是第二份作业
        self.assertIn("前缀式解答的答案", hw[0]["answer"])
        hw2, pairing2 = B.classify_homework_files(["作业3.pdf", "答案_作业3.pdf"])
        self.assertEqual(pairing2["答案_作业3.pdf"], "作业3.pdf")   # 中文前缀同理
        hw3, pairing3 = B.classify_homework_files(["answer_questions_hw2.pdf"])
        self.assertEqual((len(hw3), pairing3), (1, {}))            # 动词短语仍归作业（中间夹词）

    def test_repeated_headings_solutions_section_pairs(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw23.pdf": ["Problem 1\n题面一内容。\n\nProblem 2\n题面二内容。",
                                         "Solutions\nProblem 1\n解答一正文。\n\nProblem 2\n解答二正文。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(len(hw), 2)                              # 解答区重复标题不是新题也不是垃圾重复
        self.assertIn("解答一正文", hw[1]["answer"])
        self.assertIn("解答二正文", hw[2]["answer"])
        self.assertFalse([w for w in report["warnings"] if "hw_duplicate_problem" in w])

    def test_page_header_repeat_still_deduped(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw24.pdf": ["Problem 1\n题面一。\n\nProblem 2\n题面二第一页。",
                                         "Problem 2\n题面二第二页重复页眉后的正文。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(len(hw), 2)                              # 单号页眉重现仍按重复去重
        self.assertEqual(hw[2]["answer_status"], "unknown")       # 不会被当成解答区
        self.assertTrue([w for w in report["warnings"] if "hw_duplicate_problem" in w])

    def test_alpha_suffix_solution_not_paired_to_base(self):
        hw, pairing = B.classify_homework_files(["hw1.pdf", "hw1a_sol.pdf", "hw1_extra_sol.pdf"])
        self.assertIsNone(pairing["hw1a_sol.pdf"])                # hw1a 的答案不能安到 hw1 头上
        self.assertIsNone(pairing["hw1_extra_sol.pdf"])
        hw2, pairing2 = B.classify_homework_files(["hw1_probability_worksheet.pdf", "hw1_sol.pdf"])
        self.assertEqual(pairing2["hw1_sol.pdf"], "hw1_probability_worksheet.pdf")   # 作业名延长方向仍配

    # ---- regression guards for Codex round-8 (4 findings) ----

    def test_unnumbered_solution_block_in_paired_file(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw25.pdf": ["Problem 1\n真正的题面内容。"],
                            "hw25_sol.pdf": ["Problem 1\n题面复述而已。\nSolution\n无号真解答内容在此。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("无号真解答内容", q["answer"])                # 无号 Solution 继承前题号，解答段获胜
        self.assertNotIn("题面复述", q["answer"])                  # 不再把复述切片当官方答案

    def test_letter_variant_assignment_not_paired_to_base_sol(self):
        hw, pairing = B.classify_homework_files(["hw1a.pdf", "hw1_sol.pdf"])
        self.assertIsNone(pairing["hw1_sol.pdf"])                 # hw1 的答案不能安到 hw1a 头上

    def test_selfcontained_solutions_pdf_extracted(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1_solutions.pdf": ["Problem 1\n自含册的题面。\nSolution\n自含册的解答。\n\n"
                                                  "Problem 2\n第二题题面。\nSolution\n第二题解答。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(len(hw), 2)                              # 自含题+解答的孤儿册按作业解析
        self.assertIn("自含册的解答", hw[1]["answer"])
        self.assertIn("第二题解答", hw[2]["answer"])
        self.assertTrue(any(w.startswith("hw_selfcontained_solutions") for w in report["warnings"]))
        self.assertFalse(any(w.startswith("hw_unpaired_solution_file") for w in report["warnings"]))

    def test_chapterless_homework_gets_discovery_warning(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw26.pdf": ["Problem 1\n没有章节线索的题面。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertNotIn("chapter", q)                            # 作业号≠章节号：仍绝不猜
        self.assertTrue(any(w.startswith("hw_no_chapter") for w in report["warnings"]))

    # ---- regression guards for Codex round-9 (7 findings) ----

    def test_pure_answer_key_not_promoted_to_homework(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw9_key_solutions.pdf": ["Problem 1\nAnswer 1: 42\n\nProblem 2\nAnswer 2: 17"]})
        code, payload, report = _run(mat, be)
        self.assertFalse([q for q in payload["quiz_bank"] if q.get("source_type") == "homework"])
        self.assertTrue(any(w.startswith("hw_unpaired_solution_file") for w in report["warnings"]))

    def test_paired_solution_pages_kept_out_of_wiki(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": ["Problem 1\n泄题检查的题面。"],
                            "hw1_sol.pdf": ["Problem 1\nAnswer 1: 泄题检查的官方答案。"]})
        code, payload, report = _run(mat, be)
        wiki_all = " ".join(ph.get("wiki_content", "") for ph in payload.get("phases", []))
        self.assertNotIn("泄题检查的官方答案", wiki_all)            # 官方答案页绝不进章节 wiki
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("泄题检查的官方答案", q["answer"])            # 但答案出处保留

    def test_mirrored_trees_under_common_root_pair(self):
        tmp = tempfile.mkdtemp()
        mat = os.path.join(tmp, "mat")
        for wk in ("week1", "week2"):
            os.makedirs(os.path.join(mat, "course", "homework", wk), exist_ok=True)
            os.makedirs(os.path.join(mat, "course", "solutions", wk), exist_ok=True)
            for top in ("homework", "solutions"):
                with open(os.path.join(mat, "course", top, wk, "hw1.pdf"), "wb") as f:
                    f.write(b"%PDF-fake")

        class RootBackend(FakeBackend):
            def page_texts(self, pdf_path):
                p = pdf_path.replace("\\", "/")
                wk = "week1" if "week1" in p else "week2"
                if "solutions" in p:
                    return ["Problem 1\nAnswer 1: %s 公共前缀答案。" % wk]
                return ["Problem 1\n%s 公共前缀题面。" % wk]
        code, payload, report = _run(mat, RootBackend({}))
        hw = {q["source_file"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("week1 公共前缀答案", hw["course/homework/week1/hw1.pdf"]["answer"])
        self.assertIn("week2 公共前缀答案", hw["course/homework/week2/hw1.pdf"]["answer"])

    def test_multiline_blank_answer_box_unknown(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw27.pdf": ["Problem 1\n计算 2+2。\nAnswer:\n________\nShow your work.\n\n"
                                         "Problem 2\n下一题题面。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertNotIn("answer", hw[1])                         # 多行空栏+指示语不是官方答案
        self.assertEqual(hw[1]["answer_status"], "unknown")

    def test_answer_key_suffix_filenames_pair(self):
        hw, pairing = B.classify_homework_files(["hw1.pdf", "hw1_answer_key.pdf"])
        self.assertEqual(pairing["hw1_answer_key.pdf"], "hw1.pdf")
        hw2, pairing2 = B.classify_homework_files(["hw2.pdf", "hw2_solution_key.pdf"])
        self.assertEqual(pairing2["hw2_solution_key.pdf"], "hw2.pdf")
        hw3, pairing3 = B.classify_homework_files(["keyboard_hw1.pdf"])
        self.assertEqual((len(hw3), pairing3), (1, {}))            # keyboard 不是 key 后缀

    def test_same_line_solution_content_pairs(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw28.pdf": ["Problem 1\n题面文字内容。\n\nProblem 1 Solution: A1 就是答案。\n\n"
                                         "Problem 2\n下一题题面。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertIn("A1 就是答案", hw[1]["answer"])              # 同行带内容的解答段配上
        self.assertEqual(hw[2]["answer_status"], "unknown")
        tmp2 = tempfile.mkdtemp()
        mat2, be2 = _mk(tmp2, {"hw29.pdf": ["Problem 1: Answer the following about stacks.\n更多题面。"]})
        code2, payload2, report2 = _run(mat2, be2)
        hw2 = [q for q in payload2["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw2), 1)                             # 题面动词形式不回退

    def test_numeric_only_body_is_page_reference(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw30.pdf": ["Problem 1\n12\n\nProblem 2\n2+2=?"]})
        asset_root = os.path.join(tmp, "ws", "references", "assets")
        code, payload, report = _run(mat, be, ["--asset-root", asset_root])
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(hw[1]["question_text_status"], "page_reference")   # 页脚数字是抽取残渣
        self.assertIs(hw[1]["requires_assets"], True)
        self.assertEqual(hw[2]["question_text_status"], "full")   # 带运算符的数字题面仍 full

    # ---- regression guards for Codex round-10 (6 findings) ----

    def test_solution_with_connector_prefix_is_companion(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw1.pdf": ["Problem 1\n连接词配对的题面。"],
                            "solutions_for_hw1.pdf": ["Problem 1\nAnswer 1: 连接词配对的答案。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 1)                              # solutions_for_hw1 是伴随解答
        self.assertIn("连接词配对的答案", hw[0]["answer"])
        hw2, pairing2 = B.classify_homework_files(["hw2.pdf", "answers_to_hw2.pdf"])
        self.assertEqual(pairing2["answers_to_hw2.pdf"], "hw2.pdf")
        hw3, pairing3 = B.classify_homework_files(["answer_questions_hw3.pdf"])
        self.assertEqual((len(hw3), pairing3), (1, {}))            # 动词短语（questions 夹词）仍归作业

    def test_selfcontained_same_line_prompt_extracted(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw2_solutions.pdf": ["Problem 1 Compute 2+2.\nSolution\n答案是 4。"]})
        code, payload, report = _run(mat, be)
        hw = [q for q in payload["quiz_bank"] if q.get("source_type") == "homework"]
        self.assertEqual(len(hw), 1)                              # 同行题面也算真实题面
        self.assertIn("答案是 4", hw[0]["answer"])
        self.assertTrue(any(w.startswith("hw_selfcontained_solutions") for w in report["warnings"]))

    def test_homework_pages_kept_out_of_wiki(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"作业2.pdf": ["第1题" + chr(10) + "作业题面。" + chr(10) + "Solution"
                                          + chr(10) + "作业的官方解答内容。"]})
        with open(os.path.join(mat, "lecture_ch1.pdf"), "wb") as f:
            f.write(b"%PDF-fake")
        be.texts["lecture_ch1.pdf"] = ["Example 1.1 Problem" + chr(10) + "讲义正文知识点。"]
        code, payload, report = _run(mat, be)
        wiki_all = " ".join(ph.get("wiki_content", "") for ph in payload.get("phases", []))
        self.assertNotIn("作业的官方解答内容", wiki_all)            # inline 解答不泄进 wiki
        self.assertNotIn("作业题面", wiki_all)                     # 作业册整册不进 wiki（题在 quiz_bank）
        self.assertIn("讲义正文知识点", wiki_all)                  # 讲义照常进 wiki
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("作业的官方解答内容", q["answer"])

    def test_blank_answer_sheet_companion_stays_unknown(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw3.pdf": ["Problem 1\n空白答卷的题面。"],
                            "hw3_sol.pdf": ["Problem 1\nAnswer 1: ________"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertNotIn("answer", q)                             # 独立空白答卷不是官方答案
        self.assertEqual(q["answer_status"], "unknown")

    def test_untitled_multi_header_repeats_stay_questions(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw4.pdf": ["Problem 1\n题面一。\n\nProblem 2\n题面二。",
                                        "Problem 1\n续页一正文。\n\nProblem 2\n续页二正文。"]})
        code, payload, report = _run(mat, be)
        hw = {q["homework_number"]: q for q in payload["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(hw[1]["answer_status"], "unknown")       # 无 Solutions 节标题的多号重现 ≠ 答案
        self.assertEqual(hw[2]["answer_status"], "unknown")
        self.assertTrue([w for w in report["warnings"] if "hw_duplicate_problem" in w])

    def test_single_problem_unnumbered_solution_companion(self):
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw5.pdf": ["Problem 1\n单题作业的题面。"],
                            "hw5_sol.pdf": ["Solution\n整册就是这道题的解答。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("整册就是这道题的解答", q["answer"])          # 无号单块解答按唯一题配上
        tmp2 = tempfile.mkdtemp()
        mat2, be2 = _mk(tmp2, {"hw6.pdf": ["Problem 1\n多题一。\n\nProblem 2\n多题二。"],
                               "hw6_sol.pdf": ["Solution\n只有一块答案不知道归谁。"]})
        code2, payload2, report2 = _run(mat2, be2)
        hw2 = {q["homework_number"]: q for q in payload2["quiz_bank"] if q.get("source_type") == "homework"}
        self.assertEqual(hw2[1]["answer_status"], "unknown")       # 多题作业不猜归属
        self.assertEqual(hw2[2]["answer_status"], "unknown")

    def test_figure_dash_artifact_not_a_blank(self):
        # 真实解答首行常是图表轴线残渣（单个 '-'）——填空线须 ≥3 个连续填充符，不能误否真解答
        tmp = tempfile.mkdtemp()
        mat, be = _mk(tmp, {"hw7.pdf": ["Problem 1\n图表题的题面。"],
                            "hw7_sol.pdf": ["Problem 1 Solution\n-\n6\ny\nx\n真正的图表解答正文。"]})
        code, payload, report = _run(mat, be)
        q = next(x for x in payload["quiz_bank"] if x.get("source_type") == "homework")
        self.assertIn("真正的图表解答正文", q["answer"])

    def test_no_network_or_llm(self):










        src = open(os.path.join(ROOT, "scripts", "build_raw_input_from_workspace.py"), encoding="utf-8").read()
        for banned in ("import requests", "urllib.request", "import anthropic", "import socket"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
