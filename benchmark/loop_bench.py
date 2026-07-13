#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Loop-benchmark SESSION DRIVER（备考全流程 v4 设计冻结稿 §协议的执行器）。

把「一个学生备考三段会话」确定性地演出来，bare（通用助手+原始材料）与 skill（v4 工作区+
技能包）两臂同模型、同题目、同会话脚本：

  S1 教学会话：教 3 道金标题 → 测 2 道（模拟学生把 wrong_id 那题答错——错误答案文案来自 config）
  S2 存续会话：**全新上下文**（转写前缀清空，只有磁盘工作区还在）→「上次错了哪几道」
              「把上次讲过的 <q1> 结论再给我看一眼」
  S3 小抄会话：同样全新上下文 →「给我 2 页的考前小抄 PDF」

多轮 = 逐轮 `claude -p`：每轮 prompt = 臂前导语 + 此前各轮（学生话语, 助手回答）的转写前缀 +
新学生话语。会话边界即前缀清空边界——S2/S3 里唯一能带回 S1 事实的通道是磁盘。

── 冻结的转写接口（判分器 loop_score.py 与本驱动共同依赖，勿改形状）──────────────
<results_dir>/<course>_<arm>/sessions.jsonl —— 每轮一行：
  {"course": str, "arm": "bare"|"skill", "session": "S1"|"S2"|"S3", "turn": int,
   "user": str, "assistant": str, "cost_usd": float|null, "files_opened": [str]|null,
   "status": "ok"|"infra_error"|"quota_stop"}
<results_dir>/<course>_<arm>/meta.json ——
  {"model", "workspace", "materials", "questions": [教学题 id], "wrong_id", "started", …附加键}
skill 臂的工作区（meta.workspace 指向处）在跑完后**本身就是评分产物**——S1–S3 真实改写它。
──────────────────────────────────────────────────────────────────────────────

工程约定：
· skill 臂在 <results_dir>/<course>_skill/workspace 上工作——**开跑时从 config.skill_ws 拷贝**，
  拷贝后立刻剥净 notebook/mistakes/cheatsheet.md/cheatsheet.pdf/study_state.json 等运行时产物
  （若源 skill_ws 已带旧跑/人工用过的痕迹，照抄会让 M4/M5 白捡分——见 Finding 4），并把
  study_progress.md 重渲染回空错题/疑难点/阶段 1 的干净视图（study_state.json 一删，它就是技能
  契约唯一的 fallback 读取源——留着旧痕迹是同一类白捡分，见 Finding 1）。
  绝不原地改写源工作区：psyc110_full 等还被 run_matrix 复用，其 _dir_hash 配置指纹一变，
  矩阵臂就全部拒绝续跑。bare 臂 cwd=materials（只读工具，材料不会被写脏）。
· 断点续跑：sessions.jsonl 里 status=ok 的 (session, turn) 直接跳过（回答用于重建前缀）；
  非 ok 行视作未完成，重跑后**追加**新行——消费者按 (session, turn) 取**最后一行**。resume 时
  额外核对 meta.config_fingerprint（items 内容+materials/skill_ws 目录内容+wrong_id/
  wrong_answer/questions/quiz，skill 臂再加 skill_md **内容**——每轮前导语都嵌入它、要求模型
  先读，技能定义变了不能被当"配置没变"续跑，见 Finding 3）与当前 config 一致——变了（哪怕题目
  id 没变）就拒绝复用，防止拿新 prompt 续跑对着旧账本打分（Finding 2）。
· 配额感知：回答是限额通知（复用 run_matrix._is_quota_notice + gen.classify 的 hard 词表）→
  落一行 status=quota_stop 并**干净地停**（退出码 7，供外层 runner 退避重试）；
  瞬时错误重试 3 次仍失败 → status=infra_error，退出码 1（转写出现空洞，后续轮的前缀
  就不完整，绝不带着洞往下跑）。退出码：0 完成 · 1 infra · 2 用法/config · 7 配额。
· --mock：不碰 claude——canned 回答来自 benchmark/loop_fixtures/（string.Template 夹具）。
  skill 臂夹具带溯源块/锚点/笔记本回执，并**真实创建**磁盘产物（notebook/ mistakes/
  cheatsheet.md + 恰含 2 个 /Type /Page 对象的假 PDF——scripts/cheatsheet_render.pdf_page_count
  数得出来）；bare 臂夹具流畅但无出处、零磁盘产物。mock 端到端打通全部六项指标的判分路径，
  但**不测量任何东西**（与 run_matrix --mock 同一诚实姿态）。
· 为什么不直接用 gen.run_claude 发真轮次：gen 的 skill=True 只放行 Read/Glob/Grep——单题问答
  够用，但 loop 的 skill 臂必须能真落盘（notebook/小抄/PDF 需要 Write/Edit/Bash），否则
  「工作区就是评分产物」无从谈起。流式轨迹解析（files_opened）完全复用 gen.parse_stream_events，
  配额识别复用 run_matrix._is_quota_notice / gen.classify——没有第二套实现。

    python benchmark/loop_bench.py --config loop.json            # 真跑（可断点续跑）
    python benchmark/loop_bench.py --config loop.json --mock     # 离线全管线（零成本）
    python benchmark/loop_bench.py --config ... --course psyc --arm skill
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import string
import subprocess
import sys
import time

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gen                                  # noqa: E402  parse_stream_events / classify 复用
import run_matrix as RM                     # noqa: E402  _is_quota_notice / _file_hash 复用（唯一实现）
import notebook as NB                       # noqa: E402  entry_anchor + 官方落盘路径（mock 用）
import update_progress as UP                # noqa: E402  render_md/default_state（Finding 1 清空用）

