# -*- coding: utf-8 -*-
"""B5 calibrate_matrix.py 回归：从 run_matrix 输出抽分层校准样本 + Cohen's kappa。"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BENCH)
import calibrate_matrix as CM  # noqa: E402

FIX = os.path.join(BENCH, "fixtures", "mini_course_matrix", "config.json")


def _cm(*args):
    return subprocess.run([sys.executable, os.path.join(BENCH, "calibrate_matrix.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


def _run_matrix(out):
    subprocess.run([sys.executable, os.path.join(BENCH, "run_matrix.py"), "--mock",
                    "--config", FIX, "--results-dir", out],
                   capture_output=True, text=True, encoding="utf-8")


class SampleFromMatrix(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="b5cal_")
        self.addCleanup(shutil.rmtree, self.out, True)
        _run_matrix(self.out)

    def _sheet(self):
        return os.path.join(self.out, "calibration", "calibration_sheet.csv")

    def _rows(self):
        with open(self._sheet(), encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_sample_writes_hidden_sheet(self):
        r = _cm("sample", "--results-dir", self.out, "--config", FIX, "--n", "6")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self._rows()
        self.assertEqual(len(rows), 6)
        # 裁判判定不出现在待填表（human_correct 全空）——盲填
        self.assertTrue(all((row["human_correct"] or "").strip() == "" for row in rows))
        self.assertLessEqual({"ref_id", "question", "gold_answer", "reference_span", "model_answer"},
                             set(rows[0].keys()))
        # 隐藏 key 有对应判定
        keyp = os.path.join(self.out, "calibration", ".calibration_key.jsonl")
        with open(keyp, encoding="utf-8") as kf:
            keys = [json.loads(l) for l in kf if l.strip()]
        self.assertEqual(len(keys), 6)
        self.assertTrue(all("judge_correct" in k for k in keys))

    def test_sample_deterministic_by_seed(self):
        _cm("sample", "--results-dir", self.out, "--config", FIX, "--n", "6", "--seed", "3")
        a = [r["ref_id"] + r["question"] for r in self._rows()]
        _cm("sample", "--results-dir", self.out, "--config", FIX, "--n", "6", "--seed", "3")
        b = [r["ref_id"] + r["question"] for r in self._rows()]
        self.assertEqual(a, b)

    def test_no_answers_fails_loud(self):
        empty = tempfile.mkdtemp(prefix="b5empty_")
        self.addCleanup(shutil.rmtree, empty, True)
        r = _cm("sample", "--results-dir", empty, "--config", FIX, "--n", "6")
        self.assertEqual(r.returncode, 2)


class KappaComputation(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="b5kap_")
        self.addCleanup(shutil.rmtree, self.out, True)
        self.cal = os.path.join(self.out, "calibration")
        os.makedirs(self.cal)

    def _write(self, pairs):
        # pairs: list of (human, judge)
        sheet = os.path.join(self.cal, "calibration_sheet.csv")
        keyp = os.path.join(self.cal, ".calibration_key.jsonl")
        with open(sheet, "w", encoding="utf-8-sig", newline="") as f, open(keyp, "w", encoding="utf-8") as kf:
            w = csv.DictWriter(f, fieldnames=CM._FIELDS)
            w.writeheader()
            for i, (h, j) in enumerate(pairs, 1):
                ref = "cal_%03d" % i
                w.writerow({"ref_id": ref, "course": "c", "model": "m", "arm": "closedbook",
                            "answerable": 1, "question": "q", "gold_answer": "g",
                            "reference_span": "s", "model_answer": "a", "human_correct": str(h)})
                kf.write(json.dumps({"ref_id": ref, "judge_correct": j}) + "\n")

    def test_perfect_agreement(self):
        self._write([(1, 1), (0, 0), (1, 1), (0, 0)])
        r = _cm("kappa", "--results-dir", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("一致率 agreement = 100.0%", r.stdout)
        self.assertIn("无分歧", r.stdout)

    def test_disagreement_listed(self):
        self._write([(1, 1), (1, 0), (0, 0), (0, 1)])   # 两条分歧
        r = _cm("kappa", "--results-dir", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("人机分歧 2 条", r.stdout)

    def test_all_blank_fails(self):
        self._write([("", 1), ("", 0)])
        r = _cm("kappa", "--results-dir", self.out)
        self.assertEqual(r.returncode, 1)

    def test_unmatched_ref_surfaced(self):
        # 填了但 ref_id 对不上 key（表被改/串）→ 不静默丢，报未匹配数 + stderr 警告
        self._write([(1, 1), (0, 0)])
        sheet = os.path.join(self.cal, "calibration_sheet.csv")
        with open(sheet, "a", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=CM._FIELDS).writerow(
                {"ref_id": "cal_999", "course": "c", "model": "m", "arm": "closedbook",
                 "answerable": 1, "question": "q", "gold_answer": "g", "reference_span": "s",
                 "model_answer": "a", "human_correct": "1"})
        r = _cm("kappa", "--results-dir", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("未匹配 1", r.stdout)
        self.assertIn("对不上", r.stderr)


class Units(unittest.TestCase):
    def test_model_family(self):
        self.assertEqual(CM._model_family("opus"), "claude")
        self.assertEqual(CM._model_family("claude-haiku-4-5"), "claude")
        self.assertEqual(CM._model_family("gemini-2.5"), "gemini")
        self.assertEqual(CM._model_family("gpt-4o"), "openai")
        self.assertEqual(CM._model_family("deepseek-chat"), "deepseek")

    def test_self_preference_warning(self):
        # summary.json judge_model=haiku + pool 有 opus → 同 claude 家族 → 警告
        out = tempfile.mkdtemp(prefix="b5sp_")
        self.addCleanup(shutil.rmtree, out, True)
        with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"judge_model": "haiku"}, f)
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            CM._warn_self_preference(out, [{"model": "opus"}])
        self.assertIn("自我偏好", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
