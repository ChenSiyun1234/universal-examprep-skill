# calibration/ — Judge Reliability Calibration

English · [中文](README.md)

An LLM judge can be wrong (this round caught a bug that misjudged correct answers as hallucinations), so **before trusting any judge numbers**,
have a human (you) blind-label a small batch and measure human-vs-judge agreement. Only when agreement is high enough do the report's correctness/hallucination rates hold up.

## Completed calibration results (two independent rounds that corroborate each other)

- **16-question spot check**: Cohen's kappa = **0.875**, agreement 93.8% (early; see the README and the report).
- **24-question four-stratum blind test** (four strata: answerable and judged correct / judged wrong + out-of-scope and abstained / did not abstain; the judge's verdicts hidden from the human): agreement **91.7%**,
  Cohen's kappa = **0.833**, with 8/8 agreement on the out-of-scope strata. The de-identified summary is in [`kappa_n24_summary.json`](kappa_n24_summary.json)
  (the real data, such as the blind sheet, answer key and human labels, is not committed; this directory is gitignored, and the summary is the only committed file).
  The disagreements in both rounds were **all cases of the judge being too strict** (marking correct answers wrong) → the report's numbers are more likely conservative than inflated.

## Two calibration tools

- **`calibrate_matrix.py` (current; general three-arm matrix)**: draws a stratified sample from real matrix results, hides the verdicts, and computes kappa;
  the 24-question calibration above was produced with it. It has config fingerprint checks + self-preference warnings + a degenerate-kappa gate.
- **`calibrate.py` (the older two-arm scaffold; example below)**: the same workflow for the two-arm baseline/skill setup.

## Using `calibrate.py` (two-arm scaffold)

```bash
cd benchmark

# 1) Sample: stratified (half judged correct, half judged wrong, to avoid a degenerate kappa); generates a sheet to fill in, with the judge's verdicts hidden
python calibrate.py sample --n 24 --course both --seed 7

# 2) Open calibration/calibration_sheet.csv (Excel/editor) and fill the human_correct column with 1 (correct) / 0 (wrong)
#    Decide whether model_answer is correct using only question + gold_answer + reference_span; for out-of-scope questions, the criterion is "did it honestly abstain".

# 3) Compute kappa + list the human/judge disagreements (where the judge is most likely wrong)
python calibrate.py kappa
```

- `calibration_sheet.csv` (the one you fill in) and `.calibration_key.jsonl` (the hidden judge verdicts) are both **gitignored**; they contain answer details and are not committed.
- Data source: the authoritative re-judging cache `results/matrix/judge_cache.jsonl` (run `rejudge.py --llm` first).

## Decision rules

- Treat **kappa ≥ ~0.6** as acceptable (judge and human broadly agree); only then trust the judge-based metrics in the report;
- If it is low, improve the judge prompt/questions, or use a model from a different family as the judge (for example Codex/GPT later on).
- When the label distribution is very skewed (almost everything in one class), kappa comes out low; look at Gwet's AC2 as well (more stable). The underlying algorithm is `cohen_kappa` in [`../stats.py`](../stats.py).
