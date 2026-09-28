# Test Tiers

English · [中文](test_tiers.md)

> **This file = the concise, authoritative definition of the tiers (canonical tier taxonomy).** For the detailed audit of the current state see
> [`testing-audit.en.md`](testing-audit.en.md); for the capability × tier coverage table see [`coverage-matrix.en.md`](coverage-matrix.en.md).
> All three documents must define each tier (especially **Tier 2 = behavior smoke**) the same way.

The full anti-hallucination benchmark (real runs across models) is **expensive**: one full single-round matrix costs tens of dollars and takes hours,
and long-horizon drift testing costs subscription quota measured in days. To avoid "running everything for every small change", we split testing into 5 tiers:
**the earlier the tier, the cheaper it is and the more often it should run; the later the tier, the more expensive it is and the more it should be triggered by hand**.

| Tier | Contents | Cost | When to run |
| --- | --- | --- | --- |
| **Tier 0 unit/static tests** | `python -m unittest discover -s tests` (ingest, validator, skill structure, language policy, etc.; pure stdlib, no network/LLM) | Seconds, $0 | **Required on every commit / in CI** |
| **Tier 1 workspace validation** | `python scripts/validate_workspace.py <ws>` (a built workspace's structure / question-bank schema / provenance labels / path safety) | Seconds, $0 | When changing schema/ingest/skills (locally or by hand); its validation logic is already covered by Tier 0 on `tests/fixtures/` |
| **Tier 2 behavior smoke (behavioral smoke)** | **Scripted agent behavior smoke**: a tiny **self-authored fixture workspace** + **scripted prompts** + **deterministic assertions on the produced files/output** (covering quiz_bank-only / provenance labels / hint·skip·mistake logging / confusion tracking / checkpoint resume / no-Python fallback / beginner walkthrough). **The deterministic mock layer has landed** (see [`../behavior_smoke/`](../behavior_smoke/); pure stdlib, in CI); **since T5c there is an opt-in real-agent smoke runner** (`../drift/run_live_smoke.py`: drive → record → T4 scoring in one command; env-gated, not in CI); **the behavior_smoke `--llm` single-turn real-agent smoke is wired up (B2; the wiring is tested deterministically with a stub agent)**; real paid runs remain opt-in and have not yet been run against a real model; lazy loading is best-effort | Near $0 by default | Mock layer whenever skill behavior changes (in CI); real-agent smoke is opt-in and manual |
| **Tier 3 full benchmark matrix** | **6.006 has all three arms in full** (`closedbook`/`rawfiles`/`skill`); **PSYC is partial** (`closedbook`/`skill` in full; `rawfiles` complete only for Opus, a small amount for Sonnet, none for Haiku; `report_matrix.py` also defines only closedbook/skill for PSYC). **Since T3, the aggregation layer [`aggregate_matrix.py`](matrix_pipeline.en.md) + fixture pipeline are committed, and the mechanism is reproducible from a clean checkout**; but **the full published matrix still needs private/intermediate artifacts + paid runs**. For the data see [`testing-audit.en.md`](testing-audit.en.md) | Tens of dollars, hours (fixture mechanism $0) | **Manual trigger only**, when published data/methods change |
| **Tier 4 long-horizon drift benchmark** | Measures drift across multi-turn long sessions. **Since T4, the deterministic replay harness has landed** ([`../drift/`](../drift/): replays scripted transcripts + snapshots; pure stdlib; in root-level tests); **real-LLM long sessions remain opt-in, unimplemented, and not in CI** (see below) | Replay $0; real LLM costs days of quota | Replay can run whenever skill behavior changes; real LLM is manual |

> **Tier 2 ≠ "benchmark pipeline mock check"**: `run_benchmark.py --mock` (a dry run on `items/items.example.jsonl` that
> only verifies that the benchmark pipeline connects end to end) is a **separate "benchmark pipeline mock check"**.
> It only proves that the pipeline runs. It is **not** the canonical Tier 2 behavior smoke and does not replace it: Tier 2 tests **skill behavior**, not pipeline connectivity.

## CI policy (stated honestly)
- **CI (`.github/workflows/ci.yml`) currently runs only Tier 0** (`python -m unittest discover -s tests -v`): zero cost, cross-platform, no secrets.
- **The Tier 1 validator's logic is covered by Tier 0 tests + `tests/fixtures/`**; but **there is currently no** separate CI step that runs `validate_workspace.py` on "a workspace produced by a real ingest" (this PR adds no CI step).
- **Tier 2's deterministic mock layer is in CI** (included in `tests/test_behavior_smoke.py`; pure stdlib, zero cost); but **Tier 2's real-LLM behavior smoke (opt-in) and Tiers 3–4 are not in automated CI**, so that no PR has to pay for them.

## How Tier 2 differs from Tier 4
Both test "behavior", but **at a different granularity and cost**: Tier 2 is a **single-scenario, deterministic, near-zero-cost** behavior smoke (one scripted interaction + assertions on the artifacts);
Tier 4 measures drift across **multi-turn long sessions** (next section). Tier 2 is the cheap early warning for Tier 4. **Tier 2's deterministic layer landed in PR T2** (real-LLM behavior is still opt-in and not in CI); **Tier 4's deterministic replay harness landed in PR T4** (it replays scripted transcripts; pure stdlib; in root-level tests); **real-LLM long sessions remain opt-in, unimplemented, and not in CI**.

## Tier 4: long-horizon drift benchmark (deterministic replay has landed; real-LLM long sessions are still future work)
This targets the blind spot raised in the PR #7 discussion: the current benchmark measures only "single-question accuracy" and cannot reproduce "gradual breakdown over a multi-turn long session"
(goal drift, unauthorized plan changes, inventing questions outside the question bank, failed checkpoint recovery). **T4 has landed a deterministic replay harness**
[`../drift/`](../drift/): it replays scripted multi-turn transcripts + workspace snapshots (self-authored, non-copyrighted fixtures) and measures the following metrics
**deterministically**, comparing them against thresholds (pure stdlib, zero cost, in root-level tests; `python benchmark/drift/run_drift.py --all`):

- **Goal retention**: after N turns, does it still follow the original plan/goal?
- **Plan adherence**: does it avoid rewriting the phase sequence in `study_plan.md` without the user's consent?
- **Quiz-bank fidelity / invention rate**: can every question the AI asks be found in `quiz_bank.json`, in the right phase? (Invention rate = the share that cannot be found.)
- **Checkpoint recovery**: after a restart, can it continue from the current phase in `study_progress.md` (instead of falling back to phase 1)?
- **Provenance fidelity**: does every later explanation turn carry the 🟢/🟡/⚠️ content labels? (Uses the same check as T2; the legend does not count.)
- **Mistake/confusion persistence**: once mistakes/confusions are recorded, are they **never silently deleted**?
- **Per-turn cost / context growth (optional)** and **wiki lazy loading / out-of-chapter reads**: the cost curve as turns accumulate, and whether it reads only the chapter for the current phase.

> Current state: **Tiers 0–1** low-cost structural validation + **the Tier 2 deterministic mock layer** (PR T2) + **the Tier 4 deterministic replay harness**
> (PR T4) have all landed in (root-level) tests; **Tier 2's real-LLM behavior validation and Tier 4's real-LLM long sessions remain opt-in, are not in CI,
> and have not yet been run against a real model** (behavior_smoke `--llm` single-turn is **wired up** and tested deterministically with a stub, and the drift multi-turn live runner is also ready; real paid runs are always opt-in and never in CI); **the full long-horizon LLM benchmark (costing days of quota) is still future work**.
