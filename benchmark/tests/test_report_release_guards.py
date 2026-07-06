# -*- coding: utf-8 -*-
"""B8-1 — report-release guards: mock must never silently clobber the committed real artifacts,
and block_generic must not drop an arm that the summary's top-level `arms` list forgot.

Stdlib only; no network/LLM; nothing writes into the published results/ directory."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # benchmark/
sys.path.insert(0, HERE)
import run_benchmark as RB          # noqa: E402
import report_matrix as RM          # noqa: E402


class ResultsDirGuard(unittest.TestCase):
    """_resolve_results_dir: mock → results_mock/ by default; mock → results/ refused w/o --force."""

    def test_real_run_defaults_to_results(self):
        self.assertEqual(RB._resolve_results_dir("results", None, False, False), "results")

    def test_mock_defaults_to_results_mock(self):
        # the documented `run_benchmark.py --mock` must NOT target the published results/
        self.assertEqual(RB._resolve_results_dir("results", None, True, False), "results_mock")

    def test_mock_explicit_published_dir_is_refused(self):
        with self.assertRaises(SystemExit):
            RB._resolve_results_dir("results", "results", True, False)

    def test_mock_explicit_published_dir_allowed_with_force(self):
        self.assertEqual(RB._resolve_results_dir("results", "results", True, True), "results")

    def test_explicit_other_dir_is_fine_for_mock(self):
        self.assertEqual(RB._resolve_results_dir("results", "results_x", True, False), "results_x")

    def test_real_run_may_target_results(self):
        # a REAL run legitimately writes to results/ — the guard only blocks mock
        self.assertEqual(RB._resolve_results_dir("results", "results", False, False), "results")


class RoundsDemoDir(unittest.TestCase):
    """rounds.py CLI demo must write to results/_demo, never the published results/convergence.*."""

    def test_demo_targets_subdir_not_published(self):
        src = io.open(os.path.join(HERE, "rounds.py"), encoding="utf-8").read()
        self.assertIn('os.path.join("results", "_demo")', src)
        self.assertNotIn('render_convergence(demo, "results", mock=True)', src)


class BlockGenericArms(unittest.TestCase):
    """block_generic derives arms from the matrix cell keys, so an arm the summary's top-level
    `arms` list forgot (e.g. rawfiles) is still rendered instead of silently dropped."""

    def _summary(self):
        return {
            "models": ["opus"],
            "arms": ["closedbook", "skill"],          # deliberately OMITS 'rawfiles'
            "matrix": {
                "opus|closedbook": {"correct": 0.2, "hallucination": 0.1, "abstention_oos": 0.5},
                "opus|rawfiles": {"correct": 0.8, "hallucination": 0.05, "abstention_oos": 1.0},
                "opus|skill": {"correct": 0.9, "hallucination": 0.04, "abstention_oos": 1.0},
            },
            "cost_per_q": {}, "n_items": 3,
        }

    def test_rawfiles_column_not_dropped(self):
        err = io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            html_zh = "".join(RM.block_generic("zh", self._summary()))
        finally:
            sys.stderr = old
        # the undeclared arm appears as a column header AND its cell value renders
        self.assertIn("rawfiles", html_zh)
        self.assertIn("80", html_zh)                  # 0.8 → 80% for the rawfiles/correct cell
        self.assertIn("rawfiles", err.getvalue())     # fail-loud warning to stderr

    def test_declared_arms_order_preserved(self):
        html_zh = "".join(RM.block_generic("zh", self._summary()))
        # declared arms keep their order; the recovered arm is appended after them
        self.assertLess(html_zh.index("closedbook"), html_zh.index("rawfiles"))


if __name__ == "__main__":
    unittest.main()
