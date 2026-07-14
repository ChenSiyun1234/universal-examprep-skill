# -*- coding: utf-8 -*-
"""依赖预检清单（check_deps.py）：清单结构、材料感知的 needed 判定、退出码契约、分发包收录。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import check_deps  # noqa: E402
PY = sys.executable


def make_workspace(root, wiki="# Chapter 1\n\nNo formulas.\n", teaching=None,
                   quizzes=None, notebook=None):
    os.makedirs(os.path.join(root, "references", "wiki"), exist_ok=True)
    with open(os.path.join(root, "references", "wiki", "ch01.md"),
              "w", encoding="utf-8") as stream:
        stream.write(wiki)
    with open(os.path.join(root, "references", "teaching_examples.json"),
              "w", encoding="utf-8") as stream:
        json.dump(teaching or [], stream, ensure_ascii=False)
    with open(os.path.join(root, "references", "quiz_bank.json"),
              "w", encoding="utf-8") as stream:
        json.dump(quizzes or [], stream, ensure_ascii=False)
    if notebook is not None:
        os.makedirs(os.path.join(root, "notebook"), exist_ok=True)
        with open(os.path.join(root, "notebook", "ch01.md"),
                  "w", encoding="utf-8") as stream:
            stream.write(notebook)
    return root


class ManifestShape(unittest.TestCase):
    def test_groups_cover_the_three_capabilities(self):
        ids = {g["id"] for g in check_deps.GROUPS}
        self.assertEqual(ids, {"pdf_text", "pdf_render", "browser", "mathml"})

    def test_every_pip_group_has_install_command(self):
        rep = check_deps.build_report()
        for r in rep["groups"]:
            self.assertTrue(r["install"], r["id"])
            if r["id"] != "browser" and not r["ok"]:
                self.assertIn("pip install", r["install"])

    def test_json_mode_is_machine_readable(self):
        r = subprocess.run([PY, os.path.join(SCRIPTS, "check_deps.py"), "--json"],
                           capture_output=True, text=True, encoding="utf-8")
        rep = json.loads(r.stdout)
        self.assertIn("groups", rep)
        self.assertIn("missing_needed", rep)

    def test_mathml_is_usable_only_at_the_audited_exact_version(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace, wiki="# Formula\n\nUse $x^2$.\n")
            with mock.patch.object(check_deps, "_probe_import", return_value=True), \
                    mock.patch.object(check_deps, "_probe_browser", return_value=True), \
                    mock.patch.object(check_deps, "installed_distribution_version",
                                      return_value="3.81.0"):
                report = check_deps.build_report(
                    artifact_mode="visual", workspace=workspace, chapter=1,
                    pdf_backend="html",
                )
            row = {item["id"]: item for item in report["groups"]}["mathml"]
            self.assertFalse(row["ok"])
            self.assertEqual(row["available"], ["latex2mathml==3.81.0"])
            self.assertIn("mathml", report["missing_needed"])

            with mock.patch.object(check_deps, "_probe_import", return_value=True), \
                    mock.patch.object(check_deps, "_probe_browser", return_value=True), \
                    mock.patch.object(check_deps, "installed_distribution_version",
                                      return_value="3.60.0"):
                report = check_deps.build_report(
                    artifact_mode="visual", workspace=workspace, chapter=1,
                    pdf_backend="html",
                )
            row = {item["id"]: item for item in report["groups"]}["mathml"]
            self.assertTrue(row["ok"])
            self.assertNotIn("mathml", report["missing_needed"])

    def test_low_level_capability_probe_exceptions_are_not_missing_results(self):
        with mock.patch.object(check_deps.importlib.util, "find_spec",
                               side_effect=OSError("registry unavailable")):
            with self.assertRaises(check_deps.DependencyProbeError):
                check_deps._probe_import("latex2mathml")

        import cheatsheet_render
        with mock.patch.object(cheatsheet_render, "find_browser",
                               side_effect=OSError("registry unavailable")):
            with self.assertRaises(check_deps.DependencyProbeError):
                check_deps._probe_browser()


class MaterialsAwareness(unittest.TestCase):
    def test_no_materials_means_unknown_needed(self):
        rep = check_deps.build_report(None)
        self.assertEqual(rep["materials_have_pdf"], None)
        self.assertEqual([r for r in rep["groups"] if r["id"] == "pdf_text"][0]["needed"],
                         "unknown")
        self.assertEqual(rep["missing_needed"], [], "不可判定时绝不硬报缺失")

    def test_pdf_materials_flip_needed_true(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "lec01.pdf"), "wb") as stream:
                stream.write(b"%PDF")
            rep = check_deps.build_report(d)
            self.assertTrue(rep["materials_have_pdf"])
            row = [r for r in rep["groups"] if r["id"] == "pdf_text"][0]
            self.assertIs(row["needed"], True)

    def test_pdf_backend_capability_truth_table_matches_material_builder(self):
        cases = (
            ({"pypdf"}, True, False),
            ({"fitz"}, True, True),
            ({"pypdfium2"}, False, False),       # renderer is incomplete without Pillow
            ({"pypdfium2", "PIL"}, False, True),
            ({"pypdf", "pypdfium2", "PIL"}, True, True),
        )
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "lec01.pdf"), "wb") as stream:
                stream.write(b"%PDF")
            for present, text_ok, render_ok in cases:
                with self.subTest(present=present), \
                        mock.patch.object(check_deps, "_probe_import",
                                          side_effect=lambda name, have=present: name in have):
                    rows = {row["id"]: row for row in check_deps.build_report(d)["groups"]}
                self.assertIs(rows["pdf_text"]["ok"], text_ok)
                self.assertIs(rows["pdf_render"]["ok"], render_ok)

    def test_text_only_materials_not_needed(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "notes.md"), "w", encoding="utf-8") as stream:
                stream.write("x")
            rep = check_deps.build_report(d)
            self.assertIs(rep["materials_have_pdf"], False)
            row = [r for r in rep["groups"] if r["id"] == "pdf_text"][0]
            self.assertIs(row["needed"], False)
            self.assertEqual(rep["missing_needed"], [])

    def test_browser_group_never_hard_missing(self):
        # 小抄 PDF 有降级路径（HTML+手动打印）——browser 永远是 optional，不进 missing_needed
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "lec01.pdf"), "wb") as stream:
                stream.write(b"%PDF")
            rep = check_deps.build_report(d)
            self.assertNotIn("browser", rep["missing_needed"])

    def test_visual_materials_only_probe_keeps_artifact_needs_unknown(self):
        rep = check_deps.build_report(None, artifact_mode="visual")
        rows = {row["id"]: row for row in rep["groups"]}
        self.assertEqual(rows["mathml"]["needed"], "unknown")
        self.assertEqual(rows["browser"]["needed"], "unknown")
        self.assertEqual(rep["missing_needed"], [])
        self.assertIsNone(rep["probe_error"])
        self.assertEqual(rows["mathml"]["install"], "pip install latex2mathml==3.60.0")

    def test_chat_mode_keeps_visual_only_dependencies_optional(self):
        rep = check_deps.build_report(None, artifact_mode="chat")
        rows = {row["id"]: row for row in rep["groups"]}
        self.assertIs(rows["mathml"]["needed"], False)
        self.assertEqual(rows["browser"]["needed"], "optional")

    def test_pdf_backend_controls_only_browser_hard_need(self):
        expected = {"auto": "unknown", "browser": True, "native": False, "html": False}
        for backend, needed in expected.items():
            with self.subTest(backend=backend), \
                    mock.patch.object(check_deps, "_probe_browser", return_value=False):
                rep = check_deps.build_report(
                    artifact_mode="visual", pdf_backend=backend
                )
                browser = {row["id"]: row for row in rep["groups"]}["browser"]
                self.assertEqual(browser["needed"], needed)
                self.assertEqual("browser" in rep["missing_needed"], needed is True)

    def test_pdf_backend_cli_is_machine_readable(self):
        result = subprocess.run(
            [PY, os.path.join(SCRIPTS, "check_deps.py"), "--artifact-mode", "visual",
             "--pdf-backend", "native", "--json"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["pdf_backend"], "native")
        browser = {row["id"]: row for row in report["groups"]}["browser"]
        self.assertIs(browser["needed"], False)

    def test_chat_mode_never_hard_requires_browser_even_if_backend_is_browser(self):
        with mock.patch.object(check_deps, "_probe_browser", return_value=False):
            rep = check_deps.build_report(artifact_mode="chat", pdf_backend="browser")
        browser = {row["id"]: row for row in rep["groups"]}["browser"]
        self.assertEqual(browser["needed"], "optional")
        self.assertNotIn("browser", rep["missing_needed"])

    def test_exit_code_contract(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as stream:
                stream.write("x")
            r = subprocess.run([PY, os.path.join(SCRIPTS, "check_deps.py"),
                                "--materials", d], capture_output=True, text=True,
                               encoding="utf-8")
            self.assertEqual(r.returncode, 0, "无 PDF 材料时任何缺失都不算 NEEDED")


class ChapterContentAwareness(unittest.TestCase):
    def row(self, report, group_id):
        return {item["id"]: item for item in report["groups"]}[group_id]

    def test_selected_chapter_without_standard_formula_does_not_need_mathml(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace)
            rep = check_deps.build_report(
                artifact_mode="visual", workspace=workspace, chapter=1,
                pdf_backend="html",
            )
        self.assertIs(rep["chapter_has_standard_math"], False)
        self.assertIs(self.row(rep, "mathml")["needed"], False)
        self.assertNotIn("mathml", rep["missing_needed"])

    def test_standard_formula_in_each_persisted_render_source_needs_mathml(self):
        cases = (
            {"wiki": "# X\n\nInline $x^2$.\n"},
            {"teaching": [{"chapter": 1, "question": "Find $$x+1$$"}]},
            {"quizzes": [{"chapter": 1, "question": "Pick one",
                           "options": ["$x$", "plain"]}]},
            {"notebook": "# Notes\n\nAnswer $y=2$.\n"},
        )
        for values in cases:
            with self.subTest(source=next(iter(values))):
                with tempfile.TemporaryDirectory() as workspace:
                    make_workspace(workspace, **values)
                    with mock.patch.object(check_deps, "_probe_import", return_value=False):
                        rep = check_deps.build_report(
                            artifact_mode="visual", workspace=workspace, chapter=1,
                            pdf_backend="html",
                        )
                self.assertIs(rep["chapter_has_standard_math"], True)
                self.assertIs(self.row(rep, "mathml")["needed"], True)
                self.assertIn("mathml", rep["missing_needed"])

    def test_other_chapter_and_markdown_code_formulas_are_ignored(self):
        teaching = [{"chapter": 2, "question": "SECRET $x$"}]
        quizzes = [{"chapter": 2, "question": "SECRET $$y$$"}]
        wiki = "# X\n\n`$inline_code$`\n\n```latex\n$$fenced$$\n```\n"
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace, wiki=wiki, teaching=teaching, quizzes=quizzes)
            rep = check_deps.build_report(
                artifact_mode="visual", workspace=workspace, chapter=1,
                pdf_backend="html",
            )
        self.assertIs(rep["chapter_has_standard_math"], False)
        self.assertIs(self.row(rep, "mathml")["needed"], False)

    def test_chat_mode_keeps_mathml_optional_even_when_selected_chapter_has_formula(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace, wiki="# X\n\n$x$\n")
            rep = check_deps.build_report(
                artifact_mode="chat", workspace=workspace, chapter=1
            )
        self.assertIs(rep["chapter_has_standard_math"], True)
        self.assertIs(self.row(rep, "mathml")["needed"], False)
        self.assertNotIn("mathml", rep["missing_needed"])

    def test_quiz_explanation_math_is_needed_only_when_renderer_will_show_it(self):
        cases = (
            (None, False),
            ("answer text", True),
        )
        for answer, expected in cases:
            with self.subTest(answer=answer):
                quizzes = [{"chapter": 1, "question": "plain", "answer": answer,
                            "explanation": "because $x^2$"}]
                with tempfile.TemporaryDirectory() as workspace:
                    make_workspace(workspace, quizzes=quizzes)
                    rep = check_deps.build_report(
                        artifact_mode="visual", workspace=workspace, chapter=1,
                        pdf_backend="html",
                    )
                self.assertIs(rep["chapter_has_standard_math"], expected)

    def test_math_in_nested_dictionary_key_matches_renderer_json_display(self):
        quizzes = [{"chapter": 1, "question": "plain", "answer": "A",
                    "options": [{"$x$": "plain"}]}]
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace, quizzes=quizzes)
            rep = check_deps.build_report(
                artifact_mode="visual", workspace=workspace, chapter=1,
                pdf_backend="html",
            )
        self.assertIs(rep["chapter_has_standard_math"], True)

    def test_chapter_visual_requires_resolved_pdf_backend(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace)
            rep = check_deps.build_report(
                artifact_mode="visual", workspace=workspace, chapter=1,
            )
            result = subprocess.run(
                [PY, os.path.join(SCRIPTS, "check_deps.py"), "--workspace", workspace,
                 "--chapter", "1", "--artifact-mode", "visual"],
                capture_output=True, text=True, encoding="utf-8",
            )
        self.assertIn("--pdf-backend", rep["probe_error"])
        self.assertEqual(self.row(rep, "browser")["needed"], "probe_error")
        self.assertNotIn("browser", rep["missing_needed"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("probe_error", result.stdout)
        self.assertNotIn("↳ 安装", result.stdout)

    def test_needed_import_probe_exception_is_probe_error_not_missing(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace, wiki="# X\n\n$x$\n")
            with mock.patch.object(check_deps, "_probe_import", side_effect=OSError("metadata I/O")):
                rep = check_deps.build_report(
                    artifact_mode="visual", workspace=workspace, chapter=1,
                    pdf_backend="native",
                )
        self.assertIn("mathml", rep["probe_error"])
        self.assertEqual(self.row(rep, "mathml")["needed"], "probe_error")
        self.assertNotIn("mathml", rep["missing_needed"])

    def test_needed_browser_probe_exception_is_probe_error_not_missing(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace)
            with mock.patch.object(check_deps, "_probe_browser", side_effect=OSError("registry I/O")):
                rep = check_deps.build_report(
                    artifact_mode="visual", workspace=workspace, chapter=1,
                    pdf_backend="browser",
                )
        self.assertIn("browser", rep["probe_error"])
        self.assertEqual(self.row(rep, "browser")["needed"], "probe_error")
        self.assertNotIn("browser", rep["missing_needed"])

    def test_unselected_browser_probe_is_not_run_on_native_route(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace)
            with mock.patch.object(check_deps, "_probe_browser",
                                   side_effect=AssertionError("must not probe fallback")):
                rep = check_deps.build_report(
                    artifact_mode="visual", workspace=workspace, chapter=1,
                    pdf_backend="native",
                )
        self.assertIsNone(rep["probe_error"])
        self.assertIs(self.row(rep, "browser")["needed"], False)
        self.assertFalse(self.row(rep, "browser")["probed"])

    def test_probe_error_is_clear_and_never_becomes_install_request(self):
        with tempfile.TemporaryDirectory() as workspace:
            make_workspace(workspace)
            wiki = os.path.join(workspace, "references", "wiki", "ch01.md")
            with open(wiki, "wb") as stream:
                stream.write(b"\xff\xfe\x00")
            rep = check_deps.build_report(
                artifact_mode="visual", workspace=workspace, chapter=1,
                pdf_backend="html",
            )
            result = subprocess.run(
                [PY, os.path.join(SCRIPTS, "check_deps.py"), "--workspace", workspace,
                 "--chapter", "1", "--artifact-mode", "visual", "--pdf-backend", "html"],
                capture_output=True, text=True, encoding="utf-8",
            )
        self.assertIn("UTF-8", rep["probe_error"])
        self.assertEqual(self.row(rep, "mathml")["needed"], "probe_error")
        self.assertNotIn("mathml", rep["missing_needed"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("probe_error", result.stdout)
        self.assertNotIn("latex2mathml==", result.stdout)

    def test_workspace_and_chapter_must_be_paired(self):
        result = subprocess.run(
            [PY, os.path.join(SCRIPTS, "check_deps.py"), "--workspace", "missing"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--workspace and --chapter", result.stderr)

    def test_missing_workspace_reports_probe_error_without_hard_missing(self):
        rep = check_deps.build_report(
            artifact_mode="visual", workspace=os.path.join(tempfile.gettempdir(), "absent-ws"),
            chapter=1,
        )
        self.assertIn("workspace", rep["probe_error"])
        self.assertEqual(self.row(rep, "mathml")["needed"], "probe_error")
        self.assertNotIn("mathml", rep["missing_needed"])


class ShipsInDist(unittest.TestCase):
    def test_check_deps_in_runtime_manifest(self):
        import build_dist
        self.assertIn("scripts/check_deps.py", build_dist.manifest(),
                      "预检工具必须随运行时包分发——它就是给安装现场用的")


if __name__ == "__main__":
    unittest.main(verbosity=2)
