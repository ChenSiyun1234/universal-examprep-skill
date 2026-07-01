# -*- coding: utf-8 -*-
"""Root-level tests for the T5b Markdown live-session adapter."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIFT = os.path.join(ROOT, "benchmark", "drift")
CONVERT = os.path.join(DRIFT, "convert_session_log.py")
SCEN = os.path.join(DRIFT, "scenarios", "long_session_basic.json")
FIXTURE_MD = os.path.join(DRIFT, "fixtures", "live_logs", "good_session.md")
EXPECTED_JSONL = os.path.join(DRIFT, "fixtures", "live_logs", "good_session.expected.jsonl")

sys.path.insert(0, DRIFT)
import convert_session_log as C  # noqa: E402
import run_drift as D            # noqa: E402


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _cli(args):
    return subprocess.run(
        [sys.executable, CONVERT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@unittest.skipUnless(os.path.isfile(CONVERT), "live adapter not present")
class DriftLiveAdapter(unittest.TestCase):
    def test_converter_reads_fixture_markdown_and_writes_expected_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "live_session.jsonl")
            r = _cli(["--in", FIXTURE_MD, "--out", out])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(_read(out), _read(EXPECTED_JSONL))

    def test_converter_preserves_chinese_and_emoji_labels(self):
        rows = C.parse_session_log(_read(FIXTURE_MD))
        text = "\n".join(row["assistant"] for row in rows)
        self.assertIn("🟢 来自资料", text)
        self.assertIn("🟡 AI补充，可能与你老师讲的不完全一致", text)
        self.assertIn("栈与队列复习", text)

    def test_converter_parses_kind_and_phase_context(self):
        rows = C.parse_session_log(_read(FIXTURE_MD))
        self.assertEqual(rows[0]["kind"], "resume")
        self.assertEqual(rows[0]["phase_context"], 1)
        self.assertEqual(rows[1]["kind"], "quiz")
        self.assertEqual(rows[1]["phase_context"], 1)

    def test_converter_parses_read_file_events(self):
        rows = C.parse_session_log(_read(FIXTURE_MD))
        self.assertEqual(rows[1]["events"][0], {
            "type": "read_file",
            "path": "references/wiki/ch1_stack_queue.md",
        })
        self.assertEqual(rows[1]["events"][1]["path"], "references/quiz_bank.json")

    def test_converter_parses_files_after_snapshot(self):
        rows = C.parse_session_log(_read(FIXTURE_MD))
        snap = rows[2]["files_after"]["study_progress.md"]
        self.assertIn("当前阶段：1", snap)
        self.assertIn("为什么 stack 是 LIFO：待回顾", snap)

    def test_generated_jsonl_is_accepted_by_drift_harness(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "live_session.jsonl")
            self.assertEqual(_cli(["--in", FIXTURE_MD, "--out", out]).returncode, 0)
            loaded = D.load_jsonl(out, "transcript")
            self.assertEqual(len(loaded), 3)
            result = D.evaluate(D.load_scenario(SCEN), out)
            self.assertTrue(result["passed"], result["failures"])

    def test_check_mode_validates_without_writing(self):
        r = _cli(["--in", FIXTURE_MD, "--check"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 3 turns", r.stdout)

    def test_template_command_prints_utf8_template(self):
        r = _cli(["--template", os.path.join(DRIFT, "templates", "live_session_template.md")])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("🟢 来自资料", r.stdout)
        self.assertIn("## Turn 1", r.stdout)

    def test_malformed_turn_structure_exits_2(self):
        bad = """# Live Agent Session Log

## Turn 1

### User
我回来了。
"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(bad)
            r = _cli(["--in", path, "--check"])
            self.assertEqual(r.returncode, 2)
            self.assertIn("missing ### Assistant", r.stderr)

    def test_invalid_utf8_input_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.md")
            with open(path, "wb") as f:
                f.write(b"\xff\xfe\xfa")
            r = _cli(["--in", path, "--check"])
            self.assertEqual(r.returncode, 2)
            self.assertIn("UTF-8", r.stderr)

    def test_converter_has_no_network_llm_api_or_dependency_hooks(self):
        source = _read(CONVERT).lower()
        forbidden = [
            "requests", "urllib", "socket", "subprocess", "openai",
            "anthropic", "gemini", "api_key", "run_skill_",
        ]
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertEqual(C.__doc__.count("stdlib"), 1)

    def test_jsonl_rows_are_plain_json_objects(self):
        rows = [json.loads(line) for line in _read(EXPECTED_JSONL).splitlines()]
        self.assertTrue(all(isinstance(row, dict) for row in rows))
        self.assertEqual([row["turn"] for row in rows], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
