#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Deterministic scorer for the loop benchmark（设计冻结稿 metrics 1/4/5/6；2/3 走既有 judge/matrix 路径）.

    python benchmark/loop_score.py --results <dir> --out summary_loop.json [--config <json>]

Input（冻结转写接口，由 loop_bench 驱动器产出）:
  <results>/<course>_<arm>/sessions.jsonl   一行一轮:
      {"course","arm","session":"S1|S2|S3","turn":int,"user","assistant",
       "cost_usd":float|null,"files_opened":[..]|null,"status":"ok|infra_error|quota_stop"}
  <results>/<course>_<arm>/meta.json        {"model","workspace","materials","questions":[ids],
                                             "wrong_id","started"}
  跑完后的 workspace 目录本身是被评物（S1-S3 会改写它）。

四项度量（全部确定性，零 LLM）：

M1 溯源可核验率（claim proxy —— 诚实声明）
  「结论」不做句级抽取：**每个 S1 教学回合（turn ≤ 3 且 status=ok）计 1 个 claim 单元**；
  该单元通过 = 回合的 assistant 文本携带 ≥1 条**可核验**来源：
    a) 来源块行  zh `题目来源：…｜答案来源：…｜<标签>` / en `Question source: … | Answer source: …`
       （全角｜/ASCII| 都认，同 behavior_smoke 口径），且行内 ≥1 个文件名 token 能在
       workspace / materials / workspace/references(/assets) 下解析为真实文件；
    b) markdown 链接指进 references/wiki|notebook|mistakes：目标文件存在于该臂 workspace，
       且 notebook/mistakes 带 #锚 时锚 ∈ validate_workspace._md_anchors(目标)
       （wiki 链接保持文件级校验，与 validate_workspace 的小抄 lint 同口径）。
  m1 = 通过回合数 / 可评教学回合数。局限：一回合十句话只带一条真来源也算过——这是回合级
  代理指标，不是句级；换取的是 100% 确定性与零判分成本。

M4 跨会话存续率
  S2 的两个探针（先按用户话语正则分类，兜底按轮次顺序）：
    A「上次错了哪题」: assistant 含 meta.wrong_id（ASCII 边界防 q2 误配 q20），或 config 的
      gist 关键词覆盖 ≥60%；
    B「再给我看一眼 <q1>」: config 按题给的 keywords（确定性词表）在 assistant 里覆盖 ≥60%，
      q1 = config[course].reshow_question 或 meta.questions[0]。
  m4 = 通过探针 / 可评探针。config 缺该题 keywords 时探针 B **不可评**（大声告警 + 计入
  m4_unscored，不硬造 0 分也不假装满分）。

M5 交付物完备性（checklist 各项 0/1，m5 = 已评项均值）
  notebook_index : notebook/index.md 存在 + 条目链接 ≥3 + 每条链接目标存在且 #锚可解析
  mistakes_entry : mistakes/chNN.md 里存在 id == wrong_id 的条目块（fence-aware）
  cheatsheet_md  : cheatsheet.md 存在 + validate_workspace.validate(ws) 0 错误
  cheatsheet_pdf : cheatsheet.pdf 存在 + cheatsheet_render.pdf_page_count()==目标页数（默认 2，
                   meta.cheatsheet_pages 可覆写）；驱动器 --mock html-degraded（meta.mock ==
                   "html-degraded" 或 meta.html_degraded == true）时该项 skip-not-fail（记 null，
                   不进均值分母）。

M6 成本
  m6_total_usd = Σ cost_usd（null 安全：null 行不计）；m6_per_turn = 均值（仅有成本数据的轮）；
  n_turns 全轮数；n_quota_stops = status=="quota_stop" 的轮数。

Output（--out）:
  {course: {"bare": {...}, "skill": {...}, "gap": {m1/m4/m5/m6_* 的 skill−bare，缺臂记 null}},
   "_warnings": [...]}   —— 告警同时打到 stderr（缺臂/缺文件/不可评都必须大声）。

