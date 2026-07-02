#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Official pre-ingest: scan a course-materials folder → raw_input.json (+ optional page-image
assets + a parse report) for scripts/ingest.py.

This is NOT an OCR project. It is a deterministic, honest, first official entrypoint that:
  - preserves page provenance (source_file / source_pages),
  - preserves full-page renders for figure-dependent lecture pages (so diagram questions keep context),
  - extracts obvious lecture Example/Quiz problem-solution pairs into quiz_bank items,
  - never pretends lossy text extraction is complete, and
  - fails / warns clearly when the OPTIONAL PDF backends are unavailable.

stdlib-only core + tests. PDF *text extraction* and *page rendering* are OPTIONAL backends:
  - text:   pypdf
  - render: PyMuPDF (`fitz`, native PNG, no extra deps) OR pypdfium2 + Pillow (its to_pil adapter)
Install only if you need them, e.g.:  pip install pypdf pymupdf   (or: pip install pypdf pypdfium2 Pillow)
Rendering also needs --asset-root <workspace>/references/assets (where the page PNGs are written).

Usage:
  python scripts/build_raw_input_from_workspace.py \\
      --materials ./course_materials --out raw_input.json \\
      --asset-root skill_workspace/references/assets \\
      --render-pages auto --extract-lecture-questions auto --report parse_report.json
  python scripts/ingest.py -i raw_input.json -o skill_workspace
  python scripts/validate_workspace.py skill_workspace
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Heading detection / lecture extraction — PURE, stdlib, unit-tested on synthetic page text.
# A "page" is a dict: {"file": str, "page": int (1-based), "text": str}.
# ---------------------------------------------------------------------------

_NUM = r"(\d+)\s*\.\s*(\d+)"
# anchor markers to a line START (after optional bullet/number/markdown-heading prefix) so inline
# prose like "see Example 1.1" or a TOC entry isn't mistaken for a heading, while `## Quiz 1.1` (a
# Markdown heading in .md materials) and `- Example 1.1` (a bullet) still match.
_HEAD = r"^[ \t>*•·\-\d.)）、#]*"
_EXAMPLE_RE = re.compile(_HEAD + r"Example\s+" + _NUM, re.I | re.M)
_QUIZ_RE = re.compile(_HEAD + r"Quiz\s+" + _NUM, re.I | re.M)

# ---- A3: homework / solution files (separate PDFs paired by filename; inline solutions supported) ----
# a homework FILE is recognized by its path (folder or stem), NOT by content guessing
_HW_FILE_RE = re.compile(r"(?:^|[\\/_\-. ])(?:hw|homework|assignments?|problem[ _-]?sets?|ps[ _\-]?\d|作业|习题)",
                         re.I)
# tokens that mark a SOLUTION companion file (hw1_sol.pdf / HW2_Answers.pdf / 作业3答案.pdf)
_SOL_TOKEN_RE = re.compile(r"solutions?|answers?|(?:^|[_\-. ])(?:sol|ans)(?=[_\-. ]|$)|答案|解答", re.I)
# problem headings inside homework/solution files（行首锚定，与 lecture 标记同族）
_HW_PROB_RES = (re.compile(_HEAD + r"(?:Problem|Exercise|Question)\s*#?\s*(\d+)", re.I | re.M),
                re.compile(_HEAD + r"(?:第\s*(\d+)\s*题|习题\s*(\d+)[.:：]?|题目\s*(\d+)[.:：]?)", re.M))
# inline solution heading (same file, follows its problem)
_HW_SOL_RE = re.compile(_HEAD + r"(?:Solution|Answer|解答|答案)\s*(?:#?\s*(\d+))?\s*(?:[.:：]|$)",
                        re.I | re.M)

# Two classes of asset cue. ASSET_EXCLUDE masks known false-positive phrases first.
ASSET_EXCLUDE = ("table of contents", "figure it out", "figure out", "graph theory", "figure caption")
# STRONG: the question explicitly references a figure SHOWN to the student ("at right", "Venn", "shade
# the region", "image below"). Asset-dependent on ANY source — a .txt that says "shade the Venn at right"
# is fail-closed because the figure is genuinely missing from the text.
STRONG_CUES = [re.compile(p, re.I) for p in (
    r"venn", r"at right", r"to the right", r"shown (on the right|below|above)", r"as shown",
    r"\bshaded?\b",
    r"(figure|diagram|table|image|picture|chart|graph|tree|plot)s?\s+(below|above|at right|to the right)",
    "文氏图", "图示", "如图", "阴影", "区域", "示意图",
)]
# WEAK: a figure NOUN that might instead be a "produce" prompt ("draw the graph of y=x^2", "sketch the
# tree"). Asset-dependent only for a renderable PDF source (where over-flagging just renders an extra
# page, harmless); on .txt/.md the text is already complete, so don't fail-close a drawing prompt.
WEAK_CUES = [re.compile(p, re.I) for p in (
    r"\bdiagram\b", r"\bfigure\b", r"\btable\b", r"\bgraph\b", r"\bplot\b", r"\btree\b", r"\bcircuit\b",
    r"\bdraw\b", r"\bdrawn\b", r"\baxes\b", r"\brectangle\b", r"\btriangle\b",
)]


def _cue_in(text, patterns):
    masked = (text or "").lower()
    for ex in ASSET_EXCLUDE:
        masked = masked.replace(ex, " ")   # drop known false-positive phrases before matching
    return any(p.search(masked) for p in patterns)


def requires_assets_heuristic(text, renderable=True):
    """True if the question depends on a figure that isn't in the text. STRONG figure-SHOWN cues fire on
    any source; WEAK figure-noun cues (possibly a 'draw the X' produce-prompt) fire only for a renderable
    PDF source. Fail-closed by design: when unsure on a PDF we prefer attaching a page image."""
    return _cue_in(text, STRONG_CUES) or (renderable and _cue_in(text, WEAK_CUES))


# role is decided by the word IMMEDIATELY after the marker number (anchored), NOT a loose tail scan —
# otherwise a problem whose text merely contains "solution" ("find the solution set") is misread.
_ROLE_PROBLEM_RE = re.compile(r"^\s*[\)\.:\-]?\s*\(?\s*problems?\b", re.I)             # incl. plural "Problems"
_ROLE_SOLUTION_RE = re.compile(r"^\s*[\)\.:\-]?\s*\(?\s*(?:solutions?|answers?)\b", re.I)  # Solution(s)/Answer(s)
_TOC_RE = re.compile(r"\.{4,}")   # 4+ dot-leaders → a table-of-contents line, not a heading


