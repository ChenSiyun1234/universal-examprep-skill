# Tier 4 · Long-horizon drift harness (deterministic replay)

English · [中文](README.md)

This is the **first working implementation** of Tier 4, "long-horizon drift": a **deterministic, zero-cost, standard-library-only**
**replay** framework that measures whether a multi-turn tutoring session **stays steadily on the study goal** or **slowly drifts off course** as the turns add up.

> ⚠️ **It replays scripted transcripts; it does not run a real agent.** So it measures "whether a **recorded** session drifted,"
> **not** "whether a **live** model will drift." Real-LLM long sessions remain a **future / opt-in** path (see the end of this file); this directory does not connect to one, pay for calls, or go online.

## How T2 differs from T4

| | Tier 2 behavior smoke | Tier 4 long-horizon drift (this directory) |
| :-- | :-- | :-- |
| Time span | **Single-turn / small-sample** behavior | **Long multi-turn sessions** (a dozen to several dozen turns) |
| Focus | Whether a single output complies (source labels, quizzing only from the question bank…) | Whether the session, **over time**, **keeps the goal / does not change the plan on its own / does not get messier and messier** |
| Relationship | A cheap early warning for Tier 4 | Uses the same kind of deterministic detectors, but accumulates them across the **whole session** |

Both layers are **deterministic mock/replay**: they prove "the detectors hold for the **expected artifacts**," and do **not** prove that a real LLM will actually behave this way.

## Inputs

- **scenario** (`scenarios/*.json`): `name` / `fixture` (workspace snapshot) / `transcript` (the session replayed by default) / `thresholds`
  (table below) / optional `goal_markers`, `unrelated_goal_phrases`.
- **transcript** (`transcripts/*.jsonl`): one line per turn; every field is optional:
  ```json
  {"turn": 3, "user": "从阶段1考我", "assistant": "题目 [#stack_lifo_1] …", "kind": "quiz",
   "phase_context": 1,
   "events": [{"type": "read_file", "path": "references/wiki/ch1_stack_queue.md"},
              {"type": "write_file", "path": "study_progress.md"}],
   "files_after": {"study_progress.md": "…整份快照…"},
   "tokens_in": 900, "tokens_out": 120, "cost_usd": 0.001}
  ```
  `files_after` carries the snapshot of the workspace files (progress / plan) **after** that turn; the drift metrics are computed deterministically from **the differences between adjacent snapshots**.
- **Workspace snapshot parsing** accepts both **this harness's simple format** (`## 阶段1` ("Phase 1"), `当前阶段：1` ("current phase: 1"), `- ` lines) **and the real `scripts/ingest.py` template format** (`| **阶段 1** | … |` tables / `- [ ] **阶段 1**` checkboxes, `* **当前进行阶段**：阶段 1：…` ("phase in progress: Phase 1: …"), Markdown table rows for mistakes/confusions), so it can run self-authored fixtures and also replay sessions recorded in real workspaces.
- **fixture** (`fixtures/mini_course_long/`, self-authored, not copyrighted): `study_plan.md` (a fixed phase sequence),
  `study_progress.initial.md` (the starting phase), `study_progress.final.{good,bad}.md` (good/bad reference end states),
  `references/wiki/ch{1,2}_*.md`, `references/quiz_bank.json` (stable question IDs + `phase`).

## Metrics and thresholds

| Metric | Meaning | Matching threshold |
| :-- | :-- | :-- |
| `goal_retention` | Share of assistant turns that neither go off topic nor reject the original plan | `goal_retention_min` |
| `plan_mutations` / `plan_adherence` | Number of times a phase was deleted/replaced/added without the user's consent | `plan_mutations_max` |
| `invention_rate` (`quiz_items`/`bank_backed`/`invented`/`untagged_questions`/`wrong_phase_quiz`) | Whether every quiz question comes from the question bank, belongs to the right phase, and carries a `[#id]` | `quiz_invention_rate_max` / `untagged_questions_max` / `wrong_phase_quiz_max` |
| `reset_detected` (`resumed_phase`/`expected_phase`) | Whether resuming from a checkpoint continues from the current phase (instead of falling back to Phase 1) | `checkpoint_reset_max` |
| `provenance_fidelity` | Whether later **explanation turns** still carry the 🟢/🟡/⚠️ content labels (using the same check as T2; a legend does not count) | `provenance_fidelity_min` |
| `mistake_rows_added` / `confusion_rows_added` / `progress_rows_lost` | Whether mistakes/confusions get recorded and are **not silently deleted** later | `progress_rows_lost_max` |
| `wiki_reads` / `unique_wiki_files` / `overread_flag` | Whether only the current phase's chapter wiki is read (lazy loading) | `wiki_unique_files_max` / `overread_max` |
| `cost.*` (optional) | `total_tokens_in/out`, `total_cost_usd`, `context_growth_ratio` (tokens_in of the last turn / the first turn) | No threshold; reported only |

