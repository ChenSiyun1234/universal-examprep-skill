# -*- coding: utf-8 -*-
"""Tests for benchmark/aggregate_matrix.py (T3) + report_matrix.py --summary. Pure stdlib; no network,
no LLM, no API keys, no non-stdlib deps. Drives the fixture pipeline and asserts honest aggregation."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # benchmark/
sys.path.insert(0, BENCH)
import aggregate_matrix as A   # noqa: E402

FIX = os.path.join(BENCH, "tests", "fixtures", "matrix_pipeline")
ANS = os.path.join(FIX, "answers.jsonl")
SCO = os.path.join(FIX, "scores.jsonl")
EXP = os.path.join(FIX, "expected_summary.json")


def _run_agg(args):
    return subprocess.run([sys.executable, os.path.join(BENCH, "aggregate_matrix.py")] + args,
                          capture_output=True, text=True, encoding="utf-8")


class AggregateMatrix(unittest.TestCase):
    def _aggregate(self):
        out = os.path.join(tempfile.mkdtemp(), "s.json")
        A.main(["--answers", ANS, "--scores", SCO, "--primary-course", "courseA",
                "--secondary-course", "courseB", "--judge-model", "fixture-judge", "--out", out])
        with open(out, encoding="utf-8") as f:
            return json.load(f)

    def test_writes_summary_matching_expected(self):
        with open(EXP, encoding="utf-8") as f:
            self.assertEqual(self._aggregate(), json.load(f))   # deterministic, byte-for-byte cell parity

    def test_correctness_counts(self):
        s = self._aggregate()
        self.assertEqual(s["matrix"]["opus|rawfiles"]["correct"], 1.0)       # 1/1 answerable correct
        self.assertEqual(s["matrix"]["sonnet|closedbook"]["correct"], 0.0)   # 1/1 incorrect

    def test_oos_abstention_metrics(self):
        s = self._aggregate()
        self.assertEqual(s["matrix"]["opus|closedbook"]["n_oos"], 1)
        self.assertEqual(s["matrix"]["opus|closedbook"]["abstention_oos"], 1.0)    # abstained on OOS
        self.assertEqual(s["matrix"]["sonnet|closedbook"]["abstention_oos"], 0.0)  # fabricated on OOS
        self.assertEqual(s["matrix"]["opus|closedbook"]["hallucination"], 0.0)

    def test_cost_totals_and_per_question(self):
        s = self._aggregate()
        self.assertAlmostEqual(s["total_cost_usd"], 2.14, places=4)
        self.assertAlmostEqual(s["cost_per_q"]["courseA"]["closedbook"], 0.0092, places=4)
        self.assertAlmostEqual(s["cost_per_q"]["courseA"]["material"], 0.9, places=4)
        self.assertAlmostEqual(s["matrix"]["opus|material"]["cost_usd"], 1.8, places=4)

    def test_failed_cells_surfaced_not_correct(self):
        # the all-infra material cell honestly shows null rates + n_infra_error, never silently 'correct'
        mat = self._aggregate()["matrix"]["opus|material"]
        self.assertEqual(mat["n_infra_error"], 2)
        self.assertEqual(mat["n_answerable"], 0)
        self.assertIsNone(mat["correct"])

    def test_missing_score_is_judge_error_not_dropped(self):
        # sonnet|rawfiles a1 has NO score → judge_error, counted NOT-correct (lower bound), not dropped
        rf = self._aggregate()["matrix"]["sonnet|rawfiles"]
        self.assertEqual(rf["n_judge_error"], 1)
        self.assertEqual(rf["n_answerable"], 1)
        self.assertEqual(rf["correct"], 0.0)

    def test_present_judge_error_score_counted_not_correct(self):
        # a PRESENT {judge_error: true} score (no 'correct' field) must also count NOT-correct (lower
        # bound), NOT be dropped from the denominator. opus|closedbook = a1(correct) + a3(judge_error).
        c = self._aggregate()["matrix"]["opus|closedbook"]
        self.assertEqual(c["n_answerable"], 2)
        self.assertEqual(c["n_judge_error"], 1)
        self.assertEqual(c["correct"], 0.5)   # NOT inflated to 1.0 by dropping the undecided item

    def test_material_arm_present_as_legacy(self):
        s = self._aggregate()
        self.assertIn("material", s["arms"])
        self.assertIn("opus|material", s["matrix"])   # present, but all-infra → legacy/stress, not inflated

    def test_two_courses_represented_honestly(self):
        s = self._aggregate()
        self.assertEqual(sorted(s["course_matrix"]), ["courseA", "courseB"])
        self.assertEqual(s["matrix"], s["course_matrix"]["courseA"])          # primary course → matrix
        self.assertTrue(all(k.startswith("psyc|") for k in s["psyc"]))        # secondary → psyc block
        self.assertEqual(s["models"], ["opus", "sonnet"])
        self.assertEqual(s["courses"], ["courseA", "courseB"])

    def test_default_primary_course_is_largest(self):
        # with no --primary-course, the course with the most distinct items becomes `matrix`
        out = os.path.join(tempfile.mkdtemp(), "s.json")
        A.main(["--answers", ANS, "--scores", SCO, "--out", out])
        with open(out, encoding="utf-8") as f:
            s = json.load(f)
        self.assertEqual(s["matrix"], s["course_matrix"]["courseA"])   # courseA has more items

    def test_missing_input_file_fails(self):
        r = _run_agg(["--answers", os.path.join(FIX, "nope.jsonl"), "--scores", SCO,
                      "--out", os.path.join(tempfile.mkdtemp(), "o.json")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("找不到", r.stderr)

    def test_malformed_row_fails(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.jsonl"), "w", encoding="utf-8") as f:
            f.write("{ not valid json }\n")
        r = _run_agg(["--answers", os.path.join(d, "a.jsonl"), "--scores", SCO, "--out", os.path.join(d, "o.json")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("不是合法 JSON", r.stderr)

    def test_missing_required_field_fails(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.jsonl"), "w", encoding="utf-8") as f:   # missing item_id + answerable
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill"}) + "\n")
        r = _run_agg(["--answers", os.path.join(d, "a.jsonl"), "--scores", SCO, "--out", os.path.join(d, "o.json")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("缺必需字段", r.stderr)

    def test_unscored_oos_counts_not_abstained(self):
        # symmetric lower bound: a completed OOS item with no abstention verdict counts NOT-abstained
        d = tempfile.mkdtemp()
        a, sc = os.path.join(d, "a.jsonl"), os.path.join(d, "s.jsonl")
        with open(a, "w", encoding="utf-8") as f:
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "o1", "answerable": False}) + "\n")
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "o2", "answerable": False}) + "\n")
        with open(sc, "w", encoding="utf-8") as f:
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "o2", "abstained": True}) + "\n")
        out = os.path.join(d, "s.json")
        A.main(["--answers", a, "--scores", sc, "--out", out])
        with open(out, encoding="utf-8") as f:
            cell = json.load(f)["matrix"]["m|skill"]
        self.assertEqual(cell["n_oos"], 2)
        self.assertEqual(cell["abstention_oos"], 0.5)   # o2 abstained; o1 unscored → not-abstained (1/2)

    def test_string_boolean_score_fails(self):
        # a string-encoded boolean ("false" is truthy) must FAIL, not silently corrupt the rate
        d = tempfile.mkdtemp()
        a, sc = os.path.join(d, "a.jsonl"), os.path.join(d, "s.jsonl")
        with open(a, "w", encoding="utf-8") as f:
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "q", "answerable": True}) + "\n")
        with open(sc, "w", encoding="utf-8") as f:
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "q", "correct": "false"}) + "\n")
        r = _run_agg(["--answers", a, "--scores", sc, "--out", os.path.join(d, "o.json")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("必须是布尔值", r.stderr)

    def test_orphan_score_fails_loud(self):
        # a score with no matching answer must fail loudly, not be silently ignored
        d = tempfile.mkdtemp()
        a, sc = os.path.join(d, "a.jsonl"), os.path.join(d, "s.jsonl")
        with open(a, "w", encoding="utf-8") as f:
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "x", "answerable": True}) + "\n")
        with open(sc, "w", encoding="utf-8") as f:
            f.write(json.dumps({"course": "c", "model": "m", "arm": "skill", "item_id": "ORPHAN"}) + "\n")
        r = _run_agg(["--answers", a, "--scores", sc, "--out", os.path.join(d, "o.json")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("没有对应 answer", r.stderr)

    def test_does_not_silently_use_committed_summary(self):
        # behavioral proof: output reflects ONLY the explicit fixture inputs (2 items, opus+sonnet) —
        # if it had silently read results/matrix/summary.json it would show 65 items / haiku.
        s = self._aggregate()
        self.assertEqual(s["n_items"], 3)   # courseA fixture has 3 distinct items, NOT the committed 65
        self.assertEqual(s["models"], ["opus", "sonnet"])
        self.assertNotIn("haiku", s["models"])

    def test_no_network_or_llm_or_dep(self):
        with open(os.path.join(BENCH, "aggregate_matrix.py"), encoding="utf-8") as f:
            src = f.read()
        for dep in ("import requests", "import anthropic", "import openai", "import numpy",
                    "urllib.request", "http.client", "import socket", "subprocess"):
            self.assertNotIn(dep, src)                   # no network / LLM / non-stdlib dep / subprocess

    def test_cell_parity_with_rejudge(self):
        # aggregate_matrix._cell must agree with benchmark/rejudge.aggregate() (prevent drift)
        try:
            import rejudge
        except Exception as e:   # pragma: no cover
            self.skipTest("rejudge import unavailable: %s" % e)
        items = [
            {"answerable": True, "infra_error": False, "judge_error": False, "correct": True,
             "faithfulness": 1.0, "hallucinated": False, "abstained": None, "scored_by": "llm", "cost_usd": 0.0},
            {"answerable": True, "infra_error": False, "judge_error": True, "correct": False,
             "faithfulness": None, "hallucinated": None, "abstained": None, "scored_by": "lexical", "cost_usd": 0.0},
            {"answerable": False, "infra_error": False, "judge_error": False, "correct": None,
             "faithfulness": None, "hallucinated": None, "abstained": True, "scored_by": "lexical", "cost_usd": 0.0},
            {"answerable": True, "infra_error": True, "judge_error": False, "correct": None,
             "faithfulness": None, "hallucinated": None, "abstained": None, "scored_by": None, "cost_usd": 0.0},
        ]
        cell, rj = A._cell(items), rejudge.aggregate(items)
        for k in ("n", "n_answerable", "n_oos", "correct", "faithfulness", "hallucination",
                  "abstention_oos", "n_judge_error", "n_lexical", "n_infra_error"):
            self.assertEqual(cell[k], rj[k], k)


class ReportMatrixExplicitSummary(unittest.TestCase):
    def _render(self, out_dir):
        return subprocess.run([sys.executable, os.path.join(BENCH, "report_matrix.py"),
                               "--summary", EXP, "--out-dir", out_dir],
                              capture_output=True, text=True, encoding="utf-8")

    def test_explicit_summary_rendered_to_outdir(self):
        d = tempfile.mkdtemp()
        r = self._render(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        report = os.path.join(d, "report.html")
        self.assertTrue(os.path.isfile(report))
        with open(report, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("100%", html)   # the fixture's opus correctness flowed through (not the committed numbers)

    def test_render_does_not_touch_results_matrix(self):
        committed = os.path.join(BENCH, "results", "matrix", "report.html")
        before = os.path.getmtime(committed) if os.path.isfile(committed) else None
        self._render(tempfile.mkdtemp())
        after = os.path.getmtime(committed) if os.path.isfile(committed) else None
        self.assertEqual(before, after)   # committed results/matrix/report.html untouched

    def test_explicit_summary_has_not_published_banner(self):
        # an explicit (non-default) --summary render must be banner'd "NOT the published benchmark"
        d = tempfile.mkdtemp()
        self._render(d)
        with open(os.path.join(d, "report.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("NOT the published MIT/PSYC benchmark", html)
        self.assertIn("并非已发布的 MIT 6.006", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