def _role_of_tail(tail):
    """Role of a marker from the text right after its number. A leading "(Continued)" may precede the
    role word ("Example 1.1 (Continued) Solution …"); strip it before matching. Used everywhere so
    detect_lecture_markers and the text-slicers agree."""
    # strip ONLY a leading "continued" token (+ optional number/parens/separators) — not the words
    # after it, so "Continued Solution" / "Continued: Solution" (no parens) still leaves "Solution".
    tail_role = re.sub(r"^\s*\(?\s*continued\b\s*\d*\s*\)?[\s:.\-]*", "", tail, flags=re.I)
    if _ROLE_PROBLEM_RE.match(tail) or _ROLE_PROBLEM_RE.match(tail_role):
        return "problem"
    if _ROLE_SOLUTION_RE.match(tail) or _ROLE_SOLUTION_RE.match(tail_role):
        return "solution"
    return "problem"   # bare "Quiz 1.1" with no keyword → a problem


def _iter_markers(text):
    """Every NON-TOC lecture marker in TEXT-POSITION order — the single source of truth shared by
    detect_lecture_markers AND the text-slicers, so TOC-skip / role / plural never diverge between
    them. Returns dicts: {start, kind, chapter, num, role, continued}."""
    text = text or ""
    out = []
    for kind, rx in (("example", _EXAMPLE_RE), ("quiz", _QUIZ_RE)):
        for m in rx.finditer(text):
            nl = text.find("\n", m.end())
            line = text[m.start():(nl if nl >= 0 else len(text))][:300]   # the whole heading line
            if _TOC_RE.search(line):   # dot-leaders anywhere on the line → TOC entry (even long titles), skip
                continue
            tail = text[m.end():m.end() + 48]
            out.append({"start": m.start(), "kind": kind, "chapter": int(m.group(1)), "num": int(m.group(2)),
                        "role": _role_of_tail(tail), "continued": bool(re.search(r"\bContinued\b", tail, re.I))})
    out.sort(key=lambda d: d["start"])
    return out


def detect_lecture_markers(text):
    """Find lecture Example/Quiz markers on one page (TEXT-POSITION order). Returns a list of
    {kind: 'example'|'quiz', chapter: int, num: int, role: 'problem'|'solution', continued: bool}."""
    return [{k: d[k] for k in ("kind", "chapter", "num", "role", "continued")} for d in _iter_markers(text)]


def orphan_solution_keys(pages):
    """Solution markers whose (kind,chapter,num) never had a detected problem — surfaced as a
    warning so a mis-detected pair is fail-loud, not silently dropped."""
    marked = _markers_with_pages(pages)
    probs = {_key(mk) for _, mk in marked if mk["role"] == "problem"}
    sols = {_key(mk) for _, mk in marked if mk["role"] == "solution"}
    return sorted(sols - probs)


def _markers_with_pages(pages):
    marked = []
    for i, pg in enumerate(pages):
        for mk in detect_lecture_markers(pg.get("text", "")):
            marked.append((i, mk))
    return marked


def _key(mk):
    return (mk["kind"], mk["chapter"], mk["num"])


def _problem_statement(page_text, kind, chapter, num):
    """Extract the problem text for `<kind> X.Y` on a page — concatenating EVERY problem-role slice for
    that key (so a same-page `Problem …` + `Problem (Continued) …` are both captured), each cut at the
    next marker. Skips TOC lines and `Solution` markers of the same number (solution-before-problem)."""
    text = page_text or ""
    mks = _iter_markers(text)
    starts = [d["start"] for d in mks]
    parts = []
    for d in mks:
        if d["kind"] == kind and d["chapter"] == chapter and d["num"] == num and d["role"] != "solution":
            after = [st for st in starts if st > d["start"]]
            e = min(after) if after else len(text)
            parts.append(" ".join(text[d["start"]:e].split()).strip())
    return " ".join(parts).strip()


def _body_after_marker(stmt, kind, chapter, num):
    """The text of `stmt` after stripping the leading `<kind> X.Y [Problem]` heading — used to tell a
    real prompt from a marker-only title (a slide whose prompt is in an image pypdf couldn't read)."""
    rx = _EXAMPLE_RE if kind == "example" else _QUIZ_RE
    m = rx.search(stmt or "")
    if not m:
        return (stmt or "").strip()
    rest = stmt[m.end():]
    rest = re.sub(r"^\s*[\):.\-]?\s*\(?\s*problems?\b\)?", "", rest, flags=re.I)  # drop a trailing "Problem(s)"
    return rest.strip(" .:：、)）-—\t\n")


def _solution_statement(page_text, kind, chapter, num):
    """Extract the solution text for `<kind> X.Y` on a page — concatenating EVERY solution slice for
    that key (so a same-page `Solution …` + `Solution (Continued) …` are both captured), each cut at
    the next marker. The real `answer` for text-complete items so grading has something to compare to."""
    text = page_text or ""
    mks = _iter_markers(text)
    starts = [d["start"] for d in mks]
    parts = []
    for d in mks:
        if d["kind"] == kind and d["chapter"] == chapter and d["num"] == num and d["role"] == "solution":
            after = [st for st in starts if st > d["start"]]
            e = min(after) if after else len(text)
            parts.append(" ".join(text[d["start"]:e].split()).strip())
    return " ".join(parts).strip()