Every threshold is a simple, deterministic `_min` (≥) / `_max` (≤) comparison. An **unknown threshold key** in a scenario is an immediate error (exit 2).

## Running

```bash
# One scenario + a given transcript
python benchmark/drift/run_drift.py \
  --scenario benchmark/drift/scenarios/long_session_basic.json \
  --transcript benchmark/drift/transcripts/good_session.jsonl

# Run every scenario under scenarios/ with its own default transcript
python benchmark/drift/run_drift.py --all

# Optional: write the summary to an explicit path (by default it only prints and writes no results directory)
python benchmark/drift/run_drift.py --all --json-out /tmp/drift_summary.json
```

Exit codes: `0` all thresholds met · `1` a threshold was not met · `2` missing or malformed input.

Apart from `good_session.jsonl` (a long session that meets every threshold), each `bad_*.jsonl` in `transcripts/` is a minimal replay that
**triggers exactly one kind of drift** (so tests can assert that the matching metric fails): plan changed without consent / invented questions / checkpoint reset / lost provenance labels / lost progress rows / wiki read outside the current chapter.

## Live-agent session log adapter

T5b adds a tiny stdlib-only adapter so live-agent pilots can be captured in a UTF-8 Markdown log first, then
converted to the JSONL shape above. This avoids hand-authoring JSONL and reduces Windows/PowerShell Unicode
pitfalls around Chinese text and emoji provenance labels.

```bash
# Inspect the starter format
python benchmark/drift/convert_session_log.py --template \
  benchmark/drift/templates/live_session_template.md

# Validate only
python benchmark/drift/convert_session_log.py \
  --in /tmp/live_session.md \
  --check

# Convert to explicit temp output, then score with T4
python benchmark/drift/convert_session_log.py \
  --in /tmp/live_session.md \
  --out /tmp/live_session.jsonl

python benchmark/drift/run_drift.py \
  --scenario benchmark/drift/scenarios/long_session_basic.json \
  --transcript /tmp/live_session.jsonl \
  --json-out /tmp/live_metrics.json
```

The adapter reads and writes UTF-8 explicitly, exits `2` on malformed input, and does not write tracked outputs
unless you explicitly point `--out` into the repository. It also validates supported event names (`read_file` /
`write_file`) and requires matching `files_after` snapshots when a turn records writes to `study_plan.md` or
`study_progress.md`. See [`docs/live_agent_pilot.md`](docs/live_agent_pilot.md) for the live pilot runbook and
commit boundaries.

## T5c · One-command real-agent smoke test (opt-in)

`run_live_smoke.py` automates the manual T5b pilot: **drive a real agent → record (in T5b format) → convert to JSONL → score with T4**, all in one command, and the exit code is the verdict (0 thresholds met / 1 drift detected / 2 gate or input error / 3 budget exceeded or failure abort).

```bash
RUN_SKILL_DRIFT_LLM=1 python benchmark/drift/run_live_smoke.py   --agent-cmd "claude -p {prompt}" --out-dir /tmp/live_smoke
```

