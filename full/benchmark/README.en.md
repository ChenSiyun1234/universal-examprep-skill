# Anti-Hallucination Benchmark Framework

English · [中文](README.md)

This backs the `universal-exam-cram-coach` skill with **real data**: it measures a "with skill" group against a "without skill" group
on grounded Q&A over your own course materials, comparing hallucination rate, faithfulness, abstention rate and more, to replace promotional numbers like the "90% / 100%" in the README.

> Status: **the framework scaffold is in place and runs** (verified end to end in `--mock` mode). What is still missing is **real data**:
> prepare your slides/homework and a gold question set as described below, then do a real run with Claude Code.

---

## Design (why we test it this way)

- **Paired experiment**: each gold question goes through each of the three **primary matrix arms**:
  - **`closedbook`**: the prompt contains no course material, so the model answers from its own knowledge only (the lower-bound control for hallucination).
  - **`rawfiles`**: the original lecture/exercise files are placed in a folder, and the model consults them on demand with generic file-reading/search tools, but **without the skill installed**. This is the fairest control. It directly answers the question "why not just hand the AI a folder and let it read? What do you need the skill for?"
  - **`skill`**: runs `claude -p` inside `skill_workspace/` with the skill active and the file-locked knowledge base (`references/wiki/` + `quiz_bank.json`)
    already built (that is, the anti-hallucination mechanism of "read the relevant chapter instead of deriving on the spot").
- **Legacy/stress arm (legacy / stress footnote, not a primary control)**:
  - **`material` / dump-all**: stuffs the full text of the whole course into a single prompt. It is **not a fair control** and is kept only as a stress footnote. In practice a full-text dump overwhelms the weak model (Haiku) and often hits context/usage limits and crashes, which confirms that "just paste the whole book in" does not work. The `baseline` arm of the early `run_benchmark.py` (raw materials only) belongs to this category and has been replaced as the primary control by the fairer `rawfiles`.
- **How it is driven**: it calls **Claude Code headless mode, `claude -p`**, directly, under your logged-in **subscription**, so **no API key is needed**.
  (Note: **do not use `--bare`**. It actually requires an API key and skips loading the skill / CLAUDE.md.) Once you buy Codex, swap the
  generator for `codex exec` to get a cross-CLI comparison; nothing else needs to change.

### Metrics (each one is mapped to an authoritative benchmark; see `docs/related_benchmarks.md`)

| Metric | Meaning | Benchmark it maps to |
| :-- | :-- | :-- |
| Faithfulness ↑ | Share of the atomic claims in an answer that the materials support | RAGAS faithfulness / FACTS Grounding |
| Hallucination rate ↓ | Share of questions whose answer contains ≥1 unsupported claim or claim that contradicts the materials | Vectara HHEM / HalluLens (intrinsic) |
| Calculation accuracy ↑ | Deterministic grading of numeric questions (no LLM involved) | — (exact scripted grading) |
| Out-of-scope abstention rate ↑ | For questions the materials do not cover, whether the model correctly abstains instead of making something up | RGB negative-rejection / SimpleQA abstention |
| Correctness ↑ | Overall correctness against the gold answers | TRUE (NLI consistency) |

---

## Step by step

**Prerequisites**: Python 3.8+ (standard library only, no pip needed) and a logged-in Claude Code (typing `claude` in a terminal works).