def extract_lecture_items(pages):
    """Pair each `<kind> X.Y` problem with its matching `Solution` pages (incl. `(Continued)`), assign
    stable IDs, and flag asset dependence. De-dups problems by (kind, chapter, num, source_file) — a
    marker reused across files (lecture/ch01.pdf + homework/ch01.pdf both `Quiz 1.1`) yields two
    distinct, file-namespaced items. Solutions are claimed same-file-first (a continuation in a file
    with no competing problem still merges), surviving intervening problems and solution-before-problem."""
    marked = _markers_with_pages(pages)
    sol_by_key = {}
    for mj, (pj, mk2) in enumerate(marked):
        if mk2["role"] == "solution":
            sol_by_key.setdefault(_key(mk2), []).append((mj, pj))
    prob_files = {}    # key -> set of files that contain a PROBLEM marker for it
    for (pj, mk2) in marked:
        if mk2["role"] == "problem":
            prob_files.setdefault(_key(mk2), set()).add(pages[pj]["file"])
    ambiguous = {k for k, fs in prob_files.items() if len(fs) > 1}   # same marker in >1 file → namespace id
    file_idx = {}      # injective per-file index within an ambiguous key (sanitized stems can collide)
    for k in ambiguous:
        for n, f in enumerate(sorted(prob_files[k])):
            file_idx[(k, f)] = n

    claimed = set()
    items, seen = [], set()
    for mi, (i, mk) in enumerate(marked):
        if mk["role"] != "problem":
            continue
        key = _key(mk)
        prob_page = pages[i]
        pf = prob_page["file"]
        if (key, pf) in seen:
            continue
        seen.add((key, pf))
        prob_text = prob_page.get("text", "")

        # a problem may span pages: gather later `Problem (Continued)` pages of the same key+file.
        prob_idxs = sorted({i} | {pj2 for (pj2, mk2) in marked
                                  if _key(mk2) == key and mk2["role"] == "problem"
                                  and pages[pj2]["file"] == pf and mk2.get("continued")})
        q_pages = sorted({(pages[k]["file"], pages[k]["page"]) for k in prob_idxs}, key=lambda fp: (fp[1], fp[0]))

        # take ALL usable solutions (both before AND after the problem). For a key that is a problem in
        # >1 file (ambiguous), only SAME-FILE solutions are usable — a separate solutions-only file's
        # `Quiz X.Y Solution` can't be assigned to one of the competing problems, so don't claim it.
        other_prob_files = prob_files.get(key, set()) - {pf}
        ambiguous_key = key in ambiguous
        chosen = [(mj, pj) for (mj, pj) in sol_by_key.get(key, []) if mj not in claimed
                  and (pages[pj]["file"] == pf
                       or (not ambiguous_key and pages[pj]["file"] not in other_prob_files))]
        for (mj, pj) in chosen:
            claimed.add(mj)
        ans_idx = sorted({pj for (mj, pj) in chosen})

        kind = mk["kind"]
        label = "Example" if kind == "example" else "Quiz"
        # scope the asset heuristic to THIS problem's slice on the anchor page; continued pages (which
        # wholly belong to this problem) are scanned whole.
        stmt = _problem_statement(prob_text, kind, key[1], key[2])
        # STRONG figure-shown cues fire on any source (a .txt "shade the Venn at right" is fail-closed);
        # WEAK figure-noun cues fire only for a renderable PDF (a .txt "draw the graph" stays text-complete).
        renderable = pf.lower().endswith(".pdf")
        # scope the heuristic to THIS problem's sliced text on every page (anchor + continued) — a
        # continued page that also starts the next item must not lend that item's "Venn" to this one.
        needs = (requires_assets_heuristic(stmt or prob_text, renderable) or any(
            requires_assets_heuristic(_problem_statement(pages[k].get("text", ""), kind, key[1], key[2]),
                                      renderable) for k in prob_idxs if k != i))
        # marker-only: extraction yielded just the heading on a single page (real prompt likely in an
        # image) → NOT a standalone question. Detect by ABSENCE of any word/CJK content after the
        # heading (not a char-length cutoff — a terse CJK prompt like "求导"/"证明" is a real question).
        # real prompt content = a LETTER, CJK char, or math operator/relation. A bare page-number body
        # ("Quiz 1.1\n12") is a slide footer → marker_only; a symbolic prompt ("2+2=?", "√4=?") is real.
        marker_only = ((not needs) and len(prob_idxs) == 1
                       and not re.search(r"[A-Za-z一-鿿=+√∫∑^?×÷<>≤≥]",
                                         _body_after_marker(stmt, kind, key[1], key[2])))
        if needs:
            qts = "page_reference"
            question = ("（%s %d.%d）本题依赖原始讲义 %s 第 %d 页的图/表，须配合所附 asset 作答。"
                        % (label, key[1], key[2], pf, prob_page["page"]))
        elif marker_only:
            qts = "page_reference"
            question = ("（%s %d.%d）题面未能从文本提取（可能在图片中），见原始讲义 %s 第 %d 页。"
                        % (label, key[1], key[2], pf, prob_page["page"]))
        else:
            qts = "full"
            # slice each continued page to THIS problem's portion (cut at the next marker on that page)
            # so a `Quiz 1.1 Problem (Continued) … Quiz 1.2 Problem …` page doesn't append Quiz 1.2's text.
            cont_parts = [_problem_statement(pages[k].get("text", ""), kind, key[1], key[2])
                          or " ".join((pages[k].get("text") or "").split()) for k in prob_idxs if k != i]
            question = " ".join([stmt] + cont_parts).strip()
        item_id = "lecture_%s_%d_%d" % (kind, key[1], key[2])
        if key in ambiguous:   # readable stem + injective index (so a/b.pdf vs a_b.pdf don't collide)
            item_id += "__%s_%d" % (re.sub(r"[^\w]", "_", os.path.splitext(pf)[0]), file_idx[(key, pf)])
        item = {
            "id": item_id,
            "chapter": key[1],
            "type": "diagram" if needs else "subjective",
            "question": question,
            "source": "material",
            "source_file": pf,
            "source_pages": [p for (f, p) in q_pages],
            "_question_pages": q_pages,                     # stripped from the emitted bank
            "_render": bool(needs or marker_only),          # render the page for figure- AND image-prompt items
            "requires_assets": bool(needs),
            "question_text_status": qts,
        }
        if not needs:
            item["keywords"] = []  # subjective recommended field; left for the tutor/teacher to fill
        if ans_idx:
            ans = sorted({(pages[j]["file"], pages[j]["page"]) for j in ans_idx}, key=lambda fp: (fp[1], fp[0]))
            first_file = ans[0][0]
            item["answer_source_file"] = first_file
            item["answer_source_pages"] = [p for (f, p) in ans if f == first_file]
            item["_answer_pages"] = ans
            ref = "见原始讲义 %s 第 %s 页的解答。" % (
                first_file, "、".join(str(p) for (f, p) in ans if f == first_file))
            # keep the EXTRACTED solution text whenever there is one (grading needs it) — even for a
            # figure-dependent item; only fall back to the page-reference when no text was extracted.
            sol = " ".join(t for t in (_solution_statement(pages[j].get("text", ""), kind, key[1], key[2])
                                       for j in ans_idx) if t).strip()
            if sol:
                item["answer"] = sol + ("（解答可能依赖图，须看原页/asset）" if needs else "")
            else:
                item["answer"] = ref + ("（依赖图，须看原页/asset）" if needs else "")
        else:
            item["answer_status"] = "unknown"   # honest: no solution page detected
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# A3: homework / solution extraction — deterministic, filename-paired, fail-loud
# ---------------------------------------------------------------------------

