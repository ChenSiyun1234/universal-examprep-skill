# -*- coding: utf-8 -*-
"""A4 tests — structured progress state: migration, mutations, generated md, fail-loud IO,
validator schema, T4 JSON snapshots, entry-point contract."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

LEGACY_MD = ("# 🎯 复习进度\n\n## ⏱️ 当前复习断点\n* **当前进行阶段**：阶段 3：树\n\n"
             "## ❌ 错题档案记录\n| 错题ID | 关联章节 | 题目内容简述 | 错误原因分析 | 状态 |\n"
             "| :--- | :--- | :--- | :--- | :--- |\n| [#q1] | 第1章 | 栈顺序 | 混淆LIFO | 未复习 |\n\n"
             "## 💡 概念疑难点记录\n- 循环队列取模没搞懂\n")


def _mk_ws(tmp, md=LEGACY_MD):
    ws = os.path.join(tmp, "ws")
    os.makedirs(ws)
    if md is not None:
        with open(os.path.join(ws, "study_progress.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    return ws


def _up(ws, args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "update_progress.py"),
                           "--workspace", ws] + args, capture_output=True, text=True, encoding="utf-8")


def _state(ws):
    return json.load(open(os.path.join(ws, "study_state.json"), encoding="utf-8"))


class Migration(unittest.TestCase):
    def test_init_adopts_legacy_md(self):
        ws = _mk_ws(tempfile.mkdtemp())
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 0, r.stderr)
        st = _state(ws)
        self.assertEqual(st["current_phase"], 3)                  # 模板断点行被解析
        self.assertEqual(st["mistake_archive"][0]["id"], "q1")    # 表格行迁移
        self.assertIn("循环队列", st["confusion_log"][0]["note"])  # bullet 行迁移
        md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        self.assertIn("当前进行阶段**：阶段 3", md)                # md 重渲染保持可解析形态
        self.assertIn("自动生成", md)

    def test_init_idempotent_without_force(self):
        ws = _mk_ws(tempfile.mkdtemp())
        _up(ws, ["init"])
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 2)                         # 幂等保护
        self.assertEqual(_up(ws, ["init", "--force"]).returncode, 0)

    def test_init_refuses_non_utf8_md(self):
        ws = _mk_ws(tempfile.mkdtemp(), md=None)
        with open(os.path.join(ws, "study_progress.md"), "wb") as f:
            f.write("当前阶段：2".encode("gbk"))                   # 真实乱码场景
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 1)                         # fail-loud，不猜编码静默迁移
        self.assertIn("UTF-8", r.stderr)
        self.assertFalse(os.path.isfile(os.path.join(ws, "study_state.json")))


class Mutations(unittest.TestCase):
    def _ready(self):
        ws = _mk_ws(tempfile.mkdtemp())
        _up(ws, ["init"])
        return ws

    def test_set_updates_state_and_md(self):
        ws = self._ready()
        r = _up(ws, ["set", "--phase", "5", "--scope", "homework-only", "--mode", "查缺补漏",
                     "--pref", "讲解风格=七步模板"])
        self.assertEqual(r.returncode, 0, r.stderr)
        st = _state(ws)
        self.assertEqual(st["current_phase"], 5)
        self.assertEqual(st["scope"], "homework-only")
        self.assertEqual(st["preferences"]["讲解风格"], "七步模板")
        md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        self.assertIn("阶段 5", md)
        self.assertIn("homework-only", md)                        # 进度面板可见 scope/mode

    def test_add_rows_persist_and_render(self):
        ws = self._ready()
        _up(ws, ["add-mistake", "--id", "hw_hw1_3", "--chapter", "2", "--note", "Venn 阴影判断错"])
        _up(ws, ["add-confusion", "--chapter", "1", "--note", "取模边界"])
        st = _state(ws)
        self.assertEqual(len(st["mistake_archive"]), 2)           # 迁移 1 条 + 新增 1 条
        self.assertEqual(len(st["confusion_log"]), 2)
        md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        self.assertIn("[#hw_hw1_3]", md)
        self.assertIn("取模边界", md)

    def test_set_without_state_fails(self):
        ws = _mk_ws(tempfile.mkdtemp())
        r = _up(ws, ["set", "--phase", "2"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("init", r.stderr)

    def test_render_repairs_hand_edited_md(self):
        ws = self._ready()
        with open(os.path.join(ws, "study_progress.md"), "w", encoding="utf-8") as f:
            f.write("被手改坏的文件")
        r = _up(ws, ["render"])
        self.assertEqual(r.returncode, 0)
        md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        self.assertIn("当前进行阶段", md)                          # 从 state 重建

    def test_empty_note_rejected(self):
        ws = self._ready()
        r = _up(ws, ["add-mistake", "--note", "   "])
        self.assertEqual(r.returncode, 2)


class ValidatorSchema(unittest.TestCase):
    def _full_ws(self, state_patch=None):
        tmp = tempfile.mkdtemp()
        ws = os.path.join(tmp, "ws")
        os.makedirs(os.path.join(ws, "references", "wiki"))
        open(os.path.join(ws, "references", "wiki", "ch1.md"), "w", encoding="utf-8").write("# ch1\n内容")
        open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8").write(
            "# 计划\n## 阶段1：栈（references/wiki/ch1.md）\n")
        open(os.path.join(ws, "study_progress.md"), "w", encoding="utf-8").write(
            "当前阶段：1\n## 错题本\n（暂无）\n## 疑难点\n（暂无）\n")
        json.dump([{"id": "q1", "chapter": 1, "type": "subjective", "question": "x?", "answer": "y",
                    "source": "material", "ai_generated": False}],
                  open(os.path.join(ws, "references", "quiz_bank.json"), "w", encoding="utf-8"))
        if state_patch is not None:
            st = {"version": 1, "current_phase": 1, "mistake_archive": [], "confusion_log": [],
                  "knowledge_window": [], "preferences": {}}
            st.update(state_patch)
            json.dump(st, open(os.path.join(ws, "study_state.json"), "w", encoding="utf-8"),
                      ensure_ascii=False)
        return ws

    def _validate(self, ws):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "validate_workspace.py"), ws],
                              capture_output=True, text=True, encoding="utf-8")

    def test_good_state_passes(self):
        ws = self._full_ws({"mistake_archive": [{"id": "q1", "chapter": "1", "note": "x", "status": "待复盘"}]})
        r = self._validate(ws)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_state_still_valid(self):
        ws = self._full_ws(None)                                  # 无 Python 降级路径保持有效
        self.assertEqual(self._validate(ws).returncode, 0)

    def test_bad_state_types_fail(self):
        for patch in ({"current_phase": 0}, {"current_phase": "3"},
                      {"mistake_archive": ["字符串行"]},
                      {"confusion_log": [{"id": "x"}]},           # 缺 note
                      {"preferences": []}):
            ws = self._full_ws(patch)
            r = self._validate(ws)
            self.assertEqual(r.returncode, 1, "patch=%r 应报错\n%s" % (patch, r.stdout))

    def test_md_phase_mismatch_warns(self):
        ws = self._full_ws({"current_phase": 2})                  # md 说 1，state 说 2
        r = self._validate(ws)
        self.assertEqual(r.returncode, 0)                         # 仅告警（md 是生成视图）
        self.assertIn("不一致", r.stdout)


class DriftJsonSnapshots(unittest.TestCase):
    def test_t4_reads_state_json_snapshot(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        st2 = json.dumps({"version": 1, "current_phase": 2,
                          "mistake_archive": [{"id": "stack_lifo_1", "note": "误答 FIFO"}],
                          "confusion_log": []}, ensure_ascii=False)
        turns = [
            {"turn": 1, "assistant": "进入阶段2。", "phase_context": 2,
             "files_after": {"study_state.json": st2}},
            {"turn": 2, "user": "我回来了，继续复习", "kind": "resume",
             "assistant": "欢迎回来！我们接着阶段2继续复习。"},
        ]
        with open(t, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x, ensure_ascii=False) for x in turns))
        m = D.evaluate(sc, t)["metrics"]
        self.assertEqual(m["reset_detected"], 0)                  # checkpoint 从 JSON 读到阶段 2
        self.assertEqual(m["mistake_rows_added"], 1)              # 行持久性也从 JSON 统计

    def test_t4_malformed_state_json_exits_2(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        with open(t, "w", encoding="utf-8") as f:
            f.write(json.dumps({"turn": 1, "assistant": "x",
                                "files_after": {"study_state.json": "{broken"}}) + "\n")
        with self.assertRaises(D.DriftError):
            D.evaluate(sc, t)


class Contract(unittest.TestCase):
    ENTRY_POINTS = ["SKILL.md", "AGENTS.md", "prompts/web_prompt.md", "skills/exam-cram/SKILL.md",
                    "skills/exam-quiz/SKILL.md", "skills/exam-tutor/SKILL.md", "skills/exam-review/SKILL.md"]

    def test_all_entry_points_carry_state_contract(self):
        for p in self.ENTRY_POINTS:
            txt = open(os.path.join(ROOT, p), encoding="utf-8").read()
            self.assertIn("study_state.json", txt, p)
            self.assertIn("update_progress.py", txt, p)

    def test_no_network_or_llm(self):
        src = open(os.path.join(SCRIPTS, "update_progress.py"), encoding="utf-8").read()
        for banned in ("import requests", "urllib.request", "import anthropic", "import socket"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
