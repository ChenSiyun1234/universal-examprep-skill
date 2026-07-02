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

    def test_migrated_note_excludes_status_cell(self):
        ws = _mk_ws(tempfile.mkdtemp())
        _up(ws, ["init"])
        row = _state(ws)["mistake_archive"][0]
        self.assertEqual(row["status"], "未复习")
        self.assertNotIn("未复习", row["note"])                    # 状态不再在 note 里重复一份
        self.assertIn("混淆LIFO", row["note"])

    def test_migrated_three_col_row_keeps_note(self):
        md = LEGACY_MD.replace("| [#q1] | 第1章 | 栈顺序 | 混淆LIFO | 未复习 |",
                               "| [#q1] | 第1章 | 只有笔记没有状态列 |")
        ws = _mk_ws(tempfile.mkdtemp(), md=md)
        _up(ws, ["init"])
        row = _state(ws)["mistake_archive"][0]
        self.assertEqual(row["note"], "只有笔记没有状态列")         # 无状态列时整个尾部是 note
        self.assertEqual(row["status"], "待复盘")

    def test_migration_preserves_phase_checklist(self):
        md = LEGACY_MD + ("\n## 📊 知识点打卡状态\n- [x] **阶段 1**：栈与队列 (关联 `references/wiki/ch1.md`)\n"
                          "- [ ] **阶段 2**：树 (关联 `references/wiki/ch2.md`)\n")
        ws = _mk_ws(tempfile.mkdtemp(), md=md)
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 0, r.stderr)
        st = _state(ws)
        self.assertEqual(len(st["phase_checklist"]), 2)           # 打卡状态随迁移进 state，不丢
        self.assertTrue(st["phase_checklist"][0]["done"])
        self.assertFalse(st["phase_checklist"][1]["done"])
        out = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        self.assertIn("知识点打卡状态", out)                       # 生成视图渲染回打卡区
        self.assertIn("- [x] **阶段 1**", out)
        self.assertIn("- [ ] **阶段 2**", out)

    def test_set_check_official_path(self):
        md = LEGACY_MD + "\n## 📊 知识点打卡状态\n- [ ] **阶段 1**：栈与队列\n- [ ] **模拟测试**：综合自测\n"
        ws = _mk_ws(tempfile.mkdtemp(), md=md)
        _up(ws, ["init"])
        r = _up(ws, ["set-check", "--match", "阶段 1"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(_state(ws)["phase_checklist"][0]["done"])  # 勾选走官方路径
        self.assertIn("- [x] **阶段 1**", open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read())
        r = _up(ws, ["set-check", "--index", "1", "--undone"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(_state(ws)["phase_checklist"][0]["done"])

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

    def test_mutation_on_malformed_state_fails_loud(self):
        ws = self._ready()
        st = _state(ws)
        st["mistake_archive"] = 1                                 # 手改/半写坏形态
        json.dump(st, open(os.path.join(ws, "study_state.json"), "w", encoding="utf-8"))
        r = _up(ws, ["add-mistake", "--note", "x"])
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)                   # fail-loud _die，不是 Python 崩栈
        self.assertIn("损坏", r.stderr)

    def test_missing_optional_fields_tolerated(self):
        ws = self._ready()
        st = _state(ws)
        for f in ("phase_checklist", "confusion_log"):            # 旧 schema 缺字段 → 按空列表补齐
            st.pop(f, None)
        json.dump(st, open(os.path.join(ws, "study_state.json"), "w", encoding="utf-8"))
        r = _up(ws, ["add-confusion", "--note", "取模没搞懂"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(_state(ws)["confusion_log"]), 1)

    # ---- regression guards for Codex round-4 (9 findings) ----

    def test_add_confusion_uses_review_status(self):
        ws = self._ready()
        _up(ws, ["add-confusion", "--note", "取模没搞懂"])
        _up(ws, ["add-mistake", "--note", "Venn 判断错"])
        st = _state(ws)
        self.assertEqual(st["confusion_log"][-1]["status"], "待回顾")   # 疑难走 待回顾→已回顾 契约
        self.assertEqual(st["mistake_archive"][-1]["status"], "待复盘")

    def test_migrated_confusion_bullet_gets_review_status(self):
        ws = _mk_ws(tempfile.mkdtemp())
        _up(ws, ["init"])
        self.assertEqual(_state(ws)["confusion_log"][0]["status"], "待回顾")

    def test_render_rejects_non_string_note(self):
        ws = self._ready()
        st = _state(ws)
        st["mistake_archive"] = [{"id": "q1", "note": 5, "status": "待复盘"}]
        json.dump(st, open(os.path.join(ws, "study_state.json"), "w", encoding="utf-8"))
        r = _up(ws, ["render"])
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)                   # fail-loud，不是渲染中途崩栈
        self.assertIn("损坏", r.stderr)

    # ---- regression guards for Codex round-5 (5 findings) ----

    def test_multiline_note_stays_single_table_row(self):
        ws = self._ready()
        r = _up(ws, ["add-mistake", "--id", "q9", "--note", "第一行原因\n第二行补充"])
        self.assertEqual(r.returncode, 0, r.stderr)
        md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        row_lines = [ln for ln in md.splitlines() if "q9" in ln]
        self.assertEqual(len(row_lines), 1)                       # 换行归一成空格，行结构不被拆散
        self.assertIn("第一行原因 第二行补充", row_lines[0])
        self.assertNotIn("\n第二行补充", md)

    def test_init_rejects_invalid_phase_zero(self):
        ws = _mk_ws(tempfile.mkdtemp(), md="当前阶段：0\n## 错题本\n（暂无）\n")
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 1)                         # 迁移绝不产出损坏 state
        self.assertIn("非法", r.stderr)
        self.assertFalse(os.path.isfile(os.path.join(ws, "study_state.json")))

    # ---- regression guards for Codex round-6 (5 findings) ----

    def test_symlinked_tmp_rejected_before_write(self):
        ws = self._ready()
        outside = os.path.join(tempfile.mkdtemp(), "victim.txt")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("外部文件不许被截断")
        try:
            os.symlink(outside, os.path.join(ws, "study_state.json.tmp"))
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        r = _up(ws, ["set", "--phase", "1", "--mode", "x"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("符号链接", r.stderr)                        # 拒绝写入，不跟随链接
        self.assertEqual(open(outside, encoding="utf-8").read(), "外部文件不许被截断")

    def test_stale_plain_tmp_cleaned_and_overwritten(self):
        ws = self._ready()
        with open(os.path.join(ws, "study_state.json.tmp"), "w", encoding="utf-8") as f:
            f.write("上次崩溃的残留")
        r = _up(ws, ["set", "--phase", "2"])
        self.assertEqual(r.returncode, 0, r.stderr)               # 普通残留 tmp 清掉重建，不误伤
        self.assertEqual(_state(ws)["current_phase"], 2)
        self.assertFalse([f for f in os.listdir(ws) if f.endswith(".tmp")])

    def test_migration_preserves_scope_and_mode(self):
        md = ("# 🎯 复习进度\n\n## ⏱️ 当前复习断点\n* **当前进行阶段**：阶段 2\n"
              "* **范围/模式**：homework-only ｜ 查缺补漏 ｜ 时间预算 3天\n\n"
              "## ❌ 错题档案记录\n（暂无）\n")
        ws = _mk_ws(tempfile.mkdtemp(), md=md)
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 0, r.stderr)
        st = _state(ws)
        self.assertEqual(st["scope"], "homework-only")            # A2 范围偏好不因迁移被静默放宽
        self.assertEqual(st["mode"], "查缺补漏")
        self.assertEqual(st["time_budget"], "3天")
        ws2 = _mk_ws(tempfile.mkdtemp())                          # 默认「混合题池｜未设定」→ 保持 None
        _up(ws2, ["init"])
        self.assertIsNone(_state(ws2).get("scope"))

    def test_real_row_containing_placeholder_text_kept(self):
        md = LEGACY_MD.replace("| [#q1] | 第1章 | 栈顺序 | 混淆LIFO | 未复习 |",
                               "| [#q1] | 第1章 | 空集（暂无）元素时的处理 | 混淆边界 | 未复习 |")
        ws = _mk_ws(tempfile.mkdtemp(), md=md)
        _up(ws, ["init"])
        st = _state(ws)
        self.assertEqual(len(st["mistake_archive"]), 1)           # 含（暂无）字样的真实行不被当占位符丢
        self.assertIn("空集（暂无）元素", st["mistake_archive"][0]["note"])
        md2 = LEGACY_MD + "\n| （暂无） | - | - | - |\n"
        ws2 = _mk_ws(tempfile.mkdtemp(), md=md2)
        _up(ws2, ["init"])
        self.assertEqual(len(_state(ws2)["mistake_archive"]), 1)  # 纯占位行仍被跳过


    # ---- regression guards for Codex round-7 (6 findings) ----

    def test_set_phase_must_be_in_plan(self):
        ws = self._ready()
        with open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 阶段1：栈\n## 第2阶段：树\n")
        r = _up(ws, ["set", "--phase", "99"])
        self.assertNotEqual(r.returncode, 0)                      # 官方路径写之前就拒绝
        self.assertIn("不在 study_plan.md", r.stderr)
        self.assertNotEqual(_state(ws)["current_phase"], 99)      # 事实源未被污染
        self.assertEqual(_up(ws, ["set", "--phase", "2"]).returncode, 0)   # 第N阶段写法也认

    def test_symlinked_state_rejected_by_updater(self):
        ws = _mk_ws(tempfile.mkdtemp(), md=None)
        outside = os.path.join(tempfile.mkdtemp(), "evil_state.json")
        json.dump({"version": 1, "current_phase": 1, "mistake_archive": [], "confusion_log": []},
                  open(outside, "w", encoding="utf-8"))
        try:
            os.symlink(outside, os.path.join(ws, "study_state.json"))
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        r = _up(ws, ["show"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("符号链接", r.stderr)                        # 读取前 fail-loud，不采纳外部事实源


    # ---- regression guards for Codex round-8 (8 findings) ----

    def test_init_rejects_phase_outside_plan(self):
        ws = _mk_ws(tempfile.mkdtemp(), md="当前阶段：99\n## 错题本\n（暂无）\n")
        with open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 阶段1：栈\n")
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 1)                         # 迁移不产出恢复不进去的断点
        self.assertIn("不在 study_plan.md", r.stderr)
        self.assertFalse(os.path.isfile(os.path.join(ws, "study_state.json")))

    def test_skills_route_reads_and_archives_through_state(self):
        # 读侧/归档侧指令也要对齐事实源——不能只有 Boundaries 一句
        review = open(os.path.join(ROOT, "skills", "exam-review", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("`study_state.json`'s `mistake_archive`", review)
        quiz = open(os.path.join(ROOT, "skills", "exam-quiz", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("add-mistake --id", quiz)
        tutor = open(os.path.join(ROOT, "skills", "exam-tutor", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("set --phase <N>", tutor)
        tracker = open(os.path.join(ROOT, "skills", "confusion-tracker", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("output contract IS the `update_progress.py add-confusion`", tracker)


    # ---- regression guards for Codex round-9 (5 findings) ----

    def test_init_preserves_preferences_section(self):
        ws = self._ready()
        _up(ws, ["set", "--pref", "讲解风格=七步模板", "--pref", "口吻=简洁"])
        r = _up(ws, ["init", "--force"])                          # 官方推荐的恢复路径
        self.assertEqual(r.returncode, 0, r.stderr)
        st = _state(ws)
        self.assertEqual(st["preferences"].get("讲解风格"), "七步模板")   # 偏好不因重建被静默丢
        self.assertEqual(st["preferences"].get("口吻"), "简洁")

    def test_state_dir_rejected_before_any_write(self):
        ws = self._ready()
        before_md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        os.remove(os.path.join(ws, "study_state.json"))
        os.makedirs(os.path.join(ws, "study_state.json"))         # state 路径变目录
        r = _up(ws, ["init", "--force"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("拒绝写入", r.stderr)
        self.assertEqual(open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read(),
                         before_md)                               # 生成视图未被先行打掉

    def test_stale_phase_blocks_mutations_but_set_repairs(self):
        ws = self._ready()
        with open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 阶段1：栈\n## 阶段2：树\n")
        st = _state(ws)
        st["current_phase"] = 9                                   # 手改/计划回滚后的陈旧断点
        json.dump(st, open(os.path.join(ws, "study_state.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        r = _up(ws, ["add-mistake", "--note", "x"])
        self.assertEqual(r.returncode, 1)                         # 其他变更拒绝再保存坏断点
        self.assertIn("已不在 study_plan.md", r.stderr)
        r2 = _up(ws, ["set", "--phase", "2"])                     # 修复路径豁免并自校验新值
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(_up(ws, ["add-mistake", "--note", "x"]).returncode, 0)


    # ---- regression guards for Codex round-10 (5 findings) ----

    def test_language_survives_forced_rebuild(self):
        ws = self._ready()
        _up(ws, ["set", "--language", "English"])
        r = _up(ws, ["init", "--force"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(_state(ws)["language"], "English")       # 语言偏好经生成视图迁回

    def test_forced_rebuild_keeps_idless_rows_idless(self):
        ws = self._ready()
        _up(ws, ["add-confusion", "--note", "无 id 的疑难甲"])
        _up(ws, ["add-confusion", "--note", "无 id 的疑难乙"])
        r = _up(ws, ["init", "--force"])
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = [x for x in _state(ws)["confusion_log"] if "无 id" in x["note"]]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(x["id"] is None for x in rows))       # 渲染的 '-' 占位不回灌成 id


    # ---- regression guards for Codex round-11 (4 findings) ----

    def test_init_rejects_symlinked_md(self):
        ws = _mk_ws(tempfile.mkdtemp(), md=None)
        outside = os.path.join(tempfile.mkdtemp(), "evil.md")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("当前阶段：1\n")
        try:
            os.symlink(outside, os.path.join(ws, "study_progress.md"))
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("符号链接", r.stderr)                        # 外部文件不迁进事实源
        self.assertFalse(os.path.isfile(os.path.join(ws, "study_state.json")))


    # ---- regression guards for Codex round-12 (4 findings) ----

    def test_blank_init_seeds_phase_from_plan(self):
        ws = _mk_ws(tempfile.mkdtemp(), md=None)
        with open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 阶段2：树\n## 阶段3：图\n")      # 计划不含阶段1
        r = _up(ws, ["init"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(_state(ws)["current_phase"], 2)          # 空白初始化落在计划内（min）
        self.assertEqual(_up(ws, ["add-mistake", "--note", "x"]).returncode, 0)   # 后续更新不被卡死

    def test_unreadable_plan_fails_loud(self):
        ws = self._ready()
        with open(os.path.join(ws, "study_plan.md"), "wb") as f:
            f.write("阶段：乱码".encode("gbk"))                   # 计划存在但非 UTF-8
        r = _up(ws, ["set", "--phase", "2"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("无法读取", r.stderr)                        # 不静默禁用阶段守卫


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


    # ---- regression guards for Codex round-1 (P1 + 3 P2) ----

    def test_set_status_by_id_and_index(self):
        ws = self._ready()
        _up(ws, ["add-mistake", "--id", "q9", "--note", "第一条"])
        r = _up(ws, ["set-mistake-status", "--id", "q9", "--status", "已复盘"])
        self.assertEqual(r.returncode, 0, r.stderr)
        st = _state(ws)
        row = next(x for x in st["mistake_archive"] if x.get("id") == "q9")
        self.assertEqual(row["status"], "已复盘")                  # P1：官方状态更新路径
        md = open(os.path.join(ws, "study_progress.md"), encoding="utf-8").read()
        self.assertIn("已复盘", md)
        r2 = _up(ws, ["set-confusion-status", "--index", "1", "--status", "已解决"])
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(_state(ws)["confusion_log"][0]["status"], "已解决")

    def test_set_status_missing_target_fails(self):
        ws = self._ready()
        self.assertEqual(_up(ws, ["set-mistake-status", "--id", "nope", "--status", "x"]).returncode, 2)
        self.assertEqual(_up(ws, ["set-mistake-status", "--status", "x"]).returncode, 2)
        self.assertEqual(_up(ws, ["set-mistake-status", "--index", "99", "--status", "x"]).returncode, 2)

    def test_failed_write_leaves_no_tmp_and_truth_intact(self):
        ws = self._ready()
        before = _state(ws)
        md_dir = os.path.join(ws, "study_progress.md")
        os.remove(md_dir)
        os.makedirs(md_dir)                                       # md 路径变目录 → 写入必失败
        r = _up(ws, ["set", "--phase", "9"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("拒绝写入", r.stderr)                        # round-10 起：暂存任何 tmp 前就拦截
        self.assertEqual(_state(ws)["current_phase"], before["current_phase"])   # 事实源未超前
        self.assertFalse([f for f in os.listdir(ws) if f.endswith(".tmp")])      # 无 tmp 残留
        self.assertTrue(os.path.isdir(os.path.join(ws, "study_progress.md")))    # 生成视图目录未被打掉

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

    def test_scalar_array_reports_without_crash(self):
        ws = self._full_ws({"mistake_archive": 1})
        r = self._validate(ws)
        self.assertEqual(r.returncode, 1)                         # 结构化报错，不是 TypeError 崩栈
        self.assertNotIn("Traceback", r.stderr)

    def test_symlinked_state_rejected(self):
        ws = self._full_ws(None)
        outside = os.path.join(tempfile.mkdtemp(), "evil.json")
        json.dump({"version": 1, "current_phase": 1}, open(outside, "w", encoding="utf-8"))
        link = os.path.join(ws, "study_state.json")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        r = self._validate(ws)
        self.assertEqual(r.returncode, 1)
        self.assertIn("符号链接", r.stdout)

    def test_phase_checklist_schema_validated(self):
        r = self._validate(self._full_ws({"phase_checklist": 1}))
        self.assertEqual(r.returncode, 1)                         # 标量不是打卡数组
        r = self._validate(self._full_ws({"phase_checklist": [{"text": "", "done": True}]}))
        self.assertEqual(r.returncode, 1)                         # 空 text 拒绝
        r = self._validate(self._full_ws({"phase_checklist": [{"text": "阶段 1：栈", "done": "yes"}]}))
        self.assertEqual(r.returncode, 1)                         # done 必须布尔
        r = self._validate(self._full_ws({"phase_checklist": [{"text": "阶段 1：栈", "done": False}]}))
        self.assertEqual(r.returncode, 0, r.stdout)               # 合法形态通过

    def test_state_phase_check_matches_both_plan_wordings(self):
        ws = self._full_ws({"current_phase": 99})
        with open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 第1阶段：栈（references/wiki/ch1.md）\n")
        r = self._validate(ws)
        self.assertEqual(r.returncode, 1)                         # 「第N阶段」写法也参与校验，99 照样拦
        self.assertIn("不在 study_plan.md", r.stdout)
        ws2 = self._full_ws({"current_phase": 2})
        with open(os.path.join(ws2, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 第1阶段：栈（references/wiki/ch1.md）\n## 第2阶段：树（references/wiki/ch1.md）\n")
        with open(os.path.join(ws2, "study_progress.md"), "w", encoding="utf-8") as f:
            f.write("当前阶段：2\n## 错题本\n（暂无）\n## 疑难点\n（暂无）\n")
        self.assertEqual(self._validate(ws2).returncode, 0)       # 合法「第N阶段」计划不误伤

    def test_state_row_id_status_types_validated(self):
        r = self._validate(self._full_ws({"mistake_archive": [
            {"id": ["q1"], "note": "x", "status": "待复盘"}]}))
        self.assertEqual(r.returncode, 1)                         # id 非字符串 → err
        r = self._validate(self._full_ws({"confusion_log": [
            {"id": "c1", "note": "x", "status": {"s": 1}}]}))
        self.assertEqual(r.returncode, 1)                         # status 非字符串 → err

    def test_dangling_state_symlink_flagged(self):
        ws = self._full_ws(None)
        try:
            os.symlink(os.path.join(ws, "no_such_target.json"), os.path.join(ws, "study_state.json"))
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        r = self._validate(ws)
        self.assertEqual(r.returncode, 1)                         # 悬空链接不能整段跳过校验
        self.assertIn("符号链接", r.stdout)

    def test_md_phase_mismatch_warns(self):
        ws = self._full_ws({"current_phase": 2})                  # md 说 1，state 说 2
        with open(os.path.join(ws, "study_plan.md"), "w", encoding="utf-8") as f:
            f.write("# 计划\n## 阶段1：栈（references/wiki/ch1.md)\n## 阶段2：树（references/wiki/ch1.md）\n")
        r = self._validate(ws)
        self.assertEqual(r.returncode, 0)                         # 仅告警（md 是生成视图）
        self.assertIn("不一致", r.stdout)

    def test_state_phase_outside_plan_errors(self):
        ws = self._full_ws({"current_phase": 99})                 # 计划只有阶段1
        r = self._validate(ws)
        self.assertEqual(r.returncode, 1)                         # 事实源指向不存在的阶段 → 报错不是警告
        self.assertIn("不在 study_plan.md", r.stdout)


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


    def test_t4_rejects_md_only_snapshot_after_state(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        st2 = json.dumps({"version": 1, "current_phase": 2,
                          "mistake_archive": [{"id": "stack_lifo_1", "note": "误答 FIFO"}],
                          "confusion_log": []}, ensure_ascii=False)
        stale_md = ("当前阶段：9\n## ❌ 错题档案记录\n| 错题ID | 章节 | 原因 | 状态 |\n| :- | :- | :- | :- |\n"
                    "| [#stack_lifo_1] | 1 | 误答 FIFO | 待复盘 |\n| [#fake_row_2] | 1 | 手改加行 | 待复盘 |\n")
        turns = [
            {"turn": 1, "assistant": "进入阶段2。", "phase_context": 2,
             "files_after": {"study_state.json": st2}},
            {"turn": 2, "assistant": "偷偷手改 md。",                # state 已确立后的 md-only 手改
             "files_after": {"study_progress.md": stale_md}},
            {"turn": 3, "user": "我回来了，继续复习", "kind": "resume",
             "assistant": "欢迎回来！我们接着阶段2继续复习。"},
        ]
        with open(t, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x, ensure_ascii=False) for x in turns))
        m = D.evaluate(sc, t)["metrics"]
        self.assertEqual(m["mistake_rows_added"], 1)              # 手改 md 的加行不算数（state 才是事实源）
        self.assertEqual(m["reset_detected"], 0)                  # 断点仍按 state 的阶段 2，不被 md 的 9 带跑
        self.assertEqual(m["md_write_after_state"], 1)            # 且违规被计数曝光（阈值 0 会让场景 FAIL）

    def test_t4_seeds_from_fixture_state_json(self):
        # fixture 自带 study_state.json（阶段2 + 一条已有错题行）而生成视图 md 过期（阶段1、无行）——
        # 指标种子必须来自 JSON 事实源：已有行不算新增、断点按阶段2
        import shutil
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        fx = os.path.join(tempfile.mkdtemp(), "fx")
        shutil.copytree(os.path.join(ROOT, sc["fixture"]), fx)
        json.dump({"version": 1, "current_phase": 2,
                   "mistake_archive": [{"id": "stack_lifo_1", "note": "误答 FIFO"}],
                   "confusion_log": []},
                  open(os.path.join(fx, "study_state.json"), "w", encoding="utf-8"), ensure_ascii=False)
        sc2 = dict(sc, fixture=fx)
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        st_same = json.dumps({"version": 1, "current_phase": 2,
                              "mistake_archive": [{"id": "stack_lifo_1", "note": "误答 FIFO"}],
                              "confusion_log": []}, ensure_ascii=False)
        turns = [
            {"turn": 1, "user": "我回来了，继续复习", "kind": "resume",
             "assistant": "欢迎回来！我们接着阶段2继续复习。",
             "files_after": {"study_state.json": st_same}},
        ]
        with open(t, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x, ensure_ascii=False) for x in turns))
        m = D.evaluate(sc2, t)["metrics"]
        self.assertEqual(m["mistake_rows_added"], 0)              # 行在 fixture state 里就有，不算会话新增
        self.assertEqual(m["reset_detected"], 0)                  # 断点种子=阶段2，不被过期 md 的阶段1 带偏

    def test_t4_placeholder_table_row_not_a_data_row(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        md = ("当前阶段：1\n## ❌ 错题档案记录\n"
              "| 错题ID | 关联章节 | 错误原因分析 | 状态 |\n| :--- | :--- | :--- | :--- |\n"
              "| （暂无） | - | - | - |\n")
        p = D.parse_progress(md)
        self.assertEqual(p["mistake_rows"], [])                   # 生成视图的占位行不是幻影数据行

    def test_t4_rejects_invalid_state_phase(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        for bad_cp in ('"2"', "0"):                               # 字符串/0 都是坏输入，不能静默放行
            d = tempfile.mkdtemp()
            t = os.path.join(d, "t.jsonl")
            bad = '{"version": 1, "current_phase": %s, "mistake_archive": [], "confusion_log": []}' % bad_cp
            with open(t, "w", encoding="utf-8") as f:
                f.write(json.dumps({"turn": 1, "assistant": "x",
                                    "files_after": {"study_state.json": bad}}) + "\n")
            with self.assertRaises(D.DriftError):
                D.evaluate(sc, t)

    def test_t4_rejects_malformed_state_rows(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        for bad_rows in ('["[#q1] 字符串行"]', '[{"id": "q1"}]'):   # 非对象行 / 缺非空 note
            d = tempfile.mkdtemp()
            t = os.path.join(d, "t.jsonl")
            bad = '{"version": 1, "current_phase": 2, "mistake_archive": %s, "confusion_log": []}' % bad_rows
            with open(t, "w", encoding="utf-8") as f:
                f.write(json.dumps({"turn": 1, "assistant": "x",
                                    "files_after": {"study_state.json": bad}}) + "\n")
            with self.assertRaises(D.DriftError):                 # 坏行 fail-loud，不再以 0 行静默通过
                D.evaluate(sc, t)

    def test_md_write_after_state_is_gated_metric(self):
        # 场景阈值 md_write_after_state_max=0 存在，且指标真会计数——A4 违规不只是被忽略
        sc_json = json.load(open(os.path.join(ROOT, "benchmark", "drift", "scenarios",
                                              "long_session_basic.json"), encoding="utf-8"))
        self.assertEqual(sc_json["thresholds"].get("md_write_after_state_max"), 0)
        sc_live = json.load(open(os.path.join(ROOT, "benchmark", "drift", "scenarios",
                                              "live_smoke_basic.json"), encoding="utf-8"))
        self.assertEqual(sc_live["thresholds"].get("md_write_after_state_max"), 0)

    def test_t4_rejects_non_string_row_id(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        bad = json.dumps({"version": 1, "current_phase": 2, "confusion_log": [],
                          "mistake_archive": [{"id": ["q1"], "note": "x"}]}, ensure_ascii=False)
        with open(t, "w", encoding="utf-8") as f:
            f.write(json.dumps({"turn": 1, "assistant": "x",
                                "files_after": {"study_state.json": bad}}) + chr(10))
        with self.assertRaises(D.DriftError):                     # 伪键 id 不做 str() 硬转
            D.evaluate(sc, t)

    def test_t4_keeps_real_rows_containing_placeholder_text(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        md = ("当前阶段：1" + chr(10) + "## ❌ 错题档案记录" + chr(10)
              + "| 错题ID | 关联章节 | 原因 | 状态 |" + chr(10) + "| :- | :- | :- | :- |" + chr(10)
              + "| [#q1] | 1 | 空集（暂无）元素处理错 | 待复盘 |" + chr(10)
              + "| （暂无） | - | - | - |" + chr(10))
        p = D.parse_progress(md)
        self.assertEqual(len(p["mistake_rows"]), 1)               # 真行保留、纯占位行剔除
        self.assertIn("空集（暂无）", p["mistake_rows"][0])

    def test_t4_idless_state_rows_distinct_by_chapter(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        snap = D.parse_state_json(json.dumps({
            "version": 1, "current_phase": 1, "mistake_archive": [],
            "confusion_log": [{"chapter": "1", "note": "取模没搞懂"},
                                 {"chapter": "2", "note": "取模没搞懂"}]}, ensure_ascii=False))
        self.assertEqual(len(set(snap["confusion_rows"])), 2)     # 同 note 不同章不折叠

    def test_t4_counts_md_write_event_after_state(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        st2 = json.dumps({"version": 1, "current_phase": 2, "mistake_archive": [],
                          "confusion_log": []}, ensure_ascii=False)
        turns = [
            {"turn": 1, "assistant": "进入阶段2。", "files_after": {"study_state.json": st2}},
            {"turn": 2, "assistant": "只写 md 事件、不带快照。",
             "events": [{"type": "write_file", "path": "study_progress.md"}]},
        ]
        with open(t, "w", encoding="utf-8") as f:
            f.write(chr(10).join(json.dumps(x, ensure_ascii=False) for x in turns))
        m = D.evaluate(sc, t)["metrics"]
        self.assertEqual(m["md_write_after_state"], 1)            # 纯事件形态的手改也计数

    def test_review_trigger_and_cheatsheet_read_state(self):
        cram = open(os.path.join(ROOT, "skills", "exam-cram", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("judged from `study_state.json`", cram)     # 终局复盘触发看事实源
        sheet = open(os.path.join(ROOT, "skills", "exam-cheatsheet", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("Weak-spot source: `study_state.json`", sheet)   # 小抄弱点清单读事实源

    def test_t4_state_event_without_snapshot_establishes_state(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        turns = [
            {"turn": 1, "assistant": "官方工具写了 state（裸事件）。",
             "events": [{"type": "write_file", "path": "study_state.json"}]},
            {"turn": 2, "assistant": "手改 md。",
             "files_after": {"study_progress.md": "当前阶段：9"}},
        ]
        with open(t, "w", encoding="utf-8") as f:
            f.write(chr(10).join(json.dumps(x, ensure_ascii=False) for x in turns))
        m = D.evaluate(sc, t)["metrics"]
        self.assertEqual(m["md_write_after_state"], 1)            # 裸事件也确立事实源，md-only 被记违规

    def test_t4_rejects_state_phase_outside_plan(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        bad = json.dumps({"version": 1, "current_phase": 99,
                          "mistake_archive": [], "confusion_log": []})
        with open(t, "w", encoding="utf-8") as f:
            f.write(json.dumps({"turn": 1, "assistant": "x",
                                "files_after": {"study_state.json": bad}}) + chr(10))
        with self.assertRaises(D.DriftError):                     # 计划外断点是坏输入，不进指标
            D.evaluate(sc, t)

    def test_t4_state_only_fixture_without_initial_md(self):
        import shutil
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        fx = os.path.join(tempfile.mkdtemp(), "fx")
        shutil.copytree(os.path.join(ROOT, sc["fixture"]), fx)
        os.remove(os.path.join(fx, "study_progress.initial.md"))   # 纯 A4 fixture：只有 state
        json.dump({"version": 1, "current_phase": 2,
                   "mistake_archive": [], "confusion_log": []},
                  open(os.path.join(fx, "study_state.json"), "w", encoding="utf-8"))
        sc2 = dict(sc, fixture=fx)
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        with open(t, "w", encoding="utf-8") as f:
            f.write(json.dumps({"turn": 1, "user": "我回来了，继续复习", "kind": "resume",
                                "assistant": "欢迎回来！我们接着阶段2继续复习。"},
                               ensure_ascii=False) + chr(10))
        m = D.evaluate(sc2, t)["metrics"]                        # 不再因缺 initial md 报 malformed
        self.assertEqual(m["reset_detected"], 0)

    def test_converter_docs_cover_state_snapshot(self):
        doc = open(os.path.join(ROOT, "benchmark", "drift", "docs", "live_agent_pilot.md"),
                   encoding="utf-8").read()
        self.assertIn("write_file: study_state.json", doc)        # 运行手册与转换器契约一致
        tpl = open(os.path.join(ROOT, "benchmark", "drift", "templates", "live_session_template.md"),
                   encoding="utf-8").read()
        self.assertIn("study_state.json", tpl)

    def test_t4_scalar_state_field_exits_2_not_traceback(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import run_drift as D
        sc = D.load_scenario(os.path.join(ROOT, "benchmark", "drift", "scenarios", "long_session_basic.json"))
        d = tempfile.mkdtemp()
        t = os.path.join(d, "t.jsonl")
        bad = json.dumps({"version": 1, "current_phase": 2, "mistake_archive": 1})
        with open(t, "w", encoding="utf-8") as f:
            f.write(json.dumps({"turn": 1, "assistant": "x",
                                "files_after": {"study_state.json": bad}}) + "\n")
        with self.assertRaises(D.DriftError):                     # 畸形快照统一走 DriftError，不 TypeError 崩
            D.evaluate(sc, t)

    def test_converter_tracks_state_json_snapshot(self):
        sys.path.insert(0, os.path.join(ROOT, "benchmark", "drift"))
        import convert_session_log as C
        base = ["# Live Session", "", "## Turn 1", "", "### User", "u", "", "### Assistant", "a", "",
                "### Events", "- write_file: study_state.json", ""]
        # 有 write_file 无匹配快照 → 必须报错（否则 T4 拿旧状态继续算，漏掉重置/丢行）
        with self.assertRaises(C.SessionLogError):
            C.parse_session_log("\n".join(base))
        good = base + ["### Files After: study_state.json", "```json",
                       json.dumps({"version": 1, "current_phase": 1,
                                   "mistake_archive": [], "confusion_log": []}),
                       "```", ""]
        rows = C.parse_session_log("\n".join(good))
        self.assertIn("study_state.json", rows[0]["files_after"])  # 快照被跟踪进 files_after


class Contract(unittest.TestCase):
    ENTRY_POINTS = ["SKILL.md", "AGENTS.md", "prompts/web_prompt.md", "skills/exam-cram/SKILL.md",
                    "skills/exam-quiz/SKILL.md", "skills/exam-tutor/SKILL.md", "skills/exam-review/SKILL.md",
                    "skills/confusion-tracker/SKILL.md"]

    def test_all_entry_points_carry_state_contract(self):
        for p in self.ENTRY_POINTS:
            txt = open(os.path.join(ROOT, p), encoding="utf-8").read()
            self.assertIn("study_state.json", txt, p)
            self.assertIn("update_progress.py", txt, p)

    def test_root_skill_lock_prefers_state(self):
        txt = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
        self.assertIn("断点状态锁定 (`study_state.json`", txt)     # 根入口的状态锁对齐事实源
        self.assertIn("set-check", txt)

    def test_web_prompt_never_claims_local_writes(self):
        txt = open(os.path.join(ROOT, "prompts", "web_prompt.md"), encoding="utf-8").read()
        self.assertIn("网页端口径", txt)                          # A4 条款按网页端能力改写
        self.assertIn("绝不要声称你已写入", txt)                   # 不许谎称本地写入
        self.assertIn("只读事实源", txt)                          # 粘贴的 state 只读恢复

    def test_root_skill_final_review_reads_state(self):
        txt = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
        self.assertIn("从其 `mistake_archive`", txt)              # 根入口错题重温读事实源

    def test_agents_md_prefers_state(self):
        txt = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
        self.assertIn("存在 `study_state.json` 时从它恢复", txt)   # 先读进度条目对齐事实源
        self.assertIn("add-mistake/add-confusion", txt)             # 记录条目走官方路径

    def test_cram_restore_prefers_state(self):
        # 恢复断点必须先读 study_state.json（事实源）——生成视图 md 过期/被手改时不能拿它当起点
        txt = open(os.path.join(ROOT, "skills", "exam-cram", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("from `study_state.json` when it exists", txt)

    def test_review_output_contract_routes_state(self):
        txt = open(os.path.join(ROOT, "skills", "exam-review", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("via `update_progress.py set-mistake-status`", txt)   # 输出契约也走官方路径

    def test_cheatsheet_mastered_chapters_read_state(self):
        txt = open(os.path.join(ROOT, "skills", "exam-cheatsheet", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("`current_phase`/`phase_checklist` when it exists", txt)

    def test_behavior_smoke_asserts_state_writes(self):
        spec = json.load(open(os.path.join(ROOT, "benchmark", "behavior_smoke", "scenarios.json"),
                              encoding="utf-8"))
        by = {sc["name"]: sc for sc in spec["scenarios"]}
        self.assertIn("state_after", by["hint_skip_mistake_archive"])   # 冒烟断言 state 写入
        self.assertIn("state_after", by["confusion_tracking"])
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "benchmark", "behavior_smoke",
                                                          "run_behavior_smoke.py"), "--mock"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("state_row=True", r.stdout)

    def test_review_skill_documents_status_commands(self):
        # replay 流要把行标成 已订正/已回顾 —— A4 边界必须给出官方状态命令，否则 agent 无合法持久化路径
        txt = open(os.path.join(ROOT, "skills", "exam-review", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("set-mistake-status", txt)
        self.assertIn("set-confusion-status", txt)

    def test_no_python_fallback_fixture_is_stateless(self):
        # no_python_fallback 冒烟声称验证「无 state 的手写 md 工作区」——fixture 里绝不能有 study_state.json
        spec = json.load(open(os.path.join(ROOT, "benchmark", "behavior_smoke", "scenarios.json"),
                              encoding="utf-8"))
        sc = next(x for x in spec["scenarios"] if x["name"] == "no_python_fallback")
        fx = os.path.join(ROOT, "benchmark", "behavior_smoke", sc["fallback_workspace"])
        self.assertTrue(os.path.isdir(fx), fx)
        self.assertFalse(os.path.isfile(os.path.join(fx, "study_state.json")))

    def test_no_network_or_llm(self):
        src = open(os.path.join(SCRIPTS, "update_progress.py"), encoding="utf-8").read()
        for banned in ("import requests", "urllib.request", "import anthropic", "import socket"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
