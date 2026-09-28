# Testing & Benchmark Audit

English · [中文](testing-audit.md)

> This is an **honest snapshot of the current state**. Its purpose is to spell out "what we actually test and what we don't" before we invest in expensive tests.
> It is not a marketing document. Its conclusions point to the PR roadmap (see the end). Current progress: **T1** (audit doc + consistency guard), **T2** (Tier 2 deterministic behavior-smoke layer), **T3/T3.1** (committed aggregator `aggregate_matrix.py` + fixture pipeline + judging↔aggregation bridge) and **T4** (Tier 4 long-horizon drift **deterministic replay harness** [`drift/`](../drift/)) have landed; T2's **real-LLM behavior-smoke wiring is hooked up** (B2: behavior_smoke `--llm` single-turn + stub-based deterministic tests), and T4's **real-LLM long-session** runner is also ready; real paid runs and **T5** remain opt-in (the full published matrix still needs private/paid artifacts). This file is a living snapshot maintained across PRs; it does not run paid benchmarks.

---

## 1. Test tiers and what actually runs

| Tier | What it is | In CI? | Cost | Reality |
| :-- | :-- | :--: | :-- | :-- |
| **Tier 0** | `python -m unittest discover -s tests` (stdlib unit/static test suite) | ✅ Ubuntu + Windows × Py 3.8 + 3.12 | $0, pure standard library, no network, no API key | The **only** tier CI actually runs |
| **Tier 1** | `python scripts/validate_workspace.py <workspace>` (a built workspace's structure/schema/provenance labels/path safety) | 🟡 integration test runs in CI with Tier 0 | $0 | The validator logic is covered by Tier 0 unit tests; **since B6** there is also a deterministic `ingest → validate` integration test (`tests/test_ingest_validate_integration.py`: it actually runs both CLIs; real ingest output must pass validation, and tampered/missing-image/bad-JSON workspaces must exit with 1/2). It reaches CI through the root tests, with no separate Actions step (CI configuration deliberately not added) |
| **Tier 2** | **Behavior smoke**: deterministic mock layer (see [`behavior_smoke/`](../behavior_smoke/)) | ✅ mock in CI | Near $0 | The deterministic layer has landed; **since T5c there is an opt-in real-agent smoke runner** ([`drift/run_live_smoke.py`](../drift/run_live_smoke.py): drive → record → T4 scoring in one command; env-gated, not in CI); **behavior_smoke `--llm` single-turn is wired up (B2), and the wiring is tested deterministically with a stub; real paid runs remain opt-in and have not yet been run**, see §4 |
| **Tier 3** | Full benchmark (`gen.py` → judging → matrix report) | ❌ | **Expensive**: a single-round matrix costs roughly tens of dollars / several hours | Manual, ad hoc |
| **Tier 4** | Long-horizon drift | 🟡 replay layer is in (root-level) tests | Replay $0; real LLM costs days of quota | **The deterministic replay harness has landed** ([`drift/`](../drift/): replays scripted transcripts; pure stdlib; zero cost); **real-LLM long sessions remain opt-in, unimplemented, and not in CI** |

**CI status**: `.github/workflows/ci.yml` has a single step, `python -m unittest discover -s tests -v`, so it runs only Tier 0 (**which now includes `tests/test_behavior_smoke.py`, Tier 2's deterministic mock layer**); all of it is zero cost. The README has been corrected accordingly to say "CI actually runs only Tier 0". The Tier 1 validator's logic is covered by Tier 0 unit tests on `tests/fixtures/`; **since B6**, the deterministic `ingest → validate` integration test (which actually runs both CLIs) also lives in the root `tests/` and runs in CI with Tier 0 (still no separate Actions step; CI configuration deliberately not added).

---

## 2. What Tier 0 checks

`tests/` holds a stdlib unit/static test suite (run `python -m unittest discover -s tests -v` to see the current count and details). It covers:

- **Workspace validator**: structure, question-bank schema (6 question types), provenance labels (`source` enum + mandatory `ai_generated` flag), **path safety** (symlinks, directory traversal, backslashes, Markdown links, NaN), exit codes 0/1/2.
- **ingest end to end**: generated files, anchor replacement, loud errors on bad input, refusal of traversal/duplicate-name wikis, acceptance of 6 question types, warnings for missing answers, rerun/`--force` backups.
- **Language policy / bilingual control layer**: canonical provenance-label wording, English control-layer headings, Simplified Chinese as the student-facing default, no vague wording.
- **Skill collection self-consistency**: `skills/` frontmatter (name/description/license), AGENTS fallback invariants, docs present, confusion-tracker merged into `skills/`.
- **Runtime wording**: no version numbers / no abstract "protocol" wording.

**What they are**: all of these are **structure / schema / file-content** assertions + script tests of `ingest`/`validate_workspace`. They prove that "the instructions and artifacts exist and are well formed"; they **do not execute real agent behavior**.

## 3. What Tier 1 checks

`scripts/validate_workspace.py` runs zero-cost validation on an **already built exam-prep workspace**: directory structure, `quiz_bank.json` schema (question type/options/answer within the options/subjective-question keywords/diagram_type/true_false boolean/source enum/`ai_generated` flag), `references/wiki/` path safety, and progress-file consistency; exit code `0` pass / `1` errors / `2` fatal (broken structure or invalid JSON). It is driven by Tier 0 unit tests on fixtures; **since B6** there is also `tests/test_ingest_validate_integration.py`, which actually runs this CLI on **real ingest output** (happy 0 / tampered 1 / bad JSON 2) and runs in CI with the root tests.

## 4. Tier 2 behavior smoke: the deterministic layer has landed; real-LLM behavior is still opt-in (not in CI)

This PR (T2) landed Tier 2's **deterministic mock layer**: a small self-authored fixture (`benchmark/behavior_smoke/fixtures/mini_course`, which passes Tier-1 validation and covers all 6 question types) + a set of **deterministic detectors** that assert the following behaviors on mock artifacts, all in CI and at zero cost:

- quiz_bank-only questions (question IDs must ∈ the bank; invented IDs are caught)
- canonical 🟢/🟡/⚠️ provenance-label output
- hint / skip / mistake logging (escape hatches + mistake rows written)
- conceptual confusion tracking (confusion rows written to progress)
- study_progress checkpoint resume (current phase read back)
- write-to-disk fallback without a Python environment (hand-written workspace passes validation)
- beginner key-question walkthrough (upgraded to the A5 seven-step template)

The phases of the A line added **5 more Tier 2 deterministic behavior scenarios** (`behavior_smoke/scenarios.json`, registered in [`coverage-matrix.en.md`](coverage-matrix.en.md) when B1 wrapped up):

- Visual questions: prompt-image gate (`visual_first_assets`, P0-V1/A1)
- Scope filtering + out-of-scope override announcement (`scope_override`, A2)
- Seven-step walkthrough template + per-item source block (`teaching_template`, A5)
- ≤1 day skips clarification/preference/reflective follow-up questions but allows bank-verified checkpoints; only an explicit `no_questions` forbids all interactive questions and caps completion at `covered_unverified` (`time_budget_no_questions`, A6)
- Knowledge points outside the window must really be rechecked (`knowledge_window_recheck`, A6; >7 days requires an actual quiz question)

There is also **1 Tier 4 long-session replay scenario** (`benchmark/drift/scenarios/mode_urgent_no_questions.json`, **not** a Tier 2 smoke): the student in this scenario has explicitly asked not to be asked questions, so it verifies zero interactive questions (`urgent_mode_questions`) + that the urgent opening is inferred and persisted (`urgent_mode_persisted`). It does not mean that an ordinary ≤1 day budget forbids bank checkpoints.

**Still honest**: the deterministic layer only proves that the detectors hold on the **expected artifacts**; it **does not prove that a real LLM agent will produce these behaviors**. **The behavior_smoke `--llm` single-turn real-agent smoke is wired up** (B2: it drives each scenario, applies the same detectors as `--mock`, and honestly reports state-type scenarios as SKIP; `tests/test_behavior_smoke_live.py` verifies the wiring deterministically with a stub). Real paid runs remain opt-in and not in CI (`RUN_SKILL_BEHAVIOR_LLM=1` or `--agent-cmd`) and have not yet been run against a real model; **LLM Wiki lazy loading** and **running the algorithm before drawing** remain best-effort / uncovered. See [`../behavior_smoke/README.en.md`](../behavior_smoke/README.en.md) and [`coverage-matrix.en.md`](coverage-matrix.en.md) for details.

## 5. Tier 3 full benchmark: manual and expensive

A real-LLM matrix across `course × model × arm`; a single round costs roughly tens of dollars / several hours. It measures **grounding / hallucination / out-of-scope abstention in grounded Q&A**, not the interactive tutoring flow. Trigger it by hand only when you "deliberately changed skill behavior / added new course materials / are about to release"; it should not go into CI or run for every small change.

## 6. Tier 4 long-horizon drift: deterministic replay has landed; real-LLM long sessions are still future work

Goal retention / plan adherence / invention rate / checkpoint recovery / provenance labels / progress persistence in long conversations (dozens of turns + mid-session distractions). **T4 has landed a deterministic replay harness** [`drift/`](../drift/): it replays scripted multi-turn transcripts + workspace snapshots (self-authored, non-copyrighted fixtures) and measures the dimensions above **deterministically** against thresholds: pure stdlib, zero cost, in root-level tests (`python benchmark/drift/run_drift.py --all`). **But it replays scripted sessions and does not run a real agent**: it measures "whether a recorded session drifted"; it does **not** prove that an online model won't drift. **Real-LLM long sessions remain opt-in (`--llm` + `RUN_SKILL_DRIFT_LLM=1`), unimplemented, never return success, and are not in CI**; the full long-horizon LLM benchmark (costing days of quota) is still future work.

---

## 7. Benchmark pipeline status (stated honestly)

- **Two runners coexist, with different arm definitions**:
  - `run_benchmark.py` is the **older two-arm scaffold** (`baseline` / `skill`); it cannot resume and **discards cost**.
  - `gen.py` is the **newer matrix answer-generation** path; it supports all four arms (`closedbook` / `material` / `rawfiles` / `skill`), **can resume, and records cost per cell**. But it is an **incremental gap-filler ordered by feasibility, not a from-scratch full generator**: `build_tasks()` actually queues only rawfiles (both courses), PSYC's closedbook/skill, **reruns of only the failed algo `material` cells** (read from the existing `results/matrix/answers.jsonl`), and PSYC material. It **depends on an existing `answers.jsonl`** (`build_tasks()` opens it unconditionally), and that file is **not committed**, so on a clean checkout `python benchmark/gen.py` fails immediately with `FileNotFoundError` and **cannot run at all**. It also **hard-codes the MIT/PSYC item prompts and workspaces**, accepts only `--limit`, and does not read the user's `config.json`/`items.jsonl`. Therefore **the published matrix can neither be run from a clean checkout nor be reproduced from scratch with this repository's scripts alone**. This is a reproducibility gap separate from "the missing aggregator".
- **The three primary control arms are standardized as `closedbook` / `rawfiles` / `skill`**:
  - `closedbook`: no course materials at all.
  - `rawfiles`: raw files + a general-purpose agent, no skill installed. **The fairest control.**
  - `skill`: the built wiki + quiz_bank, using this skill.
  - **Legacy/stress arm `material` / dump-all**: the whole course's full text stuffed into a single prompt. **Not a primary control**; kept as a **stress footnote** (in practice it overwhelms weak models and triggers context/usage limits that crash the run).
- **`report_matrix.py` only renders; it does not compute**: by default it renders `results/matrix/summary.json`. Since T3 it supports `--summary <file> --out-dir <dir>` and can render an **explicit** summary (it is no longer forced to render only the committed one).
- **T3 filled in the `summary.json` aggregator**: `benchmark/aggregate_matrix.py` (**new in T3**, pure standard library) aggregates a `summary.json`-compatible matrix summary from **explicit** answer/score rows, and there is a fixture-level reproducible pipeline (see [`matrix_pipeline.en.md`](matrix_pipeline.en.md)). **But the published MIT/PSYC `summary.json` is still a precomputed artifact**: the full matrix still depends on **private/intermediate artifacts + paid model runs** (real answer logs and private gold labels are not committed), and the aggregator by itself does **not** reproduce the published numbers. (Also note: after re-judging, `rejudge.py` writes `summary_corrected.json`, whose structure is **nested** `algo` / `psyc` blocks, **not** the top-level `matrix`/`n_items` shape that `report_matrix.py` reads, so it **cannot** be rendered directly with `--summary summary_corrected.json`. It must first be converted to the top-level matrix shape, and re-judged results do not enter the matrix report automatically. **T3.1 built this bridge**: `rejudge.py --scores-out` (**`--answers-out` must be given too**) exports each item's score, at zero cost and without calling an LLM, as score/answer rows that `aggregate_matrix.py` can read (answer rows carry `status`/`cost_usd`), so `judge/rejudge → aggregate_matrix → report_matrix` becomes a committed, explicit path you can follow. The default behavior is unchanged, and the export writes only to explicit paths.)
- **Judging already has a deterministic fast path**: out-of-scope abstention / numeric items / exact lexical matches are decided before the LLM judge is called; only undecided factual/definition items go to the LLM judge.
- **`--mock` only validates the pipeline**: the mock answers and the mock judge are both preset. They can verify that the pipeline connects, but they **cannot catch regressions in real judging quality**.

---

## 8. Coverage gaps for new skill capabilities

In one sentence: **structure / schema / instruction text are thoroughly covered statically; behavior is barely verified by execution at all.** For a per-capability comparison see [`coverage-matrix.en.md`](coverage-matrix.en.md). Capabilities that need to be tested at the **behavior** level (and currently are not): lazy loading, quiz_bank-only questions, actual grading of the six question types, running the algorithm before drawing, beginner walkthroughs, hint/skip/mistake logging, confusion tracking, checkpoint resume, runtime provenance labels, and the no-Python fallback.

---

## 9. Token-saving principles

1. **Deterministic first**: whether provenance labels appear, whether every drawn question is in the bank, whether progress was written, whether only one chapter was read, whether diagram questions carry a render_hint: these are decided with **structural assertions on the artifact files** and **need no LLM judge**.
2. **Cache generation and judging**: `gen.py` already caches answers + cost per cell and can resume; judging results should also be cached (ideally keyed by a hash of the judge prompt, so that a change to the prompt template correctly invalidates the cache).
3. **Use the LLM judge only for undecided items**: call the judge only for factual/definition items that the deterministic fast path cannot settle.
4. **Keep Tier 2 small and mostly deterministic**: about a dozen behavior scenarios, a single cheap model (Haiku), mostly structural assertions, and only a very few that need one cheap grounding call.
5. **Paid tiers must be triggered by hand**: the full benchmark (Tier 3) and **real-LLM** long-horizon drift (the `--llm` part of Tier 4) never go into CI and never run for small changes; Tier 4's **deterministic replay layer** is zero cost and already in the root-level tests.

---

## PR roadmap (T-track)

- **T1** ✅: audit doc + coverage matrix + benchmark doc consistency guard (zero cost, docs/tests only).
- **T2** ✅ (deterministic layer): Tier 2 behavior smoke: self-authored non-copyrighted fixture + harness + deterministic detectors (in CI); the `--llm` single-turn real-agent smoke **wiring is hooked up (B2, stub-based deterministic tests)**; **real paid runs remain opt-in, are not in CI, and have not yet been run against a real model**.
- **T3** ✅ (aggregation layer): committed `summary.json` aggregator [`aggregate_matrix.py`](matrix_pipeline.en.md) + fixture-level reproducible pipeline + `report_matrix.py --summary`. **The full published matrix still depends on private/paid artifacts**; benchmark caching/resume/cost logging are later increments.
- **T4** ✅ (deterministic replay layer): Tier 4 long-horizon drift [`drift/`](../drift/): self-authored non-copyrighted fixtures that replay scripted transcripts + snapshots and deterministically measure goal retention/plan adherence/invention rate/checkpoint recovery/provenance labels/progress persistence/out-of-chapter wiki reads (in root-level tests); **real-LLM long sessions are opt-in, not in CI, and not yet implemented**.
- **T5**: judge calibration (larger kappa sample, add near-miss out-of-scope probes, cross-family judges, fix numeric extraction).
