# -*- coding: utf-8 -*-
"""End-to-end contracts for the official ingestion orchestrator."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts import ingest_course
from scripts.ingestion import ContentUnit, IngestionStore, ReviewPatch
from scripts.ingestion.pipeline import compile_review_outputs


class IngestCourseTest(unittest.TestCase):
    def run_course(self, materials, workspace):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = ingest_course.run([
                "--materials", str(materials),
                "--workspace", str(workspace),
                "--render-pages", "never",
                "--visual-index", "never",
                "--json",
            ])
        return code, json.loads(output.getvalue())

    def test_clean_text_course_is_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materials = root / "materials"
            workspace = root / "workspace"
            materials.mkdir()
            (materials / "ch01_lecture.txt").write_text(
                "Chapter 1\nCore concept\nA detailed source-backed explanation.",
                encoding="utf-8",
            )

            code, payload = self.run_course(materials, workspace)
            self.assertEqual(0, code)
            self.assertTrue(payload["process_success"])
            self.assertEqual("ready", payload["readiness"])
            self.assertTrue((workspace / ".ingest" / "build_manifest.json").is_file())
            self.assertTrue((workspace / "references" / "retrieval_index.json").is_file())

    def test_same_source_rerun_recompiles_applied_answer_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            materials = root / "materials"
            workspace = root / "workspace"
            materials.mkdir()
            (materials / "ch01_lecture.txt").write_text(
                "Chapter 1\nCore concept with enough lecture prose.\n\n"
                "Quiz 1.1 Problem\nExplain the core concept in one sentence.",
                encoding="utf-8",
            )

            first_code, first = self.run_course(materials, workspace)
            self.assertEqual(10, first_code)
            self.assertEqual("blocked", first["readiness"])

            store = IngestionStore(workspace, source_root=materials)
            question = next(
                unit for unit in store.units().values()
                if unit.kind == "question" and unit.external_id
            )
            issue = next(
                issue for issue in store.review_queue.issues()
                if "missing_answer" in issue.reason_codes
            )
            answer = ContentUnit.create(
                question.source_id,
                question.source_sha256,
                question.source_file,
                "answer",
                "Recovered answer",
                question.page,
                ordinal=question.ordinal + 1,
                external_id=question.external_id,
                chapter_id=question.chapter_id,
                phase_id=question.phase_id,
                method="ai_recovered",
                confidence=0.9,
                provenance="ai_recovered",
            )
            patch = ReviewPatch.create(
                issue.issue_id,
                issue.source_id,
                issue.source_sha256,
                [
                    {"op": "add_unit", "unit": answer.to_dict()},
                    {
                        "op": "pair_qa",
                        "question_unit_id": question.unit_id,
                        "answer_unit_id": answer.unit_id,
                    },
                ],
                list(issue.evidence),
                reviewer="test",
                created_at="2026-07-14T12:00:00Z",
                status="validated",
            )
            store.apply_patch(patch)
            compile_review_outputs(workspace)

            second_code, second = self.run_course(materials, workspace)
            self.assertEqual(0, second_code)
            self.assertIn(second["readiness"], ("ready", "usable_with_gaps"))
            bank = json.loads(
                (workspace / "references" / "quiz_bank.json").read_text(encoding="utf-8")
            )
            item = next(row for row in bank if row["id"] == question.external_id)
            self.assertEqual("Recovered answer", item["answer"])
            report = json.loads(
                (workspace / "ingest_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual([], report["missing_answer_ids"])
            self.assertEqual("applied", store.review_queue.get(issue.issue_id).status)

    def test_missing_materials_directory_fails_before_workspace_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing = root / "missing"
            workspace = root / "workspace"
            code, payload = self.run_course(missing, workspace)
            self.assertEqual(2, code)
            self.assertFalse(payload["process_success"])
            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