def _hw_norm(stem):
    """Normalized pairing key: lowercase, keep alnum + CJK only（hw1_sol → hw1 after token strip）."""
    return re.sub(r"[^a-z0-9一-鿿]+", "", stem.lower())


def classify_homework_files(files):
    """Split material files into (homework_files, {solution_file: paired_homework_file|None}).
    Solutions pair by stripped-stem equality or prefix; an unpairable solution file is fail-loud."""
    hw, sols = [], []
    for f in files:
        rel = f.replace("\\", "/")
        stem = os.path.splitext(os.path.basename(f))[0]
        is_sol = bool(_SOL_TOKEN_RE.search(stem) or _SOL_TOKEN_RE.search(os.path.dirname(rel)))
        if not (_HW_FILE_RE.search(rel) or is_sol):
            continue                                   # solutions/hw1.pdf：目录名也是 solution 记号
        (sols if is_sol else hw).append(f)
    # 目录感知配对：week1/hw1_sol 只配 week1/hw1（同名跨目录不串）；同目录找不到才允许全局唯一回退
    hw_by_key = {}
    for f in hw:
        rel = f.replace("\\", "/")
        hw_by_key.setdefault((os.path.dirname(rel), _hw_norm(os.path.splitext(os.path.basename(f))[0])),
                             []).append(f)
    pairing = {}
    for sf in sols:
        rel = sf.replace("\\", "/")
        sdir = os.path.dirname(rel)
        stem = os.path.splitext(os.path.basename(sf))[0]
        stripped = _hw_norm(_SOL_TOKEN_RE.sub("", stem))

        def _pref(a, b):
            return a.startswith(b) and (len(a) == len(b) or not a[len(b)].isdigit())

        def _lookup(dirs):
            exact = [f for (d, n), fs in hw_by_key.items() if d in dirs and n == stripped for f in fs]
            if len(exact) == 1:
                return exact[0]
            if exact:
                return None
            cands = [f for (d, n), fs in hw_by_key.items() if d in dirs and n
                     and (_pref(stripped, n) or _pref(n, stripped)) for f in fs]
            return cands[0] if len(cands) == 1 else None
        # same-dir first, then its parent (solutions/hw1 → homework/hw1 case: try all dirs), then global
        match = _lookup({sdir}) or _lookup({d for (d, _n) in hw_by_key})
        pairing[sf] = match
    return hw, pairing


def _file_stream(pages, f):
    """Concatenate one file's page texts into a single stream + (offset, page_no) bounds table, so a
    problem spanning pages slices naturally."""
    parts, bounds, cur = [], [], 0
    for pg in pages:
        if pg["file"] != f:
            continue
        t = pg.get("text", "") or ""
        bounds.append((cur, pg["page"]))
        parts.append(t)
        cur += len(t) + 1
    return "\n".join(parts), bounds


def _pages_for_span(bounds, a, b):
    """Page numbers whose text overlaps stream span [a, b)."""
    out = []
    for i, (start, pno) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else float("inf")
        if start < b and end > a:
            out.append(pno)
    return out


def _hw_markers(stream):
    """All problem/inline-solution markers in stream order: {start, num|None, role}."""
    marks = []
    for rx in _HW_PROB_RES:
        for m in rx.finditer(stream):
            num = next((g for g in m.groups() if g), None)
            line = stream[m.start(): stream.find("\n", m.end()) if stream.find("\n", m.end()) >= 0 else len(stream)]
            if _TOC_RE.search(line[:300]):
                continue
            marks.append({"start": m.start(), "num": int(num), "role": "problem"})
    for m in _HW_SOL_RE.finditer(stream):
        num = next((g for g in m.groups() if g), None)
        marks.append({"start": m.start(), "num": int(num) if num else None, "role": "solution"})
    marks.sort(key=lambda d: d["start"])
    # de-dup identical (start) collisions (EN/CN patterns can't overlap, but be safe)
    dedup, seen = [], set()
    for mk in marks:
        if mk["start"] in seen:
            continue
        seen.add(mk["start"])
        dedup.append(mk)
    return dedup