FIXTURES = os.path.join(HERE, "loop_fixtures")
ARMS = ("bare", "skill")
SESSION_NAMES = ("S1", "S2", "S3")
ROW_KEYS = ("course", "arm", "session", "turn", "user", "assistant",
            "cost_usd", "files_opened", "status")

BARE_TOOLS = ("Read", "Glob", "Grep")                       # 设计冻结稿：bare 臂只读材料
SKILL_TOOLS = ("Read", "Glob", "Grep", "Write", "Edit", "Bash")   # skill 臂必须能落盘
TURN_TIMEOUT = 1500
CHEATSHEET_PAGES = 2
MOCK_COST = {"bare": 0.05, "skill": 0.02}   # 占位数——只为打通「省上下文省钱」的求和路径
_SAFE_NAME = re.compile(r"^[\w.\-]+$")      # 课程名进目录名 <course>_<arm>，必须目录安全
_sleep = time.sleep                          # 测试可替换的退避 seam

# ---- 学生话语（两臂逐字相同——臂间唯一差异是前导语与工作目录）----
TEACH_USER = "请给我讲透这道题：%s"
QUIZ_USER = "考我这道题并当场判分。\n题目：%s\n我的答案：%s"
S2_USER_MISTAKES = "上次复习我答错了哪几道题？错在哪里？"
S2_USER_CONTENT = "把上次讲过的「%s」这道题的结论要点再给我看一眼。"
S3_USER = "请给我一份 %d 页的考前小抄 PDF（A4，恰好 %d 页）。"

BARE_PREAMBLE = ("你是通用学习助手。当前工作目录就是这门课的原始课程材料文件夹（%s），"
                 "你可以用 Read/Glob/Grep 工具按需查阅材料。请具体、直接地帮学生备考。")
SKILL_PREAMBLE = ("请严格按照已安装的「期末极速备考」技能包工作（技能定义文件：%s——先读它，"
                  "并遵循其中的流程与官方工具契约）。当前工作目录是该技能的备考工作区"
                  "（references/wiki/ 知识库、study_plan.md、study_progress.md 都在这里）。\n"
                  "**硬性落盘契约（每一轮都必须做，做不到即视为未完成本轮）**：\n"
                  "1) 讲解题目时，答案要带 v4 来源块一行：`题目来源：… ｜ 答案来源：… ｜ 🟢 来自资料`；\n"
                  "2) 讲完/判完**每一道题后，立刻**用 Bash 运行官方唯一写入路径把这次讲解/判分落盘"
                  "（正文经 STDIN；notebook.py 就在 %s）：\n"
                  "   `echo \"<本次完整讲解正文>\" | python \"<上面这个目录>/notebook.py\" "
                  "--workspace . add-entry --chapter <章号> --type walkthrough|feedback "
                  "--id <题号> --title <一句话题目>`；判分错题再加 `--mistake`；\n"
                  "3) 回复学生时给「摘要 + notebook/chNN.md#锚点」链接（锚点用命令回执打印的实际锚）。\n"
                  "notebook/、mistakes/、cheatsheet.md、cheatsheet.pdf 都必须是本工作区里真实存在的文件——"
                  "只在聊天里讲、不落盘，等于没做。")
HISTORY_HEADER = "【本会话此前的对话转写】"


def _die(msg, code=2):
    sys.stderr.write("loop_bench: " + msg + "\n")
    raise SystemExit(code)


# ---------------- config ----------------

def _resolve(base_dir, p):
    """config 里的相对路径按 config 文件所在目录解析（run_matrix 同款约定）。"""
    if not isinstance(p, str) or not p or os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(base_dir, p))


def load_config(path):
    if not os.path.isfile(path):
        _die("找不到 config: %s" % path)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except ValueError as e:
        _die("config 不是合法 JSON: %s" % e)
    if not isinstance(cfg, dict):
        _die("config 顶层必须是对象")
    courses = cfg.get("courses")
    if not isinstance(courses, list) or not courses:
        _die("config.courses 必须是非空数组（每门课含 name/skill_ws/materials/items/"
             "questions/quiz/wrong_id/wrong_answer）")
    base = os.path.dirname(os.path.abspath(path))
    seen = set()
    for c in courses:
        if not isinstance(c, dict):
            _die("courses 的每一项必须是对象")
        name = c.get("name")
        if not (isinstance(name, str) and _SAFE_NAME.match(name)):
            _die("课程 name 必须是目录安全的非空字符串（字母数字._-），当前 %r" % (name,))
        if name in seen:
            _die("课程 name 重复: %s" % name)
        seen.add(name)
        for k, check, what in (("skill_ws", os.path.isdir, "目录"),
                               ("materials", os.path.isdir, "目录"),
                               ("items", os.path.isfile, "文件")):
            c[k] = _resolve(base, c.get(k))
            if not (isinstance(c[k], str) and check(c[k])):
                _die("课程 %s 的 %s 必须是存在的%s，当前 %r" % (name, k, what, c.get(k)))
        for k, n in (("questions", 3), ("quiz", 2)):
            v = c.get(k)
            if not (isinstance(v, list) and len(v) == n
                    and all(isinstance(x, str) and x.strip() for x in v)):
                _die("课程 %s 的 %s 必须是恰好 %d 个非空字符串 id 的数组（会话脚本固定教 3 测 2）"
                     % (name, k, n))
            if len(set(v)) != len(v):
                _die("课程 %s 的 %s 有重复 id: %s" % (name, k, v))
        if c.get("wrong_id") not in c["quiz"]:
            _die("课程 %s 的 wrong_id 必须是 quiz 两题之一，当前 %r（quiz=%s）"
                 % (name, c.get("wrong_id"), c["quiz"]))
        wa = c.get("wrong_answer")
        if not (isinstance(wa, str) and wa.strip()):
            _die("课程 %s 缺 wrong_answer（模拟学生答错时给出的似真错误答案文案）" % name)
        gist = c.get("gist")   # 可选：错题 gist 关键词表，供 loop_score 的 M4「上次错了哪题」判分
        if gist is not None and not (isinstance(gist, list) and gist
                                     and all(isinstance(x, str) and x.strip() for x in gist)):
            _die("课程 %s 的 gist（可选）必须是非空字符串关键词数组；留空则 M4 存续探针不可评" % name)
    model = cfg.get("model", "sonnet")
    if not (isinstance(model, str) and model.strip()):
        _die("config.model 必须是非空字符串（缺省 sonnet）")
    cfg["model"] = model
    cfg["results_dir"] = _resolve(base, cfg.get("results_dir") or "results/loop")
    cfg["skill_md"] = _resolve(base, cfg.get("skill_md")) or os.path.join(ROOT, "SKILL.md")
    if not os.path.isfile(cfg["skill_md"]):
        _die("skill_md 不存在: %s（skill 臂前导语要指向技能定义文件）" % cfg["skill_md"])
    return cfg


