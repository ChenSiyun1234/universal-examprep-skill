# Matrix Benchmark Pipeline

English · [中文](matrix_pipeline.md)

This document describes, precisely, the pipeline "answers/scores → matrix `summary.json` → report", and **the piece T3 filled in**: a committed, tested aggregation/conversion script that makes the pipeline's **mechanism** reproducible from a clean checkout using fixture data.

> Important boundary: **T3 makes the pipeline mechanism reproducible with fixture data; it does not make the "published full MIT/PSYC benchmark" rerunnable from a clean checkout**. The full matrix still depends on private/local intermediate artifacts and paid model calls (see §2, §5).

## 1. What exists today

| Stage | Script | Notes |
| --- | --- | --- |
| Generate | `benchmark/gen.py` | An **incremental gap-filling** helper: it fills missing cells from an existing `answers.jsonl`. It is **not** a one-command full-matrix generator. |
| Judge | `benchmark/judge.py` / `benchmark/rejudge.py` | Exact numeric comparison + lexical exact-match + abstention; optional LLM re-judging (cached). `rejudge.py` contains the per-cell `aggregate()` logic, but it is coupled to judging and to reading `results/`. **Since T3.1**, `rejudge.py` supports `--scores-out` (**`--answers-out` must be given too**) to export, at zero cost, score/answer rows that `aggregate_matrix.py` can read (answer rows carry `status`/`cost_usd`). This is the bridge between judging and aggregation. |
| **Aggregate** | **`benchmark/aggregate_matrix.py` (new in T3)** | Reads **explicit** answer/score rows → a matrix summary compatible with `summary.json`. Pure standard library, deterministic, no network/LLM. |
| Render | `benchmark/report_matrix.py` | summary → bilingual Chinese/English `report.html` + chart SVGs. Supports `--summary` / `--out-dir` since T3. |

## 2. What a clean checkout actually contains

- **Published matrix artifacts** (`results/matrix/summary.json`, `report.html`, chart SVGs) are committed to the repository.
- **Private/intermediate answer artifacts** (real model answer logs, private gold labels, caches from paid runs) are **not** committed.
- So rerunning the "full MIT 6.006 / Yale PSYC 110 matrix" from scratch **still requires** private/local inputs + paid model runs. T3 does not change that, and it **does not change any published number**.

## 3. What T3 added

1. **A committed aggregation/conversion script**, `aggregate_matrix.py`: it aggregates explicit answer/score rows into a summary (it is not tangled up with judging and reading `results/` the way `rejudge.py` is, and it **never** silently reads `results/matrix/summary.json`).
2. **A fixture-level reproducible pipeline**: `benchmark/tests/fixtures/matrix_pipeline/` (self-authored, tiny, not copyrighted) runs aggregation + rendering end to end.
3. **An explicit `report_matrix.py --summary <file> --out-dir <dir>`**: the renderer is no longer forced to render only the committed summary.

### Input/output schema