Config（--config，默认 <results>/loop_config.json，可缺省）:
  {"<course>": {"gist": {"<qid>": [..]}, "keywords": {"<qid>": [..]}, "reshow_question": "<qid>"}}

纯标准库；Windows 控制台 UTF-8；坏 jsonl 行 fail-loud（沿用 run_matrix 账本先例）。
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import unquote

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
_SCRIPTS = os.path.join(ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
import validate_workspace as _vw   # noqa: E402  锚点核验唯一口径（_md_anchors）
import cheatsheet_render as _cr    # noqa: E402  PDF 页数唯一口径（pdf_page_count）
import notebook as _nb             # noqa: E402  条目块/围栏解析唯一口径（_HEAD_RE/_fence_step）

ARMS = ("bare", "skill")
SESSIONS_NAME = "sessions.jsonl"
META_NAME = "meta.json"
TEACH_TURNS = 3                    # 冻结会话脚本：S1 前 3 轮教学、后 2 轮测验
COVERAGE_THRESHOLD = 0.6
DEFAULT_PAGES = 2                  # S3 脚本固定要 2 页小抄
MIN_NOTEBOOK_ENTRIES = 3
CHECKLIST_ITEMS = ("notebook_index", "mistakes_entry", "cheatsheet_md", "cheatsheet_pdf")
GAP_KEYS = ("m1", "m4", "m5", "m6_total_usd", "m6_per_turn")
ROW_KEYS = ("course", "arm", "session", "turn", "user", "assistant", "status")
STATUSES = {"ok", "infra_error", "quota_stop"}

# ---- 来源识别（与 behavior_smoke 的来源块正则同族；en 形式按 docs/language-policy.md） ----
_ZH_SRC_RE = re.compile(r"题目来源\s*[:：].*[｜|].*答案来源\s*[:：]")
_EN_SRC_RE = re.compile(r"question\s+source\s*[:：].*\|.*answer\s+source\s*[:：]", re.I)
# markdown 链接进三大溯源目标；路径段不含空白/)/#
_MD_SRC_LINK_RE = re.compile(
    r"\[[^\]]*\]\(\s*((?:\./)?(?:references/wiki|notebook|mistakes)/[^)#\s]+?)\s*(#[^)\s]*)?\s*\)")
# 来源块行里的文件名 token（\w 含 CJK，「真题2019.pdf」也认）；扩展名收窄到材料常见类型
_FILE_TOKEN_RE = re.compile(r"[\w.\-]+(?:[/\\][\w.\-]+)*\.(?:md|pdf|txt|docx?|pptx?|json|html?)\b",
                            re.I)
# notebook/index.md 的条目链接行（render_index 产出 `- [title](chNN.md#anchor)`）
_INDEX_LINK_RE = re.compile(r"^\s*-\s*\[[^\]]*\]\(([^)#\s]+)(#[^)\s]*)?\)", re.M)
# S2 探针分类（分类不到时按轮次顺序兜底——探针文本由我们自己的驱动器写，词面可控）
_WRONG_PROBE_RE = re.compile(
    r"错了哪|哪.*错|答错|(?:which|what).{0,40}wrong|got\s+wrong|answered\s+wrong|missed",
    re.I | re.S)
_RESHOW_PROBE_RE = re.compile(
    r"再.{0,8}[看讲给]|重[新温看]|show\s.{0,60}again|\bagain\b|one\s+more\s+(?:time|look)|recap",
    re.I | re.S)


def _die(msg, code=2):
    sys.stderr.write("loop_score: %s\n" % msg)
    raise SystemExit(code)


def _warn(warnings, msg):
    warnings.append(msg)
    sys.stderr.write("[loop_score] WARNING: %s\n" % msg)


def _r4(x):
    return None if x is None else round(x, 4)


def _r6(x):
    return None if x is None else round(x, 6)


# ---------------- IO（fail-loud：坏账本行绝不静默跳过——run_matrix 同款立场） ----------------

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        _die("%s 无法读取/不是合法 JSON（%s）" % (path, e))


def _read_sessions(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, ln in enumerate(f, 1):
                if not ln.strip():
                    continue
                try:
                    row = json.loads(ln)
                except ValueError as e:
                    _die("%s 第 %d 行不是合法 JSON（%s）——转写接口坏了必须大声失败" % (path, i, e))
                if not isinstance(row, dict):
                    _die("%s 第 %d 行不是对象" % (path, i))
                missing = [k for k in ROW_KEYS if k not in row]
                if missing:
                    _die("%s 第 %d 行缺冻结接口字段 %s" % (path, i, missing))
                rows.append(row)
    except OSError as e:
        _die("%s 无法读取（%s）" % (path, e))
    return rows


# ---------------- 路径解析（realpath 归属校验，与仓库其它工具同口径） ----------------

def _resolve_rel_file(base, rel):
    """rel 在 base 下解析为真实存在的文件路径；不安全（URL/绝对/..）或不存在/逃逸返回 None。"""
    if not base or not isinstance(rel, str) or not rel.strip():
        return None
    norm = rel.replace("\\", "/").strip().rstrip("。，,;；)")
    if "://" in norm or norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
        return None
    segs = [s for s in norm.split("/") if s not in ("", ".")]
    if not segs or ".." in segs:
        return None
    full = os.path.join(base, *segs)
    if not os.path.isfile(full):
        return None
    base_real = os.path.normcase(os.path.realpath(base))
    real = os.path.normcase(os.path.realpath(full))
    if real != base_real and not real.startswith(base_real + os.sep):
        return None
    return full


def _resolve_dir(p, bases):
    """meta 里的 workspace/materials：绝对路径直接用；相对路径依次对 bases 解析。找不到返回 None。"""
    if not isinstance(p, str) or not p.strip():
        return None
    if os.path.isabs(p):
        return p if os.path.isdir(p) else None
    for base in bases:
        cand = os.path.join(base, p)
        if os.path.isdir(cand):
            return cand
    return None


# ---------------- M1 溯源可核验率 ----------------

def _anchors_cached(path, cache):
    if path not in cache:
        try:
            cache[path] = _vw._md_anchors(path)
        except (OSError, UnicodeDecodeError):
            cache[path] = None
    return cache[path]


def _turn_verified(text, ws, materials, anchor_cache):
    """该回合是否携带 ≥1 条可核验来源（docstring M1 定义）。"""
    text = text or ""
    # b) markdown 链接进 wiki/notebook/mistakes
    for rel, anchor in _MD_SRC_LINK_RE.findall(text):
        full = _resolve_rel_file(ws, rel)
        if not full:
            continue
        top = rel.replace("\\", "/").lstrip("./").split("/", 1)[0]
        frag = unquote(anchor[1:]) if anchor else ""
        if frag and top in ("notebook", "mistakes"):
            aset = _anchors_cached(full, anchor_cache)
            if aset is not None and frag in aset:
                return True
        else:
            return True     # wiki（或无锚的 notebook/mistakes）：文件级核验，与 validate 同口径
    # a) 来源块行：行内 ≥1 个文件 token 能落到真实文件
    search_bases = [b for b in (ws, materials,
                                os.path.join(ws, "references") if ws else None,
                                os.path.join(ws, "references", "assets") if ws else None) if b]
    for line in text.splitlines():
        if not (_ZH_SRC_RE.search(line) or _EN_SRC_RE.search(line)):
            continue
        for tok in _FILE_TOKEN_RE.findall(line):
            if any(_resolve_rel_file(base, tok) for base in search_bases):
                return True
    return False


def score_m1(rows, ws, materials, warnings, tag):
    """(m1|None, verified, claims) —— claims = 可评教学回合数（回合级 claim proxy，见模块 docstring）。"""
    teach = sorted((r for r in rows if r.get("session") == "S1"
                    and isinstance(r.get("turn"), int) and r["turn"] <= TEACH_TURNS),
                   key=lambda r: r["turn"])
    scorable = [r for r in teach if r.get("status") == "ok"]
    if len(teach) != len(scorable):
        _warn(warnings, "%s: %d 个教学回合 status 非 ok——从 M1 分母剔除（infra 不折成模型分）"
              % (tag, len(teach) - len(scorable)))
    if ws is None:
        _warn(warnings, "%s: workspace 不可用——M1 无法核验文件/锚点，记 null" % tag)
        return None, 0, len(scorable)
    if not scorable:
        _warn(warnings, "%s: 没有可评的 S1 教学回合（turn ≤ %d 且 status=ok）——M1 记 null"
              % (tag, TEACH_TURNS))
        return None, 0, 0
    cache = {}
    verified = sum(1 for r in scorable
                   if _turn_verified(r.get("assistant"), ws, materials, cache))
    return verified / len(scorable), verified, len(scorable)


# ---------------- M4 跨会话存续率 ----------------

def _coverage(keywords, text):
    text_low = (text or "").lower()
    hits = sum(1 for k in keywords if str(k).lower() in text_low)
    return hits / len(keywords) if keywords else 0.0


def _id_hit(wid, text):
    """wrong_id 以 ASCII 边界匹配（q2 不误配 q20；「第q2题」「#q2」都命中）。"""
    if not wid:
        return False
    return bool(re.search(r"(?<![A-Za-z0-9_])" + re.escape(str(wid)) + r"(?![A-Za-z0-9])",
                          text or "", re.I))


def _pick_probes(s2_rows):
    """(probe_a_row|None, probe_b_row|None)：先按用户话语正则各认领一行，剩的按轮次顺序补位。"""
    a = next((r for r in s2_rows if _WRONG_PROBE_RE.search(r.get("user") or "")), None)
    b = next((r for r in s2_rows if r is not a and _RESHOW_PROBE_RE.search(r.get("user") or "")),
             None)
    if a is None:
        a = next((r for r in s2_rows if r is not b), None)
    if b is None:
        b = next((r for r in s2_rows if r is not a), None)
    return a, b


def score_m4(rows, meta, course_cfg, warnings, tag):
    """(m4|None, passed, probes, unscored)。probes = 可评探针数；unscored = 存在但没法评的探针数。"""
    s2 = sorted((r for r in rows if r.get("session") == "S2"),
                key=lambda r: r.get("turn") if isinstance(r.get("turn"), int) else 0)
    ok2 = [r for r in s2 if r.get("status") == "ok"]
    if len(s2) != len(ok2):
        _warn(warnings, "%s: %d 个 S2 回合 status 非 ok——从 M4 分母剔除" % (tag, len(s2) - len(ok2)))
    if not ok2:
        _warn(warnings, "%s: 没有可评的 S2 回合——M4 记 null（存续会话缺失必须大声）" % tag)
        return None, 0, 0, 0
    probe_a, probe_b = _pick_probes(ok2)
    passed, probes, unscored = 0, 0, 0

    if probe_a is not None:
        wid = meta.get("wrong_id")
        gist = (course_cfg.get("gist") or {}).get(str(wid), []) if wid is not None else []
        if wid in (None, ""):
            unscored += 1
            _warn(warnings, "%s: meta.wrong_id 缺失——错题探针不可评" % tag)
        else:
            probes += 1
            ans = probe_a.get("assistant") or ""
            if _id_hit(wid, ans) or (gist and _coverage(gist, ans) >= COVERAGE_THRESHOLD):
                passed += 1
    else:
        _warn(warnings, "%s: S2 缺「上次错了哪题」探针回合" % tag)

    if probe_b is not None:
        questions = meta.get("questions") if isinstance(meta.get("questions"), list) else []
        q1 = course_cfg.get("reshow_question") or (questions[0] if questions else None)
        kws = (course_cfg.get("keywords") or {}).get(str(q1)) if q1 is not None else None
        if not kws:
            unscored += 1
            _warn(warnings, "%s: config 缺题 %r 的 keywords——「再看一眼」探针不可评"
                  "（不硬造 0 分也不假装满分）" % (tag, q1))
        else:
            probes += 1
            if _coverage(kws, probe_b.get("assistant") or "") >= COVERAGE_THRESHOLD:
                passed += 1
    else:
        _warn(warnings, "%s: S2 缺「再给我看一眼」探针回合" % tag)

    if probes == 0:
        _warn(warnings, "%s: M4 无可评探针——记 null" % tag)
        return None, 0, 0, unscored
    return passed / probes, passed, probes, unscored


# ---------------- M5 交付物完备性 ----------------

def _notebook_index_ok(ws, anchor_cache):
    idx = os.path.join(ws, "notebook", "index.md")
    if not os.path.isfile(idx):
        return 0
    try:
        with open(idx, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return 0
    links = _INDEX_LINK_RE.findall(text)
    if len(links) < MIN_NOTEBOOK_ENTRIES:
        return 0
    nb_dir = os.path.join(ws, "notebook")
    for fname, anchor in links:
        full = _resolve_rel_file(nb_dir, fname)
        if not full:
            return 0
        frag = unquote(anchor[1:]) if anchor else ""
        if frag:
            aset = _anchors_cached(full, anchor_cache)
            if aset is None or frag not in aset:
                return 0
    return 1


def _mistakes_entry_ok(ws, wrong_id):
    """交付物存在性：错题本里**有真实错题条目块**（任一 chNN.md 里有 `## [#…]` 条目，fence-aware）。
    不再要求 id == 内部金标 wrong_id——技能按语义命名条目（'toxo-cat-…'）而非 benchmark 内部 id，
    「记录的是否恰为那道错题」已由 M4 存续探针（内容回忆）验证；本项只问「错题本非空」。"""
    d = os.path.join(ws, "mistakes")
    if not os.path.isdir(d):
        return 0
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md") or name == "index.md":
            continue
        try:
            with open(os.path.join(d, name), "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        fence = None
        for line in text.splitlines():
            fence, marker = _nb._fence_step(fence, line)
            if marker or fence is not None:
                continue
            if _nb._HEAD_RE.match(line):      # 任一真实条目块 = 错题本已落盘（非空）
                return 1
    return 0


def score_m5(ws, meta, warnings, tag):
    """(m5|None, checklist)。ws 不可用 → 全 null；html-degraded mock → PDF 项 skip-not-fail。"""
    if ws is None:
        _warn(warnings, "%s: workspace 不可用——M5 无法清点交付物，记 null" % tag)
        return None, {k: None for k in CHECKLIST_ITEMS}
    checklist, anchor_cache = {}, {}
    checklist["notebook_index"] = _notebook_index_ok(ws, anchor_cache)
    checklist["mistakes_entry"] = _mistakes_entry_ok(ws, meta.get("wrong_id"))
    cs_md = os.path.join(ws, "cheatsheet.md")
    if os.path.isfile(cs_md):
        errors, _w, _st = _vw.validate(ws)
        checklist["cheatsheet_md"] = 1 if not errors else 0
        if errors:
            _warn(warnings, "%s: validate_workspace 报 %d 个错误——cheatsheet_md 记 0（首错：%s）"
                  % (tag, len(errors), errors[0].get("msg", "")[:120]))
    else:
        checklist["cheatsheet_md"] = 0
    degraded = meta.get("mock") == "html-degraded" or meta.get("html_degraded") is True
    if degraded:
        checklist["cheatsheet_pdf"] = None      # skip-not-fail：驱动器声明了无浏览器降级
        _warn(warnings, "%s: meta 声明 html-degraded——cheatsheet_pdf 跳过不计（非失败）" % tag)
    else:
        pages = meta.get("cheatsheet_pages")
        if not (isinstance(pages, int) and not isinstance(pages, bool) and pages >= 1):
            pages = DEFAULT_PAGES
        pdf = os.path.join(ws, "cheatsheet.pdf")
        ok = 0
        if os.path.isfile(pdf):
            try:
                got = _cr.pdf_page_count(pdf)
                ok = 1 if got == pages else 0
                if not ok:
                    _warn(warnings, "%s: cheatsheet.pdf %d 页（目标 %d）——记 0" % (tag, got, pages))
            except OSError as e:
                _warn(warnings, "%s: cheatsheet.pdf 无法读取（%s）——记 0" % (tag, e))
        checklist["cheatsheet_pdf"] = ok
    scored = [v for v in checklist.values() if v is not None]
    return (sum(scored) / len(scored) if scored else None), checklist


# ---------------- M6 成本 ----------------

def score_m6(rows):
    costs = [r.get("cost_usd") for r in rows
             if isinstance(r.get("cost_usd"), (int, float)) and not isinstance(r.get("cost_usd"), bool)]
    total = _r6(sum(costs)) if costs else None
    per = _r6(sum(costs) / len(costs)) if costs else None
    n_quota = sum(1 for r in rows if r.get("status") == "quota_stop")
    return total, per, len(rows), n_quota


# ---------------- 组装 ----------------

def score_arm(arm_dir, course, arm, config, results_dir, warnings):
    tag = "%s_%s" % (course, arm)
    rows = _read_sessions(os.path.join(arm_dir, SESSIONS_NAME))
    meta = _read_json(os.path.join(arm_dir, META_NAME))
    if not isinstance(meta, dict):
        _die("%s/meta.json 顶层必须是对象" % arm_dir)
    if not rows:
        _warn(warnings, "%s: sessions.jsonl 是空的——所有指标按缺数据处理" % tag)
    for r in rows[:1]:
        if r.get("course") != course or r.get("arm") != arm:
            _warn(warnings, "%s: 行内 course/arm（%r/%r）与目录名不符——按目录名计分"
                  % (tag, r.get("course"), r.get("arm")))
    unknown = sorted({str(r.get("status")) for r in rows} - STATUSES)
    if unknown:
        _warn(warnings, "%s: 未知 status 值 %s（冻结接口只有 ok/infra_error/quota_stop）"
              % (tag, unknown))

    bases = (arm_dir, results_dir, ROOT, os.getcwd())
    ws = _resolve_dir(meta.get("workspace"), bases)
    if ws is None:
        _warn(warnings, "%s: meta.workspace=%r 解析不到目录" % (tag, meta.get("workspace")))
    materials = _resolve_dir(meta.get("materials"), bases)

    course_cfg = config.get(course) if isinstance(config.get(course), dict) else {}
    m1, m1_v, m1_c = score_m1(rows, ws, materials, warnings, tag)
    m4, m4_p, m4_n, m4_u = score_m4(rows, meta, course_cfg, warnings, tag)
    m5, checklist = score_m5(ws, meta, warnings, tag)
    m6_total, m6_per, n_turns, n_quota = score_m6(rows)
    return {
        "m1": _r4(m1), "m1_verified": m1_v, "m1_claims": m1_c,
        "m4": _r4(m4), "m4_passed": m4_p, "m4_probes": m4_n, "m4_unscored": m4_u,
        "m5": _r4(m5), "m5_checklist": checklist,
        "m6_total_usd": m6_total, "m6_per_turn": m6_per,
        "n_turns": n_turns, "n_quota_stops": n_quota,
    }


def _gap(skill_val, bare_val):
    if isinstance(skill_val, (int, float)) and not isinstance(skill_val, bool) \
            and isinstance(bare_val, (int, float)) and not isinstance(bare_val, bool):
        return _r6(skill_val - bare_val)
    return None


def collect_runs(results_dir, warnings):
    runs = {}
    for name in sorted(os.listdir(results_dir)):
        d = os.path.join(results_dir, name)
        if not os.path.isdir(d) or "_" not in name:
            continue
        course, arm = name.rsplit("_", 1)
        if arm not in ARMS or not course:
            continue
        if not os.path.isfile(os.path.join(d, SESSIONS_NAME)):
            _warn(warnings, "%s: 缺 %s——该臂没跑完/没跑，跳过" % (name, SESSIONS_NAME))
            continue
        if not os.path.isfile(os.path.join(d, META_NAME)):
            _warn(warnings, "%s: 缺 %s——冻结接口不完整，跳过该臂" % (name, META_NAME))
            continue
        runs.setdefault(course, {})[arm] = d
    return runs


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="loop benchmark 确定性判分（M1 溯源 / M4 存续 / M5 交付物 / M6 成本）")
    ap.add_argument("--results", required=True, help="loop 结果目录（含 <course>_<arm>/ 子目录）")
    ap.add_argument("--out", required=True, help="summary_loop.json 输出路径")
    ap.add_argument("--config", default=None,
                    help="按题关键词 config（默认 <results>/loop_config.json，可缺省）")
    args = ap.parse_args(argv)

    results_dir = os.path.abspath(args.results)
    if not os.path.isdir(results_dir):
        _die("results 目录不存在: %s" % results_dir)

    warnings = []
    if args.config is not None:
        if not os.path.isfile(args.config):
            _die("--config 指定的文件不存在: %s" % args.config)
        config = _read_json(args.config)
    else:
        default_cfg = os.path.join(results_dir, "loop_config.json")
        config = _read_json(default_cfg) if os.path.isfile(default_cfg) else {}
        if not config:
            _warn(warnings, "未提供关键词 config（--config / <results>/loop_config.json）——"
                  "M4「再看一眼」探针将不可评")
    if not isinstance(config, dict):
        _die("config 顶层必须是对象 {course: {gist/keywords/reshow_question}}")

    runs = collect_runs(results_dir, warnings)
    if not runs:
        _die("在 %s 下没找到任何 <course>_<arm>/%s——先跑 loop_bench 驱动器"
             % (results_dir, SESSIONS_NAME))

    summary = {}
    for course in sorted(runs):
        entry = {}
        for arm in ARMS:
            if arm in runs[course]:
                entry[arm] = score_arm(runs[course][arm], course, arm, config,
                                       results_dir, warnings)
            else:
                _warn(warnings, "课程 %s 缺 %s 臂——gap 全记 null（对照不完整必须大声）"
                      % (course, arm))
        skill_r, bare_r = entry.get("skill") or {}, entry.get("bare") or {}
        entry["gap"] = {k: _gap(skill_r.get(k), bare_r.get(k)) for k in GAP_KEYS}
        summary[course] = entry
    summary["_warnings"] = warnings

    out_path = os.path.abspath(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, out_path)

    print("[loop_score] %s" % out_path)
    for course in sorted(runs):
        for arm in ARMS:
            r = summary[course].get(arm)
            if not r:
                continue
            print("  %-24s m1=%-6s m4=%-6s m5=%-6s cost=%s (%d turns, %d quota_stop)"
                  % ("%s/%s" % (course, arm), r["m1"], r["m4"], r["m5"],
                     r["m6_total_usd"], r["n_turns"], r["n_quota_stops"]))
        print("  %-24s %s" % ("%s/gap" % course,
                              " ".join("%s=%s" % (k, v) for k, v in summary[course]["gap"].items())))
    if warnings:
        print("[loop_score] %d 条告警（详见 stderr 与 _warnings）" % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
