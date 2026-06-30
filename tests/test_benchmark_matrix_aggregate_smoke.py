# -*- coding: utf-8 -*-
"""Root-level CI-reachable smoke test for the T3 benchmark aggregator.

CI runs only `python -m unittest discover -s tests` (the repo root tests/), so the full T3 suite under
`benchmark/tests/test_aggregate_matrix.py` is NOT discovered by CI. This thin proxy runs the aggregator
on the committed fixture so the core T3 behavior (and its honesty invariants) is covered by CI — without
adding any GitHub Actions / CI config. Pure stdlib; no network / LLM / paid run."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "benchmark")
FIX = os.path.join(BENCH, "tests", "fixtures", "matrix_pipeline")


@unittest.skipUnless(os.path.isdir(FIX), "benchmark matrix fixture not present")
class BenchmarkAggregateSmoke(unittest.TestCase):
    def test_fixture_aggregates_to_expected_with_honesty_invariants(self):
        sys.path.insert(0, BENCH)
        import aggregate_matrix as A
        out = os.path.join(tempfile.mkdtemp(), "s.json")
        A.main(["--answers", os.path.join(FIX, "answers.jsonl"), "--scores", os.path.join(FIX, "scores.jsonl"),
                "--primary-course", "courseA", "--secondary-course", "courseB",
                "--judge-model", "fixture-judge", "--out", out])
        with open(out, encoding="utf-8") as f:
            s = json.load(f)
        with open(os.path.join(FIX, "expected_summary.json"), encoding="utf-8") as f:
            self.assertEqual(s, json.load(f))                                  # deterministic, matches expected
        # honesty invariants — failures never inflate metrics:
        self.assertIsNone(s["matrix"]["opus|material"]["correct"])            # all-infra cell → null, not correct
        self.assertEqual(s["matrix"]["opus|material"]["n_infra_error"], 2)
        self.assertEqual(s["matrix"]["opus|closedbook"]["correct"], 0.5)      # present judge_error → not-correct
        self.assertEqual(s["matrix"]["sonnet|rawfiles"]["correct"], 0.0)      # missing score → not-correct


if __name__ == "__main__":
    unittest.main(verbosity=2)
