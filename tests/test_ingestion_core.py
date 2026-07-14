import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ingestion import (
    ChapterPhaseMapping,
    ConflictError,
    ContentUnit,
    EvidenceRef,
    IngestionStore,
    PatchApplicationError,
    ReviewIssue,
    ReviewPatch,
    SchemaValidationError,
    SourceDriftError,
    SourceRecord,
    UnsafePathError,
    atomic_write_json,
    atomic_write_jsonl,
    make_source_id,
    normalize_workspace_path,
    read_json,
    read_jsonl,
)


ZERO_SHA = "0" * 64


class IngestionCoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.source_path = self.workspace / "materials" / "week01.pdf"
        self.source_path.parent.mkdir(parents=True)
        self.source_path.write_bytes(b"course material revision one")
        self.evidence_path = self.workspace / "scratch" / "pages" / "week01-p1.png"
        self.evidence_path.parent.mkdir(parents=True)
        self.evidence_path.write_bytes(b"fake but content-addressed png evidence")

        self.source = SourceRecord.from_file(
            self.workspace, "materials/week01.pdf", "application/pdf", status="parsed"
        )
        self.evidence = EvidenceRef.from_file(
            self.workspace, "scratch/pages/week01-p1.png"
        )
        self.store = IngestionStore(self.workspace)
        self.store.manifest.upsert(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def unit(
        self, kind, text, page, ordinal, asset=False, provenance="material",
        external_id=None,
    ):
        asset_path = "references/assets/week01-p1.png" if asset else None
        if asset:
            destination = self.workspace / asset_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"question asset")
        return ContentUnit.create(
            source_id=self.source.source_id,
            source_sha256=self.source.sha256,
            source_file=self.source.path,
            kind=kind,
            text=text,
            page=page,
            ordinal=ordinal,
            external_id=external_id,
            bbox=(10, 20 + ordinal, 500, 90 + ordinal),
            asset_path=asset_path,
            provenance=provenance,
        )

    def issue(self, reason, targets=(), status="pending"):
        issue = ReviewIssue.create(
            source_id=self.source.source_id,
            source_sha256=self.source.sha256,
            reason_codes=[reason],
            pages=[1],
            evidence=[self.evidence],
            target_unit_ids=targets,
            description="Review page one for %s" % reason,
            status=status,
        )
        self.store.review_queue.append(issue)
        return issue

    def test_stable_ids_and_strict_model_round_trips(self):
        self.assertEqual(
            make_source_id("materials\\week01.pdf"),
            make_source_id("materials/week01.pdf"),
        )
        source_again = SourceRecord.from_dict(self.source.to_dict())
        self.assertEqual(self.source, source_again)

        unit_a = self.unit("page_anchor", "Page 1", 1, 0)
        unit_b = ContentUnit.create(
            self.source.source_id,
            self.source.sha256,
            self.source.path,
            "page_anchor",
            "Different presentation text does not alter locator identity",
            1,
            ordinal=0,
            bbox=(10.0, 20.0, 500.0, 90.0),
        )
        self.assertEqual(unit_a.unit_id, unit_b.unit_id)
        self.assertEqual(unit_a, ContentUnit.from_dict(unit_a.to_dict()))

        mapping = ChapterPhaseMapping.create(
            unit_a.unit_id, self.source.source_id, self.source.sha256,
            "Chapter 1", "Phase 1", "ch01", "phase01"
        )
        self.assertEqual(mapping, ChapterPhaseMapping.from_dict(mapping.to_dict()))

        issue_a = ReviewIssue.create(
            self.source.source_id,
            self.source.sha256,
            ["visual_question", "no_text"],
            [self.evidence],
            "Needs visual recovery",
            pages=[3, 1, 3],
            target_unit_ids=[unit_a.unit_id],
        )
        issue_b = ReviewIssue.create(
            self.source.source_id,
            self.source.sha256,
            ["no_text", "visual_question"],
            [self.evidence],
            "Localized wording may differ",
            pages=[1, 3],
            target_unit_ids=[unit_a.unit_id],
        )
        self.assertEqual(issue_a.issue_id, issue_b.issue_id)
        self.assertEqual(issue_a, ReviewIssue.from_dict(issue_a.to_dict()))

        operation_a = {"op": "add_unit", "unit": unit_a.to_dict()}
        operation_b = {"unit": unit_a.to_dict(), "op": "add_unit"}
        patch_a = ReviewPatch.create(
            issue_a.issue_id,
            self.source.source_id,
            self.source.sha256,
            [operation_a],
            [self.evidence],
        )
        patch_b = ReviewPatch.create(
            issue_a.issue_id,
            self.source.source_id,
            self.source.sha256,
            [operation_b],
            [self.evidence],
        )
        self.assertEqual(patch_a.patch_id, patch_b.patch_id)
        self.assertEqual(patch_a, ReviewPatch.from_dict(patch_a.to_dict()))

    def test_workspace_paths_reject_traversal_absolute_drive_and_unc(self):
        invalid = (
            "../secret.pdf",
            "materials/../../secret.pdf",
            "/etc/passwd",
            "C:\\course\\notes.pdf",
            "C:notes.pdf",
            "\\\\server\\share\\notes.pdf",
            "//server/share/notes.pdf",
            "materials//notes.pdf",
            "materials/./notes.pdf",
            " materials/notes.pdf",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(UnsafePathError):
                    normalize_workspace_path(value)

        with self.assertRaises(UnsafePathError):
            SourceRecord.create("../x.pdf", ZERO_SHA, 0, "application/pdf")
        with self.assertRaises(SchemaValidationError):
            EvidenceRef("../evidence.png", ZERO_SHA)
        with self.assertRaises(UnsafePathError):
            ContentUnit.create(
                self.source.source_id,
                self.source.sha256,
                self.source.path,
                "figure",
                "",
                1,
                asset_path="C:\\outside.png",
            )

    def test_schema_and_status_validation_are_fail_closed(self):
        raw = self.source.to_dict()
        raw["unknown"] = True
        with self.assertRaises(SchemaValidationError):
            SourceRecord.from_dict(raw)

        raw = self.source.to_dict()
        raw["status"] = "done-ish"
        with self.assertRaises(SchemaValidationError):
            SourceRecord.from_dict(raw)

        raw = self.source.to_dict()
        raw["source_id"] = "src_" + "f" * 64
        with self.assertRaises(SchemaValidationError):
            SourceRecord.from_dict(raw)

        issue = ReviewIssue.create(
            self.source.source_id,
            self.source.sha256,
            ["no_text"],
            [self.evidence],
            "No extractable text",
        )
        bad_issue = issue.to_dict()
        bad_issue["status"] = "complete"
        with self.assertRaises(SchemaValidationError):
            ReviewIssue.from_dict(bad_issue)

        with self.assertRaises(SchemaValidationError):
            ReviewPatch.create(
                issue.issue_id,
                self.source.source_id,
                self.source.sha256,
                [{"op": "delete_unit", "unit_id": "unit_" + "0" * 64}],
                [self.evidence],
            )

    def test_atomic_json_and_jsonl_round_trip(self):
        json_path = self.workspace / "scratch" / "atomic.json"
        jsonl_path = self.workspace / "scratch" / "atomic.jsonl"
        atomic_write_json(json_path, {"z": 1, "中文": [2, 3]})
        atomic_write_jsonl(jsonl_path, [{"id": 1}, {"id": 2}])
        self.assertEqual({"z": 1, "中文": [2, 3]}, read_json(json_path))
        self.assertEqual([{"id": 1}, {"id": 2}], read_jsonl(jsonl_path))
        self.assertEqual([], list(json_path.parent.glob(".*.tmp")))

    def test_manifest_and_review_queue_append_are_idempotent(self):
        self.assertFalse(self.store.manifest.upsert(self.source))
        parsed_again = SourceRecord.create(
            self.source.path,
            self.source.sha256,
            self.source.size_bytes,
            self.source.media_type,
            status="review_required",
        )
        self.assertTrue(self.store.manifest.upsert(parsed_again))
        self.assertFalse(self.store.manifest.upsert(parsed_again))

        issue = ReviewIssue.create(
            self.source.source_id,
            self.source.sha256,
            ["no_text"],
            [self.evidence],
            "First description",
        )
        self.assertTrue(self.store.review_queue.append(issue))
        self.assertFalse(self.store.review_queue.append(issue))
        conflict = ReviewIssue.create(
            self.source.source_id,
            self.source.sha256,
            ["no_text"],
            [self.evidence],
            "Different description, same immutable issue identity",
        )
        self.assertEqual(issue.issue_id, conflict.issue_id)
        with self.assertRaises(ConflictError):
            self.store.review_queue.append(conflict)

    def test_all_allow_list_operations_apply_and_replay_idempotently(self):
        question = self.unit(
            "question", "Old prompt", 1, 1, asset=True, external_id="q1"
        )
        answer = self.unit("answer", "42", 1, 2, external_id="q1")
        self.store.append_unit(question)
        self.store.append_unit(answer)

        added = self.unit("text", "AI recovered explanation", 1, 3, provenance="ai_recovered")
        replaced_question = ContentUnit.create(
            self.source.source_id,
            self.source.sha256,
            self.source.path,
            "question",
            "Recovered full prompt",
            1,
            ordinal=1,
            external_id="q1",
            bbox=question.bbox,
            asset_path=question.asset_path,
            provenance="ai_recovered",
        )
        self.assertEqual(question.unit_id, replaced_question.unit_id)

        issue = self.issue("visual_question", [question.unit_id, answer.unit_id])
        patch = ReviewPatch.create(
            issue.issue_id,
            self.source.source_id,
            self.source.sha256,
            [
                {"op": "replace_unit", "unit_id": question.unit_id, "unit": replaced_question.to_dict()},
                {"op": "add_unit", "unit": added.to_dict()},
                {"op": "assign_chapter", "unit_id": question.unit_id, "chapter": "Chapter 1",
                 "phase": "Phase 1", "chapter_id": "ch01", "phase_id": "phase01"},
                {"op": "pair_qa", "question_unit_id": question.unit_id, "answer_unit_id": answer.unit_id},
                {"op": "classify_asset", "unit_id": question.unit_id, "asset_role": "question_context"},
            ],
            [self.evidence],
            status="validated",
        )

        result = self.store.apply_patch(patch)
        self.assertTrue(result.applied)
        self.assertFalse(result.replayed)
        self.assertEqual("applied", result.issue_status)

        units = self.store.units()
        self.assertEqual("Recovered full prompt", units[question.unit_id].text)
        self.assertEqual("question_context", units[question.unit_id].asset_role)
        self.assertEqual(answer.unit_id, units[question.unit_id].paired_unit_id)
        self.assertEqual(question.unit_id, units[answer.unit_id].paired_unit_id)
        self.assertIn(added.unit_id, units)
        self.assertEqual("Chapter 1", self.store.mappings()[question.unit_id].chapter)
        self.assertEqual("applied", self.store.review_queue.get(issue.issue_id).status)

        replay = self.store.apply_patch(patch)
        self.assertFalse(replay.applied)
        self.assertTrue(replay.replayed)
        self.assertEqual(1, len(read_jsonl(self.store.ledger_path)))

    def test_patch_status_and_target_scope_are_checked(self):
        question = self.unit("question", "Prompt", 1, 1)
        other = self.unit("text", "Other", 1, 2)
        self.store.append_unit(question)
        self.store.append_unit(other)
        issue = self.issue("chapter_ambiguous", [question.unit_id])

        proposed = ReviewPatch.create(
            issue.issue_id,
            self.source.source_id,
            self.source.sha256,
            [{"op": "assign_chapter", "unit_id": question.unit_id, "chapter": "1", "phase": "1",
              "chapter_id": "ch01", "phase_id": "phase01"}],
            [self.evidence],
            status="proposed",
        )
        with self.assertRaises(PatchApplicationError):
            self.store.apply_patch(proposed)

        out_of_scope = ReviewPatch.create(
            issue.issue_id,
            self.source.source_id,
            self.source.sha256,
            [{"op": "assign_chapter", "unit_id": other.unit_id, "chapter": "1", "phase": "1",
              "chapter_id": "ch01", "phase_id": "phase01"}],
            [self.evidence],
            status="validated",
        )
        with self.assertRaises(PatchApplicationError):
            self.store.apply_patch(out_of_scope)
        self.assertEqual({}, self.store.mappings())

    def test_source_drift_rejects_patch_before_mutation(self):
        issue = self.issue("no_text")
        recovered = self.unit("text", "Recovered", 1, 9, provenance="ai_recovered")
        patch = ReviewPatch.create(
            issue.issue_id,
            self.source.source_id,
            self.source.sha256,
            [{"op": "add_unit", "unit": recovered.to_dict()}],
            [self.evidence],
            status="validated",
        )
        self.source_path.write_bytes(b"course material changed after review")
        with self.assertRaises(SourceDriftError):
            self.store.apply_patch(patch)
        self.assertEqual({}, self.store.units())
        self.assertEqual([], read_jsonl(self.store.ledger_path, default=[]))

    def test_evidence_drift_rejects_patch(self):
        issue = self.issue("no_text")
        patch = ReviewPatch.create(
            issue.issue_id,
            self.source.source_id,
            self.source.sha256,
            [{"op": "mark_unrecoverable", "reason": "Image is illegible"}],
            [self.evidence],
            status="validated",
        )
        self.evidence_path.write_bytes(b"evidence changed after review")
        with self.assertRaises(SourceDriftError):
            self.store.apply_patch(patch)
        self.assertEqual("pending", self.store.review_queue.get(issue.issue_id).status)

    def test_mark_unrecoverable_is_allow_list_terminal_operation(self):
        issue = self.issue("encrypted_source")
        patch = ReviewPatch.create(
            issue.issue_id,
            self.source.source_id,
            self.source.sha256,
            [{"op": "mark_unrecoverable", "reason": "Password was not provided"}],
            [self.evidence],
            status="validated",
        )
        result = self.store.apply_patch(patch)
        self.assertEqual("unrecoverable", result.issue_status)
        self.assertEqual("unrecoverable", self.store.review_queue.get(issue.issue_id).status)

        unit = self.unit("text", "Not permitted alongside terminal op", 1, 10)
        with self.assertRaises(SchemaValidationError):
            ReviewPatch.create(
                issue.issue_id,
                self.source.source_id,
                self.source.sha256,
                [
                    {"op": "mark_unrecoverable", "reason": "No"},
                    {"op": "add_unit", "unit": unit.to_dict()},
                ],
                [self.evidence],
            )


if __name__ == "__main__":
    unittest.main()