def extract_homework_items(pages):
    """Extract homework problems (+ answers from paired solution files OR inline Solution blocks)
    into bank items with source_type='homework'. Returns (items, hw_report)."""
    files = sorted({pg["file"] for pg in pages})
    is_pdf = {f: any(pg.get("_pdf") for pg in pages if pg["file"] == f) for f in files}
    hw_files, pairing = classify_homework_files(files)
    report = {"homework_files": hw_files,
              "homework_solution_files": sorted(pairing),
              "homework_pairs": sorted([s, h] for s, h in pairing.items() if h),
              "homework_problems": 0, "homework_answered": 0, "warnings": []}
    for sf, h in sorted(pairing.items()):
        if h is None:
            report["warnings"].append("hw_unpaired_solution_file: %s（配不到对应作业题面文件，未导入答案）" % sf)

    # answers available per (hw_file, num) from paired solution files
    sol_answers = {}
    for sf, hf in pairing.items():
        if hf is None:
            continue
        stream, bounds = _file_stream(pages, sf)
        marks = [m for m in _hw_markers(stream) if m["num"] is not None]
        for i, mk in enumerate(marks):
            end = marks[i + 1]["start"] if i + 1 < len(marks) else len(stream)
            body = stream[mk["start"]:end].strip()
            if not body:
                continue
            key = (hf, mk["num"])
            prev = sol_answers.get(key)
            # 同号既有 Problem 复述又有 Answer 段时，答案段优先（不再"先到先得"存题面复述）
            if prev is None or (mk["role"] == "solution" and prev[3] != "solution"):
                sol_answers[key] = (sf, body, _pages_for_span(bounds, mk["start"], end), mk["role"])

    items = []
    for hf in hw_files:
        stream, bounds = _file_stream(pages, hf)
        marks = _hw_markers(stream)
        probs = [m for m in marks if m["role"] == "problem"]
        if not probs:
            report["warnings"].append("hw_no_markers: %s（识别为作业文件但没找到 Problem/第N题 标记）" % hf)
            continue
        stem_full = re.sub(r"[^0-9A-Za-z_\-一-鿿]+", "_",
                           os.path.splitext(hf.replace("\\", "/"))[0])   # 含子目录，week1/hw1 ≠ week2/hw1
        if len(stem_full) > 60:                        # 截断会撞 id——加内容哈希后缀保唯一
            import hashlib as _hl
            stem = stem_full[:52] + "_" + _hl.sha1(stem_full.encode("utf-8")).hexdigest()[:7]
        else:
            stem = stem_full
        seen_nums = set()
        dup_counts = {}
        for i, mk in enumerate(marks):
            if mk["role"] != "problem":
                continue
            if mk["num"] in seen_nums:
                dup_counts[mk["num"]] = dup_counts.get(mk["num"], 0) + 1   # 真实 PDF 里题号会反复出现
                continue                                                    #（分页眉/解答区重现）——去重计数
            seen_nums.add(mk["num"])
            nxt = marks[i + 1]["start"] if i + 1 < len(marks) else len(stream)
            q_text = stream[mk["start"]:nxt].strip()
            # inline solution: the very next marker is an un/same-numbered Solution → its slice is the answer
            ans = None
            if i + 1 < len(marks) and marks[i + 1]["role"] == "solution" \
                    and marks[i + 1]["num"] in (None, mk["num"]):
                s_start = marks[i + 1]["start"]
                s_end = next((m2["start"] for m2 in marks[i + 2:] if m2["role"] == "problem"), len(stream))
                a_body = stream[s_start:s_end].strip()
                # worksheet 填空线（Answer: ______）不是官方答案——去掉标记行后只剩下划线/点/空白即忽略
                a_tail = a_body.split("\n", 1)[1] if "\n" in a_body else re.sub(_HW_SOL_RE, "", a_body, count=1)
                if re.sub(r"[_\s.．。:：…\-—]+", "", a_tail):
                    ans = (hf, a_body, _pages_for_span(bounds, s_start, s_end))
            if ans is None:
                got = sol_answers.get((hf, mk["num"]))
                ans = got[:3] if got else None
            q_pages = _pages_for_span(bounds, mk["start"], nxt)
            # marker-only prompt: the heading is all the text extractor got — the real prompt is an
            # image on the page → page_reference（镜像 lecture 的 marker_only 语义），并渲染原页
            body_txt = q_text.split("\n", 1)[1] if "\n" in q_text else ""
            # 只有正文【完全没有】内容字符才算 marker-only——"2+2=?"/"求导" 这类短而完整的题面仍是 full
            marker_only = len(re.findall(r"[0-9A-Za-z一-鿿]", body_txt)) == 0
            # chapter：只在题文/文件名明说时才标（第N章 / Chapter N / chNN）——作业号 ≠ 章节号，不硬编
            chm = (re.search(r"(?:第\s*(\d+)\s*章|Chapter\s+(\d+))", q_text, re.I)
                   or re.search(r"(?:^|[\/_\-. ])ch\s*0*(\d+)", hf, re.I))
            item = {"id": "hw_%s_%d" % (stem, mk["num"]), "type": "subjective",
                    "question": q_text, "source": "material", "ai_generated": False,   # 不静默截断（长题保完整）
                    "source_type": "homework", "homework_number": mk["num"],
                    "question_text_status": "page_reference" if marker_only else "full",
                    "source_file": hf, "source_pages": q_pages or [bounds[0][1] if bounds else 1]}
            if chm:
                item["chapter"] = int(next(g for g in chm.groups() if g))
            if ans:
                sf, body, apages = ans
                item["answer"] = body                     # 不静默截断
                item["answer_source_file"] = sf
                item["answer_source_pages"] = apages or None
                if item["answer_source_pages"] is None:
                    del item["answer_source_pages"]
                report["homework_answered"] += 1
            else:
                item["answer_status"] = "unknown"
                report["warnings"].append("hw_unanswered: %s（没找到配对答案，考前需人工核对）" % item["id"])
            # visual dependence — same heuristic family as lecture items; renderable only for PDF sources
            if marker_only and is_pdf.get(hf, False):
                item["requires_assets"] = True
                item["_render"] = True
                item["_question_pages"] = [(hf, p) for p in (q_pages or [])]
            elif requires_assets_heuristic(q_text, renderable=is_pdf.get(hf, False)):
                item["requires_assets"] = True
                item["_render"] = True
                item["_question_pages"] = [(hf, p) for p in (q_pages or [])]
                if ans and requires_assets_heuristic(ans[1], renderable=is_pdf.get(ans[0], False)):
                    item["_answer_pages"] = [(ans[0], p) for p in (ans[2] or [])]
            items.append(item)
            report["homework_problems"] += 1
        if dup_counts:
            report["warnings"].append("hw_duplicate_problem: %s（%s——每题保留第一处标记，重现多为页眉/"
                                      "解答区重复）" % (hf, "、".join("Problem %d×%d" % (n, c)
                                                                      for n, c in sorted(dup_counts.items()))))
    return items, report


def group_sections(pages):
    """Group pages into chapters. A chapter number comes from a lecture marker on the page, else from
    a `ch<NN>` token in the filename, else the chapter CARRIED FORWARD from the previous page of the
    same file (so an unmarked ch-2 prose page after `Example 2.1` stays in ch 2, not ch 1), else 1.
    Returns ordered list of {chapter, files, pages, text}."""
    by_ch = {}
    order = []
    last_ch_by_file = {}
    for pg in pages:
        f = pg.get("file")
        markers = detect_lecture_markers(pg.get("text", ""))
        m = re.search(r"ch(?:apter)?[ _-]?0*(\d+)", os.path.basename(f or ""), re.I)
        if markers:
            ch = markers[0]["chapter"]
        elif m:
            ch = int(m.group(1))
        else:
            ch = last_ch_by_file.get(f, 1)   # carry forward the previous marked page's chapter (same file)
        last_ch_by_file[f] = ch
        if ch not in by_ch:
            by_ch[ch] = {"chapter": ch, "files": [], "pages": [], "text_blocks": []}
            order.append(ch)
        sec = by_ch[ch]
        if pg.get("file") not in sec["files"]:
            sec["files"].append(pg.get("file"))
        sec["pages"].append(pg.get("page"))
        if (pg.get("text") or "").strip():
            sec["text_blocks"].append("<!-- %s p.%d -->\n%s" % (pg.get("file"), pg.get("page"),
                                                                 pg.get("text", "").strip()))
    return [by_ch[c] for c in sorted(order)]


def _safe_asset_name(file, page, item_id, suffix=""):
    # keep subdirs (sanitized) so lecture/ch01.pdf and solutions/ch01.pdf don't collide on the same page
    stem = re.sub(r"[^\w.\-]", "_", os.path.splitext(file or "src")[0])
    if re.fullmatch(r"[.\-_]*", stem):         # all-dots/dashes/underscores (e.g. a ".." name) → a token
        stem = "src"
    sid = re.sub(r"[^\w.\-]", "_", str(item_id))
    return "%s_p%03d_%s%s.png" % (stem, int(page), sid, suffix)