- **answers.jsonl** (the full item set + each answer attempt): required `course, model, arm, item_id`; optional `answerable` (`bool`/`0`/`1`. It may instead go on the matching score row, which is this repository's `gen.py→judge` path; but **at least** one of the answer or the score must provide it, or the script fails loudly. **If both sides provide it and they disagree**, the script fails loudly for that `(course,model,arm,item_id)` and does not silently favor either side), `status` (`"ok"`/`"infra_error"`, default `ok`), `cost_usd`. Two in-repo row aliases, `id`→`item_id` and `cost`→`cost_usd`, are also accepted.
- **scores.jsonl** (judging): required `course, model, arm, item_id`; optional `correct`, `hallucinated`, `abstained`, `judge_error` (`bool` or `0`/`1`; `judge.py` actually writes integers), `faithfulness` (numeric, must be within `[0,1]`), `answerable`, `scored_by`.
- **summary (output)**: `matrix` (the primary course's `model|arm` cells; this is the block the renderer reads), `course_matrix` (**general**: cells for every course), `cost_per_q` (per-question cost, course → arm), `psyc` (a renderer-compatible block for `--secondary-course`), `models/arms/courses/n_items/total_cost_usd/judge_model`.

### Honest counting rules (aligned with `rejudge.aggregate()`)

- An `infra_error` (rate limit/context error) is **not** a model answer → it is **excluded** from the accuracy denominator but counted in `n_infra_error`. It is **never silently dropped**.
- An answered answerable item with **no matching score** → recorded as `judge_error` and counted as **wrong** (a trustworthy lower bound). A missing score **never** raises accuracy.
- `correct`/`hallucination` are rates over completed answerable items; `faithfulness` is averaged over items that were actually judged; `abstention_oos` is computed over completed out-of-scope items. Failed/errored/missing cells are reported as they are; failures are **not** swallowed in any way that inflates the metrics.

## 4. Fixture commands (runnable on a clean checkout)

```bash
python benchmark/aggregate_matrix.py \
  --answers benchmark/tests/fixtures/matrix_pipeline/answers.jsonl \
  --scores  benchmark/tests/fixtures/matrix_pipeline/scores.jsonl \
  --primary-course courseA --secondary-course courseB \
  --out /tmp/examprep-summary.json

python benchmark/report_matrix.py \
  --summary /tmp/examprep-summary.json \
  --out-dir /tmp/examprep-report
```

## 5. Expected path for a real run (needs private inputs + paid calls; **not run in this PR**)

```text
gen.py (fill in/generate answers, real model, paid)
   → judge.py / rejudge.py (judge/re-judge, optional LLM)
   → rejudge.py --deterministic --scores-out (zero-cost score-row export: the bridge between judging and aggregation)
   → aggregate_matrix.py (aggregate, zero cost)
   → report_matrix.py --summary <summary.json> --out-dir <dir> (render)
```

Explicit commands you can run one at a time (on a machine that **has the real artifacts**; the export, aggregate and render steps themselves cost nothing and do not call an LLM):

```bash
# 1) Zero-cost export of score rows (+ answer rows aligned strictly by (course,model,arm,item_id)).
#    Note: rejudge.py still reads the private/local results artifacts and gold labels. On a clean checkout these files are missing and it raises FileNotFoundError;
#    run this step on a machine with the real artifacts. Deterministic mode calls no LLM. The export writes only to the explicit paths given by
#    --scores-out/--answers-out; rejudge itself still writes its (gitignored) summary_corrected.json/progress files to
#    results/matrix/ as before (existing behavior), but it NEVER touches the published results/matrix/summary.json or report.html.
python benchmark/rejudge.py --deterministic \
  --scores-out  /tmp/scores.jsonl \
  --answers-out /tmp/answers.jsonl

# 2) Aggregate into a summary (pure standard library, zero cost, deterministic)
python benchmark/aggregate_matrix.py \
  --answers /tmp/answers.jsonl --scores /tmp/scores.jsonl \
  --primary-course algo --secondary-course psyc \
  --out /tmp/summary.json

# 3) Render into a CUSTOM directory (always pass --out-dir)
python benchmark/report_matrix.py \
  --summary /tmp/summary.json --out-dir /tmp/report
```

A few points need to be stated plainly:

- **The score-row export is the bridge**: `rejudge.py --scores-out` (**`--answers-out` must be given too**) normalizes each item's score into the fields `aggregate_matrix.py` needs (`answerable` is carried over from the gold labels; `scored_by` keeps the judge's own label, lexical/llm/judge_error/infra_error), and it also carries over **the answer rows' `status` (infra_error) and `cost_usd`**. Without them the aggregator would count infra failures as answerable items and compute the cost as `$0`. **It exports only matrix/psyc cells** (not the `conv_*` convergence rounds, to avoid `(course,model,arm,item_id)` key collisions; a duplicate key **fails loudly** instead of being silently dropped). It is off by default, zero cost, calls no LLM, and the export writes only to explicit paths.
- **`summary_corrected.json` cannot be rendered directly**: by default `rejudge.py` still writes its original `summary_corrected.json` (a nested `algo`/`psyc` structure). That shape is **different** from the top-level `matrix`/`n_items` that `report_matrix.py` reads, so you **cannot** feed it straight to the renderer with `--summary summary_corrected.json`. Go through `--scores-out → aggregate_matrix.py` to get a summary the renderer can read.
- **A custom summary requires `--out-dir`**: rendering a **custom** `--summary` without `--out-dir` (that is, into the default `results/matrix/`) is **refused** (exit code 2) so that it cannot overwrite the published `results/matrix/report.html`. Always point it somewhere else.

## 6. What this PR does not do

- It does **not** rerun the real MIT/PSYC benchmark, and it does **not** change any published result number or chart.
- It does **not** commit private answer artifacts, private gold labels, paid-run artifacts, or any copyrighted course text/page images.
- It does **not** redesign the report's visual style, and it does **not** change the skill's runtime behavior, `scripts/ingest.py`, or the P0A/P0B/P0D material builders.
- It does **not** add dependencies, GitHub Actions, or any network/LLM/API calls.

> Wording standard: **"the pipeline mechanism is reproducible with fixture data"**, not "the full published MIT/PSYC benchmark can now be reproduced from a clean checkout". The latter still needs private/intermediate artifacts and paid runs. The P0A/P0B material builders are **unrelated** to this benchmark aggregation path and should not be confused with it.