def load_items_map(course):
    """items jsonl → {id: item}。config 引用的 5 个 id 必须在场、可答、有金标——教学与
    「学生答对」的话语都要用 gold_answer，缺了就是脚本没法演，fail-loud。"""
    items, path = {}, course["items"]
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                d = json.loads(s)
            except ValueError as e:
                _die("课程 %s 的 items 第 %d 行不是合法 JSON: %s" % (course["name"], ln, e))
            if not (isinstance(d, dict) and d.get("id") and d.get("question")):
                _die("课程 %s 的 items 第 %d 行缺 id/question" % (course["name"], ln))
            rid = str(d["id"])
            if rid in items:
                _die("课程 %s 的 items id 重复: %s（第 %d 行）" % (course["name"], rid, ln))
            items[rid] = d
    for qid in list(course["questions"]) + list(course["quiz"]):
        it = items.get(qid)
        if it is None:
            _die("课程 %s 的 config 引用了 items 里不存在的 id: %s" % (course["name"], qid))
        if it.get("answerable") is False:
            _die("课程 %s 的 %s 是越界探针（answerable=false）——教学/测验会话只能用可答金标题"
                 % (course["name"], qid))
        if not str(it.get("gold_answer", "")).strip():
            _die("课程 %s 的 %s 缺 gold_answer——教学与「学生答对」话语都需要金标" % (course["name"], qid))
    return items


# ---------------- session scripts (设计冻结稿 §协议，两臂逐字相同) ----------------

def build_sessions(course, items):
    """{"S1": [step...], "S2": [...], "S3": [...]}；step = {kind, idx?, qid?, user}。"""
    q = lambda i: items[i]["question"]
    gold = lambda i: str(items[i].get("gold_answer", ""))
    s1 = []
    for idx, qid in enumerate(course["questions"]):
        s1.append({"kind": "teach", "idx": idx, "qid": qid, "user": TEACH_USER % q(qid)})
    for idx, qid in enumerate(course["quiz"]):
        wrong = qid == course["wrong_id"]
        student = course["wrong_answer"] if wrong else gold(qid)
        s1.append({"kind": "quiz", "idx": idx, "qid": qid,
                   "user": QUIZ_USER % (q(qid), student)})
    # M4 存续探针只保留「错题回忆」——它是唯一无法从原始材料重推的探针（问的是学生自己这次
    # 的历史：错了哪道）。原「再念一遍讲义结论」探针可被裸智能体重读材料答出，不具区分度，已删。
    s2 = [{"kind": "recall_mistakes", "user": S2_USER_MISTAKES}]
    s3 = [{"kind": "cheatsheet", "user": S3_USER % (CHEATSHEET_PAGES, CHEATSHEET_PAGES)}]
    return {"S1": s1, "S2": s2, "S3": s3}


def make_preamble(cfg, course, arm):
    if arm == "bare":
        return BARE_PREAMBLE % course["materials"]
    scripts_dir = os.path.join(ROOT, "scripts")
    return SKILL_PREAMBLE % (cfg["skill_md"], scripts_dir)


def build_prompt(preamble, history, user_line):
    """臂前导语 + 转写前缀 + 新话语。history=[] 就是全新会话——S2/S3 的隔离全靠这里。"""
    parts = [preamble]
    if history:
        parts += ["", HISTORY_HEADER]
        for u, a in history:
            parts += ["", "学生：%s" % u, "", "助手：%s" % a]
    parts += ["", "学生：%s" % user_line, "", "助手："]
    return "\n".join(parts)


# ---------------- real turns (claude -p) ----------------