def build_raw_input(course_name, sections, lecture_items, homework_items=None):
    """Assemble a raw_input.json compatible with scripts/ingest.py.
    `quiz_items` mirrors the bank for downstream tools; ingest reads `quiz_bank`."""
    phases = []
    for n, sec in enumerate(sections, 1):
        body = "\n\n".join(sec["text_blocks"]) or "（本章未提取到文本，请结合原始页/asset 复习）"
        phases.append({
            "phase_num": n,
            "phase_name": "第 %d 章" % sec["chapter"],
            "wiki_filename": "ch%02d.md" % sec["chapter"],
            "wiki_content": "# 第 %d 章\n\n来源文件：%s\n\n%s" % (
                sec["chapter"], "、".join(sec["files"]), body),
            "source_pages": sorted(set(p for p in sec["pages"] if p)),
        })
    if not phases:
        phases = [{"phase_num": 1, "phase_name": "第 1 章", "wiki_filename": "ch01.md",
                   "wiki_content": "# 第 1 章\n\n（未提取到内容）"}]
    # strip internal render-only keys (e.g. _answer_pages) so they don't leak into the bank
    def _clean(it):
        return {k: v for (k, v) in it.items() if not k.startswith("_")}
    bank = [_clean(it) for it in (list(lecture_items) + list(homework_items or []))]
    return {"course_name": course_name, "phases": phases, "quiz_bank": bank,
            "quiz_items": bank}   # optional mirror field (documented); ingest ignores unknown keys


# ---------------------------------------------------------------------------
# PDF backends — OPTIONAL. Core/tests never import these; tests inject a fake backend.
# ---------------------------------------------------------------------------

class NoBackend(object):
    name = "none"

    def can_text(self):
        return False

    def can_render(self):
        return False

    def page_texts(self, pdf_path):
        raise RuntimeError(
            "没有可用的 PDF 文本后端。请安装可选依赖 `pypdf`（pip install pypdf）后重试——"
            "PDF 文本提取需要它（.txt/.md 材料无需任何后端）。")

    def render_page_png(self, pdf_path, page_index):
        return None


class RealBackend(object):
    def __init__(self, text_lib=None, render_lib=None):
        self.text_lib, self.render_lib = text_lib, render_lib
        self.name = "+".join(x for x in (text_lib, render_lib) if x) or "none"

    def can_text(self):
        return bool(self.text_lib)

    def can_render(self):
        return bool(self.render_lib)

    def page_texts(self, pdf_path):
        if self.text_lib != "pypdf":
            return NoBackend().page_texts(pdf_path)
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return [(pg.extract_text() or "") for pg in reader.pages]

    def render_page_png(self, pdf_path, page_index):
        if self.render_lib == "pypdfium2":
            import io
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(pdf_path)
            bitmap = doc[page_index].render(scale=1.5)
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")   # PIL adapter — Pillow verified at detect time
            return buf.getvalue()
        if self.render_lib == "pymupdf":
            import fitz
            doc = fitz.open(pdf_path)
            return doc[page_index].get_pixmap().tobytes("png")   # native PNG, no Pillow needed
        return None


def detect_backend():
    text_lib = render_lib = None
    try:
        import pypdf  # noqa: F401
        text_lib = "pypdf"
    except Exception:
        pass
    # PyMuPDF renders to PNG natively; pypdfium2 needs Pillow for its .to_pil() adapter, so only
    # claim pypdfium2 as a render backend when Pillow is ALSO importable (else can_render() lies).
    try:
        import fitz  # noqa: F401  (PyMuPDF) — preferred: no extra deps
        render_lib = "pymupdf"
    except Exception:
        try:
            import pypdfium2  # noqa: F401
            import PIL  # noqa: F401  (Pillow — required by pypdfium2's to_pil adapter)
            render_lib = "pypdfium2"
        except Exception:
            pass
    return RealBackend(text_lib, render_lib) if (text_lib or render_lib) else NoBackend()


# ---------------------------------------------------------------------------
# Path safety + filesystem
# ---------------------------------------------------------------------------

def _under(root, child):
    root_r = os.path.normcase(os.path.realpath(root))
    child_r = os.path.normcase(os.path.realpath(child))
    return child_r == root_r or child_r.startswith(root_r + os.sep)


# Tooling/VCS dirs that NEVER hold course material → always pruned from the materials scan.
ALWAYS_PRUNE = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
                ".idea", ".vscode", ".pytest_cache", ".ipynb_checkpoints"}
# generated skill-workspace files (not course material) → skipped even if they sit at the materials root.
SKIP_FILES = {"study_plan.md", "study_progress.md", "walkthrough.md", "raw_input.json", "parse_report.json"}


def _is_leftover_workspace(path, name):
    """True only if a `references`/`scratch` dir looks like a generated skill workspace / prior-attempt
    scratch — NOT a legitimate course `references/` of real PDFs. Keyed on the workspace SIGNATURE
    (references/wiki, scratch/extracted|images) so we don't drop a real `materials/references/ch02.pdf`."""
    low = name.lower()
    if low == "references":
        # only `references/wiki` is a reliable skill-workspace signature (ingest always creates it);
        # `references/assets` alone is NOT — a course may legitimately store PDFs under references/assets.
        return os.path.isdir(os.path.join(path, "wiki"))
    if low == "scratch":
        return any(os.path.isdir(os.path.join(path, s)) for s in ("extracted", "images"))
    return False


def _is_workspace_root(path):
    """True if a directory IS a generated skill workspace (a prior run's output nested under
    --materials, e.g. `skill_workspace/`) — has `references/wiki/` or `references/quiz_bank.json`.
    The WHOLE dir is pruned so its study_progress.md / wiki / etc. never leak in as materials."""
    return (os.path.isdir(os.path.join(path, "references", "wiki"))
            or os.path.isfile(os.path.join(path, "references", "quiz_bank.json")))


