# -*- coding: utf-8 -*-
"""B7 tests — unified run ledger: record/show/verify, schema rejection, hash stability,
live-smoke integration (offline fake agent), warning-only failure semantics."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "benchmark", "runs")
sys.path.insert(0, RUNS)
import ledger as L   # noqa: E402


class LedgerCore(unittest.TestCase):
    def test_record_show_verify_roundtrip(self):
        path = os.path.join(tempfile.mkdtemp(), "ledger.jsonl")
        e = L.record({"kind": "live_smoke", "model": "m", "exit_code": 0}, path)
        self.assertTrue(e["run_id"])
        r = subprocess.run([sys.executable, os.path.join(RUNS, "ledger.py"), "--ledger", path,
                            "show", "--last", "5"], capture_output=True, text=True, encoding="utf-8")
        self.assertIn(e["run_id"], r.stdout)
        v = subprocess.run([sys.executable, os.path.join(RUNS, "ledger.py"), "--ledger", path, "verify"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(v.returncode, 0)
        self.assertIn("全部有效", v.stdout)

    def test_invalid_entries_rejected(self):
        path = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        for bad in ({"kind": "nonsense"}, {"kind": "live_smoke", "cost_usd": -1},
                    {"kind": "live_smoke", "exit_code": "0"}, {"kind": "live_smoke", "model": 3}):
            with self.assertRaises(SystemExit):
                L.record(bad, path)
        self.assertFalse(os.path.isfile(path))        # 无效行绝不落盘

    def test_verify_flags_bad_rows(self):
        path = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        L.record({"kind": "other"}, path)
        with open(path, "a", encoding="utf-8") as f:
            f.write("{broken json\n")
            f.write(json.dumps({"kind": "nonsense", "run_id": "x", "created_at": "t"}) + "\n")
        r = subprocess.run([sys.executable, os.path.join(RUNS, "ledger.py"), "--ledger", path, "verify"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1)
        self.assertIn("2 行无效", r.stdout)

    def test_workspace_hash_stable_and_sensitive(self):
        ws = tempfile.mkdtemp()
        os.makedirs(os.path.join(ws, "references"))
        with open(os.path.join(ws, "references", "quiz_bank.json"), "w", encoding="utf-8") as f:
            f.write("[]")
        h1 = L.workspace_hash(ws)
        self.assertEqual(h1, L.workspace_hash(ws))    # 稳定
        with open(os.path.join(ws, "references", "quiz_bank.json"), "w", encoding="utf-8") as f:
            f.write('[{"id":"q1"}]')
        self.assertNotEqual(h1, L.workspace_hash(ws))  # 输入变则指纹变

    def test_try_record_never_raises(self):
        e, warn = L.try_record({"kind": "nonsense"}, os.path.join(tempfile.mkdtemp(), "l.jsonl"))
        self.assertIsNone(e)
        self.assertIn("不受影响", warn)

    def test_committed_sample_is_valid(self):
        r = subprocess.run([sys.executable, os.path.join(RUNS, "ledger.py"),
                            "--ledger", os.path.join(RUNS, "ledger.sample.jsonl"), "verify"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_real_ledger_gitignored(self):
        gi = open(os.path.join(ROOT, "benchmark", ".gitignore"), encoding="utf-8").read()
        self.assertIn("runs/ledger.jsonl", gi)         # 真实账本绝不进仓库


class LiveSmokeIntegration(unittest.TestCase):
    def test_live_smoke_writes_ledger_row(self):
        out = tempfile.mkdtemp()
        led = os.path.join(out, "ledger.jsonl")
        fake = os.path.join(ROOT, "tests", "fake_live_agent.py")
        cmd = json.dumps([sys.executable, fake, "{prompt}"])
        env = dict(os.environ, RUN_SKILL_DRIFT_LLM="1")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "benchmark", "drift", "run_live_smoke.py"),
                            "--agent-cmd", cmd, "--out-dir", out, "--ledger", led, "--model", "fake-agent"],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = [json.loads(x) for x in open(led, encoding="utf-8") if x.strip()]
        self.assertEqual(len(rows), 1)
        e = rows[0]
        self.assertEqual(e["kind"], "live_smoke")
        self.assertEqual(e["model"], "fake-agent")
        self.assertEqual(e["exit_code"], 0)
        self.assertTrue(e["prompt_hash"].startswith("sha256:"))
        self.assertTrue(e["workspace_hash"].startswith("sha256:"))
        self.assertTrue(os.path.isfile(e["transcript_path"]))

    def test_no_ledger_flag_skips(self):
        out = tempfile.mkdtemp()
        led = os.path.join(out, "ledger.jsonl")
        fake = os.path.join(ROOT, "tests", "fake_live_agent.py")
        cmd = json.dumps([sys.executable, fake, "{prompt}"])
        env = dict(os.environ, RUN_SKILL_DRIFT_LLM="1")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "benchmark", "drift", "run_live_smoke.py"),
                            "--agent-cmd", cmd, "--out-dir", out, "--ledger", led, "--no-ledger"],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.isfile(led))

    def test_ledger_failure_does_not_break_run(self):
        out = tempfile.mkdtemp()
        bad_led = os.path.join(out, "no_dir_here", "x", "..", "..", "l.jsonl")   # still writable? use a dir path
        bad_led = out                                            # 目录当文件 → 写入必失败
        fake = os.path.join(ROOT, "tests", "fake_live_agent.py")
        cmd = json.dumps([sys.executable, fake, "{prompt}"])
        env = dict(os.environ, RUN_SKILL_DRIFT_LLM="1")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "benchmark", "drift", "run_live_smoke.py"),
                            "--agent-cmd", cmd, "--out-dir", out, "--ledger", bad_led],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)              # 记账失败绝不影响运行结果
        self.assertIn("ledger", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
