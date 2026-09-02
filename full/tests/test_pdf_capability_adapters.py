# -*- coding: utf-8 -*-
import json
import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "docs", "pdf-capability-adapters.json")


class PdfCapabilityAdapters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REGISTRY, encoding="utf-8") as fh:
            cls.data = json.load(fh)
        cls.runtimes = {entry["id"]: entry for entry in cls.data["runtimes"]}

    def test_policy_never_silently_downloads(self):
        policy = self.data["policy"]
        self.assertFalse(policy["automatic_network_install"])
        self.assertFalse(policy["external_source_rules"]["runtime_download_without_confirmation"])
        self.assertIn("inspect_the_latest_render", policy["required_visual_qa"])

    def test_required_runtimes_are_distinct(self):
        self.assertEqual(
            set(self.runtimes), {"codex", "claude_code", "generic_agent_skills"}
        )
        self.assertEqual(len(self.runtimes), len(self.data["runtimes"]))

    def test_external_sources_are_https_and_commit_pinned(self):
        sha = re.compile(r"^[0-9a-f]{40}$")
        source_blocks = [
            self.runtimes["codex"]["current_catalog"],
            self.runtimes["codex"]["historical_reference"],
            self.runtimes["claude_code"]["source"],
            self.runtimes["generic_agent_skills"]["standard"],
        ]
        for source in source_blocks:
            self.assertTrue(source["repository"].startswith("https://"))
            self.assertRegex(source["review_commit"], sha)
            self.assertIn(source["review_commit"], source["pinned_source"])
            self.assertTrue(source["license"])

    def test_license_and_deprecation_boundaries_are_explicit(self):
        historical = self.runtimes["codex"]["historical_reference"]
        self.assertEqual(historical["status"], "deprecated_reference_only")
        self.assertFalse(historical["install_allowed"])
        self.assertEqual(historical["license"], "Apache-2.0")

        claude = self.runtimes["claude_code"]["source"]
        self.assertIn("Proprietary", claude["license"])
        self.assertFalse(claude["vendoring_allowed"])
        self.assertFalse(claude["derivative_allowed"])

    def test_repository_fallback_files_exist(self):
        for rel in ("skills/exam-study-guide/SKILL.md", "scripts/study_guide_render.py"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, *rel.split("/"))), rel)

    def test_native_and_browser_routes_have_distinct_preflight_backends(self):
        contract = self.data["policy"]["preflight_contract"]
        self.assertTrue(contract["native_replaces_browser_print"])
        self.assertEqual(contract["browser_required_only_for_backend"], "browser")
        self.assertTrue(contract["mathml_required_only_when_chapter_has_standard_math"])

        self.assertEqual(self.runtimes["codex"]["preferred"]["preflight_backend"],
                         "native")
        self.assertEqual(self.runtimes["claude_code"]["preferred"]["preflight_backend"],
                         "native")
        for runtime in self.runtimes.values():
            fallback = runtime.get("fallback", {})
            if fallback.get("script") == "scripts/study_guide_render.py":
                self.assertEqual(fallback["preflight_backend"], "browser")

    def test_mathml_dependency_is_audited_and_exactly_pinned(self):
        dependencies = {item["id"]: item for item in self.data["audited_dependencies"]}
        mathml = dependencies["latex2mathml"]
        self.assertEqual(mathml["package_pin"], "latex2mathml==3.60.0")
        self.assertEqual(mathml["review_commit"],
                         "de87cf0f228416e3152218c12b8bdb4ee6f4ecca")
        self.assertRegex(mathml["wheel_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(mathml["sdist_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(mathml["install_requires_confirmation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
