# -*- coding: utf-8 -*-
"""Tests for scripts/build_raw_input_from_workspace.py — the official course-material builder.

All tests are stdlib-only and NEVER import pypdf/pypdfium2/PyMuPDF: the parser core runs on
synthetic page text, and the PDF backend is a fake object injected into run(). This mirrors CI,
where the optional PDF dependencies are not installed.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import build_raw_input_from_workspace as B  # noqa: E402


# --------------------------------------------------------------------------- helpers

class FakeBackend(object):
    """Stands in for a real pypdf/pypdfium2 backend. `pages_by_file` maps a pdf basename to a
    list of per-page text strings; `can_render` toggles whether page rendering is available."""

    def __init__(self, pages_by_file, can_render=True):
        self._pages = pages_by_file
        self._can_render = can_render
        self.name = "fake"

    def can_text(self):
        return True

    def can_render(self):
        return self._can_render

    def page_texts(self, pdf_path):
        return self._pages.get(os.path.basename(pdf_path), [])

    def render_page_png(self, pdf_path, page_index):
        if not self._can_render:
            return None
        return b"\x89PNG\r\n\x1a\n" + bytes([page_index & 0xFF])  # tiny non-empty fake PNG


def _pages(file, *texts):
    return [{"file": file, "page": i + 1, "text": t} for i, t in enumerate(texts)]


def _materials_with_pdf(basename="ch01.pdf"):
    """A temp materials dir holding one empty .pdf on disk (the fake backend supplies its text)."""
    d = tempfile.mkdtemp(prefix="mat-")
    with open(os.path.join(d, basename), "wb") as f:
        f.write(b"%PDF-1.4 fake")
    return d


def _args(materials, **over):
    out = over.pop("out", os.path.join(materials, "raw_input.json"))
    rep = over.pop("report", os.path.join(materials, "parse_report.json"))
    aroot = over.pop("asset_root", os.path.join(materials, "ws", "references", "assets"))
    argv = ["--materials", materials, "--out", out, "--report", rep, "--asset-root", aroot]
    for k, v in over.items():
        argv += ["--" + k.replace("_", "-"), v]
    return B.build_arg_parser().parse_args(argv)


# --------------------------------------------------------------------------- pure-core tests

class CoreExtraction(unittest.TestCase):
    def test_requires_assets_heuristic(self):
        self.assertTrue(B.requires_assets_heuristic("Shade the Venn diagram at right."))
        self.assertTrue(B.requires_assets_heuristic("see the figure / table below"))
        self.assertFalse(B.requires_assets_heuristic("Compute 2 + 2 and simplify."))

    def test_detect_example_problem_and_solution(self):
        pages = _pages("ch01.pdf",
                       "Example 1.1 Problem  Prove the identity.",
                       "Example 1.1 Solution  By induction ...")
        items = B.extract_lecture_items(pages)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["id"], "lecture_example_1_1")
        self.assertEqual(it["source_pages"], [1])
        self.assertEqual(it["answer_source_pages"], [2])

    def test_detect_quiz_and_solution(self):
        pages = _pages("ch01.pdf", "Quiz 1.1  State the theorem.", "Quiz 1.1 Solution  It says ...")
        items = B.extract_lecture_items(pages)
        self.assertEqual([it["id"] for it in items], ["lecture_quiz_1_1"])
        self.assertEqual(items[0]["answer_source_pages"], [2])

    def test_merges_continued_solution_pages(self):
        pages = _pages("ch01.pdf",
                       "Quiz 1.4  Long one.",
                       "Quiz 1.4 Solution  part 1",
                       "Quiz 1.4 Solution (Continued 2)  part 2")
        items = B.extract_lecture_items(pages)
        self.assertEqual(items[0]["answer_source_pages"], [2, 3])

    def test_stable_ids_and_dedup(self):
        pages = _pages("ch01.pdf",
                       "Quiz 1.1  v1.",
                       "Quiz 1.1  duplicated heading v2.",
                       "Quiz 1.1 Solution  s.")
        ids = [it["id"] for it in B.extract_lecture_items(pages)]
        self.assertEqual(ids, ["lecture_quiz_1_1"])  # deduped by (kind, chapter, num)
        # determinism: same input -> identical output
        again = [it["id"] for it in B.extract_lecture_items(pages)]
        self.assertEqual(ids, again)

    def test_requires_assets_flag_on_venn(self):
        pages = _pages("ch01.pdf",
                       "Quiz 1.1  Shade the corresponding region in the Venn diagram at right.",
                       "Quiz 1.1 Solution  A∩B.")
        it = B.extract_lecture_items(pages)[0]
        self.assertTrue(it["requires_assets"])
        self.assertEqual(it["question_text_status"], "page_reference")
        self.assertEqual(it["type"], "diagram")

    def test_plain_question_is_not_asset_required(self):
        pages = _pages("ch01.pdf", "Example 2.3 Problem  Compute the sum 1+...+n.",
                       "Example 2.3 Solution  n(n+1)/2.")
        it = B.extract_lecture_items(pages)[0]
        self.assertFalse(it["requires_assets"])
        self.assertEqual(it["question_text_status"], "full")

    def test_problem_text_containing_solution_not_misclassified(self):
        # P1 regression: a problem whose text mentions "solution" must stay a problem (not dropped)
        cases = [
            ("Example 4.4 Problem  Find the solution set of the inequality.", "Example 4.4 Solution  x>2."),
            ("Quiz 6.1  Sketch the solution curve.", "Quiz 6.1 Solution  see plot."),
            ("Example 5.2 Problem: write the general solution.", "Example 5.2 Solution  y=Ce^x."),
        ]
        for prob, sol in cases:
            items = B.extract_lecture_items([{"file": "ch.pdf", "page": 1, "text": prob},
                                             {"file": "ch.pdf", "page": 2, "text": sol}])
            self.assertEqual(len(items), 1, "dropped pair for: %r -> %r" % (prob, items))
            self.assertEqual(items[0]["answer_source_pages"], [2])

    def test_orphan_solution_keys_detected(self):
        pages = _pages("ch.pdf", "Example 9.9 Solution  answer with no problem page.")
        self.assertIn(("example", 9, 9), B.orphan_solution_keys(pages))

    def test_solution_before_problem_still_paired(self):
        # P2 regression: solution page preceding its problem must still be claimed
        pages = _pages("ch.pdf", "Example 1.1 Solution  ans here.", "Example 1.1 Problem  the question.")
        it = B.extract_lecture_items(pages)[0]
        self.assertEqual(it["answer_source_pages"], [1])
        self.assertNotIn("answer_status", it)

    def test_continued_solution_after_intervening_problem(self):
        # P2 regression: a continued solution page after a different problem is not lost
        pages = _pages("ch.pdf",
                       "Example 1.1 Problem  q1.",
                       "Example 1.1 Solution  part1.",
                       "Example 1.2 Problem  q2.",
                       "Example 1.1 Solution (Continued)  part2.")
        items = {it["id"]: it for it in B.extract_lecture_items(pages)}
        self.assertEqual(items["lecture_example_1_1"]["answer_source_pages"], [2, 4])

    def test_heuristic_excludes_known_false_positives(self):
        for t in ("See the table of contents on page 2.", "Just figure it out yourself.",
                  "The graph theory chapter is hard."):
            self.assertFalse(B.requires_assets_heuristic(t), "false positive: %r" % t)

    def test_section_grouping_from_headings(self):
        pages = (_pages("a.pdf", "Quiz 1.1  x") + _pages("b.pdf", "Example 2.1 Problem  y"))
        secs = B.group_sections(pages)
        self.assertEqual([s["chapter"] for s in secs], [1, 2])

    def test_section_grouping_from_filename_when_no_heading(self):
        pages = _pages("ch03_notes.pdf", "no markers here, just prose")
        self.assertEqual(B.group_sections(pages)[0]["chapter"], 3)

    def test_homework_items_not_dropped(self):
        hw = [{"id": "hw_1", "type": "subjective", "question": "q", "answer": "a", "source": "material"}]
        lec = [{"id": "lecture_quiz_1_1", "type": "diagram", "question": "q", "source": "material"}]
        ri = B.build_raw_input("C", [{"chapter": 1, "files": ["ch01.pdf"], "pages": [1], "text_blocks": ["t"]}],
                               lec, homework_items=hw)
        ids = [q["id"] for q in ri["quiz_bank"]]
        self.assertIn("hw_1", ids)
        self.assertIn("lecture_quiz_1_1", ids)


# --------------------------------------------------------------------------- CLI / run() tests

class CliAndRun(unittest.TestCase):
    def test_cli_help_without_pdf_deps(self):
        # the script emits UTF-8 (it reconfigures stdout); decode UTF-8 explicitly so the test is
        # independent of the OS console locale (cp1252 on CI / gbk on a zh Windows box).
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_raw_input_from_workspace.py"), "--help"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0)
        self.assertIn("materials", r.stdout)

    def test_missing_pdf_backend_clear_error(self):
        d = _materials_with_pdf()
        code, payload, report = B.run(_args(d), backend=B.NoBackend())
        self.assertEqual(code, 3)
        self.assertIn("pypdf", payload["error"])
        self.assertIn("no_pdf_text_backend", report["warnings"])

    def test_txt_materials_work_without_backend(self):
        d = tempfile.mkdtemp(prefix="mat-")
        with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("Example 1.1 Problem  hi\n")
        code, ri, report = B.run(_args(d), backend=B.NoBackend())  # no PDFs -> stdlib path works
        self.assertEqual(code, 0)
        self.assertGreaterEqual(report["pages_extracted"], 1)

    def test_render_required_without_backend_errors(self):
        d = _materials_with_pdf()
        be = FakeBackend({"ch01.pdf": ["Quiz 1.1  Venn diagram at right.", "Quiz 1.1 Solution  s"]},
                         can_render=False)
        code, payload, _ = B.run(_args(d, render_pages="required"), backend=be)
        self.assertEqual(code, 3)
        self.assertIn("pypdfium2", payload["error"])

    def test_emits_asset_metadata_when_rendered(self):
        d = _materials_with_pdf()
        be = FakeBackend({"ch01.pdf": ["Quiz 1.1  Shade the Venn diagram at right.",
                                       "Quiz 1.1 Solution  A∩B."]})
        args = _args(d)
        code, ri, report = B.run(args, backend=be)
        self.assertEqual(code, 0)
        item = next(q for q in ri["quiz_bank"] if q["id"] == "lecture_quiz_1_1")
        self.assertTrue(item["requires_assets"])
        qside = [a for a in item["assets"] if a["role"] == "question_context"]
        self.assertTrue(qside)
        # the rendered PNG actually exists on disk under the asset root
        png = os.path.join(args.asset_root, os.path.basename(qside[0]["path"]))
        self.assertTrue(os.path.isfile(png))
        self.assertGreaterEqual(report["pages_rendered"], 1)

    def test_warns_when_asset_required_but_no_render(self):
        d = _materials_with_pdf()
        be = FakeBackend({"ch01.pdf": ["Quiz 1.1  Venn diagram at right.", "Quiz 1.1 Solution  s"]},
                         can_render=False)
        code, ri, report = B.run(_args(d, render_pages="auto"), backend=be)
        self.assertEqual(code, 0)
        self.assertTrue(any("likely_asset_required_but_no_image" in w for w in report["warnings"]))


# --------------------------------------------------------------------------- ingest integration

def _ingest(raw_input_path, out_dir):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "ingest.py"),
                           "-i", raw_input_path, "-o", out_dir],
                          capture_output=True, text=True, encoding="utf-8")


def _validate(ws):
    spec = importlib.util.spec_from_file_location("vw", os.path.join(SCRIPTS, "validate_workspace.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class IngestIntegration(unittest.TestCase):
    def test_generated_raw_input_accepted_by_ingest(self):
        d = _materials_with_pdf()
        be = FakeBackend({"ch01.pdf": ["Example 1.1 Problem  compute.", "Example 1.1 Solution  ok."]})
        args = _args(d)
        code, ri, _ = B.run(args, backend=be)
        self.assertEqual(code, 0)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(ri, f, ensure_ascii=False)
        ws = os.path.join(d, "ws")
        r = _ingest(args.out, ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(ws, "references", "quiz_bank.json")))

    def test_asset_fields_survive_into_quiz_bank(self):
        d = _materials_with_pdf()
        be = FakeBackend({"ch01.pdf": ["Quiz 1.1  Shade the Venn diagram at right.", "Quiz 1.1 Solution  s."]})
        args = _args(d)  # asset-root points into ws/references/assets so renders land in the workspace
        args.asset_root = os.path.join(d, "ws", "references", "assets")
        code, ri, _ = B.run(args, backend=be)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(ri, f, ensure_ascii=False)
        ws = os.path.join(d, "ws")
        self.assertEqual(_ingest(args.out, ws).returncode, 0)
        with open(os.path.join(ws, "references", "quiz_bank.json"), encoding="utf-8") as f:
            qb = json.load(f)
        item = next(q for q in qb if q["id"] == "lecture_quiz_1_1")
        for k in ("source_file", "source_pages", "assets", "requires_assets", "question_text_status"):
            self.assertIn(k, item)
        # and the generated workspace validates clean (the rendered asset exists on disk)
        V = _validate(ws)
        self.assertEqual(V._exit_code(V.validate(ws)[0]), 0)

    def test_validator_catches_missing_asset_from_generated_item(self):
        # render unavailable -> requires_assets item has an asset path but no file -> validator errors
        d = _materials_with_pdf()
        be = FakeBackend({"ch01.pdf": ["Quiz 1.1  Venn diagram at right.", "Quiz 1.1 Solution  s."]},
                         can_render=False)
        args = _args(d, render_pages="auto")
        args.asset_root = os.path.join(d, "ws", "references", "assets")
        code, ri, _ = B.run(args, backend=be)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(ri, f, ensure_ascii=False)
        ws = os.path.join(d, "ws")
        self.assertEqual(_ingest(args.out, ws).returncode, 0)
        V = _validate(ws)
        errors = V.validate(ws)[0]
        self.assertEqual(V._exit_code(errors), 1)  # missing required asset -> fail-closed

    def test_old_handauthored_raw_input_still_works(self):
        d = tempfile.mkdtemp(prefix="old-")
        ri = {"course_name": "Old", "phases": [{"phase_num": 1, "phase_name": "P1",
              "wiki_filename": "ch1.md", "wiki_content": "# c"}],
              "quiz_bank": [{"id": "q1", "chapter": 1, "type": "choice", "question": "?",
                             "options": ["A", "B"], "answer": "A", "source": "material"}]}
        p = os.path.join(d, "raw_input.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ri, f)
        ws = os.path.join(d, "ws")
        self.assertEqual(_ingest(p, ws).returncode, 0)


class Hygiene(unittest.TestCase):
    def test_no_required_pdf_dependencies(self):
        with open(os.path.join(SCRIPTS, "build_raw_input_from_workspace.py"), encoding="utf-8") as f:
            src = f.read()
        # optional backends must only be imported lazily (inside functions), never at module top level
        head = src[:src.index("def ")]
        for dep in ("import pypdf", "import pypdfium2", "import fitz", "import requests"):
            self.assertNotIn(dep, head)

    def test_no_committed_course_pdfs_or_images(self):
        # the repo must not carry real course PDFs or slide images
        for dirpath, _dirs, files in os.walk(ROOT):
            if ".git" in dirpath:
                continue
            for fn in files:
                low = fn.lower()
                if low.endswith(".pdf"):
                    self.fail("committed PDF found: %s" % os.path.join(dirpath, fn))
                if low.endswith((".png", ".jpg", ".jpeg")):
                    size = os.path.getsize(os.path.join(dirpath, fn))
                    self.assertLess(size, 4096, "suspiciously large image (real slide?): %s" %
                                    os.path.join(dirpath, fn))


if __name__ == "__main__":
    unittest.main(verbosity=2)
