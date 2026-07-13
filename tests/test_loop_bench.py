# -*- coding: utf-8 -*-
"""loop_bench.py（备考全流程会话驱动器）——mock 全管线形状 / 断点续跑 / 配额停跑 exit 7 /
S2 前缀隔离（prompt 捕获桩）。真跑一律桩掉 _claude_turn，测试永不 shell claude。"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "benchmark"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import loop_bench as LB                      # noqa: E402
import validate_workspace as VW              # noqa: E402
import cheatsheet_render as CR               # noqa: E402

FIX = os.path.join(ROOT, "benchmark", "loop_fixtures")
TEACH_IDS = ["m01", "m02", "m03"]
QUIZ_IDS = ["m04", "m05"]
WRONG_ID = "m05"
# 会话脚本的固定轮数：S1 教 3 + 测 2，S2 存续 1（只剩「错题回忆」——「内容复原」探针已删，
# 因为裸智能体重读材料就能答出，不具区分度），S3 小抄 1
EXPECT_TURNS = [("S1", 1), ("S1", 2), ("S1", 3), ("S1", 4), ("S1", 5),
                ("S2", 1), ("S3", 1)]


def make_env(tmp, course_over=None, **cfg_over):
    """把 mini_course 夹具拷进临时目录并写一份 config——夹具本体永不被测试写脏。"""
    shutil.copytree(os.path.join(FIX, "mini_course"), os.path.join(tmp, "mini_course"))
    course = {"name": "mini", "skill_ws": "mini_course/ws",
              "materials": "mini_course/materials", "items": "mini_course/items.jsonl",
              "questions": list(TEACH_IDS), "quiz": list(QUIZ_IDS),
              "wrong_id": WRONG_ID, "wrong_answer": "7 到 11 岁"}
    course.update(course_over or {})
    cfg = {"model": "sonnet", "results_dir": "results", "courses": [course]}
    cfg.update(cfg_over)
    path = os.path.join(tmp, "loop.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    return path


def read_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class MockEndToEnd(unittest.TestCase):
    """--mock 一次全跑（两臂），后续用例只读产物。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="loopbench_")
        cls.cfg = make_env(cls.tmp)
        rc = LB.main(["--config", cls.cfg, "--mock"])
        assert rc == 0, "mock 全跑必须退 0，实得 %r" % rc
        cls.res = os.path.join(cls.tmp, "results")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def rows(self, arm):
        return read_rows(os.path.join(self.res, "mini_%s" % arm, "sessions.jsonl"))

    def test_sessions_jsonl_full_frozen_shape(self):
        for arm in ("bare", "skill"):
            rows = self.rows(arm)
            self.assertEqual([(r["session"], r["turn"]) for r in rows], EXPECT_TURNS, arm)
            for r in rows:
                self.assertEqual(list(r.keys()), list(LB.ROW_KEYS), "冻结行形状被改")
                self.assertEqual(r["course"], "mini")
                self.assertEqual(r["arm"], arm)
                self.assertEqual(r["status"], "ok")
                self.assertIsInstance(r["turn"], int)
                self.assertTrue(isinstance(r["user"], str) and r["user"].strip())
                self.assertTrue(isinstance(r["assistant"], str) and r["assistant"].strip())
                self.assertIsInstance(r["cost_usd"], float)
                if arm == "skill":
                    self.assertIsInstance(r["files_opened"], list, "skill 臂必须带检索足迹")
                    self.assertTrue(all(isinstance(x, str) for x in r["files_opened"]))
                else:
                    self.assertIsNone(r["files_opened"], "bare 臂不开轨迹，必须是 null")

    def test_meta_json_frozen_keys(self):
        for arm in ("bare", "skill"):
            with open(os.path.join(self.res, "mini_%s" % arm, "meta.json"),
                      encoding="utf-8") as f:
                meta = json.load(f)
            for k in ("model", "workspace", "materials", "questions", "wrong_id", "started"):
                self.assertIn(k, meta, "meta 冻结键缺失: %s（%s 臂）" % (k, arm))
            self.assertEqual(meta["model"], "sonnet")
            self.assertEqual(meta["questions"], TEACH_IDS)
            self.assertEqual(meta["wrong_id"], WRONG_ID)
            self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", meta["started"]))
            self.assertTrue(os.path.isdir(meta["workspace"]), "meta.workspace 必须真实存在")
            self.assertTrue(os.path.isdir(meta["materials"]))
            self.assertEqual(meta["mode"], "mock")

    def test_skill_workspace_is_copy_not_source(self):
        """skill 臂在 results 下的**拷贝**上落盘——config.skill_ws 源工作区保持只读干净。"""
        src = os.path.join(self.tmp, "mini_course", "ws")
        self.assertFalse(os.path.exists(os.path.join(src, "notebook")))
        self.assertFalse(os.path.exists(os.path.join(src, "cheatsheet.md")))
        ws = os.path.join(self.res, "mini_skill", "workspace")
        self.assertTrue(os.path.isdir(os.path.join(ws, "notebook")))

    def test_skill_disk_artifacts_complete(self):
        """交付物完备性指标的判分路径：笔记本条目≥教学数、错题本含答错题、小抄 md+2 页 PDF。"""
        ws = os.path.join(self.res, "mini_skill", "workspace")
        nb_entries = []
        for n in (1, 2, 3):
            p = os.path.join(ws, "notebook", "ch%02d.md" % n)
            self.assertTrue(os.path.isfile(p), p)
            nb_entries += re.findall(r"^## \[#([^\]\s]+)\]", open(p, encoding="utf-8").read(),
                                     re.M)
        for qid in TEACH_IDS:
            self.assertIn(qid, nb_entries, "教学题必须有笔记本条目")
        mist = open(os.path.join(ws, "mistakes", "ch02.md"), encoding="utf-8").read()
        self.assertIn("[#%s]" % WRONG_ID, mist, "答错的题必须进错题本")
        self.assertTrue(os.path.isfile(os.path.join(ws, "cheatsheet.md")))
        self.assertEqual(CR.pdf_page_count(os.path.join(ws, "cheatsheet.pdf")), 2,
                         "假 PDF 必须恰好数出 2 个 /Type /Page（页数判分路径）")
        self.assertTrue(os.path.isfile(os.path.join(ws, "notebook", "index.md")))
        self.assertTrue(os.path.isfile(os.path.join(ws, "mistakes", "index.md")))

    def test_skill_workspace_validates_clean(self):
        """跑完的 skill 工作区必须过 validate_workspace（小抄溯源 lint 全绿）——
        判分器直接用它清点交付物。"""
        ws = os.path.join(self.res, "mini_skill", "workspace")
        errors, _warnings, stats = VW.validate(ws)
        self.assertEqual(errors, [], "mock 产物必须 validate 零错误：%s" % errors)
        self.assertGreaterEqual(stats.get("cheatsheet_bullets", 0), 4)

    def test_skill_teach_turns_carry_resolvable_anchors(self):
        """溯源可核验率指标的判分路径：教学轮回答里的 notebook 锚点真实可解析、wiki 文件真实存在。"""
        ws = os.path.join(self.res, "mini_skill", "workspace")
        teach_rows = [r for r in self.rows("skill") if r["session"] == "S1" and r["turn"] <= 3]
        for r in teach_rows:
            links = re.findall(r"\((notebook/[^)#\s]+)#([^)\s]+)\)", r["assistant"])
            self.assertTrue(links, "教学轮必须带 notebook 溯源链接")
            for rel, frag in links:
                target = os.path.join(ws, *rel.split("/"))
                self.assertTrue(os.path.isfile(target), rel)
                self.assertIn(frag, VW._md_anchors(target), "死锚：%s#%s" % (rel, frag))
            wikis = re.findall(r"\((references/wiki/[^)#\s]+)\)", r["assistant"])
            self.assertTrue(wikis, "教学轮必须带 wiki 出处")
            for rel in wikis:
                self.assertTrue(os.path.isfile(os.path.join(ws, *rel.split("/"))), rel)

    def test_bare_leaves_no_disk_artifacts(self):
        mats = os.path.join(self.tmp, "mini_course", "materials")
        self.assertEqual(sorted(os.listdir(mats)), ["lecture01.md"],
                         "bare 臂绝不能写脏材料文件夹")
        self.assertFalse(os.path.exists(os.path.join(self.res, "mini_bare", "workspace")))
        for r in self.rows("bare"):
            self.assertNotIn("notebook/", r["assistant"], "bare 夹具不该伪装出落盘回执")

    def test_s2_persistence_signal_split(self):
        """跨会话存续指标：skill 从错题本准确报出 wrong_id；bare 如实说没有记录。
        （S2 现在只有「错题回忆」一轮——「内容复原」探针已被驱动删除，不再有第二行可测。）"""
        skill_s2 = [r for r in self.rows("skill") if r["session"] == "S2"]
        bare_s2 = [r for r in self.rows("bare") if r["session"] == "S2"]
        self.assertEqual(len(skill_s2), 1)
        self.assertEqual(len(bare_s2), 1)
        self.assertIn(WRONG_ID, skill_s2[0]["assistant"])
        self.assertNotIn(WRONG_ID, bare_s2[0]["assistant"])

    def test_demo_config_loads(self):
        cfg = LB.load_config(os.path.join(FIX, "demo_config.json"))
        self.assertEqual(cfg["courses"][0]["name"], "mini")
        self.assertEqual(cfg["model"], "sonnet")


