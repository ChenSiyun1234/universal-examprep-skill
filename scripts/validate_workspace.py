#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Static validator for a built exam-cram workspace (stdlib only, no network/LLM).

Checks structure + quiz_bank.json schema + provenance + path safety against docs/file-format.md.
Cheap (Tier-1) engineering validation — runnable in CI or locally without any agent/benchmark run.

    python scripts/validate_workspace.py <workspace_dir>
    python scripts/validate_workspace.py <workspace_dir> --json

Exit codes:  0 = valid (warnings allowed)   1 = validation errors   2 = malformed/unreadable
"""
import os
import re
import sys
import json
import argparse

SIX_TYPES = {"choice", "subjective", "diagram", "fill_blank", "true_false", "code"}
MATERIAL_SOURCES = {"teacher", "material"}
ALL_SOURCES = {"teacher", "material", "ai_generated", "mixed", "unknown"}
SAFE_WIKI = re.compile(r"^[\w.\-]+\.md$")
WIKI_REF_RE = re.compile(r"references/wiki/([^\s)`'\"]+)")
TRUE_FALSE_OK = {"true", "false", "t", "f", "yes", "no", "真", "假", "对", "错", "是", "否"}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def validate(ws):
    """Return (errors, warnings, stats). errors may carry level 'error' or 'fatal'."""
    errors, warnings, stats = [], [], {}

    def err(msg, level="error"):
        errors.append({"level": level, "msg": msg})

    def warn(msg):
        warnings.append({"level": "warning", "msg": msg})

    if not os.path.isdir(ws):
        err(f"工作区目录不存在或不可读: {ws}", level="fatal")
        return errors, warnings, stats

    # ---- structure ----
    wiki_dir = os.path.join(ws, "references", "wiki")
    has_wiki = os.path.isdir(wiki_dir)
    if not has_wiki:
        err("缺少 references/wiki/ 目录")
    qb_path = os.path.join(ws, "references", "quiz_bank.json")
    has_qb = os.path.isfile(qb_path)
    if not has_qb:
        err("缺少 references/quiz_bank.json")
    for name, label in (("study_plan.md", "复习计划"), ("study_progress.md", "进度文件")):
        if not os.path.isfile(os.path.join(ws, name)):
            err(f"缺少 {label}: {name}")

    # ---- wiki filenames must be safe ----
    wiki_files = set()
    if has_wiki:
        for entry in sorted(os.listdir(wiki_dir)):
            if os.path.isdir(os.path.join(wiki_dir, entry)):
                err(f"references/wiki/ 下不应有子目录: {entry}")
                continue
            if not SAFE_WIKI.match(entry):
                err(f"不安全的 wiki 文件名（疑似路径穿越/非法字符）: {entry}")
            wiki_files.add(entry)
        stats["wiki_files"] = len(wiki_files)

    # ---- path-traversal in wiki references inside the .md files ----
    def scan_refs(text, where):
        for m in WIKI_REF_RE.finditer(text or ""):
            ref = m.group(1)
            if ".." in ref or ref.startswith(("/", "\\")) or (len(ref) >= 2 and ref[1] == ":"):
                err(f"{where} 中存在路径穿越的 wiki 引用: references/wiki/{ref}")
            elif has_wiki and SAFE_WIKI.match(ref) and ref not in wiki_files:
                warn(f"{where} 引用的 wiki 文件不存在: references/wiki/{ref}")
    for name in ("study_plan.md", "study_progress.md"):
        p = os.path.join(ws, name)
        if os.path.isfile(p):
            try:
                scan_refs(_read(p), name)
            except OSError:
                warn(f"{name} 读取失败，跳过引用检查")

    # ---- quiz_bank.json schema ----
    if has_qb:
        try:
            data = json.loads(_read(qb_path))
        except (ValueError, OSError) as e:
            err(f"quiz_bank.json 不是合法 JSON: {e}", level="fatal")
            return errors, warnings, stats
        if not isinstance(data, list):
            err("quiz_bank.json 顶层必须是 JSON 数组", level="fatal")
            return errors, warnings, stats
        stats["quiz_items"] = len(data)
        seen, type_counts = set(), {}
        for i, q in enumerate(data):
            if not isinstance(q, dict):
                err(f"题[{i}] 必须是对象")
                continue
            tag = f"题[{q.get('id', i)}]"
            for fld in ("id", "type", "question"):
                if not q.get(fld):
                    err(f"{tag} 缺少必需字段 {fld}")
            if q.get("chapter") in (None, "") and q.get("phase") in (None, ""):
                err(f"{tag} 缺少 chapter 或 phase（二者至少其一——章节复习按此过滤抽题）")
            # id/type must be SCALAR before being used as set/dict keys: a malformed list/object id or
            # type would raise TypeError (unhashable) and crash before any structured error is returned.
            qid = q.get("id")
            if qid is not None and not isinstance(qid, (str, int, float, bool)):
                err(f"{tag} 的 id 必须是标量（字符串/数字），当前为 {type(qid).__name__}")
                qid = None
            if qid is not None:
                if qid in seen:
                    err(f"重复的题目 id: {qid}")
                seen.add(qid)
            t = q.get("type")
            if t is not None and not isinstance(t, str):
                err(f"{tag} 的 type 必须是字符串，当前为 {type(t).__name__}")
                t = None
            if t is not None:
                type_counts[t] = type_counts.get(t, 0) + 1
                if t not in SIX_TYPES:
                    err(f"{tag} 的 type 非法: {t!r}（应为 {sorted(SIX_TYPES)} 之一）")

            # per-type required/recommended
            if t == "choice" and not (isinstance(q.get("options"), list) and q.get("options")):
                err(f"{tag} choice 题必须有非空 options")
            if t == "subjective" and not q.get("keywords"):
                warn(f"{tag} subjective 题建议提供 keywords（要点检索判分）")
            if t == "diagram" and not q.get("diagram_type"):
                warn(f"{tag} diagram 题建议提供 diagram_type / 渲染说明（画图先跑算法再画）")
            if t == "code" and not (q.get("language") and (q.get("expected_behavior") or q.get("tests"))):
                warn(f"{tag} code 题建议提供 language 与 expected_behavior/tests")
            if t == "true_false":
                a = q.get("answer")
                if a is not None and not (isinstance(a, bool) or str(a).strip().lower() in TRUE_FALSE_OK):
                    warn(f"{tag} true_false 的 answer 应为布尔型（true/false/真/假/对/错），当前 {a!r}")

            # provenance + answer presence
            src = q.get("source")
            if src is not None and src not in ALL_SOURCES:
                err(f"{tag} 的 source 取值非法: {src!r}（应为 {sorted(ALL_SOURCES)}）")
            if bool(q.get("ai_generated")) and src not in {"ai_generated", "mixed"}:
                err(f"{tag} 为 AI 生成答案，但 source 未标注为 ai_generated/mixed——"
                    "严禁把 AI 生成答案伪装成老师提供或隐藏来源")
            answer_val = q.get("answer")
            has_answer = answer_val not in (None, "", [], {})
            status = str(q.get("answer_status", "")).strip().lower()
            if not has_answer:
                if status == "unknown" or src in {"ai_generated", "unknown"}:
                    warn(f"{tag} 无 answer，已按 unknown/ai_generated 标注（考前需补全/核对）")
                else:
                    # ingest.py ACCEPTS answer-less questions (it warns, doesn't fail) and writes neither
                    # answer_status nor source — so a valid ingest output must NOT fail Tier 1. Keep this a
                    # WARNING (the "AI answer hidden as teacher" case above stays a hard error).
                    warn(f"{tag} 无 answer（建议补 answer，或标 answer_status=unknown / source=ai_generated）")
            elif src is None:
                warn(f"{tag} 有答案但未标 source（建议标 teacher/material/ai_generated）")
        stats["quiz_types"] = type_counts

    # ---- study_progress consistency (best-effort, lenient → warnings only) ----
    prog_path = os.path.join(ws, "study_progress.md")
    if os.path.isfile(prog_path):
        try:
            prog = _read(prog_path)
            if "疑难点" not in prog and "confusion" not in prog.lower():
                warn("study_progress.md 未见「概念疑难点记录」区（confusion-tracker 应维护此区）")
            # current checkpoint phase should correspond to a phase listed in study_plan.md, else the
            # agent can't resume correctly. Best-effort + lenient (skip silently if unparseable).
            plan_path = os.path.join(ws, "study_plan.md")
            m_cur = re.search(r"当前[^#]*?阶段\s*(\d+)", prog, re.S)
            if m_cur and os.path.isfile(plan_path):
                plan_phases = set(re.findall(r"阶段\s*(\d+)", _read(plan_path)))
                if plan_phases and m_cur.group(1) not in plan_phases:
                    warn(f"study_progress.md 当前阶段 {m_cur.group(1)} 不在 study_plan.md 的阶段列表 "
                         f"{sorted(int(x) for x in plan_phases)} 中（断点可能无法正确恢复）")
        except OSError:
            pass

    return errors, warnings, stats


def _exit_code(errors):
    if any(e.get("level") == "fatal" for e in errors):
        return 2
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验一个备考工作区是否符合 docs/file-format.md")
    ap.add_argument("workspace", help="工作区目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出 errors/warnings/stats")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    errors, warnings, stats = validate(args.workspace)
    code = _exit_code(errors)

    if args.json:
        print(json.dumps({"exit_code": code, "ok": code == 0, "workspace": args.workspace,
                          "errors": errors, "warnings": warnings, "stats": stats},
                         ensure_ascii=False, indent=2))
    else:
        print(f"工作区: {args.workspace}")
        if stats:
            print("  统计:", ", ".join(f"{k}={v}" for k, v in stats.items()))
        for e in errors:
            print(f"  [{'致命' if e['level'] == 'fatal' else '错误'}] {e['msg']}")
        for w in warnings:
            print(f"  [告警] {w['msg']}")
        verdict = {0: "✓ 通过（无错误）", 1: "✗ 有校验错误", 2: "✗ 工作区损坏/不可读"}[code]
        print(f"结论: {verdict}（错误 {sum(1 for e in errors)} / 告警 {len(warnings)}）")
    return code


if __name__ == "__main__":
    sys.exit(main())
