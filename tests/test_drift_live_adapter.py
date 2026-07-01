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


def _cli(args, env=None):
    return subprocess.run(
        [sys.executable, CONVERT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _check_markdown(text):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "session.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return _cli(["--in", path, "--check"])


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
        self.assertEqual(rows[2]["events"][1], {
            "type": "write_file",
            "path": "study_progress.md",
        })

    def test_converter_parses_files_after_snapshot(self):
        rows = C.parse_session_log(_read(FIXTURE_MD))
        snap = rows[2]["files_after"]["study_progress.md"]
        self.assertIn("当前阶段：1", snap)
        self.assertIn("为什么 stack 是 LIFO：待回顾", snap)

    def test_markdown_headings_inside_message_body_are_preserved(self):
        heading = "### \u8fdb\u5ea6\u9762\u677f"
        log = "\n".join([
            "# Live Agent Session Log",
            "",
            "## Turn 1",
            "kind: explanation",
            "phase_context: 1",
            "",
            "### User",
            "\u8bf7\u7ee7\u7eed\u8bb2\u89e3\u3002",
            "",
            "### Assistant",
            "\U0001f7e2 \u6765\u81ea\u8d44\u6599\uff1a\u5148\u8bb2\u89e3\u6982\u5ff5\u3002",
            heading,
            "\u5f53\u524d\u9636\u6bb5\uff1a1",
            "",
            "### Events",
            "- read_file: references/wiki/ch1_stack_queue.md",
            "",
        ])

        rows = C.parse_session_log(log)

        self.assertIn(heading, rows[0]["assistant"])
        self.assertIn("\u5f53\u524d\u9636\u6bb5\uff1a1", rows[0]["assistant"])
        self.assertEqual(rows[0]["events"], [{
            "type": "read_file",
            "path": "references/wiki/ch1_stack_queue.md",
        }])

    def test_unknown_event_type_exits_2(self):
        bad = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Resume.

### Assistant
Ready.

### Events
- readfile: study_progress.md
"""
        r = _check_markdown(bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("event type", r.stderr)
        self.assertIn("readfile", r.stderr)

    def test_write_file_study_progress_requires_snapshot(self):
        bad = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Why is stack LIFO?

### Assistant
Because the last pushed item is popped first.

### Events
- write_file: study_progress.md
"""
        r = _check_markdown(bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("requires matching", r.stderr)
        self.assertIn("study_progress.md", r.stderr)

    def test_write_file_study_plan_requires_snapshot(self):
        bad = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Plan the next step.

### Assistant
Keeping the same stage order.

### Events
- write_file: study_plan.md
"""
        r = _check_markdown(bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("requires matching", r.stderr)
        self.assertIn("study_plan.md", r.stderr)

    def test_duplicate_scalar_fields_exit_2(self):
        bad = """# Live Agent Session Log

## Turn 1
kind: quiz
phase_context: 1
phase_context: 2

### User
Give me a quiz.

### Assistant
[#stack_lifo_1] 栈遵循什么访问顺序？
"""
        r = _check_markdown(bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("repeats field phase_context", r.stderr)

    def test_non_finite_cost_values_exit_2(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            bad = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1
cost_usd: %s

### User
Explain stack.

### Assistant
🟢 来自资料：栈是后进先出。
""" % value
            r = _check_markdown(bad)
            self.assertEqual(r.returncode, 2, value)
            self.assertIn("cost_usd must be finite", r.stderr)

    def test_negative_cost_values_exit_2(self):
        bad = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1
cost_usd: -0.50

### User
Explain stack.

### Assistant
🟢 来自资料：栈是后进先出。
"""
        r = _check_markdown(bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("cost_usd cannot be negative", r.stderr)

    def test_files_after_snapshot_can_contain_inner_code_fence(self):
        good = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Record my code note.

### Assistant
🟢 来自资料：已记录代码片段。

### Events
- write_file: study_progress.md

### Files After: study_progress.md
````text
# 复习进度

## 疑难点（confusion tracker）
- 代码片段：
```python
print("stack")
```
````
"""
        rows = C.parse_session_log(good)
        snap = rows[0]["files_after"]["study_progress.md"]
        self.assertIn("```python", snap)
        self.assertIn('print("stack")', snap)

    def test_turn_like_heading_inside_snapshot_is_not_a_turn_boundary(self):
        good = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Record my note.

### Assistant
🟢 来自资料：已记录。

### Events
- write_file: study_progress.md

### Files After: study_progress.md
```text
# 复习进度

## Turn 2
kind: quiz

### User
this is a note snippet, not a transcript turn
```
"""
        rows = C.parse_session_log(good)
        self.assertEqual(len(rows), 1)
        self.assertIn("## Turn 2", rows[0]["files_after"]["study_progress.md"])

    def test_turn_like_heading_inside_assistant_message_is_not_a_turn_boundary(self):
        good = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Show me the transcript format.

### Assistant
🟢 来自资料：示例里可能出现标题。

## Turn 2
This is just a Markdown heading inside the answer.
"""
        rows = C.parse_session_log(good)
        self.assertEqual(len(rows), 1)
        self.assertIn("## Turn 2", rows[0]["assistant"])

    def test_fenced_session_log_example_inside_assistant_message_is_preserved(self):
        good = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Show me the transcript format.

### Assistant
🟢 来自资料：示例需要放在代码块里。

```md
## Turn 2
kind: quiz

### User
Give me a quiz.

### Events
- read_file: references/wiki/ch1_stack_queue.md
```
"""
        rows = C.parse_session_log(good)
        self.assertEqual(len(rows), 1)
        self.assertIn("### Events", rows[0]["assistant"])
        self.assertIn("kind: quiz", rows[0]["assistant"])

    def test_typoed_scalar_field_after_turn_header_exits_2(self):
        bad = """# Live Agent Session Log

## Turn 1
phase_contex: 1

### User
Resume.

### Assistant
Ready.

## Turn 2
kind: quiz
phase_context: 1

### User
Quiz me.

### Assistant
[#stack_lifo_1] 栈遵循什么访问顺序？
"""
        r = _check_markdown(bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown field", r.stderr)
        self.assertIn("phase_contex", r.stderr)

    def test_tracked_write_with_matching_snapshot_passes_check_mode(self):
        good = """# Live Agent Session Log

## Turn 1
kind: explanation
phase_context: 1

### User
Plan the next step.

### Assistant
Keeping the same stage order.

### Events
- write_file: study_plan.md

### Files After: study_plan.md
```text
# Study Plan

Phase 1: stack and queue.
```
"""
        r = _check_markdown(good)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 1 turns", r.stdout)

    def test_generated_jsonl_is_accepted_by_drift_harness(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "live_session.jsonl")
            self.assertEqual(_cli(["--in", FIXTURE_MD, "--out", out]).returncode, 0)
            loaded = D.load_jsonl(out, "transcript")
            self.assertEqual(len(loaded), 3)
            result = D.evaluate(D.load_scenario(SCEN), out)
            self.assertEqual(result["scenario"], "long_session_basic")
            self.assertEqual(result["metrics"]["turns"], 3)
            self.assertIsInstance(result["passed"], bool)

    def test_check_mode_validates_without_writing(self):
        r = _cli(["--in", FIXTURE_MD, "--check"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK: 3 turns", r.stdout)

    def test_check_mode_status_uses_utf8_safe_writer(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "ascii"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "会话.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(_read(FIXTURE_MD))
            r = _cli(["--in", path, "--check"], env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("会话.md", r.stdout)

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