def _claude_turn(prompt, model, cwd, arm, timeout=TURN_TIMEOUT):
    """一轮真 `claude -p` → (answer, cost, files_opened, ok, err_text)。
    skill 臂开流式轨迹（files_opened=该轮 Read/Glob/Grep 的检索足迹，解析复用
    gen.parse_stream_events）；bare 臂普通 json（files_opened=None）。
    ok=False 时 err_text 供分类：限额通知（run_matrix._is_quota_notice 口径）/ TIMEOUT /
    API Error / 非 JSON stdout。prompt 走 STDIN——转写前缀会长过 Windows argv 上限。"""
    trace = arm == "skill"
    if trace:
        args = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model]
    else:
        args = ["claude", "-p", "--output-format", "json", "--model", model]
    args += ["--allowedTools"] + list(SKILL_TOOLS if arm == "skill" else BARE_TOOLS)
    try:
        p = subprocess.run(args, cwd=cwd, input=prompt, capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return "", None, None, False, "TIMEOUT"
    except Exception as e:                     # 绝不让一次坏调用弄崩整趟
        return "", None, None, False, "API Error: %s" % e
    if trace:
        result, cost, files = gen.parse_stream_events(p.stdout)
        if result.strip():
            if RM._is_quota_notice(result):    # 整个 result 就是限额通知 → 配额错，不是回答
                return "", cost, None, False, result.strip()
            return result, cost, files, True, ""
        return "", cost, None, False, (p.stdout or p.stderr or "").strip()[:2000]
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return "", None, None, False, (p.stdout or p.stderr or "").strip()[:2000]
    res = data.get("result") or ""
    if res.strip():
        if RM._is_quota_notice(res):
            return "", data.get("total_cost_usd"), None, False, res.strip()
        return res, data.get("total_cost_usd"), None, True, ""
    return "", data.get("total_cost_usd"), None, False, (p.stdout or p.stderr or "").strip()[:2000]


def real_turn(prompt, model, cwd, arm):
    """→ (assistant_text, cost, files, status)。瞬时错误退避重试 3 次（gen 同节奏）；
    配额（限额通知 / hard 词表）不重试——status=quota_stop 由上层干净停跑。"""
    ans, cost, files, err = "", None, None, ""
    for attempt in range(3):
        ans, cost, files, ok, err = _claude_turn(prompt, model, cwd, arm)
        if ok:
            return ans, cost, files, "ok"
        if RM._is_quota_notice(err) or gen.classify(err) == "hard":
            return err, cost, files, "quota_stop"
        if attempt < 2:
            _sleep(5 * (attempt + 1) ** 2)     # 5s, 20s（仅真跑瞬时错误触发）
    return err or "（空响应）", cost, files, "infra_error"


# ---------------- mock turns (loop_fixtures 夹具 + 真实磁盘产物) ----------------

_TMPL_CACHE = {}


def _render(rel, **kw):
    if rel not in _TMPL_CACHE:
        with open(os.path.join(FIXTURES, rel), encoding="utf-8") as f:
            _TMPL_CACHE[rel] = string.Template(f.read())
    try:
        return _TMPL_CACHE[rel].substitute(**kw).rstrip() + "\n"
    except KeyError as e:
        _die("夹具 %s 缺占位变量 %s——夹具与 mock_turn 的变量表脱节了" % (rel, e))


def _title(question):
    return re.sub(r"\s+", " ", question or "").strip()[:20] or "题目"


def _wiki_file(ws, n):
    """第 n 章 wiki 的实际文件名（ingest 可能带标题后缀，如 ch02_linear_list.md）。"""
    d = os.path.join(ws, "references", "wiki")
    if os.path.isdir(d):
        pref = "ch%02d" % n
        for name in sorted(os.listdir(d)):
            if name.startswith(pref) and name.endswith(".md"):
                return name
    return "ch%02d.md" % n


def _slot(course, items, ws, role, idx):
    """mock 的确定性布局：教学题第 i 道 → 第 i+1 章 walkthrough；测验题第 i 道 → 第 i+1 章
    feedback（标题加「·判分」后缀，与同 id 的 walkthrough 锚永不撞 slug）。resume/S3 重算
    出的锚与 S1 落盘时完全一致（全部由 config+items 决定）。"""
    qid = (course["questions"] if role == "teach" else course["quiz"])[idx]
    it = items[qid]
    ch = idx + 1
    title = _title(it["question"]) + ("" if role == "teach" else "·判分")
    wrong = role == "quiz" and qid == course["wrong_id"]
    return {"qid": qid, "chapter": ch, "ch_file": "ch%02d.md" % ch,
            "wiki_file": _wiki_file(ws, ch), "title": title,
            "anchor": NB.entry_anchor(qid, title),
            "question": it["question"], "gold": str(it.get("gold_answer", "")),
            "wrong": wrong,
            "student_answer": course["wrong_answer"] if wrong else str(it.get("gold_answer", ""))}


def _notebook_add(ws, chapter, etype, eid, title, body, mistake=False):
    """走官方唯一写入路径 scripts/notebook.py（正文经 STDIN）——mock 产物与真 skill 落盘
    同格式、同锚点词汇，判分器不用为 mock 单开解析口径。"""
    old_stdin, old_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(body), io.StringIO()   # 回执噪音不进测试输出
    try:
        rc = NB.run(["--workspace", ws, "add-entry", "--chapter", str(chapter),
                     "--type", etype, "--id", eid, "--title", title]
                    + (["--mistake"] if mistake else []))
    except SystemExit as e:
        rc = e.code
    finally:
        sys.stdin, sys.stdout = old_stdin, old_stdout
    if rc != 0:
        _die("mock 落盘失败（notebook add-entry 退出码 %r）——夹具产物必须真实写盘" % (rc,), 1)


# 恰含 2 个页对象的最小 PDF——cheatsheet_render.pdf_page_count 的 /Type /Page 计数（排除
# /Pages）在这上面数出 2，交付物完备性的「PDF 页数」判分路径由此打通。
_FAKE_PDF = (b"%PDF-1.4\n"
             b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
             b"2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >> endobj\n"
             b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >> endobj\n"
             b"4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >> endobj\n"
             b"trailer << /Root 1 0 R >>\n"
             b"%%EOF\n")


def _mock_cheatsheet(course, items, ws):
    """cheatsheet.md（每条顶层要点都带真锚点溯源链接，validate_workspace 的小抄 lint 全绿）
    + 假 2 页 PDF。"""
    teach = []
    for idx in range(len(course["questions"])):
        s = _slot(course, items, ws, "teach", idx)
        teach.append("- %s（[出处](notebook/%s#%s)·[wiki](references/wiki/%s)）"
                     % (s["gold"], s["ch_file"], s["anchor"], s["wiki_file"]))
    widx = course["quiz"].index(course["wrong_id"])
    w = _slot(course, items, ws, "quiz", widx)
    mistake = ("- 上次答错：%s——正确答案是「%s」（[错题本](mistakes/%s#%s)）"
               % (_title(w["question"]), w["gold"], w["ch_file"], w["anchor"]))
    md = _render("skill/cheatsheet_md.md", course=course["name"],
                 teach_bullets="\n".join(teach), mistake_bullets=mistake)
    with open(os.path.join(ws, "cheatsheet.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    with open(os.path.join(ws, "cheatsheet.pdf"), "wb") as f:
        f.write(_FAKE_PDF)


def mock_turn(course, items, ws, arm, step):
    """→ (assistant_text, cost, files_opened)。skill 臂边出话边真实落盘。"""
    kind, cost = step["kind"], MOCK_COST[arm]
    if arm == "bare":
        if kind == "teach":
            s = _slot(course, items, ws, "teach", step["idx"])
            return _render("bare/S1_teach.md", question=s["question"], gold=s["gold"]), cost, None
        if kind == "quiz":
            s = _slot(course, items, ws, "quiz", step["idx"])
            name = "bare/S1_quiz_wrong.md" if s["wrong"] else "bare/S1_quiz_correct.md"
            return _render(name, student_answer=s["student_answer"], gold=s["gold"]), cost, None
        if kind == "recall_mistakes":
            return _render("bare/S2_wrong_recall.md"), cost, None
        if kind == "recall_content":
            s = _slot(course, items, ws, "teach", step["idx"])
            return _render("bare/S2_content_recall.md", title=_title(s["question"])), cost, None
        return _render("bare/S3_cheatsheet.md"), cost, None

    if kind == "teach":
        s = _slot(course, items, ws, "teach", step["idx"])
        body = _render("skill/nb_walkthrough.md", **{k: s[k] for k in
                       ("qid", "question", "gold", "chapter", "wiki_file")})
        _notebook_add(ws, s["chapter"], "walkthrough", s["qid"], s["title"], body)
        text = _render("skill/S1_teach.md", **{k: s[k] for k in
                       ("qid", "question", "gold", "chapter", "wiki_file", "ch_file", "anchor")})
        return text, cost, ["references/wiki/" + s["wiki_file"]]
    if kind == "quiz":
        s = _slot(course, items, ws, "quiz", step["idx"])
        verdict = "❌ 答错" if s["wrong"] else "✅ 正确"
        comment = "相邻概念记混，对照 wiki 对应小节再过一遍" if s["wrong"] else "掌握到位，保持"
        body = _render("skill/nb_feedback.md", verdict=verdict, comment=comment,
                       **{k: s[k] for k in ("qid", "student_answer", "gold", "wiki_file")})
        _notebook_add(ws, s["chapter"], "feedback", s["qid"], s["title"], body,
                      mistake=s["wrong"])
        name = "skill/S1_quiz_wrong.md" if s["wrong"] else "skill/S1_quiz_correct.md"
        text = _render(name, **{k: s[k] for k in
                       ("qid", "student_answer", "gold", "wiki_file", "ch_file", "anchor")})
        return text, cost, ["references/wiki/" + s["wiki_file"]]
    if kind == "recall_mistakes":
        widx = course["quiz"].index(course["wrong_id"])
        s = _slot(course, items, ws, "quiz", widx)
        text = _render("skill/S2_wrong_recall.md", wrong_id=s["qid"],
                       title=_title(s["question"]), student_answer=s["student_answer"],
                       gold=s["gold"], ch_file=s["ch_file"], anchor=s["anchor"])
        return text, cost, ["mistakes/index.md", "mistakes/" + s["ch_file"]]
    if kind == "recall_content":
        s = _slot(course, items, ws, "teach", step["idx"])
        text = _render("skill/S2_content_recall.md", title=_title(s["question"]),
                       gold=s["gold"], wiki_file=s["wiki_file"],
                       ch_file=s["ch_file"], anchor=s["anchor"])
        return text, cost, ["notebook/" + s["ch_file"]]
    _mock_cheatsheet(course, items, ws)
    return (_render("skill/S3_cheatsheet.md", pages=CHEATSHEET_PAGES), cost,
            ["notebook/index.md", "mistakes/index.md"])


# ---------------- results plumbing (resume / meta) ----------------

def _read_sessions(path):
    """已落盘的转写行。中间坏行 fail-loud（静默跳过会让该轮被当未做而重打）；末行无换行=
    崩溃残段——完整则补换行、非法则截掉自愈（run_matrix._read_ledger 同策略）。"""
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, "rb") as f:
        raw = f.read()
    nl = raw.rfind(b"\n")
    body, tail = raw[:nl + 1], raw[nl + 1:]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        _die("%s 编码损坏（%s）——无法安全续跑，请人工修复" % (path, e))
    for ln, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            d = json.loads(s)
            (d["session"], int(d["turn"]), d["status"], d["assistant"])
        except (ValueError, KeyError, TypeError) as e:
            _die("%s 第 %d 行坏转写行（%s: %s）——请人工修复/删除该行后再续跑" %
                 (path, ln, type(e).__name__, e))
        rows.append(d)
    if tail.strip():
        try:
            d = json.loads(tail.decode("utf-8"))
            (d["session"], int(d["turn"]), d["status"], d["assistant"])
            rows.append(d)
            with open(path, "a", encoding="utf-8") as f:   # 行完整只缺换行——补上防黏行
                f.write("\n")
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            sys.stderr.write("[loop] 警告：%s 末行是崩溃残段（无换行且非法）——视作未写入，截掉自愈\n"
                             % path)
            with open(path, "r+b") as f:
                f.truncate(nl + 1)
    return rows


RUNTIME_ARTIFACT_DIRS = ("notebook", "mistakes")
RUNTIME_ARTIFACT_FILES = ("cheatsheet.md", "cheatsheet.pdf",
                          "study_state.json")   # 进度结构化事实源（update_progress.py 的
                          # STATE_NAME）——同样是运行时产物。study_progress.md 单独处理（见下）：
                          # 它不能只删/留原样——study_state.json 一旦没了，技能契约的官方 fallback
                          # 就是改读 study_progress.md（scripts/update_progress.py 顶部 docstring：
                          # "a workspace WITHOUT study_state.json keeps working (no-Python
                          # fallback: hand-written study_progress.md still validates)"；
                          # skills/exam-review/SKILL.md 同样写明 state 缺失时错题/疑难点表改读
                          # study_progress.md）——留着源里可能带的旧错题/疑难点/已推进阶段，
                          # 就是把「上一轮」的痕迹当成本轮的存续证据（Finding 1）。


def _strip_runtime_artifacts(ws):
    """把刚拷贝进来的工作区剥回「刚建库、一次都没跑过」的干净状态（Finding 4）：源 skill_ws
    若已带着上一次跑（或人工用过）留下的 notebook/mistakes/cheatsheet/study_state.json，原样
    拷进 results 工作区会让 M4（存续）/M5（交付物完备性）白捡分——本轮明明什么都没讲、没判、
    没落盘，判分器却看见"早就有了"。只在**首次**拷贝后、S1 开跑前调用一次；续跑绝不能碰
    （那时工作区里的产物是这一轮自己写的，剥了就是自毁转写）。"""
    for name in RUNTIME_ARTIFACT_DIRS:
        p = os.path.join(ws, name)
        if os.path.isdir(p):
            shutil.rmtree(p)
    for name in RUNTIME_ARTIFACT_FILES:
        p = os.path.join(ws, name)
        if os.path.isfile(p):
            os.remove(p)
    _reset_study_progress(ws)


def _reset_study_progress(ws):
    """Finding 1：study_state.json 剥掉后，study_progress.md 变成技能契约的**唯一**错题/疑难点/
    断点读取来源——源里若带着旧跑（或人工用过）留下的已推进阶段/非空错题表/疑难点表，原样留着
    就是让技能把"上一轮"的痕迹当成本轮的存续证据，重演 Finding 4 同一类白捡分。
    用 update_progress.render_md(default_state()) 直接调库函数重渲染——这是官方唯一的
    state→md 渲染实现（真跑时 update_progress.py 的每次 save() 都用它生成 study_progress.md），
    不新造第二套格式；也不必先造一个 study_state.json 再删（`update_progress.py render` 的 CLI
    路径需要 state 文件存在，直接调库函数绕开这个前提）。产出：phase=1、错题/疑难点/打卡表全空
    ——与「刚建库、一次都没跑过」的工作区应有的断点一致。"""
    p = os.path.join(ws, "study_progress.md")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(UP.render_md(UP.default_state()))


def prepare_workspace(course, arm, dirp):
    """skill 臂：<results>/<course>_skill/workspace（首跑从 skill_ws 拷贝 + 剥净运行时产物、
    续跑原样保留——S1 的落盘就是 S2/S3 的记忆）。bare 臂：直接在材料文件夹里干活（只读工具）。"""
    if arm == "bare":
        return course["materials"]
    dst = os.path.join(dirp, "workspace")
    if not os.path.isdir(dst):
        shutil.copytree(course["skill_ws"], dst)
        _strip_runtime_artifacts(dst)
    return dst


def _config_fingerprint(cfg, course, arm):
    """决定 S1-S3 会话脚本的 prompt 内容 + 判分口径的配置指纹：items **文件内容**、materials/
    skill_ws **目录内容**（含就地重生成 wiki/工作区——路径没变但内容变了也要让指纹变，
    run_matrix._config_fingerprint 同一立场）+ wrong_id/wrong_answer/questions/quiz 取值 +
    （仅 skill 臂）skill_md **文件内容**。改了任一，即便题目 id 照旧（同一批 wrong_id/questions/
    quiz），旧账本也是对着**旧** prompt 写的——续跑必须拒绝复用（Finding 2）。哈希用文件/目录内容
    而非仅路径字符串，专治"config 路径没变、但底下文件被就地改写"这种最容易被忽略的漏网场景。

    skill_md 只在 arm=="skill" 时才进指纹（Finding 3）：SKILL_PREAMBLE 每轮都嵌入 cfg["skill_md"]
    并要求模型先读它——技能定义变了却复用旧 results_dir，ensure_meta 会把旧账本当"配置没变"放行
    续跑，报告悄悄测量的却是旧版技能。bare 臂前导语从不引用 skill_md，改它不该拒绝 bare 臂续跑
    ——与 run_matrix._config_fingerprint「材料/workspace 只在选了对应臂时才进指纹」同一立场，
    避免臂无关的资源变化触发误报的"配置变了"。"""
    sig = {
        "items": RM._file_hash(course.get("items")),
        "materials": RM._dir_hash(course.get("materials")),
        # skill_ws 只在 skill 臂进指纹（Codex r4 P2，与 skill_md 同门）：bare 臂前导语走 materials、
        # cwd 也是 materials，从不碰 skill_ws——重建 wiki/工作区后 bare-only 续跑不该被误拒。
        "skill_ws": RM._dir_hash(course.get("skill_ws")) if arm == "skill" else None,
        "wrong_id": course.get("wrong_id"),
        "wrong_answer": course.get("wrong_answer"),
        "questions": list(course.get("questions") or []),
        "quiz": list(course.get("quiz") or []),
        "skill_md": RM._file_hash(cfg.get("skill_md")) if arm == "skill" else None,
    }
    return hashlib.sha256(
        json.dumps(sig, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def ensure_meta(dirp, cfg, course, arm, ws, mock):
    """meta.json：冻结键 + 附加键。已有 meta（续跑）时核对 mock/real 与题目配置一致——
    mock 占位混进真跑目录、或换了题还复用旧目录，转写就成了对不上的杂拌；config_fingerprint
    另外核对 items/materials/skill_ws/wrong_answer 等**内容**是否也没变（Finding 2——这些字段
    单独看未必等值改变就能查出，比如就地重生成 wiki）；skill 臂还核对 skill_md **内容**
    （Finding 3——技能定义变了却复用旧账本，报告会悄悄测量成旧版技能）。"""
    meta_path = os.path.join(dirp, "meta.json")
    mode = "mock" if mock else "real"
    fp = _config_fingerprint(cfg, course, arm)
    want = {"model": cfg["model"], "workspace": ws, "materials": course["materials"],
            "questions": list(course["questions"]), "wrong_id": course["wrong_id"],
            # 附加键（判分器只依赖上面的冻结键；这些是给人/续跑核对用的）：
            "course": course["name"], "arm": arm, "mode": mode,
            "quiz": list(course["quiz"]), "wrong_answer": course["wrong_answer"],
            "items": course["items"], "cheatsheet_pages": CHEATSHEET_PAGES,
            "config_fingerprint": fp}
    if arm == "skill":
        want["skill_md"] = cfg["skill_md"]
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                prev = json.load(f)
        except ValueError as e:
            _die("%s 损坏（%s）——无法核对续跑一致性，请修复或换 results_dir" % (meta_path, e))
        for k in ("mode", "model", "questions", "quiz", "wrong_id"):
            if prev.get(k) != want[k]:
                _die("results 目录 %s 的 meta.%s 与当前 config 不一致（%r vs %r）——"
                     "mock/real 或题目配置混目录；请换一个 results_dir"
                     % (dirp, k, prev.get(k), want[k]))
        if not prev.get("config_fingerprint"):
            _die("results 目录 %s 的 meta.json 缺 config_fingerprint（大概率是本次修复前生成的旧"
                 "账本，没法核对 items/materials/skill_ws/wrong_answer 是否也没变）——无法安全续跑；"
                 "请换一个干净的 --results-dir，或删除该目录重新跑" % dirp)
        elif prev["config_fingerprint"] != fp:
            _die("results 目录 %s 的配置指纹变了——items/materials/skill_ws/wrong_answer 等实际"
                 "取值/内容与上次不同（即便题目 id 没变），旧转写是对着旧 prompt 打的，继续续跑会"
                 "拿新配置的判分标准套旧回答；请换一个干净的 --results-dir，或删除该目录重新跑"
                 % dirp)
        return prev
    want["started"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(want, f, ensure_ascii=False, indent=2)
    os.replace(tmp, meta_path)
    return want


# ---------------- run ----------------

def run_course_arm(cfg, course, items, arm, mock):
    dirp = os.path.join(cfg["results_dir"], "%s_%s" % (course["name"], arm))
    os.makedirs(dirp, exist_ok=True)
    sessions_path = os.path.join(dirp, "sessions.jsonl")
    done = {}
    for d in _read_sessions(sessions_path):            # 后行覆盖前行（非 ok 重跑后追加新行）
        done[(d["session"], int(d["turn"]))] = d
    meta_path = os.path.join(dirp, "meta.json")
    # Finding B（Codex r3）：有转写行却缺 meta.json（目录被删剩一半、或从别处拷来半份结果）——
    # meta 是续跑指纹的唯一载体，缺了就无从校验这些 ok 转写是不是本课程/本配置打的。绝不能当
    # 「干净新跑」静默复用：否则 ensure_meta 会照当前 config 现造一份 meta、把来路不明的旧转写
    # 当成本配置的成果直接跳过。宁可大声失败，逼人换干净目录或整轮重跑。
    if done and not os.path.isfile(meta_path):
        _die("results 目录 %s 有 sessions.jsonl 转写却缺 meta.json——无法校验续跑指纹，拒绝把"
             "来路不明的旧转写当本次新跑复用；请换干净 --results-dir，或删掉该目录整轮重跑" % dirp)
    # Finding C（Codex r3）：skill 臂的 workspace/ 本身就是被判分的产物（M4 存续/M5 交付物都读它）。
    # 转写记着某些轮已 ok（产物理应在 workspace/ 里），可 workspace/ 被删/没恢复——续跑会跳过那些
    # ok 轮、却只重铺一个空的干净种子，最终判分对着空工作区，凭空丢掉本已产出的 notebook/错题/小抄。
    # 同样大声失败，让人要么恢复 workspace/、要么删目录整轮重跑，绝不静默把满分产物洗成 0。
    if arm == "skill" and any(r.get("status") == "ok" for r in done.values()) \
            and not os.path.isdir(os.path.join(dirp, "workspace")):
        _die("results 目录 %s 的转写记有已完成(ok)轮次，但被判分的 workspace/ 已不在——续跑会跳过"
             "这些轮又只铺空种子，判分将凭空丢失已产出的 notebook/错题/小抄；请恢复 workspace/ 后"
             "再续，或删掉该目录整轮重跑" % dirp)
    ws = prepare_workspace(course, arm, dirp)
    ensure_meta(dirp, cfg, course, arm, ws, mock)
    plan = build_sessions(course, items)
    preamble = make_preamble(cfg, course, arm)
    n_new = n_skip = 0
    with open(sessions_path, "a", encoding="utf-8") as sf:
        for sname in SESSION_NAMES:
            history = []                               # 会话边界 = 前缀清空（磁盘是唯一通道）
            for tno, step in enumerate(plan[sname], 1):
                prior = done.get((sname, tno))
                if prior is not None and prior.get("status") == "ok":
                    history.append((prior["user"], prior["assistant"]))
                    n_skip += 1
                    continue
                prompt = build_prompt(preamble, history, step["user"])
                if mock:
                    text, cost, files = mock_turn(course, items, ws, arm, step)
                    status = "ok"
                else:
                    text, cost, files, status = real_turn(prompt, cfg["model"], ws, arm)
                row = {"course": course["name"], "arm": arm, "session": sname, "turn": tno,
                       "user": step["user"], "assistant": text, "cost_usd": cost,
                       "files_opened": files, "status": status}
                assert list(row) == list(ROW_KEYS)
                sf.write(json.dumps(row, ensure_ascii=False) + "\n")
                sf.flush()
                if status == "quota_stop":
                    print("[loop] %s/%s %s T%d 撞配额上限——已落 quota_stop 行，干净停跑"
                          "（配额恢复后原命令续跑）。" % (course["name"], arm, sname, tno))
                    return 7
                if status == "infra_error":
                    print("[loop] %s/%s %s T%d 基础设施错误（重试 3 次仍失败）——转写有洞"
                          "不能往下跑；已落 infra_error 行，重跑该命令会重试此轮。"
                          % (course["name"], arm, sname, tno))
                    return 1
                history.append((step["user"], text))
                n_new += 1
    print("[loop] %s/%s 完成：新跑 %d 轮，跳过（已完成）%d 轮 → %s"
          % (course["name"], arm, n_new, n_skip, sessions_path))
    return 0


def _emit_scorer_config(cfg):
    """把驱动 config 里各课程的 gist 关键词翻成 loop_score 认的
    {course: {"gist": {wrong_id: [...]}}}，落到 <results>/loop_config.json（Codex r3 P2）。
    否则一次普通 loop_bench 跑完，loop_score 找不到关键词，M4「上次错了哪题」探针只能记 null、
    整条跨会话存续指标白测——用户还得另手写一份 config 才评得了。只写有 gist 的课程；没配 gist
    的课程留给 loop_score 照旧大声告警「不可评」（不硬造关键词、不假装可评）。"""
    scorer = {c["name"]: {"gist": {c["wrong_id"]: list(c["gist"])}}
              for c in cfg["courses"] if c.get("gist")}
    path = os.path.join(cfg["results_dir"], "loop_config.json")
    if not scorer:
        # 本次没有任何课配 gist——若同一 results_dir 上一轮遗留了自动落的 loop_config.json，
        # 必须清掉：loop_score 默认读它，留着会用**旧**关键词判 M4，而不是按本次配置转「不可评」
        # 大声告警（Codex r4 P2）。文件本身的在场必须跟随当前配置。
        if os.path.isfile(path):
            os.remove(path)
            print("[loop] 无课程配 gist——已清除上次遗留的判分关键词 %s（M4 转为不可评）" % path)
        return
    os.makedirs(cfg["results_dir"], exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(scorer, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    print("[loop] 已落判分关键词 → %s（%d 门课的 gist，loop_score 默认自动读取）"
          % (path, len(scorer)))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="备考全流程 loop benchmark 会话驱动器（bare vs skill；断点续跑、配额感知）")
    ap.add_argument("--config", required=True, help="loop config json（路径按 config 所在目录解析）")
    ap.add_argument("--mock", action="store_true",
                    help="离线夹具跑通全管线（不碰 claude；不测量任何东西）")
    ap.add_argument("--course", default=None, help="只跑这一门课（config.courses 里的 name）")
    ap.add_argument("--arm", choices=list(ARMS), default=None, help="只跑这一臂")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    _emit_scorer_config(cfg)   # 把 gist 关键词落到 <results>/loop_config.json，让 loop_score 直接可评 M4
    courses = cfg["courses"]
    if args.course:
        courses = [c for c in courses if c["name"] == args.course]
        if not courses:
            _die("--course %s 不在 config.courses 里（有：%s）"
                 % (args.course, "/".join(c["name"] for c in cfg["courses"])))
    arms = [args.arm] if args.arm else list(ARMS)
    for course in courses:
        items = load_items_map(course)
        for arm in arms:
            rc = run_course_arm(cfg, course, items, arm, mock=args.mock)
            if rc:
                return rc
    print("[loop] 全部课程×臂完成 → %s%s"
          % (cfg["results_dir"], "（mock 占位转写，未测量任何指标）" if args.mock else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
