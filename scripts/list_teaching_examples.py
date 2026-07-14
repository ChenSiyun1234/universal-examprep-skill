#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""List teaching-example snapshots for exactly one chapter.

The manifest is deliberately separate from ``quiz_bank.json``: it is a teaching-reachability
index, not an assessment pool.  Requiring ``--chapter`` prevents an agent from dumping the whole
course manifest into context and preserves the exam coach's lazy-load contract.

Exit codes: 0 success (including a legacy workspace with no manifest); 2 invalid input/manifest.
"""
import argparse
import json
import os
import sys


for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8")
    except Exception:
        pass


def _die(message):
    sys.stderr.write("list_teaching_examples: " + message + "\n")
    raise SystemExit(2)


def _reject_constant(value):
    raise ValueError("non-standard JSON constant %s" % value)


def _validate_workspace(workspace):
    if not os.path.isdir(workspace):
        _die("workspace does not exist or is not a directory: %s" % workspace)
    references = os.path.join(workspace, "references")
    if os.path.lexists(references) and os.path.islink(references):
        _die("workspace references directory must not be a symbolic link")
    if not os.path.isdir(references):
        _die("workspace is missing the references directory")
    signatures = (
        os.path.join(references, "quiz_bank.json"),
        os.path.join(references, "teaching_examples.json"),
    )
    if not any(os.path.isfile(path) and not os.path.islink(path) for path in signatures):
        _die("path has no exam-workspace signature (quiz bank or teaching manifest)")


def _scope_key(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return str(value)
    text = str(value).strip() if value is not None else ""
    if text.isdigit() and int(text) >= 1:
        return str(int(text))
    return text


def load_manifest(workspace):
    _validate_workspace(workspace)
    path = os.path.join(workspace, "references", "teaching_examples.json")
    # lexists sees a broken symlink; exists would misclassify it as a legacy workspace with no
    # manifest and silently bypass the containment contract.
    if not os.path.lexists(path):
        return [], True
    if os.path.islink(path):
        _die("references/teaching_examples.json must not be a symbolic link")
    ws_real = os.path.normcase(os.path.realpath(workspace))
    path_real = os.path.normcase(os.path.realpath(path))
    if path_real != ws_real and not path_real.startswith(ws_real + os.sep):
        _die("teaching manifest escapes the workspace")
    if not os.path.isfile(path):
        _die("references/teaching_examples.json is not a regular file")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f, parse_constant=_reject_constant)
    except (OSError, ValueError) as exc:
        _die("invalid teaching manifest: %s" % exc)
    if not isinstance(data, list):
        _die("references/teaching_examples.json must contain a JSON array")
    for i, item in enumerate(data):
        if not isinstance(item, dict) or item.get("id") is None:
            _die("teaching_examples[%d] must be an object with an id" % i)
        if item.get("chapter") is not None and item.get("phase") is not None:
            chapter, phase = _scope_key(item.get("chapter")), _scope_key(item.get("phase"))
            if chapter != phase:
                _die("teaching_examples[%d] has conflicting chapter=%r and phase=%r" %
                     (i, item.get("chapter"), item.get("phase")))
    return data, False


def _chapter_keys(item):
    value = item.get("chapter") if item.get("chapter") is not None else item.get("phase")
    return {_scope_key(value)} if value is not None else set()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="List teaching examples for one chapter (never reads the assessment bank)."
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--chapter", required=True,
                        help="required exact chapter-or-phase value; whole-course dumps are disabled")
    parser.add_argument("--limit", type=int, default=0, help="0 = all matches in this chapter")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 0:
        _die("--limit must be >= 0")

    items, missing = load_manifest(os.path.abspath(args.workspace))
    chapter = _scope_key(args.chapter)
    hits = [item for item in items if chapter in _chapter_keys(item)]
    total = len(hits)
    if args.limit:
        hits = hits[:args.limit]

    if args.json:
        print(json.dumps({
            "chapter": chapter,
            "manifest_missing": missing,
            "total_matched": total,
            "returned": len(hits),
            "items": hits,
        }, ensure_ascii=False, indent=2))
        return 0

    if missing:
        print("[teaching examples] legacy workspace: manifest absent; 0 matches")
        return 0
    print("[teaching examples] chapter %s: %d matches (showing %d)" %
          (chapter, total, len(hits)))
    for item in hits:
        pages = ",".join(str(p) for p in (item.get("source_pages") or [])) or "?"
        print("- [#%s] %s | %s p.%s | %s" % (
            item.get("id"), item.get("teaching_role", "?"),
            item.get("source_file", "source unknown"), pages,
            str(item.get("title") or item.get("question") or "")[:80],
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