def _scan_materials(materials_dir):
    """Return sorted (pdf_paths, text_paths, pruned_dirs). Prunes tooling/VCS dirs unconditionally, and
    a `references/`+`scratch/` dir ONLY when it carries a generated-workspace signature — so a prior
    workspace inside the course folder isn't re-ingested, but a real course `references/` of PDFs is kept.
    (Real case: D:\\EEC 160 held a previous ad-hoc workspace → without pruning every lecture marker was
    triplicated across the pdf + extracted .txt + wiki .md, blowing up the bank with broken items.)"""
    pdfs, texts, pruned = [], [], []
    for dirpath, dirs, files in os.walk(materials_dir):
        keep = []
        for d in dirs:
            full = os.path.join(dirpath, d)
            if d.lower() in ALWAYS_PRUNE or _is_leftover_workspace(full, d) or _is_workspace_root(full):
                pruned.append(os.path.relpath(full, materials_dir).replace(os.sep, "/"))
            else:
                keep.append(d)
        dirs[:] = keep   # os.walk: prune in place
        at_root = os.path.realpath(dirpath) == os.path.realpath(materials_dir)
        for fn in sorted(files):
            low = fn.lower()
            if at_root and low in SKIP_FILES:   # generated workspace file at the ROOT (study_plan/progress/…)
                continue                          # a same-named file in a subfolder is kept (could be real)
            full = os.path.join(dirpath, fn)
            if low.endswith(".pdf"):
                pdfs.append(full)
            elif low.endswith((".txt", ".md")):
                texts.append(full)
    return sorted(pdfs), sorted(texts), sorted(pruned)


def _rel(path, base):
    """Workspace-relative POSIX identifier for a material file (keeps subdir uniqueness, e.g.
    lecture/ch01.pdf vs homework/ch01.pdf, so same-named files in different folders don't collide)."""
    return os.path.relpath(path, base).replace(os.sep, "/")


def _read_text_file_pages(path, rel):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    parts = raw.split("\f") if "\f" in raw else [raw]
    return [{"file": rel, "page": i + 1, "text": p} for i, p in enumerate(parts)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="官方课程材料 → raw_input.json（+ 可选页面图 assets + 解析报告），供 ingest.py 使用。",
        epilog="可选依赖：文本 pip install pypdf；渲染 pip install pymupdf（自带 PNG）或 pypdfium2 Pillow。"
               "（.txt/.md 材料无需任何依赖。）")
    p.add_argument("--materials", required=True, help="课程材料文件夹（含 PDF / txt / md）")
    p.add_argument("--out", default="raw_input.json", help="输出 raw_input.json 路径")
    p.add_argument("--report", default="parse_report.json", help="解析报告 JSON 路径")
    p.add_argument("--asset-root", default=None,
                   help="渲染页图写入目录，应指向 <workspace>/references/assets。"
                        "渲染开启而未指定时：auto 跳过渲染并告警，required 报错")
    p.add_argument("--render-pages", choices=["never", "auto", "required"], default="auto",
                   help="渲染依赖图的页面：never/auto/required（required 时无渲染后端/无 --asset-root 则报错）")
    p.add_argument("--extract-lecture-questions", choices=["never", "auto"], default="auto",
                   help="是否抽取讲义 Example/Quiz 题：never/auto")
    p.add_argument("--extract-homework", choices=["never", "auto"], default="auto",
                   help="是否抽取作业题（含题答分离 PDF 的自动配对与 inline Solution）：never/auto")
    p.add_argument("--course-name", default=None, help="科目名称（默认取材料目录名）")
    return p


