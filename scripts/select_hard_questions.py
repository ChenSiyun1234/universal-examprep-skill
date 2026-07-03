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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_difficulty as sd   # noqa: E402  同目录，复用打分与题库加载

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

STATE_NAME = "study_state.json"
LEARNING_MODES = ("零基础从头讲", "某章起步补弱", "查缺补漏")


def _die(msg, code=2):
    sys.stderr.write("select_hard_questions: " + msg + "\n")
    raise SystemExit(code)


def load_state(ws):
    path = os.path.join(ws, STATE_NAME)
    if not os.path.isfile(path):
        return None
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
        if isinstance(m, dict):
            if m.get("id"):
                idx["mistake_ids"].add(str(m["id"]))
            if m.get("chapter") is not None:
                idx["trouble_ch"].add(str(m["chapter"]))
    for c in state.get("confusion_log") or []:
        if isinstance(c, dict) and c.get("chapter") is not None:
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
            d = it["difficulty"]                         # 全局先易后难
        else:
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
                    help="只出该数值章号及之后（某章起步补弱用）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    bank = sd.load_bank(args.workspace)
    items = [q for q in bank if isinstance(q, dict) and q.get("id") is not None]
    state = load_state(args.workspace)
    mode = args.mode or (state or {}).get("mode") or "查缺补漏"
    if mode not in LEARNING_MODES:
        mode = "查缺补漏"                                # state 里可能是旧模式串——回落默认，不炸
    idx = build_mastery(state)
    late = sd._late_chapter_cutoff(items)

    scored = []
    for i, q in enumerate(items):
        if args.chapter is not None and str(args.chapter) not in _chapter_keys(q):
            continue
        if args.from_chapter is not None:
            nc = sd._numeric_chapter(q)
            if nc is None or nc < args.from_chapter:
                continue
        d = q.get("difficulty")
        if not (isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 5):
            d = sd.score_item(q, late)[0]                # 题库未评分 → 即时补算，不落盘
        cls, trig = classify(q, idx)
        scored.append({"id": q.get("id"), "difficulty": d, "cls": cls, "trigger": trig,
                       "chapter": _chapter_key(q), "orig_idx": i})

    ordered = order_items(scored, mode)[: max(args.num, 0)]

    payload = [{"id": it["id"], "difficulty": it["difficulty"], "class": it["cls"],
                "chapter": it["chapter"],
                "select_reason": "%s（%s）" % (_CLASS_REASON[it["cls"]], it["trigger"])}
               for it in ordered]

    if args.json:
        print(json.dumps({"mode": mode, "count": len(payload),
                          "state_loaded": state is not None, "items": payload},
                         ensure_ascii=False, indent=2))
    else:
        print("[A7] 模式=%s｜%s｜选出 %d 题（难度×掌握状态启发式排序，非 LLM）"
              % (mode, "已读 study_state" if state is not None else "无 state（全按常规）", len(payload)))
        for it in payload:
            print("  %-16s d=%d  %-8s  %s" % (it["id"], it["difficulty"], it["class"], it["select_reason"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