- **Gate**: running any agent command requires `RUN_SKILL_DRIFT_LLM=1` (it incurs real call costs); CI never runs it.
- **Budget/abort**: `--max-turns/--max-output-chars/--max-prompt-chars/--turn-timeout`; if any limit is exceeded or the agent fails, it exits 3. An incomplete session is never scored as a clean one.
- **Honest division of labor**: the agent is invoked once per turn and can only "talk." File-writing behavior (progress persistence, writing plan changes to disk) is **not** covered by this smoke test (the deterministic replay layer guards it). What it tests is the **text-observable contract**: goal retention, quizzing from the bank ([#id] + no invented questions), provenance labels, and checkpoint language. Ten turns is a pilot, not statistical proof.
- **Scoring scenario**: `scenarios/live_smoke_basic.json` **contains only text-observable thresholds**. Wiki lazy loading, out-of-chapter reads, and progress-row persistence cannot be observed from one-shot text calls, so they **deliberately have no thresholds** (the deterministic replay layer covers them). This keeps a vacuous pass from being misread as verified.
- **The checkpoint is driven by the script (by design)**: the turn script plays the "student/environment." When the student says they are moving to Phase 2, the environment updates the progress file. The agent's compliance with the checkpoint is measured by the reset/goal metrics, and **state never advances based on the agent's verbal reply** (semantic interpretation is left to a future LLM judge).
- **Sandbox workspace**: each run copies the fixture to `<out-dir>/workspace` and makes it the agent's CWD, so reads and writes by a tool-using agent land in a throwaway copy and never touch the committed fixture (give the program in `--agent-cmd` as an absolute path or a command on PATH). The question-bank summary includes **options and reference answers** (so the scoring probes do not depend on the model's prior knowledge).
- Turn script: `templates/live_smoke_turns.json`; golden sample (produced by a local fake agent, self-authored): `fixtures/live_logs/live_smoke_golden.{md,jsonl}`. A clean checkout is enough to reproduce the "convert → score" half.

## Boundaries and limitations (stated honestly)

- **Deterministic replay ≠ real agent behavior**: the detectors hold only for scripted transcripts; whether a real model behaves this way is **not verified**.
- **Real-LLM long sessions have graduated to opt-in (B3)**: `run_drift.py --llm` is no longer a skeleton. It delegates to the real pipeline in `run_live_smoke.py`
  (drive a real agent turn by turn → record a T5b log → convert to JSONL → score with **the same** `compute_metrics`/thresholds → record in the ledger);
  token caps, failure aborts, and the fixture sandbox all live in the live runner. It requires `RUN_SKILL_DRIFT_LLM=1` (no env → exit 2;
  env set but no `--agent-cmd`/`--turns` → the delegated live runner exits nonzero because required arguments are missing; it **never reports success without an agent**).
  Usage: `RUN_SKILL_DRIFT_LLM=1 python run_drift.py --llm --agent-cmd "claude -p {prompt}" --out-dir <dir> --turns <spec>`.
- **The paid part stays out of CI**: this harness's deterministic layer costs nothing and runs in the root-level tests; the real-agent `--llm` path incurs real call costs
  (against a daily quota), so it is **triggered manually and never runs in CI**.

### The metrics are smoke heuristics, not semantic scorers: known inherent limitations

After an adversarial self-review, the items below are **inherent limitations of regex/structural heuristics**. Deterministic methods cannot fully fix them; semantic judgment is left to the future opt-in `--llm`:

- **Goal retention** is a **keyword blocklist**: it only catches off-topic phrasing listed in `unrelated_goal_phrases`; a different phrasing that is not on the list goes undetected.
  As a positive signal, the optional threshold `goal_marker_min` (requiring the assistant to mention the exam goal at least once) adds a floor, but it is still not semantic judgment.
- **Provenance labels**: `has_content_label` cannot tell "a one-line legend definition (🟢 来自资料：表示… ("🟢 From your materials: means…"))" apart from "actually labeling a specific sentence,"
  so a one-line legend counts as labeled (the same limitation as T2). Real sentence-by-sentence label checking is a job for an LLM.
- **Invention rate** depends on the skill's `[#id]` labeling convention: a question invented entirely in **prose** with no `[#id]` at all can only be caught
  by the structural signal "asked to quiz, but zero `[#id]`" (recorded as `untagged_questions`); it cannot decide sentence by sentence whether a piece of prose is an "invented question."
- **Checkpoint reset** only recognizes "阶段/phase + a number" or the restart words in `RESTART_PHRASES`; a purely natural-language 「从头再过一遍」 ("let's go through it all again from the start") that contains none of these cues is missed.
- **Plan authorization** relies on nearby keywords: `--` authorization only checks whether "the turn that made the change, or the user message right before it" contains a word like `改计划` ("change the plan"); it cannot understand
  **scope-limited** instructions such as 「只改错别字、别动顺序」 ("only fix typos, don't change the order") and will treat the adjacent change as authorized. What has been fixed is the **session-level** latch (one authorization letting everything through for the rest of the session).

**These are not bugs but the boundaries of deterministic replay.** On **labeled scripted transcripts** the harness makes structural assertions; adversarial evasion is left to
a future LLM judge. By contrast, the following **structural evasions are closed** (see the regressions in `tests/test_drift_harness.py`): out-of-phase quizzing and out-of-chapter reads
**no longer** stop being detected when `phase_context` is missing (they use **the current phase as it rolls forward within the session**, and phase↔chapter follows the **study_plan mapping**, not `chNN==阶段`);
checkpoint reset is checked on **every** resume turn and takes the **lowest** phase mentioned ("we're at Phase 2 now, but let's start from Phase 1 first" also counts as a reset); explanation-turn detection **cannot** be bypassed
through the `kind` value; progress rows are tracked by `[#id]` (rewording does not count as loss); plan authorization is not a session-level latch; a question that carries a real `[#id]` but **whose text has been swapped for an invented question** is judged invented by the same content comparison as T2;
extra unnumbered questions in mixed turns also count toward `untagged`; empty-run transcripts with only user turns and no assistant turns, as well as broken fixture JSON, both exit 2.
**Parsing is compatible with both self-authored fixtures and the real `scripts/ingest.py` template** (tables / checkboxes / checkpoint lines / mistake and confusion table rows).