def run(args, backend=None):
    """Core run. `backend` injectable for tests (a fake with page_texts/render_page_png)."""
    backend = backend or detect_backend()
    report = {"materials": args.materials, "backend": getattr(backend, "name", "none"),
              "files_scanned": [], "pages_extracted": 0, "pages_rendered": 0,
              "examples_detected": 0, "quizzes_detected": 0, "pairs_detected": 0,
              "skipped": [], "warnings": []}

    materials = args.materials
    if not os.path.isdir(materials):
        return 2, {"error": "materials 目录不存在: %s" % materials}, None

    pdfs, texts, pruned = _scan_materials(materials)
    report["files_scanned"] = [os.path.relpath(p, materials) for p in (texts + pdfs)]
    report["pruned_dirs"] = pruned
    if pruned:   # fail-loud: a prior workspace/tooling dir was skipped, so the user knows why it's ignored
        report["warnings"].append("pruned_non_material_dirs: %s（不当作课程材料扫描）" % "、".join(pruned[:8]))

    # Honest dependency failure: PDFs present but no text backend → stop with a clear, actionable error.
    if pdfs and not backend.can_text():
        report["warnings"].append("no_pdf_text_backend")
        return 3, {"error": "发现 %d 个 PDF，但没有可用的 PDF 文本后端。请安装可选依赖："
                            "`pip install pypdf`（PDF 文本提取需要它；把页面渲染成图还需 "
                            "`pip install pymupdf` 或 `pypdfium2 Pillow`——只装 pypdfium2 而无 Pillow 不会启用渲染）。"
                            "纯 .txt/.md 材料无需任何依赖。" % len(pdfs)}, report

    pages = []
    for tp in texts:
        pages.extend(_read_text_file_pages(tp, _rel(tp, materials)))
    for pdf in pdfs:
        rel = _rel(pdf, materials)   # subdir-qualified identifier, not bare basename (avoids collisions)
        try:
            nonblank = 0
            for i, txt in enumerate(backend.page_texts(pdf)):
                pages.append({"file": rel, "page": i + 1, "text": txt, "_pdf": pdf})
                if (txt or "").strip():
                    nonblank += 1
            if nonblank == 0:   # image-only/scanned PDF: pypdf returns "" per page → no usable text
                report["skipped"].append({"file": rel, "why": "PDF 文本为空（可能是扫描件/图片 PDF，需 OCR，本工具不做）"})
                report["warnings"].append("pdf_no_text: %s" % rel)
        except Exception as e:  # backend present but failed on this one file → skip it, keep going
            report["skipped"].append({"file": rel, "why": "PDF 文本提取失败: %s" % e})

    report["pages_extracted"] = len(pages)
    # require some ACTUAL text, not just blank pages from a scanned PDF (else we'd emit an empty wiki and exit 0)
    if not any((p.get("text") or "").strip() for p in pages):
        report["warnings"].append("no_text_extracted")
        return 4, {"error": "未从 --materials 提取到任何文本内容（页面为空或全是扫描件/图片）。请确认有可解析的 "
                            "PDF/.txt/.md（PDF 文本需 pypdf；图片/扫描件需 OCR，本工具不做）。"}, report

    lecture_items = []
    if args.extract_lecture_questions != "never":
        lecture_items = extract_lecture_items(pages)
        report["examples_detected"] = sum(1 for it in lecture_items if it["id"].startswith("lecture_example"))
        report["quizzes_detected"] = sum(1 for it in lecture_items if it["id"].startswith("lecture_quiz"))
        report["pairs_detected"] = sum(1 for it in lecture_items if it.get("answer_source_pages"))
        # fail-loud: a solution detected with no matching problem (mis-detected pair) → surface it
        for k in orphan_solution_keys(pages):
            report["warnings"].append("solution_without_problem: %s %d.%d" % k)

    homework_items = []
    if getattr(args, "extract_homework", "auto") != "never":
        homework_items, hw_rep = extract_homework_items(pages)
        report["warnings"].extend(hw_rep.pop("warnings"))
        report.update(hw_rep)

    # ---- render assets for figure-dependent items ----
    asset_root = args.asset_root
    page_pdf = {(pg["file"], pg["page"]): pg["_pdf"] for pg in pages if pg.get("_pdf")}

    want_render = args.render_pages in ("auto", "required")
    if want_render and not backend.can_render():
        if args.render_pages == "required":
            return 3, {"error": "render-pages=required 但没有渲染后端。请安装 PyMuPDF（pip install pymupdf）"
                                "或 pypdfium2+Pillow（pip install pypdfium2 Pillow）。"}, report
        report["warnings"].append("render_unavailable")
    if want_render and not asset_root:
        if args.render_pages == "required":
            return 2, {"error": "--render-pages required 但未指定 --asset-root（应指向 "
                                "<workspace>/references/assets）。"}, report
        report["warnings"].append("asset_root_not_set: 未指定 --asset-root，跳过页图渲染——依赖图的题将因"
                                  "缺图被校验器 fail-closed；请用 --asset-root <workspace>/references/assets 渲染")
    # asset paths in raw_input are recorded as references/assets/<name>; warn if --asset-root, when given,
    # isn't the conventional <workspace>/references/assets (else on-disk files and JSON paths diverge).
    if asset_root and not os.path.normpath(asset_root).replace("\\", "/").lower().endswith("references/assets"):
        report["warnings"].append("asset_root_not_standard: JSON 里 asset 路径按 references/assets/ 记，"
                                  "请把 --asset-root 指向 <workspace>/references/assets，否则文件与路径会对不上")

    can_write = bool(asset_root) and want_render and backend.can_render()
    rendered, missing_required = 0, []
    for it in list(lecture_items) + list(homework_items):
        ans_files = {f for (f, _p) in it.get("_answer_pages", [])}
        if len(ans_files) > 1:   # answer pages span >1 source file → page numbers are ambiguous
            report["warnings"].append("answer_spans_multiple_files: %s (%s)"
                                      % (it["id"], "、".join(sorted(ans_files))))
        if not it.get("_render"):   # figure-dependent (requires_assets) OR image-prompt (marker_only)
            continue
        assets = []
        # one asset PER (file, page) — render every question page AND every (continued) answer page,
        # each from its OWN source file.
        plan = ([("question_context", f, p, "") for (f, p) in it.get("_question_pages", [])]
                + [("answer_context", f, p, "_sol") for (f, p) in it.get("_answer_pages", [])])
        for role, file, page, suffix in plan:
            name = _safe_asset_name(file, page, it["id"], suffix)
            rel_path = "references/assets/" + name
            wrote = False
            pdf = page_pdf.get((file, page))
            if can_write and pdf is not None:
                try:
                    png = backend.render_page_png(pdf, page - 1)
                except Exception as e:   # a single malformed/encrypted page must not crash the whole run
                    png = None
                    report["skipped"].append({"file": file, "why": "渲染失败 p.%d: %s" % (page, e)})
                if png:
                    full = os.path.join(asset_root, name)
                    if not _under(asset_root, full):   # name is sanitized; defensive belt-and-braces
                        report["warnings"].append("unsafe_asset_target_skipped")
                    else:
                        os.makedirs(asset_root, exist_ok=True)
                        with open(full, "wb") as f:
                            f.write(png)
                        wrote = True
                        rendered += 1
            if not wrote and role == "answer_context":
                # don't DECLARE a missing answer-side asset — it would fail-close an otherwise-valid
                # question whose own figure rendered fine (the text `answer` already covers it).
                report["warnings"].append("answer_image_unavailable: %s (p.%d)" % (it["id"], page))
                continue
            assets.append({"path": rel_path, "role": role, "type": "page_image",
                           "caption": "%s p.%d (%s)" % (file, page, role)})
            if not wrote:
                why = ("无渲染后端" if not (want_render and backend.can_render())
                       else "未指定 --asset-root" if not asset_root
                       else "该页非 PDF 来源（无法渲染）" if pdf is None
                       else "渲染返回空")
                report["warnings"].append(
                    "likely_asset_required_but_no_image: %s (%s, %s)" % (it["id"], role, why))
                # render=required fails when a needed QUESTION figure can't be produced — for a
                # requires_assets figure OR a marker-only image-prompt (both have _render; role here is
                # always question_context, since answer-side misses were already `continue`d above).
                if it.get("_render"):
                    missing_required.append("%s (%s, %s)" % (it["id"], role, why))
        it["assets"] = assets
    report["pages_rendered"] = rendered

    # --render-pages required must FAIL (not just warn) when a required figure couldn't be produced,
    # else we'd emit requires_assets=true items with missing images that the validator then rejects.
    if args.render_pages == "required" and missing_required:
        return 3, {"error": "render-pages=required 但有 %d 个必需页图未能渲染：%s。请确保对应源为可渲染的 "
                            "PDF、渲染后端可用（pymupdf 或 pypdfium2+Pillow）、并已指定 --asset-root。"
                            % (len(missing_required), "；".join(missing_required[:6]))}, report

    course = args.course_name or os.path.basename(os.path.abspath(materials)) or "未命名科目"
    raw_input = build_raw_input(course, group_sections(pages), lecture_items, homework_items)
    return 0, raw_input, report


def main(argv=None, backend=None):
    # reconfigure BEFORE parse_args so argparse's Chinese --help text prints on Windows consoles
    # (cp1252) without a UnicodeEncodeError that would make `--help` exit non-zero.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_arg_parser().parse_args(argv)
    code, raw_input, report = run(args, backend=backend)
    if code != 0:
        sys.stderr.write((raw_input or {}).get("error", "失败") + "\n")
        if report is not None:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        return code
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(raw_input, f, ensure_ascii=False, indent=2)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("[+] raw_input: %s（%d 阶段 / %d 题，其中讲义题 %d）"
          % (args.out, len(raw_input["phases"]), len(raw_input["quiz_bank"]),
             report["examples_detected"] + report["quizzes_detected"]))
    print("[+] report: %s（后端 %s，渲染 %d 页，警告 %d）"
          % (args.report, report["backend"], report["pages_rendered"], len(report["warnings"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
