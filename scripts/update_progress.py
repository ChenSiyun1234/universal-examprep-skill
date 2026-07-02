#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Structured progress state (A4) — study_state.json is the SINGLE SOURCE OF TRUTH;
study_progress.md becomes a GENERATED human-readable view.

Why: hand-patching study_progress.md caused mojibake (GBK writes), patch-mismatch drift and
silently-lost rows in real sessions (EEC160 report #7). All mutations now go through this official
tool: it writes study_state.json (explicit UTF-8, atomic temp+rename) and re-renders the Markdown
view from it. A write failure is FAIL-LOUD (non-zero exit + message) — never silently "updated".

    python scripts/update_progress.py --workspace <ws> init                # migrate md → json (once)
    python scripts/update_progress.py --workspace <ws> set --phase 3
    python scripts/update_progress.py --workspace <ws> set --scope homework-only --mode 查缺补漏
    python scripts/update_progress.py --workspace <ws> add-mistake --id hw_hw1_3 --chapter 2 --note "Venn 阴影判断错"
    python scripts/update_progress.py --workspace <ws> add-confusion --chapter 1 --note "循环队列取模"
    python scripts/update_progress.py --workspace <ws> render               # json → md（修复被手改的 md）
    python scripts/update_progress.py --workspace <ws> show                 # 打印当前状态 JSON

Backward compatible: a workspace WITHOUT study_state.json keeps working (no-Python fallback:
hand-written study_progress.md still validates); `init` adopts the existing md losslessly
(phase + mistake/confusion rows, both bullet and ingest-template table forms).
Exit codes: 0 ok · 1 write/render failure · 2 bad input/usage.
"""
import argparse
import datetime
import json
import os
import re
import sys

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

STATE_NAME = "study_state.json"
MD_NAME = "study_progress.md"
SCHEMA_VERSION = 1


def _die(msg, code=2):
    sys.stderr.write("update_progress: " + msg + "\n")
    raise SystemExit(code)


def default_state():
    return {"version": SCHEMA_VERSION, "current_phase": 1, "scope": None, "mode": None,
            "time_budget": None, "language": None, "preferences": {},
            "mistake_archive": [], "confusion_log": [], "knowledge_window": [],
            "last_updated": None}


# ---------------- md → state (migration; tolerant of both bullet and table forms) ----------------

_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|?\s*$")
_HDR_WORDS = ("错题id", "关联章节", "题目内容", "错误原因", "序号", "疑难点", "解答要点", "状态")
_PLACEHOLDER = re.compile(r"（暂无）|（无）|（清空重来）")


def parse_md(text):
    """Lossless-enough adoption of an existing study_progress.md: phase + mistake/confusion rows."""
    t = text or ""
    pm = re.search(r"(?:当前进行阶段|当前阶段|current\s*phase)\D*?(\d+)", t, re.I)
    phase = int(pm.group(1)) if pm else 1
    mistakes, confusions, cur = [], [], None
    for ln in t.splitlines():
        h = ln.strip()
        is_heading = bool(re.match(r"^\s{0,3}(#{1,4}\s|\*\*)", ln))
        if is_heading and re.search(r"错题|mistake", h, re.I):
            cur = mistakes
            continue
        if is_heading and re.search(r"疑难|困惑|confusion", h, re.I):
            cur = confusions
            continue
        if re.match(r"^\s{0,3}#{1,4}\s", ln):
            cur = None
            continue
        if cur is None or _PLACEHOLDER.search(h):
            continue
        if re.match(r"^\s*[-*]\s+\S", ln):
            ids = re.findall(r"\[#([^\]\s]+)\]", h)
            cur.append({"id": ids[0] if ids else None, "chapter": None,
                        "note": re.sub(r"^\s*[-*]\s+", "", h), "status": "待复盘"})
        elif h.startswith("|") and not _TABLE_SEP.match(ln):
            low = h.lower()
            if sum(1 for w in _HDR_WORDS if w in low) >= 2:
                continue
            cells = [c.strip(" *`") for c in h.strip("|").split("|")]
            if not any(c and c != "-" for c in cells):
                continue
            ids = re.findall(r"\[#([^\]\s]+)\]", h)
            cur.append({"id": ids[0] if ids else (cells[0] or None), "chapter": cells[1] if len(cells) > 1 else None,
                        "note": " / ".join(c for c in cells[2:] if c) or (cells[0] if cells else ""),
                        "status": cells[-1] if cells else "待复盘"})
    return phase, mistakes, confusions


# ---------------- state → md (generated view; keeps validator/T4-parseable shape) ----------------

def render_md(state):
    def _tbl(rows, headers):
        out = ["| " + " | ".join(headers) + " |",
               "| " + " | ".join(":---" for _ in headers) + " |"]
        if not rows:
            out.append("| " + " | ".join("（暂无）" if i == 0 else "-" for i in range(len(headers))) + " |")
        for r in rows:
            rid = ("[#%s]" % r["id"]) if r.get("id") else "-"
            out.append("| %s | %s | %s | %s |" % (rid, r.get("chapter") or "-",
                                                  (r.get("note") or "").replace("|", "/"),
                                                  r.get("status") or "待复盘"))
        return "\n".join(out)

    lines = [
        "# 🎯 复习进度与错题档案（由 study_state.json 自动生成——请勿手改本文件，改动会在下次渲染时丢失）",
        "",
        "## ⏱️ 当前复习断点",
        "* **当前进行阶段**：阶段 %d" % state["current_phase"],
        "* **范围/模式**：%s ｜ %s ｜ 时间预算 %s" % (state.get("scope") or "混合题池",
                                                     state.get("mode") or "未设定",
                                                     state.get("time_budget") or "未设定"),
        "* **最后更新时间**：%s" % (state.get("last_updated") or "-"),
        "",
        "## ❌ 错题档案记录",
        _tbl(state["mistake_archive"], ("错题ID", "关联章节", "错误原因分析", "状态")),
        "",
        "## 💡 概念疑难点记录",
        _tbl(state["confusion_log"], ("疑难ID", "关联章节", "疑难点", "状态")),
        "",
    ]
    if state.get("preferences"):
        lines += ["## ⚙️ 偏好（讲解风格等）",
                  "\n".join("- %s: %s" % (k, v) for k, v in sorted(state["preferences"].items())), ""]
    return "\n".join(lines)


# ---------------- IO (explicit UTF-8, atomic, fail-loud) ----------------

def load_state(ws):
    path = os.path.join(ws, STATE_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            st = json.load(f)
    except UnicodeDecodeError as e:
        _die("study_state.json 不是 UTF-8（%s）——状态文件已损坏，请从 study_progress.md 重新 init" % e, 1)
    except ValueError as e:
        _die("study_state.json 不是合法 JSON: %s" % e, 1)
    if not isinstance(st, dict):
        _die("study_state.json 顶层必须是对象", 1)
    return st


def save(ws, state, note):
    """Atomic UTF-8 write of BOTH the state json and the rendered md. Any failure is fail-loud."""
    state["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for name, content in ((STATE_NAME, json.dumps(state, ensure_ascii=False, indent=2)),
                          (MD_NAME, render_md(state))):
        path = os.path.join(ws, name)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(tmp, path)
        except OSError as e:
            _die("写入 %s 失败：%s——进度未更新，请告知用户（绝不静默继续）" % (name, e), 1)
    print("[+] %s（state + md 已同步更新）" % note)


# ---------------- commands ----------------

def cmd_init(ws, args):
    path = os.path.join(ws, STATE_NAME)
    if os.path.isfile(path) and not args.force:
        _die("study_state.json 已存在（init 幂等保护）；确要从 md 重建请加 --force")
    md_path = os.path.join(ws, MD_NAME)
    phase, mistakes, confusions = 1, [], []
    if os.path.isfile(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError as e:
            _die("study_progress.md 不是 UTF-8（%s）——这正是结构化状态要根治的乱码；"
                 "请先把 md 转存为 UTF-8 再 init（不要猜编码静默迁移）" % e, 1)
        phase, mistakes, confusions = parse_md(text)
    st = default_state()
    st.update({"current_phase": phase, "mistake_archive": mistakes, "confusion_log": confusions})
    save(ws, st, "init：从 %s 迁移（阶段 %d，错题 %d，疑难 %d）"
         % (MD_NAME if os.path.isfile(md_path) else "空白", phase, len(mistakes), len(confusions)))
    return 0


def _require_state(ws):
    st = load_state(ws)
    if st is None:
        _die("尚无 study_state.json——先跑 `update_progress.py --workspace <ws> init` 迁移")
    return st


def cmd_set(ws, args):
    st = _require_state(ws)
    changed = []
    if args.phase is not None:
        if args.phase < 1:
            _die("--phase 必须 ≥ 1")
        st["current_phase"] = args.phase
        changed.append("phase=%d" % args.phase)
    for k in ("scope", "mode", "time_budget", "language"):
        v = getattr(args, k)
        if v is not None:
            st[k] = v or None
            changed.append("%s=%s" % (k, v or "（清除）"))
    for kv in (args.pref or []):
        if "=" not in kv:
            _die("--pref 需要 key=value 形式，当前 %r" % kv)
        k, v = kv.split("=", 1)
        st.setdefault("preferences", {})[k.strip()] = v.strip()
        changed.append("pref %s" % k.strip())
    if not changed:
        _die("set 没有任何改动参数（--phase/--scope/--mode/--time-budget/--language/--pref）")
    save(ws, st, "set：" + "、".join(changed))
    return 0


def cmd_add(ws, args, field, label):
    st = _require_state(ws)
    if not (args.note or "").strip():
        _die("--note 不能为空")
    row = {"id": args.id, "chapter": args.chapter, "note": args.note.strip(), "status": "待复盘"}
    st[field].append(row)
    save(ws, st, "%s +1（共 %d 条）" % (label, len(st[field])))
    return 0


def cmd_render(ws, _args):
    st = _require_state(ws)
    save(ws, st, "render：md 已从 state 重建")
    return 0


def cmd_show(ws, _args):
    st = _require_state(ws)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def run(argv=None):
    ap = argparse.ArgumentParser(description="结构化进度状态（study_state.json 唯一事实源；md 为生成视图）。")
    ap.add_argument("--workspace", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--force", action="store_true")
    p_set = sub.add_parser("set")
    p_set.add_argument("--phase", type=int, default=None)
    p_set.add_argument("--scope", default=None)
    p_set.add_argument("--mode", default=None)
    p_set.add_argument("--time-budget", dest="time_budget", default=None)
    p_set.add_argument("--language", default=None)
    p_set.add_argument("--pref", action="append", default=None, help="key=value，可重复")
    for name in ("add-mistake", "add-confusion"):
        p = sub.add_parser(name)
        p.add_argument("--id", default=None)
        p.add_argument("--chapter", default=None)
        p.add_argument("--note", required=True)
    sub.add_parser("render")
    sub.add_parser("show")
    args = ap.parse_args(argv)
    ws = args.workspace
    if not os.path.isdir(ws):
        _die("workspace 不存在: %s" % ws)
    if args.cmd == "init":
        return cmd_init(ws, args)
    if args.cmd == "set":
        return cmd_set(ws, args)
    if args.cmd == "add-mistake":
        return cmd_add(ws, args, "mistake_archive", "错题")
    if args.cmd == "add-confusion":
        return cmd_add(ws, args, "confusion_log", "疑难")
    if args.cmd == "render":
        return cmd_render(ws, args)
    return cmd_show(ws, args)


if __name__ == "__main__":
    sys.exit(run())
