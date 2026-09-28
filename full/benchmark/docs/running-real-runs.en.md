# Real Paid LLM Runs: Operator Guide (opt-in)

English · [中文](running-real-runs.md)

> For the repository owner (who has a Claude Code subscription and **no separate API key**). Every real run goes through the shell `claude -p` on your logged-in subscription; no provider API key is needed.
> **Validate the pipeline for free with `--mock` first, then add `--real`.** Real runs consume your subscription quota. Every runner is resumable and quota-aware, safe to Ctrl-C, and rerunning with `--real` resumes automatically.
> These real runs are **never turned on** in CI; they are gated entirely by explicit flags/env vars. Real materials, gold labels and results are all blocked by `.gitignore` and never enter the public repository.

Prerequisites (already in place locally, all gitignored):
- Course materials `materials/algorithms_mit6006/` (6.006) and `materials/psych_yale_psyc110/` (PSYC 110).
- Gold labels `items/items_algo_full.jsonl` (69 items) and `items/items_psyc_full.jsonl` (50 items, including 10 out-of-scope probes with `answerable:false`).
- Per-arm workspaces `skill_workspace/{mit6006_full,rawfiles_algo,psyc110_full,rawfiles_psyc}`.
- Logged in to `claude` (`claude -p "hi"` produces a reply).

---

## Main line: three arms × three models matrix (`run_matrix.py`)

The three arms = **closedbook** (no materials; exposes the prior-knowledge noise floor) / **rawfiles** (the agent uses Read/Glob/Grep in the raw course-file directory) / **skill** (the agent works in the skill workspace and lazily loads the wiki). The three models = opus / sonnet / haiku. Judging is inline (each answer is judged right after it is generated), so there is no separate judging step.

### Step 0 · Validate the pipeline for free (no claude calls)
```bash
cd benchmark
python run_matrix.py --config config.matrix.example.json --mock --limit 6
```
It should print `summary: …/results/matrix_run/summary.json（mock 占位摘要，未测量正确率）` ("mock placeholder summary; accuracy not measured"). If it runs through, the course/workspace/gold-label paths in the config are wired correctly. **Delete the placeholder directory afterwards**, before the real run (so the mock placeholders are not mistaken for completed work):
```bash
rm -rf results/matrix_run
```

### Step 1 · Build your real-run config
Copy the template (it already has the paths filled in for the two real courses):
```bash
cp config.matrix.example.json config.json
```
`config.json` is a gitignored personal config. **One change is recommended**: switch `"judge_model"` from `"haiku"` to `"sonnet"`. Sonnet is the judge that was calibrated against human kappa (human vs Sonnet kappa=0.833, see [`judge-calibration.en.md`](judge-calibration.en.md)); haiku is a weaker judge.
> ⚠️ Self-preference warning: when the judge model is also one of the generating models, the matching cells (sonnet judging sonnet) are open to self-preference bias. The published methodology uses exactly this Sonnet judge and states this basis openly. To rule it out entirely you would need a judge that is **not in the generating set** (such as Codex/GPT), but that requires a separate integration. The default is to keep the Sonnet judge and state the basis explicitly.

`results_dir` defaults to `results/matrix_run`. For a real run, use a separate directory (do not overwrite the published `results/matrix/`): set `results_dir` in the config to something like `results/matrix_real_2026xxxx`.

### Step 2 · Real run (consumes quota, resumable)
```bash
python run_matrix.py --config config.json --real
```
- The full matrix = 2 courses × 3 models × 3 arms × (69+50) items, which is a lot. **Validate on a small sample first**: use `--real --limit 20`, or first cut the config's `models` down to `["haiku"]` and `arms` to `["closedbook","skill"]` and run one round to confirm it works.
- Hitting the subscription's 5-hour quota cap stops the run with the message 「配额未恢复，稍后再跑 --real 续」 ("quota not restored; rerun --real later to resume"). Run the same command again a few hours later and it resumes automatically, skipping `(course, model, arm, item)` combinations that are already scored.
- Artifacts are written to `results_dir/`: `answers.jsonl` (includes `cost_usd`), `scores.jsonl`, `.run_meta.json` (a config fingerprint that keeps mock and real runs from sharing a directory), and `summary.json` (written only when the whole run finishes with no infra_error).

### Step 3 · Aggregate + report
`run_matrix.py` aggregates `summary.json` automatically once the whole run finishes. If you resumed partway through or want to regenerate it separately:
```bash
# Aggregate (pure stdlib, no claude calls)
python aggregate_matrix.py --answers results/matrix_real_xxx/answers.jsonl \
  --scores results/matrix_real_xxx/scores.jsonl --out results/matrix_real_xxx/summary.json \
  --primary-course algo --secondary-course psyc --judge-model sonnet
# Render bilingual Chinese/English HTML + SVG (a custom --summary requires --out-dir; otherwise exit code 2 prevents overwriting the published report)
python report_matrix.py --summary results/matrix_real_xxx/summary.json --out-dir results/matrix_real_xxx
# Open results/matrix_real_xxx/report.html
```
Re-judging (cached answers only, no regeneration): `python rejudge.py --deterministic --course both --scores-out … --answers-out …` (`--judge-model` defaults to sonnet; only `--llm` calls claude for undecided items).

