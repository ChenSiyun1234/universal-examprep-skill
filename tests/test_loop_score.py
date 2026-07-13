# -*- coding: utf-8 -*-
"""benchmark/loop_score.py —— loop benchmark 确定性判分器的合成夹具测试。

覆盖：M1 溯源（wiki 链接 / notebook 死锚 vs 真锚 / zh+en 来源块 / 缺文件 / 只数教学回合）、
M4 存续（wrong_id 命中与否 / gist 兜底 / 关键词覆盖阈值双向 / 缺 config 不可评+告警）、
M5 交付物 checklist 每项翻转 + html-degraded 跳过、M6 成本 null 安全 + quota 计数、
缺臂告警 + gap 记 null。纯标准库、零网络、零 LLM。"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "benchmark")
sys.path.insert(0, BENCH)
import loop_score as LS  # noqa: E402


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _entry_block(eid, title):
    return "## [#%s] %s\n\n> 精讲 · 2026-07-12 10:00\n\n%s 的正文。\n\n---\n" % (eid, title, title)


def make_pdf(path, pages):
    """chromium 风格的 /Type /Page 计数夹具（/Type /Pages 树节点不算页）。"""
    data = b"%PDF-1.4\n<< /Type /Pages /Kids [] >>\n" + b"<< /Type /Page >>\n" * pages
    with open(path, "wb") as f:
        f.write(data)


def make_ws(base, n_entries=3, dead_anchor=False, mistake_ids=("q2",), cheatsheet=True,
            pdf_pages=2, with_pdf=True, name="ws"):
    """S1-S3 跑完后的 skill 工作区夹具：validate_workspace 0 错误（默认参数下）。"""
    ws = os.path.join(base, name)
    _w(os.path.join(ws, "references", "wiki", "ch01.md"), "# 第一章\n\n内容。\n")
    _w(os.path.join(ws, "references", "quiz_bank.json"), "[]")
    _w(os.path.join(ws, "study_plan.md"), "# 复习计划\n")
    _w(os.path.join(ws, "study_progress.md"), "# 进度\n\n疑难点：无\n")
    ids_titles = [("q%d" % i, "概念%d" % i) for i in range(1, n_entries + 1)]
    _w(os.path.join(ws, "notebook", "ch01.md"),
       "\n".join(_entry_block(e, t) for e, t in ids_titles))
    links = []
    for j, (e, t) in enumerate(ids_titles):
        anchor = "不存在的锚" if (dead_anchor and j == 0) else LS._nb.entry_anchor(e, t)
        links.append("- [%s](ch01.md#%s)" % (t, anchor))
    _w(os.path.join(ws, "notebook", "index.md"),
       "# 学习笔记本\n\n## 第 1 章\n\n" + "\n".join(links) + "\n")
    if mistake_ids:
        _w(os.path.join(ws, "mistakes", "ch01.md"),
           "\n".join(_entry_block(e, "错题 " + e) for e in mistake_ids))
    if cheatsheet:
        _w(os.path.join(ws, "cheatsheet.md"),
           "# 小抄\n\n- 要点一 [笔记](notebook/ch01.md#%s)\n" % LS._nb.entry_anchor("q1", "概念1"))
    if with_pdf:
        make_pdf(os.path.join(ws, "cheatsheet.pdf"), pdf_pages)
    return ws


def make_bare_ws(base):
    d = os.path.join(base, "bare_ws")
    _w(os.path.join(d, "lecture01.md"), "# 讲义\n")
    return d


def row(session, turn, user, assistant, status="ok", cost=None, course="c1", arm="skill"):
    return {"course": course, "arm": arm, "session": session, "turn": turn, "user": user,
            "assistant": assistant, "cost_usd": cost, "files_opened": None, "status": status}


def s1_rows(assistants, course="c1", arm="skill"):
    return [row("S1", i, "教我第%d题" % i, a, course=course, arm=arm)
            for i, a in enumerate(assistants, 1)]


def make_meta(ws, materials="", wrong_id="q2", questions=("q1", "q2", "q3"), **extra):
    m = {"model": "sonnet", "workspace": ws, "materials": materials,
         "questions": list(questions), "wrong_id": wrong_id, "started": "2026-07-12T00:00:00"}
    m.update(extra)
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loopscore_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.results = os.path.join(self.tmp, "results")
        os.makedirs(self.results)

    def write_run(self, course, arm, rows, meta):
        d = os.path.join(self.results, "%s_%s" % (course, arm))
        os.makedirs(d)
        with open(os.path.join(d, "sessions.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

    def run_scorer(self, config=None):
        out = os.path.join(self.tmp, "summary_loop.json")
        argv = ["--results", self.results, "--out", out]
        if config is not None:
            cfg = os.path.join(self.tmp, "cfg.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False)
            argv += ["--config", cfg]
        err, dev = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(dev):
            rc = LS.main(argv)
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as f:
            return json.load(f)


# ---------------- M1 溯源可核验率 ----------------

class M1Provenance(Base):
    def test_wiki_link_verified_counts_turn(self):
        ws = make_ws(self.tmp)
        rows = s1_rows(["结论见 [第一章](references/wiki/ch01.md)。", "无来源答复。", "也无来源。"])
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual((r["m1_verified"], r["m1_claims"]), (1, 3))
        self.assertAlmostEqual(r["m1"], 1 / 3, places=4)

    def test_notebook_anchor_verified_vs_dead(self):
        ws = make_ws(self.tmp)
        good = LS._nb.entry_anchor("q1", "概念1")
        rows = s1_rows(["详见 [笔记](notebook/ch01.md#%s)。" % good,          # 真锚 → 过
                        "详见 [笔记](notebook/ch01.md#这个锚不存在)。",         # 死锚 → 不过
                        "见 [wiki](references/wiki/ch01.md#任意锚)。"])       # wiki 文件级 → 过
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual((r["m1_verified"], r["m1_claims"]), (2, 3))
        self.assertAlmostEqual(r["m1"], 2 / 3, places=4)

    def test_zh_source_block_resolves_in_materials(self):
        ws = make_ws(self.tmp)
        mats = os.path.join(self.tmp, "mats")
        _w(os.path.join(mats, "lecture01.md"), "# 讲义\n")
        rows = s1_rows(["自然选择解释适应性。\n题目来源：lecture01.md 第 3 页（lecture_quiz）｜"
                        "答案来源：lecture01.md 第 5 页｜🟢 来自资料"])
        self.write_run("c1", "skill", rows, make_meta(ws, materials=mats))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual((r["m1_verified"], r["m1_claims"]), (1, 1))
        self.assertEqual(r["m1"], 1.0)

    def test_en_source_block_resolves_in_workspace(self):
        ws = make_ws(self.tmp)
        with open(os.path.join(ws, "notes.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 fake")
        rows = s1_rows(["Adaptation follows selection.\n"
                        "Question source: notes.pdf p.3 | Answer source: notes.pdf | grounded"])
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual(r["m1"], 1.0)

    def test_source_block_with_missing_file_fails(self):
        ws = make_ws(self.tmp)
        rows = s1_rows(["题目来源：ghost.pdf 第 1 页｜答案来源：ghost.pdf｜🟢 来自资料"])
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual((r["m1"], r["m1_verified"], r["m1_claims"]), (0.0, 0, 1))

    def test_only_first_three_turns_are_claims(self):
        ws = make_ws(self.tmp)
        rows = s1_rows(["无来源一。", "无来源二。", "无来源三。"])
        rows.append(row("S1", 4, "测验第 1 题", "带来源 [wiki](references/wiki/ch01.md)。"))
        rows.append(row("S1", 5, "测验第 2 题", "也带来源 [wiki](references/wiki/ch01.md)。"))
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual((r["m1"], r["m1_claims"]), (0.0, 3))   # 测验回合不进 M1 分母/分子


# ---------------- M4 跨会话存续率 ----------------

KWS = {"c1": {"keywords": {"q1": ["自然选择", "适应", "环境"]}}}   # 无 gist（q2）——探针 A 默认不可评


class M4Persistence(Base):
    def _s2(self, a_ans, b_ans, course="c1", arm="skill"):
        return [row("S2", 1, "上次我错了哪几道？", a_ans, course=course, arm=arm),
                row("S2", 2, "把上次讲过的 q1 结论再给我看一眼", b_ans, course=course, arm=arm)]

    def test_wrong_id_probe_pass_and_fail_with_gap(self):
        # skill 是真实内容回忆（gist 关键词覆盖 100%），bare 是诚实的"不记得"（0% 覆盖）——
        # 用真实回忆信号而非单纯报出题号来区分两臂（Finding 1：正向内容信号，不是 id 提及）。
        ws, bws = make_ws(self.tmp), make_bare_ws(self.tmp)
        cfg = {"c1": {"keywords": {"q1": ["自然选择", "适应", "环境"]},
                      "gist": {"q2": ["米尔格拉姆", "服从"]}}}
        self.write_run("c1", "skill", self._s2(
            "你上次错的是 q2，那道关于米尔格拉姆服从实验的题（错题本 mistakes/ch01.md 有完整条目）。",
            "q1 结论：自然选择塑造适应，环境压力是筛选器。"), make_meta(ws))
        self.write_run("c1", "bare", self._s2(
            "抱歉，我没有上一次会话的记录。",
            "我不记得之前讲过什么。", arm="bare"), make_meta(bws))
        s = self.run_scorer(config=cfg)["c1"]
        self.assertEqual(s["skill"]["m4"], 1.0)
        self.assertEqual(s["bare"]["m4"], 0.0)
        self.assertEqual(s["gap"]["m4"], 1.0)
        self.assertIsNone(s["gap"]["m1"])                       # 无 S1 回合 → m1 null → gap null

    def test_wrong_id_gist_coverage_passes_without_naming_id(self):
        # 探针 A 只认 gist 内容覆盖——回答全程没提 "q2" 这个 token，纯靠内容覆盖也能过。
        ws = make_ws(self.tmp)
        self.write_run("c1", "skill", self._s2(
            "上次错的是关于米尔格拉姆服从实验的那道题。", "（略）"), make_meta(ws))
        cfg = {"c1": {"gist": {"q2": ["米尔格拉姆", "服从"]}}}   # 无 keywords → 探针 B 不可评
        r = self.run_scorer(config=cfg)["c1"]["skill"]
        self.assertEqual((r["m4"], r["m4_passed"], r["m4_probes"], r["m4_unscored"]),
                         (1.0, 1, 1, 1))

    def test_naming_wrong_id_without_content_recall_does_not_pass(self):
        """Finding 1 回归钉：只报出/提到 wrong_id 这个 token（哪怕报对了、哪怕报错成 q20）不是
        充分条件——config 明明给了 gist 关键词，但回答里一个都没覆盖到，必须判不过。防止
        「说不清是不是 q5，反正没有错题本」这类实为弃答的回答被误判为存续成功（曾经的
        `_id_hit` 让这类回答假通过）。"""
        ws = make_ws(self.tmp)
        cfg = {"c1": {"gist": {"q2": ["米尔格拉姆", "服从"]}}}
        self.write_run("c1", "skill", self._s2(
            "你错的是 q20 那道，不太确定具体是哪一题、错在哪。", "（略）"), make_meta(ws))
        r = self.run_scorer(config=cfg)["c1"]["skill"]
        self.assertEqual((r["m4"], r["m4_passed"], r["m4_probes"]), (0.0, 0, 1))

    def test_missing_gist_is_unscored_not_defaulted(self):
        """Finding 1：config 没给该 wrong_id 的 gist 关键词——不硬判 0 也不假装满分，必须
        unscored + 大声告警（同探针 B 缺 keywords 的既有处理姿势）。"""
        ws = make_ws(self.tmp)
        cfg = {"c1": {"keywords": {"q1": ["自然选择", "适应", "环境"]}}}   # 有 keywords，无 gist
        self.write_run("c1", "skill", self._s2(
            "你错的是 q2。", "结论：自然选择带来适应，环境是关键。"), make_meta(ws))
        summary = self.run_scorer(config=cfg)
        r = summary["c1"]["skill"]
        # 探针 A（无 gist）不可评；探针 B（有 keywords，3/3 覆盖）过 → m4 只算探针 B
        self.assertEqual((r["m4"], r["m4_probes"], r["m4_unscored"]), (1.0, 1, 1))
        self.assertTrue(any("gist" in w for w in summary["_warnings"]))

    def test_keyword_coverage_threshold_both_directions(self):
        # KWS 没给 q2 的 gist——探针 A 两臂都不可评，阈值行为只由探针 B（keywords）单独体现。
        ws, bws = make_ws(self.tmp), make_bare_ws(self.tmp)
        self.write_run("c1", "skill", self._s2(
            "你错的是 q2。", "结论：自然选择带来适应。"), make_meta(ws))          # 2/3 ≥ 60% → 过
        self.write_run("c1", "bare", self._s2(
            "你错的是 q2。", "只记得和适应有关。", arm="bare"), make_meta(bws))   # 1/3 < 60% → 不过
        s = self.run_scorer(config=KWS)["c1"]
        self.assertEqual((s["skill"]["m4"], s["skill"]["m4_probes"], s["skill"]["m4_unscored"]),
                         (1.0, 1, 1))
        self.assertEqual((s["bare"]["m4"], s["bare"]["m4_probes"], s["bare"]["m4_unscored"]),
                         (0.0, 1, 1))

    def test_missing_keywords_is_unscored_with_loud_warning(self):
        ws = make_ws(self.tmp)
        cfg = {"c1": {"gist": {"q2": ["米尔格拉姆", "服从"]}}}   # 有 gist（探针 A 可评），无 keywords
        self.write_run("c1", "skill", self._s2(
            "你错的是 q2，那道米尔格拉姆服从实验题。", "（无所谓）"), make_meta(ws))
        summary = self.run_scorer(config=cfg)                    # 无 keywords
        r = summary["c1"]["skill"]
        self.assertEqual((r["m4"], r["m4_probes"], r["m4_unscored"]), (1.0, 1, 1))
        self.assertTrue(any("keywords" in w for w in summary["_warnings"]))

    def test_single_probe_protocol_does_not_warn_about_missing_probe_b(self):
        """Finding 5 回归钉：驱动器现在只发探针 A（错题回忆）一轮——S2 探针 B 缺席是单探针
        协议设计如此，不该对每一次完整跑都告警"缺「再给我看一眼」探针回合"，污染 _warnings
        让本来完整的跑看着像没跑完。"""
        ws = make_ws(self.tmp)
        cfg = {"c1": {"gist": {"q2": ["米尔格拉姆", "服从"]}}}
        rows = [row("S2", 1, "上次我错了哪几道？", "你错的是 q2，那道米尔格拉姆服从实验题。")]
        self.write_run("c1", "skill", rows, make_meta(ws))
        summary = self.run_scorer(config=cfg)
        self.assertFalse(any("再给我看一眼" in w for w in summary["_warnings"]),
                         "单探针协议下缺探针 B 不该告警：%s" % summary["_warnings"])
        r = summary["c1"]["skill"]
        self.assertEqual((r["m4"], r["m4_probes"]), (1.0, 1))


# ---------------- M5 交付物完备性 ----------------

class M5Deliverables(Base):
    def _run_one(self, ws, meta=None, course="c1"):
        self.write_run(course, "skill",
                       s1_rows(["无来源。"], course=course), meta or make_meta(ws))
        return self.run_scorer()[course]["skill"]

    def test_all_items_pass(self):
        r = self._run_one(make_ws(self.tmp))
        self.assertEqual(r["m5_checklist"],
                         {"notebook_index": 1, "mistakes_entry": 1,
                          "cheatsheet_md": 1, "cheatsheet_pdf": 1})
        self.assertEqual(r["m5"], 1.0)

    def test_notebook_index_flips_on_few_entries_and_dead_anchor(self):
        ws_few = make_ws(self.tmp, n_entries=2, name="ws_few")
        ws_dead = make_ws(self.tmp, dead_anchor=True, name="ws_dead")
        self.write_run("c1", "skill", s1_rows(["无。"]), make_meta(ws_few))
        self.write_run("c2", "skill", s1_rows(["无。"], course="c2"), make_meta(ws_dead))
        s = self.run_scorer()
        self.assertEqual(s["c1"]["skill"]["m5_checklist"]["notebook_index"], 0)   # 条目 <3
        self.assertEqual(s["c2"]["skill"]["m5_checklist"]["notebook_index"], 0)   # 目录死锚

    def test_mistakes_cheatsheet_and_pdf_flip(self):
        # 新语义：mistakes_entry 只问「错题本非空」——故用 EMPTY 错题本才让该项翻 0
        ws = make_ws(self.tmp, mistake_ids=(), cheatsheet=False, pdf_pages=3)
        r = self._run_one(ws)                     # 错题本空；无 md；PDF 3 页≠2
        self.assertEqual(r["m5_checklist"],
                         {"notebook_index": 1, "mistakes_entry": 0,
                          "cheatsheet_md": 0, "cheatsheet_pdf": 0})
        self.assertEqual(r["m5"], 0.25)

    def test_mistakes_entry_ok_on_any_semantic_id(self):
        # 技能按语义命名错题条目（非 benchmark 内部 wrong_id）——错题本有任一真实条目即记 1
        ws = make_ws(self.tmp, mistake_ids=("toxo-cat-弓形虫",))   # wrong_id=q2，语义 id 不同
        r = self._run_one(ws)
        self.assertEqual(r["m5_checklist"]["mistakes_entry"], 1)

    def test_cheatsheet_md_flips_on_validate_errors(self):
        ws = make_ws(self.tmp)
        _w(os.path.join(ws, "cheatsheet.md"), "# 小抄\n\n- 无溯源链接的裸要点\n")   # lint 必红
        r = self._run_one(ws)
        self.assertEqual(r["m5_checklist"]["cheatsheet_md"], 0)

    def test_pdf_skipped_not_failed_when_html_degraded(self):
        ws = make_ws(self.tmp, with_pdf=False)
        r = self._run_one(ws, meta=make_meta(ws, mock="html-degraded"))
        self.assertIsNone(r["m5_checklist"]["cheatsheet_pdf"])   # skip，不是 0
        self.assertEqual(r["m5"], 1.0)                           # 均值只除已评 3 项


# ---------------- M6 成本 + 缺臂告警 ----------------

class M6CostAndWarnings(Base):
    def test_cost_null_safe_and_quota_counted(self):
        ws = make_ws(self.tmp)
        rows = [row("S1", 1, "教", "答", cost=0.1),
                row("S1", 2, "教", "答", cost=None),
                row("S2", 1, "问", "答", cost=0.2),
                row("S3", 1, "小抄", "", cost=None, status="quota_stop")]
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertAlmostEqual(r["m6_total_usd"], 0.3, places=6)
        self.assertAlmostEqual(r["m6_per_turn"], 0.15, places=6)
        self.assertEqual((r["n_turns"], r["n_quota_stops"]), (4, 1))

    def test_missing_arm_warns_and_gap_is_null(self):
        ws = make_ws(self.tmp)
        self.write_run("c1", "skill", s1_rows(["无。"]), make_meta(ws))
        summary = self.run_scorer()
        self.assertNotIn("bare", summary["c1"])
        self.assertTrue(all(v is None for v in summary["c1"]["gap"].values()))
        self.assertTrue(any("缺 bare 臂" in w for w in summary["_warnings"]))


# ---------------- 断点续跑去重（Finding 2） ----------------

class ResumeDedup(Base):
    """驱动器断点续跑对失败行（quota_stop/infra_error）保留原位、成功后**追加**新的 ok 行——
    冻结转写接口写明"消费者按 (session, turn) 取最后一行"。判分器之前直接对原始行打分，被
    resume 覆盖的失败行会和取代它的 ok 行一起被计入 n_quota_stops/n_turns/成本，重复计数。"""

    def test_superseded_quota_stop_row_not_double_counted(self):
        ws = make_ws(self.tmp)
        rows = [
            row("S1", 1, "教我第1题", "无来源一。", cost=0.01),
            row("S1", 2, "教我第2题", "无来源二。", cost=0.01),
            # 撞配额那次的占位行——保留原位，cost 非零以确认它不会被重复求和
            row("S1", 3, "教我第3题", "You've hit your usage limit · resets 10am",
                status="quota_stop", cost=0.5),
            # resume 成功后追加的真行——冻结接口的"最后一行"
            row("S1", 3, "教我第3题",
                "真实讲解见 [wiki](references/wiki/ch01.md)。", status="ok", cost=0.02),
        ]
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual(r["n_turns"], 3, "按 (session, turn) 去重后只剩 3 个回合")
        self.assertEqual(r["n_quota_stops"], 0, "被 resume 覆盖的 quota_stop 行不能再计入")
        self.assertAlmostEqual(r["m6_total_usd"], 0.04, places=6,
                               msg="被超越行的 0.5 成本不能重复求和进总成本")
        # M1：turn3 只剩 ok 版本，且它带 wiki 出处 → 计入且判过；quota_stop 的占位文本不参与判分
        self.assertEqual((r["m1_verified"], r["m1_claims"]), (1, 3))
        self.assertAlmostEqual(r["m1"], 1 / 3, places=4)

    def test_superseded_infra_error_row_not_double_counted(self):
        # infra_error 同样是「保留原位 + resume 后追加 ok 行」的失败态，去重口径一致
        ws = make_ws(self.tmp)
        rows = [
            row("S1", 1, "教我第1题", "API Error: boom", status="infra_error", cost=None),
            row("S1", 1, "教我第1题", "无来源一。", status="ok", cost=0.03),
        ]
        self.write_run("c1", "skill", rows, make_meta(ws))
        r = self.run_scorer()["c1"]["skill"]
        self.assertEqual(r["n_turns"], 1)
        self.assertAlmostEqual(r["m6_total_usd"], 0.03, places=6)
        self.assertEqual(r["m1_claims"], 1, "去重后只有 1 个可评教学回合（ok 版本）")


class PortableResults(Base):
    """Codex r4 P2：被判分的 skill 工作区恒在 <arm_dir>/workspace。结果目录被拷/移走后
    meta.workspace 的绝对路径会失效，判分器必须优先用就地的 <arm_dir>/workspace，M1/M5 仍可评。"""

    def test_moved_results_dir_scores_via_local_workspace(self):
        arm_dir = os.path.join(self.results, "c1_skill")
        os.makedirs(arm_dir)
        make_ws(arm_dir, name="workspace")                 # 工作区就地在 <arm_dir>/workspace
        rows = s1_rows(["结论见 [第一章](references/wiki/ch01.md)。", "无来源。", "无来源。"])
        with open(os.path.join(arm_dir, "sessions.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        stale_abs = os.path.join(self.tmp, "ORIGINAL_gone", "workspace")   # 跑时的绝对路径，将失效
        with open(os.path.join(arm_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(make_meta(stale_abs), f, ensure_ascii=False)
        moved = os.path.join(self.tmp, "moved_results")    # 整个 results 目录搬走
        shutil.move(self.results, moved)
        out = os.path.join(self.tmp, "summary_loop.json")
        err, dev = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(dev):
            rc = LS.main(["--results", moved, "--out", out])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as f:
            summary = json.load(f)
        r = summary["c1"]["skill"]
        self.assertIsNotNone(r["m5"], "搬走后应经 <arm_dir>/workspace 兜底，M5 不该是 null")
        self.assertIsNotNone(r["m1"], "M1 同理经就地工作区解析，不该 null")
        self.assertFalse(any("解析不到目录" in w for w in summary["_warnings"]),
                         "就地工作区在场，不该告警解析不到：%s" % summary["_warnings"])


if __name__ == "__main__":
    unittest.main()