class Resume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopbench_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = make_env(self.tmp)
        self.sessions = os.path.join(self.tmp, "results", "mini_skill", "sessions.jsonl")

    def test_rerun_skips_done_turns_and_partial_resume_completes(self):
        self.assertEqual(LB.main(["--config", self.cfg, "--mock", "--arm", "skill"]), 0)
        snap = open(self.sessions, encoding="utf-8").read()
        self.assertEqual(len(read_rows(self.sessions)), 7)
        # 整跑重来：全部 7 轮跳过，文件一个字节都不追加
        self.assertEqual(LB.main(["--config", self.cfg, "--mock", "--arm", "skill"]), 0)
        self.assertEqual(open(self.sessions, encoding="utf-8").read(), snap)
        # 截断到前 3 轮（模拟中途崩溃）→ 续跑补齐后 4 轮，且 mock 确定性 = 全文件复原
        lines = snap.splitlines(True)
        with open(self.sessions, "w", encoding="utf-8") as f:
            f.writelines(lines[:3])
        self.assertEqual(LB.main(["--config", self.cfg, "--mock", "--arm", "skill"]), 0)
        rows = read_rows(self.sessions)
        self.assertEqual([(r["session"], r["turn"]) for r in rows], EXPECT_TURNS)
        self.assertEqual(open(self.sessions, encoding="utf-8").read(), snap,
                         "mock 确定性：断点续跑补出的轮次必须与整跑逐字节一致")

    def test_mock_real_mixing_refused(self):
        self.assertEqual(LB.main(["--config", self.cfg, "--mock", "--arm", "skill"]), 0)
        LB._claude_turn, orig = (lambda *a, **k: ("x", 0.0, None, True, "")), LB._claude_turn
        self.addCleanup(setattr, LB, "_claude_turn", orig)
        with self.assertRaises(SystemExit) as cm:      # 同目录 real 续跑 mock 产物 → 拒绝
            LB.main(["--config", self.cfg, "--arm", "skill"])
        self.assertEqual(cm.exception.code, 2)