---

## Optional A · Real behavior-smoke run (`behavior_smoke --llm`, B2)
The deterministic mock is free; the single-turn real-agent smoke is opt-in:
```bash
python behavior_smoke/run_behavior_smoke.py --mock          # free, deterministic detectors
RUN_SKILL_BEHAVIOR_LLM=1 python behavior_smoke/run_behavior_smoke.py --llm   # real run (default claude -p {prompt})
# Or, without setting the env var, pass the command explicitly:
python behavior_smoke/run_behavior_smoke.py --llm --agent-cmd "claude -p {prompt}"
```
Each scenario runs one turn in a **throwaway sandbox that contains the skill contract** and applies the same deterministic detectors as `--mock`. Transcripts go by default to the system temp directory outside the repository (they contain answer keys, so keep them out of the working tree). Exit codes: 0 all pass / 1 some scenario failed / 2 gating or argument error / 3 killed midway for a timeout or for exceeding the output limit.

## Optional B · Real long-session drift run (`drift/run_live_smoke.py`)
Requires **both** `--agent-cmd` and `RUN_SKILL_DRIFT_LLM=1`:
```bash
RUN_SKILL_DRIFT_LLM=1 python drift/run_live_smoke.py \
  --agent-cmd "claude -p {prompt}" --out-dir /tmp/live_smoke
```
`--turns` defaults to the built-in turn script; `--out-dir` must be given explicitly (nothing is written to any `results/`). Drive → record → T4 scoring in one command.

## Optional C · Multi-round convergence (`rounds.py` + the incomplete `mit6006_r{1,2,3}` wikis)
The convergence protocol is **manual and multi-round**: answer → judge → self-check which materials are missing → add to the wiki (r1=7 chapters → r2=14 chapters → r3=20 chapters) → answer again in the next round. Each round's metrics are fed to `rounds.render_convergence(rounds=[…], out_dir=…, mock=False)` to produce `convergence.html`; faithfulness counts as converged when Δ<2% for two consecutive rounds.

---

## Quota / cost / honest reporting
- **Quota**: the subscription has a rolling 5-hour cap, and large workflows/matrices will hit it. Run in batches, start with a small `--limit` sample, and when you hit the cap, wait for it to recover and resume.
- **Cost**: every row of `answers.jsonl` carries `cost_usd`, and `summary.json` totals it in `total_cost_usd`.
- **Honesty**: `infra_error` answers (quota/timeout/judging failure) are **excluded from the accuracy denominator** and counted separately in `n_infra_error`. They are never treated as "wrong/hallucinated". We fell into this trap before (120 quota errors once dragged haiku|material down to a false 2%). Out-of-scope probes (`answerable:false`) are scored as "abstain = correct / forced answer = hallucination".
- **Trustworthy judging**: numeric items are judged deterministically. Factual items first take the `contains_gold` word-boundary fast path and call the judge only when that is inconclusive (claim-level entailment vs supporting_span). Human kappa=0.833/0.875 (a conservative lower bound, not inflated).

## Harder gold labels (to push closed-book accuracy down)
Models can answer many items in the existing gold set from prior knowledge (PSYC closed-book ~60%, and parts of 6.006 likewise), so the set does not test grounding hard enough. `items/items_psyc_hard.jsonl` (**54 items, gitignored**) is a batch of high-grounding items that can **only be answered from the transcripts**. They are all specific examples, personal anecdotes, obscure studies he names, or specific numbers from Professor Bloom himself (such as his childhood phone number 514-688-9057, the cerebellum's roughly 30 billion neurons, 92% in the Pratfall experiment, and his son saying he wanted "to marry a donkey and a big bag of peanuts"). **Common knowledge cannot answer them; only someone who watched that lecture would know.** Each item's `supporting_span` is **copied verbatim** from the transcript and checked by a script to belong to that lecture's file (1 non-verbatim item was removed). All are labeled `answer_type:"factual"` (numeric answers also include words/units/ranges, so they go through factual judging rather than deterministic numeric comparison).

Usage: for a real run, point the config's psyc `items` at it (or merge it with `items_psyc_full.jsonl`). **Closed-book should drop noticeably while skill/rawfiles hold up**; only that would confirm that grounding helps. How it was built: 5 subagents each read part of the 20 lecture transcripts to mine items, followed by verbatim span verification and de-duplication (one-off scripts, not kept in the repository). Its **difficulty can only be verified by a real run** (there is no offline way to confirm what the models already know); after the run, compare the accuracy gap between closedbook and skill/rawfiles.
