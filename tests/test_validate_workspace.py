#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for scripts/validate_workspace.py (Tier-0 unit, stdlib only, no network/LLM).

    python -m unittest discover -s tests -v
"""
import io
import os
import sys
import json
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import validate_workspace as V  # noqa: E402

FX = os.path.join(ROOT, "tests", "fixtures")


def run(name):
    """Validate a fixture; return (errors, warnings, stats, exit_code)."""
    errors, warnings, stats = V.validate(os.path.join(FX, name))
    return errors, warnings, stats, V._exit_code(errors)


def err_text(errors):
    return " | ".join(e["msg"] for e in errors)


def warn_text(warnings):
    return " | ".join(w["msg"] for w in warnings)


class TestValidateWorkspace(unittest.TestCase):

    def test_valid_workspace_returns_0(self):
        errors, warnings, stats, code = run("valid_workspace")
        self.assertEqual(code, 0, f"valid workspace had errors: {err_text(errors)}")
        self.assertEqual([e for e in errors], [])
        self.assertEqual(stats.get("quiz_items"), 7)

    def test_missing_quizbank_is_error(self):
        errors, _, _, code = run("invalid_workspace_missing_quizbank")
        self.assertEqual(code, 1)
        self.assertIn("quiz_bank.json", err_text(errors))

    def test_invalid_json_is_exit_2(self):
        errors, _, _, code = run("invalid_workspace_bad_json")
        self.assertEqual(code, 2)
        self.assertTrue(any(e["level"] == "fatal" for e in errors))

    def test_duplicate_quiz_ids_rejected(self):
        errors, _, _, code = run("invalid_workspace_dupe_type")
        self.assertEqual(code, 1)
        self.assertIn("重复的题目 id", err_text(errors))

    def test_unknown_quiz_type_rejected(self):
        errors, *_ = run("invalid_workspace_dupe_type")
        self.assertIn("type 非法", err_text(errors))

    def test_choice_without_options_rejected(self):
        errors, *_ = run("invalid_workspace_dupe_type")
        self.assertIn("choice 题必须有非空 options", err_text(errors))

    def test_subjective_without_keywords_warns(self):
        errors, warnings, _, code = run("warnings_workspace")
        self.assertEqual(code, 0, f"warnings-only workspace must stay valid: {err_text(errors)}")
        self.assertIn("keywords", warn_text(warnings))

    def test_diagram_without_diagram_type_warns(self):
        _, warnings, _, _ = run("warnings_workspace")
        self.assertIn("diagram_type", warn_text(warnings))

    def test_missing_answer_without_provenance_is_error(self):
        errors, _, _, code = run("invalid_workspace_provenance")
        self.assertEqual(code, 1)
        self.assertIn("缺答案必须如实标注", err_text(errors))

    def test_ai_generated_answer_without_marker_rejected(self):
        errors, *_ = run("invalid_workspace_provenance")
        self.assertTrue(any("AI 生成答案" in e["msg"] for e in errors),
                        "an AI-generated answer mislabeled as teacher must be rejected")

    def test_path_traversal_wiki_reference_rejected(self):
        errors, _, _, code = run("invalid_workspace_traversal")
        self.assertEqual(code, 1)
        self.assertIn("路径穿越", err_text(errors))

    def test_json_output_parses(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = V.main([os.path.join(FX, "valid_workspace"), "--json"])
        payload = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["exit_code"], 0)
        self.assertTrue(payload["ok"])
        for key in ("errors", "warnings", "stats"):
            self.assertIn(key, payload)

    def test_unreadable_workspace_is_exit_2(self):
        errors, _, _, code = run("does_not_exist_dir")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
