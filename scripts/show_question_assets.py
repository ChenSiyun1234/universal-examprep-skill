#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print the EXACT prompt-side asset Markdown for one question (P0-V2 official tool).

The visual-first contract (P0-V1) says: a requires/maybe_requires_assets item must SHOW its
prompt-side image(s) before asking/explaining, with renderable relative-POSIX paths — and if that is
impossible the item must be skipped, fail-closed. This tool makes that step deterministic instead of
hand-written: it emits the Markdown lines to paste BEFORE the question, verifies the files actually
exist/are safe (same rules as validate_workspace), and refuses (exit 1) when the contract can't be met.
Answer-side assets are only printed with --with-answer, AFTER a separator — never before the prompt.

    python scripts/show_question_assets.py --workspace <ws> --id <qid> [--with-answer]

Exit codes: 0 printed · 1 fail-closed (visual item without a displayable prompt asset) · 2 bad input.
"""
import argparse
import json
import os
import sys

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import validate_workspace as V   # noqa: E402 — reuse the validator's safety rules verbatim

QUESTION_SIDE = V.QUESTION_SIDE_ROLES
ANSWER_SIDE = {"answer_context", "worked_solution"}


def _die(msg, code=2):
    sys.stderr.write("show_question_assets: " + msg + "\n")
    raise SystemExit(code)


def _usable(ws, a):
    full, unsafe = V._asset_safety(ws, a.get("path"))
    return (not unsafe) and full and os.path.isfile(full) and os.access(full, os.R_OK)


def run(argv=None):
    ap = argparse.ArgumentParser(description="输出某题应先展示的题面图 Markdown（fail-closed）。")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--id", required=True, help="题目 id")
    ap.add_argument("--with-answer", action="store_true", help="随后追加答案侧 asset（默认不展示）")
    args = ap.parse_args(argv)

    bank_path = os.path.join(args.workspace, "references", "quiz_bank.json")
    if not os.path.isfile(bank_path):
        _die("找不到 quiz_bank.json: %s" % bank_path)
    try:
        bank = json.load(open(bank_path, encoding="utf-8"))
    except ValueError as e:
        _die("quiz_bank.json 不是合法 JSON: %s" % e)
    q = next((x for x in bank if isinstance(x, dict) and str(x.get("id")) == args.id), None)
    if q is None:
        _die("题库里没有 id=%s 的题" % args.id)

    visual = q.get("requires_assets") is True or q.get("maybe_requires_assets") is True
    assets = [a for a in (q.get("assets") or []) if isinstance(a, dict)]
    prompt = [a for a in assets if a.get("role") in QUESTION_SIDE and _usable(args.workspace, a)]
    answer = [a for a in assets if a.get("role") in ANSWER_SIDE and _usable(args.workspace, a)]

    if visual and not prompt:
        sys.stderr.write("show_question_assets: %s 是图依赖题（%s），但没有任何可展示的题面侧 asset——"
                         "按 fail-closed 契约必须跳过此题，不得无图出题/讲解\n"
                         % (args.id, "requires" if q.get("requires_assets") is True else "maybe"))
        raise SystemExit(1)

    for a in prompt:                                   # POSIX relative paths → renderable Markdown
        rel = str(a["path"]).replace("\\", "/")
        print("![%s 题面图](%s)" % (args.id, rel))
        if a.get("caption"):
            print("*%s*" % a["caption"])
    if not prompt:
        print("（该题不依赖图片，无题面 asset）")
    if args.with_answer and answer:
        print("\n---（以下为答案/解析侧图片，讲解或复盘时才展示）---")
        for a in answer:
            print("![%s 解答图](%s)" % (args.id, str(a["path"]).replace("\\", "/")))
    return 0


if __name__ == "__main__":
    sys.exit(run())
