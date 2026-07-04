#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mastery-aware hard-question selector (A7) — order questions by difficulty × 本人掌握状态 × A6 学习模式.

honest scope: this is DETERMINISTIC heuristic ordering, not LLM relevance ranking. Difficulty comes from
score_difficulty.py (a structural lower bound — see that file); mastery comes from study_state.json (A4:
错题/疑难/知识点窗口). No network, no LLM.

per-item mastery class (A4 state):
  · weak      本题 id 在 mistake_archive / 本题章节有错题或疑难 / 章节或知识点在"窗口外"
  · mastered  本题章节或知识点在"在窗口/已实测"（且不 weak）
  · neutral   其余

ordering (A6 mode，接 A6 的三学习模式)：
  · 查缺补漏（默认）   weak 先（先易后难巩固）→ neutral（先难）→ mastered（先难挑战）
  · 零基础从头讲       全局先易后难（新手绝不 hard-first），weak 仍排最前
  · 某章起步补弱       同查缺补漏，但先按 --from-chapter 收敛到起步章及之后

    python scripts/select_hard_questions.py --workspace <ws> -n 10
    python scripts/select_hard_questions.py --workspace <ws> -n 10 --mode 零基础从头讲
    python scripts/select_hard_questions.py --workspace <ws> --from-chapter 3 --json

若题库尚未评分（无 difficulty 字段），本工具会即时用 score_difficulty 的启发式补算（不落盘）。
exit: 0 ok · 2 bad input/usage
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_difficulty as sd            # noqa: E402  同目录，复用打分与题库加载
from select_questions import SOURCE_TYPES  # noqa: E402  单一 source_type 词表，与 A2 一致
from update_progress import _normalize_mode  # noqa: E402  复用 A6 旧模式迁移（panic→零基础 等），口径统一

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

STATE_NAME = "study_state.json"
LEARNING_MODES = ("零基础从头讲", "某章起步补弱", "查缺补漏")
_MIXED_SCOPES = {None, "", "混合题池", "mixed", "混合"}   # 非限制性范围——不过滤
# 已订正/已解决的错题、已回顾的疑难不再算薄弱——否则查缺补漏会把「已经拿下的」永远顶在最前，
# 挤掉仍待复盘的真薄弱点（错题走 待复盘→已订正/已复盘/已解决；疑难走 待回顾→已回顾）。
_MISTAKE_RESOLVED = {"已订正", "已复盘", "已解决"}
_CONFUSION_RESOLVED = {"已回顾"}


def _die(msg, code=2):
    sys.stderr.write("select_hard_questions: " + msg + "\n")
    raise SystemExit(code)


def _parse_source_types(raw):
    """把 '--source-type homework,exam' 解析成校验过的集合（与 A2 select_questions 同语义）。
    显式空过滤（'' 或 ','）是用法错误——绝不静默退回混合池（引号/模板拼错会整场无题）。"""
    vals = [v.strip() for v in raw.split(",") if v.strip()]
    if not vals:
        _die("--source-type 不能为空（'' 或 ','）——显式空过滤视为用法错误，"
             "不写就是混合池，别用空串静默清空（与 A2 select_questions 一致）")
    bad = [v for v in vals if v not in SOURCE_TYPES]
    if bad:
        _die("非法 source_type: %s（应为 %s）" % (", ".join(bad), sorted(SOURCE_TYPES)))
    return set(vals)


def _scope_to_source_types(scope):
    """把存档的范围偏好映射到 source_type 集合。返回 None 表示不过滤（混合池）。
    非混合但映射不出干净 source_type 时 fail-loud——绝不静默放宽被记录的范围（A2 契约）。"""
    if scope in _MIXED_SCOPES:
        return None
    norm = str(scope).strip().lower()
    for suf in ("-only", "_only", " only", "-仅", "仅"):
        if norm.endswith(suf):
            norm = norm[: -len(suf)].strip()
    if norm in SOURCE_TYPES:
        return {norm}
    _die("study_state 记录了范围偏好「%s」，但无法自动映射到 source_type；"
         "请显式传 --source-type <%s>，或先解除范围偏好——避免静默越界（A2 范围契约）"
         % (scope, "/".join(sorted(SOURCE_TYPES))))


def load_state(ws):
    path = os.path.join(ws, STATE_NAME)
    # A4 事实源不得为符号链接：断链会被静默当无状态，外指链接会把工作区外的 JSON 当成掌握状态读进来
    # ——都会悄悄改变出题排序。与 update_progress / 校验器同口径 fail-loud（先于 isfile 判断）。
    if os.path.islink(path):
        _die("study_state.json 不得为符号链接（A4 事实源，可能指向工作区外）——拒绝读取")
    if not os.path.isfile(path):
        return None
    ws_real = os.path.normcase(os.path.realpath(ws))
    real = os.path.normcase(os.path.realpath(path))
    if real != ws_real and not real.startswith(ws_real + os.sep):
        _die("study_state.json 经符号链接 / 父目录逃出工作区——拒绝读取（realpath 归属校验失败）")
    try:
        with open(path, "r", encoding="utf-8") as f:
            st = json.load(f)
    except ValueError as e:
        _die("study_state.json 不是合法 JSON: %s" % e)
    if not isinstance(st, dict):
        _die("study_state.json 顶层必须是对象")
    return st