0. **Start with a dry run to check the pipeline** (uses no quota):
   ```
   cd benchmark
   python run_benchmark.py --mock --items items/items.example.jsonl
   ```
   Open `results_mock/report.html` in a browser to see what the output looks like (mock writes to `results_mock/` by default and never overwrites the committed real report in `results/`; the report is **bilingual Chinese/English, with charts and citations for each metric's source**; the numbers are placeholders and only verify the pipeline).

1. **Add materials**: drop your slides/homework into `materials/<课程>/` (`<课程>` = course). If you want to run the legacy/stress arm, also generate `materials/_combined.txt` (**only the `material`/dump-all footnote arm reads it**; none of the three primary arms `closedbook`/`rawfiles`/`skill` reads it). See `materials/README.md`.

2. **Build the skill's knowledge base**: in `skill_workspace/`, use the skill to split the materials into `references/wiki/` + `references/quiz_bank.json`. See `skill_workspace/README.md`.

3. **Write the gold question set**: copy `items/items.example.jsonl` to `items/items.jsonl` and rewrite it to fit your materials, **including a few out-of-scope probes and calculation questions**. See `items/README.md`.

4. **Configure**: copy `config.example.json` to `config.json` and change `generator_model` / `judge_repeats` etc. as needed.

5. **Real run**:

   - 📖 **The full operating manual is [`docs/running-real-runs.en.md`](docs/running-real-runs.en.md)** (real, paid LLM runs: the three-arm matrix `run_matrix.py --real` + judging/aggregation/reporting + behavior_smoke/drift smoke runs + quota/cost/honest reporting conventions + harder gold items). Below is the short version.
   - **Config-driven three-arm matrix (currently recommended, runs from a clean checkout)** `run_matrix.py`: first run `python run_matrix.py --config config.matrix.example.json --mock --limit 6` to verify the pipeline for free, then `cp config.matrix.example.json config.json` (change `judge_model` to `sonnet`) and run `python run_matrix.py --config config.json --real` (resumable, quota-aware, judging inline). It reads your `config.json` (course × model × arm) and **replaces** the MIT/PSYC-only `gen.py` described below.
   - **Run on your own course (the older two-arm scaffold)**:
     ```
     python run_benchmark.py --config config.json
     ```
     It reads the `config.json` + `items/items.jsonl` from steps 3–4 above and produces `results/report.html` (a **bilingual Chinese/English visual report**: charts + metrics hyperlinked to the authoritative benchmarks + a References section at the end), `results/report.md`, and `results/raw.jsonl` (per-question raw answers + scores).
     > **It runs only two arms**: `baseline` (raw materials only, ≈ the material/dump kind) vs `skill`, **without `closedbook` / `rawfiles`**. What it produces is a **legacy two-arm report**, not the primary matrix.

   - **Where the published primary three-arm matrix came from (provenance; users cannot reproduce it with one command)**: the `closedbook` / `rawfiles` / `skill` matrix was produced by an internal pipeline: `gen.py` (generates answers) → `rejudge.py` (judges) → `report_matrix.py` (renders). **It is specific to the existing MIT/PSYC matrix. It does not read your `config.json` / `items.jsonl` above, and it cannot run from a clean checkout**:
     > ⚠️ `gen.py` **hard-codes the MIT/PSYC question files and workspaces** and accepts only `--limit`; and `build_tasks()` **unconditionally opens an uncommitted** `results/matrix/answers.jsonl` seed, so on a clean checkout `python gen.py` fails straight away with `FileNotFoundError` and never runs. The published `summary.json` is therefore a precomputed artifact. **The full MIT/PSYC matrix still depends on private/intermediate artifacts + paid runs**, and the scripts in this repository cannot reproduce it end to end from scratch (details in [`docs/testing-audit.en.md`](docs/testing-audit.en.md)).
     > ✅ **T3 added a committed aggregator**, [`aggregate_matrix.py`](aggregate_matrix.py): it aggregates **explicit** answer/score rows into `summary.json`, which `report_matrix.py --summary <file> --out-dir <dir>` then renders. The **pipeline mechanics** can be reproduced from a clean checkout with a tiny fixture (see [`docs/matrix_pipeline.en.md`](docs/matrix_pipeline.en.md)). This reproduces only the **mechanics**, not the numbers from the published paid runs.

6. **Calibrate the judge's reliability (required before publishing a report)**: hand-label a subset of 30~50 questions, put it in `calibration/`, and use `stats.cohen_kappa`
   to compute the agreement between the human labels and the LLM judge. **Trust the judge's numbers only at kappa ≥ roughly 0.6**; otherwise improve the judge/questions first.

7. **Read the report and write conclusions**: draw conclusions according to the honesty rules below.

---

## Honesty rules (this is where the report's credibility comes from, and a plus for internship applications)

- **Paired statistics**: use **McNemar** (paired binary) for the hallucination rate, and give a **bootstrap 95% CI** for the difference (see `stats.py`).
- **Claim significance only** when the CI lower bound > 0 **and** McNemar p < 0.05 (`stats.significant`).
- **Don't overclaim with a small sample**: when n is small, present descriptive results + confidence intervals and state clearly that statistical power is limited. That is exactly the academically defensible way to write it up.
- **Judge bias**: judge ≠ generator. When possible, use a model from a **different family** as the judge (for example Codex/GPT later on). When only Claude is available,
  **hide** from the judge which arm an answer came from, randomize the order, use **per-claim span-anchored** verdicts (already done in `judge.py`), and record the judge's self-consistency across repeated re-judging.

---

## File layout

```
benchmark/
  run_benchmark.py     # older two-arm scaffold (baseline vs skill); --mock does a dry run to verify the pipeline
  gen.py               # newer matrix answer generation: incremental fill by feasibility (depends on an existing answers.jsonl), resumable, records per-cell cost
  judge.py             # judging: deterministic for numeric questions + claim-level faithfulness for factual/definition questions (LLM judge)
  rejudge.py           # re-judges stored answers with the corrected judge, writes summary_corrected.json
  aggregate_matrix.py  # (T3) explicit answer/score rows → summary.json-compatible matrix summary; pure stdlib, no network/LLM
  behavior_smoke/      # (T2) Tier 2 behavioral smoke: self-authored fixtures + deterministic detectors (runs in CI)
  drift/               # (T4) Tier 4 long-horizon drift: deterministic replay harness (replays scripted transcripts + snapshots; pure stdlib, zero cost)
  stats.py             # McNemar + paired bootstrap CI + Cohen's kappa (pure standard library)
  report.py            # two-arm reporter (bilingual Chinese/English HTML + citations)
  report_matrix.py     # matrix reporter: renders summary.json (default results/matrix/; --summary/--out-dir supported since T3)
  config.example.json  # config template (copy to config.json)
  items/               # gold question set (items.example.jsonl + authoring spec)
  materials/           # your original slides/homework (+ _combined.txt)
  skill_workspace/     # run directory for the skill arm (references/wiki + quiz_bank.json)
  calibration/         # hand-labeled subset (for judge calibration)
  results/             # run outputs (raw.jsonl + report.md + matrix/summary.json)
  tests/               # script self-tests (python -m unittest discover -s tests)
  docs/related_benchmarks.md  # survey of authoritative hallucination benchmarks (draft of the report's related-work section)
```

> **Pipeline status (stated honestly)**: `run_benchmark.py` is the older two-arm scaffold; matrix results come from the newer `gen.py` (answer generation), `rejudge.py` (judging), and `report_matrix.py` (rendering). **T3 added the committed aggregator `aggregate_matrix.py`** (explicit answer/score rows → `summary.json`) + `report_matrix.py --summary`, so the **pipeline mechanics** can be reproduced from a clean checkout with a tiny fixture (see [`docs/matrix_pipeline.en.md`](docs/matrix_pipeline.en.md)). But the published `summary.json` is still a **precomputed** artifact, and **the full MIT/PSYC matrix still depends on private/intermediate artifacts + paid runs**; the aggregator reproduces only the mechanics, not the published numbers. `aggregate_matrix.py` and the material builders (P0A/P0B) are two different things: the latter build PDF slides into a workspace and have nothing to do with aggregation in this benchmark.

## Roadmap (next steps)
- **v2 portfolio upgrade**: after buying an API key, port it to **Inspect AI** (UK AISI; Task/Solver/Scorer + model grading)
  for a more rigorous piece of work; or wrap `claude -p` directly with **promptfoo**'s `exec:` provider (industry standard, with a built-in HTML report).
- **Platform version**: once the project integrates LlamaIndex (slide ingestion/RAG) + the OpenAI Agents SDK (orchestration), this benchmark's "system under test"
  boundary can be switched straight to the platform version while reusing the gold set and statistics unchanged. It becomes the platform's **faithfulness regression gate**.
