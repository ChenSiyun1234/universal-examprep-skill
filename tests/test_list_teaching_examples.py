# -*- coding: utf-8 -*-
"""Tests for the chapter-scoped teaching-example selector."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "list_teaching_examples.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import list_teaching_examples as L  # noqa: E402


class ListTeachingExamples(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="teaching-list-")
        self.addCleanup(shutil.rmtree, self.ws, ignore_errors=True)
        os.makedirs(os.path.join(self.ws, "references"))

    def write(self, items):
        with open(os.path.join(self.ws, "references", "teaching_examples.json"),
                  "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, "--workspace", self.ws, *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def test_json_lists_only_requested_chapter(self):
        self.write([
            {"id": "e1", "chapter": 1, "teaching_role": "worked_example",
             "source_file": "ch01.pdf", "source_pages": [3]},
            {"id": "e2", "chapter": 2, "teaching_role": "paired_problem",
             "source_file": "ch02.pdf", "source_pages": [4],
             "answer_source_pages": [5]},
            {"id": "e3", "phase": "1", "teaching_role": "paired_problem",
             "source_file": "notes.pdf", "source_pages": [8]},
        ])
        result = self.run_cli("--chapter", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["chapter"], "1")
        self.assertEqual(payload["total_matched"], 2)
        self.assertEqual([x["id"] for x in payload["items"]], ["e1", "e3"])

    def test_chapter_is_required_to_prevent_whole_course_context_dump(self):
        self.write([])
        result = self.run_cli("--json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("chapter", result.stderr.lower())

    def test_legacy_workspace_without_manifest_returns_empty(self):
        with open(os.path.join(self.ws, "references", "quiz_bank.json"),
                  "w", encoding="utf-8") as f:
            json.dump([], f)
        result = self.run_cli("--chapter", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["total_matched"], 0)
        self.assertEqual(payload["items"], [])
        self.assertTrue(payload["manifest_missing"])

    def test_nonexistent_and_unsigned_paths_fail_loud(self):
        missing = subprocess.run(
            [sys.executable, SCRIPT, "--workspace", os.path.join(self.ws, "missing"),
             "--chapter", "1", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("does not exist", missing.stderr)

        unsigned = self.run_cli("--chapter", "1", "--json")
        self.assertEqual(unsigned.returncode, 2)
        self.assertIn("signature", unsigned.stderr)

    def test_conflicting_chapter_and_phase_fails_instead_of_union(self):
        self.write([{"id": "e1", "chapter": 1, "phase": 2,
                     "teaching_role": "worked_example"}])
        result = self.run_cli("--chapter", "1", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflicting", result.stderr)

    def test_equivalent_zero_padded_chapter_and_phase_is_not_a_conflict(self):
        self.write([{"id": "e1", "chapter": "01", "phase": 1,
                     "teaching_role": "worked_example"}])
        result = self.run_cli("--chapter", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["total_matched"], 1)

    def test_broken_symlink_is_rejected_not_treated_as_missing(self):
        # os.path.exists is false for a broken symlink; lexists must see it before islink rejects it.
        with mock.patch.object(L.os.path, "lexists", return_value=True), \
                mock.patch.object(L.os.path, "islink", return_value=True):
            with self.assertRaises(SystemExit) as caught:
                L.load_manifest(self.ws)
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