def _chapter_key(q):
    """展示用的主章号：chapter 优先，回落 phase。"""
    for k in ("chapter", "phase"):
        v = q.get(k)
        if v is not None:
            return str(v)
    return None


def _chapter_keys(q):
    """匹配用的章号集合：chapter 与 phase 都算（与 A2 select_questions 的 chapter-OR-phase 一致）。"""
    return {str(q.get(k)) for k in ("chapter", "phase") if q.get(k) is not None}


def _numeric_chapters(q):
    """chapter 与 phase 里所有数值章号（--from-chapter 范围用；双标 {chapter:1,phase:3} 两个都算，
    否则 phase-3 的题会被当成 chapter-1 错误剔除——与 chapter-OR-phase 口径一致）。"""
    out = set()
    for k in ("chapter", "phase"):
        v = q.get(k)
        if v is not None:
            m = re.search(r"\d+", str(v))
            if m:
                out.add(int(m.group(0)))
    return out


def _item_points(q):
    kps = q.get("knowledge_points")
    return [str(k).strip() for k in kps if str(k).strip()] if isinstance(kps, list) else []


def build_mastery(state):
    """把 study_state 拆成掌握索引；state 为 None 时返回空索引（全 neutral）。"""
    idx = {"mistake_ids": set(), "trouble_ch": set(),
           "weak_ch": set(), "weak_pt": set(), "strong_ch": set(), "strong_pt": set()}
    if not state:
        return idx
    for m in state.get("mistake_archive") or []:
        if isinstance(m, dict) and m.get("status") not in _MISTAKE_RESOLVED:   # 已订正的错题不再算薄弱
            if m.get("id"):
                idx["mistake_ids"].add(str(m["id"]))
            if m.get("chapter") is not None:
                idx["trouble_ch"].add(str(m["chapter"]))
    for c in state.get("confusion_log") or []:
        if (isinstance(c, dict) and c.get("chapter") is not None
                and c.get("status") not in _CONFUSION_RESOLVED):              # 已回顾的疑难不再算薄弱
            idx["trouble_ch"].add(str(c["chapter"]))
    for w in state.get("knowledge_window") or []:
        if not isinstance(w, dict):
            continue
        status = w.get("status") or "在窗口"
        ch = str(w["chapter"]) if w.get("chapter") is not None else None
        pt = str(w["point"]).strip() if w.get("point") else None
        if status == "窗口外":
            if ch:
                idx["weak_ch"].add(ch)
            if pt:
                idx["weak_pt"].add(pt)
        elif status in ("在窗口", "已实测"):
            if ch:
                idx["strong_ch"].add(ch)
            if pt:
                idx["strong_pt"].add(pt)
    return idx


def _pt_hit(item_pts, pt_set):
    """知识点双向子串匹配（窗口条目的 point 与题目 knowledge_points 互为子串即命中）。"""
    for ip in item_pts:
        for wp in pt_set:
            if ip and wp and (ip in wp or wp in ip):
                return True
    return False


def classify(q, idx):
    """返回 (cls, trigger)：cls ∈ {weak, mastered, neutral}，trigger 为命中原因短标签。"""
    qid = str(q.get("id"))
    chs = _chapter_keys(q)
    pts = _item_points(q)
    if qid in idx["mistake_ids"]:
        return "weak", "错题"
    if chs & idx["trouble_ch"]:
        return "weak", "本章有错题/疑难"
    if chs & idx["weak_ch"]:
        return "weak", "窗口外(章)"
    if _pt_hit(pts, idx["weak_pt"]):
        return "weak", "窗口外(点)"
    if (chs & idx["strong_ch"]) or _pt_hit(pts, idx["strong_pt"]):
        return "mastered", "在窗口/已实测"
    return "neutral", "常规"


_CLASS_RANK = {"weak": 0, "neutral": 1, "mastered": 2}
_CLASS_REASON = {
    "weak": "薄弱巩固·先易后难",
    "mastered": "已掌握·挑战(先难)",
    "neutral": "常规",
}


def order_items(scored, mode):
    """scored: list of dict(id, difficulty, cls, trigger, chapter, orig_idx). 返回排序后的新列表。"""
    def key(it):
        rank = _CLASS_RANK[it["cls"]]
        if mode == "零基础从头讲":
            # 新手：难度优先（全局先易后难），掌握类别仅作同难度内的次序 tiebreak——
            # 绝不让一道 weak 的难题排到简单题前面（那正是本模式要避免的 hard-first）。
            return (it["difficulty"], rank, it["orig_idx"])
        # 其余模式：先按掌握类别（weak→neutral→mastered），weak 内先易后难、其余先难。
        d = it["difficulty"] if it["cls"] == "weak" else -it["difficulty"]
        return (rank, d, it["orig_idx"])
    return sorted(scored, key=key)