class QuotaStop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopbench_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = make_env(self.tmp)
        self.sessions = os.path.join(self.tmp, "results", "mini_skill", "sessions.jsonl")
        self._orig = LB._claude_turn
        self.addCleanup(setattr, LB, "_claude_turn", self._orig)

    def test_quota_notice_writes_row_and_exits_7(self):
        notice = "You've hit your usage limit · resets 10:50am (America/Los_Angeles)"
        LB._claude_turn = lambda *a, **k: ("", None, None, False, notice)
        rc = LB.main(["--config", self.cfg, "--arm", "skill"])
        self.assertEqual(rc, 7, "配额停跑必须退 7（外层 runner 靠它退避）")
        rows = read_rows(self.sessions)
        self.assertEqual(len(rows), 1, "撞配额必须立刻停，不能带着配额错往下跑")
        self.assertEqual(rows[0]["status"], "quota_stop")
        self.assertIn("hit your", rows[0]["assistant"])

    def test_resume_after_quota_supersedes_row(self):
        LB._claude_turn = lambda *a, **k: ("", None, None, False,
                                           "You've hit your usage limit · resets 3pm")
        self.assertEqual(LB.main(["--config", self.cfg, "--arm", "skill"]), 7)
        LB._claude_turn = lambda *a, **k: ("答复正文", 0.01, ["references/wiki/ch01.md"], True, "")
        self.assertEqual(LB.main(["--config", self.cfg, "--arm", "skill"]), 0)
        rows = read_rows(self.sessions)
        self.assertEqual(len(rows), 8, "quota 行保留 + 7 轮 ok 追加（消费者按最后一行取）")
        last = {(r["session"], r["turn"]): r for r in rows}
        self.assertEqual(sorted(last), sorted(set(EXPECT_TURNS)))
        self.assertTrue(all(r["status"] == "ok" for r in last.values()))

    def test_infra_error_after_retries_exits_1(self):
        calls = []
        def boom(*a, **k):
            calls.append(1)
            return "", None, None, False, "API Error: boom"
        LB._claude_turn = boom
        LB._sleep, orig_sleep = (lambda s: None), LB._sleep
        self.addCleanup(setattr, LB, "_sleep", orig_sleep)
        rc = LB.main(["--config", self.cfg, "--arm", "skill"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(calls), 3, "瞬时错误重试 3 次")
        rows = read_rows(self.sessions)
        self.assertEqual(rows[-1]["status"], "infra_error")


class PrefixIsolation(unittest.TestCase):
    """S2/S3 = 全新会话：S1 的任何文本都不得混进它们的 prompt（磁盘是唯一通道）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopbench_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = make_env(self.tmp)
        self.prompts = []
        def stub(prompt, model, cwd, arm, timeout=None):
            self.prompts.append(prompt)
            return "ANS-%d" % (len(self.prompts) - 1), 0.001, None, True, ""
        self._orig = LB._claude_turn
        LB._claude_turn = stub
        self.addCleanup(setattr, LB, "_claude_turn", self._orig)
        self.assertEqual(LB.main(["--config", self.cfg, "--arm", "skill"]), 0)
        # 7 轮：S1 T1-5（索引 0-4）+ S2 T1（索引 5，「内容复原」探针已删，S2 只剩一轮）
        # + S3 T1（索引 6）。
        self.assertEqual(len(self.prompts), 7)

    def test_s1_accumulates_within_session(self):
        p1 = self.prompts[1]                            # S1 T2
        self.assertIn("ANS-0", p1, "上一轮助手回答必须进转写前缀")
        self.assertIn(LB.HISTORY_HEADER, p1)
        p4 = self.prompts[4]                            # S1 T5
        for i in range(4):
            self.assertIn("ANS-%d" % i, p4)

    def test_s2_starts_with_empty_prefix(self):
        p5 = self.prompts[5]                            # S2 T1
        self.assertNotIn("ANS-", p5, "S1 助手文本泄漏进 S2 prompt——会话隔离被破坏")
        self.assertNotIn(LB.HISTORY_HEADER, p5)
        self.assertNotIn("请给我讲透这道题", p5, "S1 学生话语也不得泄漏")
        self.assertIn("期末极速备考", p5, "臂前导语必须每轮都在")

    # test_s2_accumulates_only_its_own_turns 已删除：它验证的是 S2 T2（「内容复原」探针）
    # 累积 S2 T1 的前缀，但驱动已把该探针整个删掉——S2 现在只有一轮，没有 T2 可测。
    # S2 T1 不泄漏 S1 内容已由 test_s2_starts_with_empty_prefix 覆盖；S3 不泄漏 S2 内容
    # 由下面 test_s3_starts_fresh_too 覆盖（它断言 p6 里没有任何 "ANS-" 前缀，含 S2 T1 的
    # ANS-5）。

    def test_s3_starts_fresh_too(self):
        p6 = self.prompts[6]                            # S3 T1
        self.assertNotIn("ANS-", p6, "S2 助手文本（含 S2 T1 的 ANS-5）不得泄漏进 S3 prompt")
        self.assertNotIn(LB.HISTORY_HEADER, p6)
        self.assertIn("考前小抄", p6)

    def test_first_turn_has_preamble_and_no_history(self):
        p0 = self.prompts[0]
        self.assertNotIn(LB.HISTORY_HEADER, p0)
        self.assertIn("SKILL.md", p0, "skill 臂前导语必须指向技能定义文件")
        # 新版 SKILL_PREAMBLE：硬性落盘契约（每轮讲解/判分后立刻用 notebook.py 落盘）必须每轮都在。
        self.assertIn("硬性落盘契约", p0, "skill 臂前导语必须包含每轮强制落盘契约")
        self.assertIn("notebook.py", p0, "落盘契约必须点名官方写入路径 notebook.py")
        self.assertIn(os.path.join(LB.ROOT, "scripts"), p0,
                     "落盘契约必须给出 notebook.py 所在的 scripts 目录（make_preamble 的第二个 %s）")


class ConfigErrors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopbench_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _expect2(self, argv):
        with self.assertRaises(SystemExit) as cm:
            LB.main(argv)
        self.assertEqual(cm.exception.code, 2)

    def test_wrong_id_must_be_in_quiz(self):
        cfg = make_env(self.tmp, course_over={"wrong_id": "m01"})
        self._expect2(["--config", cfg, "--mock"])

    def test_teach_must_be_exactly_three(self):
        cfg = make_env(self.tmp, course_over={"questions": ["m01", "m02"]})
        self._expect2(["--config", cfg, "--mock"])

    def test_unknown_course_filter(self):
        cfg = make_env(self.tmp)
        self._expect2(["--config", cfg, "--mock", "--course", "nope"])

    def test_config_id_missing_from_items(self):
        cfg = make_env(self.tmp, course_over={"quiz": ["m04", "m99"], "wrong_id": "m99"})
        self._expect2(["--config", cfg, "--mock"])


class SeedWorkspaceStripping(unittest.TestCase):
    """Finding 4：seed 用的 skill_ws 源若已带旧跑/人工用过的运行时产物（notebook/mistakes/
    cheatsheet/study_state.json），拷贝进 results 工作区后必须先剥净——不能让 S1 还没开始
    就带着"上一轮存续"的证据，让 M4/M5 白捡分。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopbench_strip_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _make_stale_source(self, name="src_ws"):
        src = os.path.join(self.tmp, name)
        shutil.copytree(os.path.join(FIX, "mini_course", "ws"), src)
        os.makedirs(os.path.join(src, "notebook"), exist_ok=True)
        with open(os.path.join(src, "notebook", "ch01.md"), "w", encoding="utf-8") as f:
            f.write("## [#stale] 旧条目\n\n> 精讲 · 2020-01-01 00:00\n\n旧正文。\n\n---\n")
        os.makedirs(os.path.join(src, "mistakes"), exist_ok=True)
        with open(os.path.join(src, "mistakes", "ch01.md"), "w", encoding="utf-8") as f:
            f.write("## [#stale] 旧错题\n\n> 精讲 · 2020-01-01 00:00\n\n旧正文。\n\n---\n")
        with open(os.path.join(src, "cheatsheet.md"), "w", encoding="utf-8") as f:
            f.write("# 旧小抄\n")
        with open(os.path.join(src, "cheatsheet.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 fake old pdf\n")
        with open(os.path.join(src, "study_state.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        return src

    def _course(self, src):
        mats = os.path.join(self.tmp, "mats")
        os.makedirs(mats, exist_ok=True)
        return {"name": "seedtest", "skill_ws": src, "materials": mats, "items": "x"}

    def test_stale_artifacts_stripped_on_first_copy(self):
        src = self._make_stale_source()
        dirp = os.path.join(self.tmp, "results_dir")
        os.makedirs(dirp, exist_ok=True)
        ws = LB.prepare_workspace(self._course(src), "skill", dirp)
        self.assertFalse(os.path.exists(os.path.join(ws, "notebook")),
                         "拷贝后必须剥净源里留下的旧 notebook/")
        self.assertFalse(os.path.exists(os.path.join(ws, "mistakes")),
                         "拷贝后必须剥净源里留下的旧 mistakes/")
        self.assertFalse(os.path.isfile(os.path.join(ws, "cheatsheet.md")))
        self.assertFalse(os.path.isfile(os.path.join(ws, "cheatsheet.pdf")))
        self.assertFalse(os.path.isfile(os.path.join(ws, "study_state.json")))
        # 干净留下的其它文件不受影响
        self.assertTrue(os.path.isfile(os.path.join(ws, "study_plan.md")))
        self.assertTrue(os.path.isdir(os.path.join(ws, "references")))
        # 源工作区本身不被动——绝不原地改写源（run_matrix 复用同一份源目录的前提）
        self.assertTrue(os.path.isdir(os.path.join(src, "notebook")))
        self.assertTrue(os.path.isfile(os.path.join(src, "cheatsheet.md")))

    def test_resume_does_not_re_strip_own_run_artifacts(self):
        """续跑（workspace 已存在）绝不能再剥一次——那时里面的产物是这一轮自己刚写的。"""
        src = self._make_stale_source("src_ws2")
        dirp = os.path.join(self.tmp, "results_dir2")
        os.makedirs(dirp, exist_ok=True)
        ws = LB.prepare_workspace(self._course(src), "skill", dirp)   # 首次拷贝 + 剥净
        os.makedirs(os.path.join(ws, "notebook"), exist_ok=True)
        with open(os.path.join(ws, "notebook", "ch01.md"), "w", encoding="utf-8") as f:
            f.write("## [#this-run] 本轮条目\n\n> 精讲\n\n本轮正文。\n\n---\n")
        ws2 = LB.prepare_workspace(self._course(src), "skill", dirp)   # 续跑：目录已存在，不再剥
        self.assertEqual(ws, ws2)
        self.assertTrue(os.path.isfile(os.path.join(ws2, "notebook", "ch01.md")),
                        "续跑绝不能剥掉这一轮自己刚写的产物")

    def test_end_to_end_mock_run_starts_clean_despite_stale_seed(self):
        """端到端：源 skill_ws 带旧痕迹时，mock 全跑完，笔记本/错题本里必须只有**这一轮**写的
        条目（qid 前缀 m0x），旧的 #stale 条目不能混在里面。"""
        src = self._make_stale_source("src_ws3")
        cfg = make_env(self.tmp, course_over={"skill_ws": src})
        rc = LB.main(["--config", cfg, "--mock", "--arm", "skill"])
        self.assertEqual(rc, 0)
        ws = os.path.join(self.tmp, "results", "mini_skill", "workspace")
        nb = open(os.path.join(ws, "notebook", "ch01.md"), encoding="utf-8").read()
        self.assertNotIn("#stale", nb, "旧条目不能残留在这一轮的笔记本里")
        self.assertIn("#m01", nb, "这一轮真实教学条目必须存在")


class ConfigFingerprintResume(unittest.TestCase):
    """Finding 2：resume 复用 results_dir 时，若 items/materials/skill_ws/wrong_answer 等**实际
    内容或取值**变了（哪怕题目 id 没变），必须拒绝复用旧 sessions.jsonl——那是对着旧 prompt
    写的账本。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopbench_fp_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = make_env(self.tmp)          # 唯一一次 copytree——mini_course 落在 self.tmp 下

    def _run_once(self, cfg=None):
        self.assertEqual(LB.main(["--config", cfg or self.cfg, "--mock", "--arm", "skill"]), 0)

    def _meta(self):
        p = os.path.join(self.tmp, "results", "mini_skill", "meta.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f), p

    def _cfg_with_override(self, **course_over):
        """写一份**新** loop.json、复用 setUp 里已拷好的同一份 mini_course 树（course_over 只改
        字段取值，不再 copytree——避免对同一目标目录二次拷贝报 FileExistsError）。"""
        course = {"name": "mini", "skill_ws": "mini_course/ws",
                  "materials": "mini_course/materials", "items": "mini_course/items.jsonl",
                  "questions": list(TEACH_IDS), "quiz": list(QUIZ_IDS),
                  "wrong_id": WRONG_ID, "wrong_answer": "7 到 11 岁"}
        course.update(course_over)
        cfg = {"model": "sonnet", "results_dir": "results", "courses": [course]}
        path = os.path.join(self.tmp, "loop_override.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        return path

    def test_meta_records_config_fingerprint(self):
        self._run_once()
        meta, _ = self._meta()
        self.assertIn("config_fingerprint", meta)
        self.assertTrue(meta["config_fingerprint"])

    def test_same_config_resumes_cleanly(self):
        self._run_once()
        self.assertEqual(LB.main(["--config", self.cfg, "--mock", "--arm", "skill"]), 0)

    def test_changing_wrong_answer_text_refused_on_resume(self):
        self._run_once()
        cfg2 = self._cfg_with_override(wrong_answer="完全不同的错误答案文案")
        with self.assertRaises(SystemExit) as cm:
            LB.main(["--config", cfg2, "--mock", "--arm", "skill"])
        self.assertEqual(cm.exception.code, 2)

    def test_changing_materials_content_in_place_refused_on_resume(self):
        """materials **路径没变**，但内容被就地改写——指纹必须靠内容哈希发现，不能只比路径。"""
        self._run_once()
        mat_file = os.path.join(self.tmp, "mini_course", "materials", "lecture01.md")
        with open(mat_file, "a", encoding="utf-8") as f:
            f.write("\n新增内容——课件被重新生成过。\n")
        with self.assertRaises(SystemExit) as cm:
            LB.main(["--config", self.cfg, "--mock", "--arm", "skill"])
        self.assertEqual(cm.exception.code, 2)

    def test_changing_skill_ws_content_in_place_refused_on_resume(self):
        """skill_ws **路径没变**，但内容被就地重建——同上，必须靠内容哈希发现。"""
        self._run_once()
        ws_file = os.path.join(self.tmp, "mini_course", "ws", "study_plan.md")
        with open(ws_file, "a", encoding="utf-8") as f:
            f.write("\n新增阶段——工作区被重新生成过。\n")
        with self.assertRaises(SystemExit) as cm:
            LB.main(["--config", self.cfg, "--mock", "--arm", "skill"])
        self.assertEqual(cm.exception.code, 2)

    def test_legacy_meta_without_fingerprint_refused(self):
        """本次修复前生成的旧 meta.json（没有 config_fingerprint 键）——无法核对一致性，拒绝续跑。"""
        self._run_once()
        meta, meta_path = self._meta()
        del meta["config_fingerprint"]
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        with self.assertRaises(SystemExit) as cm:
            LB.main(["--config", self.cfg, "--mock", "--arm", "skill"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