def main(argv=None):
    ap = argparse.ArgumentParser(description="按难度 × 掌握状态 × A6 模式出题（A7）")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("-n", "--num", type=int, default=10, help="出题数量（默认 10）")
    ap.add_argument("--mode", choices=LEARNING_MODES, default=None,
                    help="A6 学习模式；缺省时读 study_state.mode，再缺省按 查缺补漏")
    ap.add_argument("--chapter", default=None, help="只出该章（chapter 或 phase 精确匹配）")
    ap.add_argument("--from-chapter", type=int, default=None,
                    help="只出该数值章号及之后（某章起步补弱用；缺省时从 study_state.current_phase 推）")
    ap.add_argument("--source-type", default=None,
                    help="按来源类型过滤（逗号分隔，与 A2 一致）；缺省时读 study_state.scope，未标签项一律排除")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    bank = sd.load_bank(args.workspace)
    items = [q for q in bank if isinstance(q, dict) and q.get("id") is not None]
    state = load_state(args.workspace)
    raw_mode = args.mode or (state or {}).get("mode")
    mode = _normalize_mode(raw_mode)[0] if raw_mode else "查缺补漏"   # panic→零基础 等旧模式迁移，与 A6 同口径
    if mode not in LEARNING_MODES:
        mode = "查缺补漏"                                # 仍非标准（未知串）→ 回落默认，不炸
    idx = build_mastery(state)
    late = sd._late_chapter_cutoff(items)
    notes = []

    # 范围过滤（A2 契约）：显式 --source-type 优先；否则按存档 scope 推导——非混合但推不出即 fail-loud。
    if args.source_type is not None:
        source_types = _parse_source_types(args.source_type)
    else:
        source_types = _scope_to_source_types((state or {}).get("scope"))
        if source_types:
            notes.append("已按存档范围 scope→source_type=%s（未标签项排除）" % "/".join(sorted(source_types)))

    # 某章起步补弱：起步章缺省时从 current_phase 推；推不出且未给 --from-chapter 即 fail-loud（不静默扫全库）。
    from_chapter = args.from_chapter
    if mode == "某章起步补弱" and from_chapter is None:
        cp = (state or {}).get("current_phase")
        if isinstance(cp, int) and not isinstance(cp, bool):
            from_chapter = cp
        elif isinstance(cp, str) and cp.strip().isdigit():
            from_chapter = int(cp.strip())
        else:
            _die("某章起步补弱 需要起步章：请传 --from-chapter <N>，"
                 "或让 study_state 带数值 current_phase——否则会退化成全库扫描，违背本模式的按章补弱")
        notes.append("某章起步补弱：起步章默认为 current_phase=%d（可用 --from-chapter 覆盖）" % from_chapter)

    scored = []
    untagged_excluded = 0                                # A2 契约：未标签项被范围排除必须"排除并如实上报"
    for i, q in enumerate(items):
        if args.chapter is not None and str(args.chapter) not in _chapter_keys(q):
            continue
        if from_chapter is not None:
            nums = _numeric_chapters(q)                   # chapter 与 phase 都算（双标不误剔）
            if not any(n >= from_chapter for n in nums):
                continue
        if source_types is not None and q.get("source_type") not in source_types:
            # 只统计"除范围外其余过滤都命中"的未标签题——它们才是被 scope 悄悄藏掉的真实候选
            # （露出摄取/打标缺口，正如 select_questions.py 会上报的那样）。
            if q.get("source_type") is None:
                untagged_excluded += 1
            continue                                     # 未标签一律排除，绝不静默越界
        d = q.get("difficulty")
        if not (isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 5):
            d = sd.score_item(q, late)[0]                # 题库未评分 → 即时补算，不落盘
        cls, trig = classify(q, idx)
        scored.append({"id": q.get("id"), "difficulty": d, "cls": cls, "trigger": trig,
                       "chapter": _chapter_key(q), "orig_idx": i})

    ordered = order_items(scored, mode)[: max(args.num, 0)]
    if source_types is not None and untagged_excluded:
        notes.append("范围过滤排除了 %d 道未标签(source_type 缺失)题——可能是摄取/打标缺口，"
                     "别当作没有这些题（A2 契约：排除并上报）" % untagged_excluded)

    payload = [{"id": it["id"], "difficulty": it["difficulty"], "class": it["cls"],
                "chapter": it["chapter"],
                "select_reason": "%s（%s）" % (_CLASS_REASON[it["cls"]], it["trigger"])}
               for it in ordered]

    if args.json:
        print(json.dumps({"mode": mode, "count": len(payload),
                          "state_loaded": state is not None,
                          "source_types": sorted(source_types) if source_types else None,
                          "untagged_excluded": untagged_excluded,
                          "from_chapter": from_chapter, "notes": notes, "items": payload},
                         ensure_ascii=False, indent=2))
    else:
        print("[A7] 模式=%s｜%s｜选出 %d 题（难度×掌握状态启发式排序，非 LLM）"
              % (mode, "已读 study_state" if state is not None else "无 state（全按常规）", len(payload)))
        for note in notes:
            print("    · " + note)
        for it in payload:
            print("  %-16s d=%d  %-8s  %s" % (it["id"], it["difficulty"], it["class"], it["select_reason"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
