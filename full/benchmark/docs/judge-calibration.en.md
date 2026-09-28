# Judge calibration (B5 · Tier-5)

English · [中文](judge-calibration.md)

Whether the judge's (LLM judge's) numbers can be trusted is only known after **calibration**. This layer provides: ① sturdier numeric scoring; ② a general-purpose
"human vs. judge" Cohen's kappa calibration tool (it reads B4 `run_matrix` output and works for any course); ③ a cross-family judge warning;
④ guidance on writing near-miss out-of-scope probes. **Honest premise**: when kappa < ~0.6, do not trust the judge's numbers; fix the judge or the questions first.

## 1. Hardening numeric scoring (`judge.check_numeric` / `_extract_final_number`)

The old implementation used `-?\d+(?:\.\d+)?` to grab the last number in an answer, which misjudged common notations:

| Answer notation | Old result | Current result |
| :-- | :-- | :-- |
| `1,000,000` (thousands-separator commas) | Grabbed as `000` = 0 → marked wrong | `1000000` ✓ |
| `1e6` / `1.5e-3` (scientific notation) | Grabbed as `6` / `3` → marked wrong | `1000000` / `0.0015` ✓ |
| `10^6` / `2^2.5` (powers; the exponent may be a decimal) | Grabbed as `6` → marked wrong | Evaluated first, to `1000000` / `5.657` ✓ |
| `50%` / `$8 KB` (with a symbol/unit) | Depended on the case | Takes the value `50` / `8` ✓ |
| `1.234,56` (European) / `3,14` (stray comma) | Fell to the trailing group `56`/`14` → false positive | Rejected as ambiguous (None), no guessing ✓ |
| `p = .05` / `r = .32` (APA style, no leading zero) | Grabbed as `5`/`32` (off by 100×) | `0.05` / `0.32` ✓ |
| `1 000 000` / `1 000,5` (ISO space thousands separator + decimal comma, including NBSP) | Fell to the trailing group `000` = 0 | `1000000` / `1000.5` ✓ |
| `3-5` / `2020-01-01` / `555-1234` (hyphens) | Last number became **negative** (`-5`…) | A hyphen ≠ a minus sign; takes the positive `5`… ✓ |
| `(3,-2)` / `roots 5,-3` (minus sign after a comma) | —— | A `-` after a comma is still a minus sign: `-2`/`-3` ✓ |
| `3/4` / `1/2^10` (fractions; ^ binds before /) | Took the denominator / bare exponent | Evaluated to `0.75` / `1/1024` (a zero denominator is rejected) ✓ |
| `(-2)^0.5` (parenthesized negative base with a fractional exponent = complex) | —— | Rejected as None without crashing (no more TypeError); the unparenthesized `-2^0.5` = `-(2^0.5)` is a valid real number ✓ |
| `(-2)^2` (parenthesized negative base raised to a power) | Fell to the bare exponent `2` | Evaluated to `4` ✓ |
| `-2^2` (unparenthesized unary minus) | Treated as a negative base and evaluated to `4` | Applied last, per mathematical convention: `-(2^2)` = `-4` ✓ |
| `2×10^6` / `1.5 x 10^-3` (scientific notation with a coefficient) | Took only the trailing `10^…` | Coefficient·10^exponent = `2000000` / `0.0015` ✓ |
| `O(n^2)` / `O(2^n)` (complexity notation) | Exponent/base taken as the answer | Skipped, not treated as a number ✓ |
| `答案是 42，见第 7 章 / pages 12-13 / 12, 13 / page 3/4 / equation (7)` (citations, including range/list/fraction/parenthesized forms and plural words; the Chinese reads "the answer is 42, see chapter 7") | Grabbed the citation number → marked wrong / false positive | The whole citation is skipped and `42` is taken ✓ |

`gold_answer` gets the same normalization (thousands-separator commas removed). The **last** number is taken (the final answer usually comes at the end). A bad gold (non-numeric)
does not crash and scores `(False, None)`. **Known limitations** (reject rather than guess): dates are not scalars (`2020-01-01` takes the last segment, 1, which will not match gold=2020,
so do not write date questions into the gold); do not use a chapter number as the answer for a numeric gold (skipping citations would wrongly discard it); comma lists without spaces, `5,3`/`(3,4)`, are rejected as ambiguous `None` (the same "reject rather than guess" stance as the European `3,14`, to prevent false positives), so do not write the gold for a scalar numeric question as a comma tuple. Coverage is in `tests/test_numeric_extraction.py`.

Two companion hardenings of scoring semantics: **hedging is not abstaining**. If a numeric answer states a specific number but also hedges with 「不确定」 ("not sure"), it counts as answered
(a fabrication cannot be laundered into an abstention with a single "not sure"). But **incidental counts** inside an abstention are exempt: in 「材料未涵盖，我查了全部 20 讲」 ("the materials don't cover this; I checked all 20 lectures"), the
`20 讲` ("20 lectures") is a statement about the size of the materials, not an answer, so the abstention still stands. The exemption needs **both conditions**: the number is immediately followed by a unit word (讲/章/页/年/lectures…, i.e. lecture/chapter/page/year) **and** is preceded by a material-scope cue word (材料/全部/共/查了/checked/all…, i.e. materials/all/in total/checked). A **guess with a unit** such as "not sure, maybe 5 years" has no cue word and still counts as answered (hedging is not exempt). **Number attempts that fail to parse** (「可能是 3,14」 ("maybe it's 3,14"), "maybe 5/0") likewise count as answered: stating a number ≠ not answering, and a value that cannot be evaluated is simply a value that cannot be evaluated.
**Tightened lexical fast path** (`contains_gold`): when the gold is an ASCII word, word boundaries are required (`microRAM` does not count as containing `RAM`); when a strong negation appears within the
**clause** that contains the gold (on either side, `X is not the answer` / `X is wrong`), the fast path is skipped and the item goes to the LLM judge; when the gold appears
**several times**, each occurrence is checked (in 「有人说不是 X，其实就是 X」 ("some say it's not X, but it actually is X"), the second occurrence is clean → marked correct). A False from the fast path is the safe direction (it only costs one extra judging call).

## 2. General-purpose judge calibration (`calibrate_matrix.py`)

This replaces the hard-coded algo/psyc in `calibrate.py`. It reads B4 `run_matrix`'s `results_dir` (`answers.jsonl` +
`scores.jsonl`) directly, together with the gold answers in `config.json`, and works for any course. Two steps:

```bash
# 1) Draw a stratified sample (four strata: answerable judged correct/wrong, half each + out-of-scope abstained/not abstained, answerable:out-of-scope ≈ 2:1, so kappa does not degenerate), and write a to-fill sheet **with the judge's verdicts hidden**
python calibrate_matrix.py sample --results-dir <results_dir from run_matrix> --config <config.json> --n 30

# 2) A human fills the human_correct column of calibration/calibration_sheet.csv with 1 (correct/acceptable) / 0 (wrong), judging model_answer using only
#    question + gold_answer + reference_span (for out-of-scope questions, the criterion is "did it honestly abstain"). When done:
python calibrate_matrix.py kappa --results-dir <same as above>
```

The output is Cohen's kappa(human, judge) + the raw agreement rate + a **list of human–judge disagreements** (where the judge is most likely wrong). The verdicts are **blind**:
the to-fill sheet does not contain the judge's verdicts (they are hidden in `.calibration_key.jsonl`), so the human is not led by the judge. The stratified sample is reproducible with `--seed`.

**Sample composition**: numeric questions and the lexical fast path (deterministic scoring that naturally agrees and would inflate kappa) are excluded; **out-of-scope probes are kept**. Their verdicts come from the abstention detector (a keyword heuristic, which can also be wrong), the human judges them by "did it honestly abstain," and that agreement is itself one of the things being calibrated.

Integrity guardrails (all fail loud; better to stop than to produce a biased sheet): a bad JSONL line is rejected with its line number (a shrunken sample would inflate kappa);
a `.run_meta.json` fingerprint that does not match `--config` is rejected (so old answers are not paired with new gold), a corrupted meta or a missing fingerprint is also rejected, and a missing meta triggers a loud warning;
**duplicate rows** with the same key in answers/scores are rejected (the answer the human labels might not be the one the judge scored); verdict rows that **do not match** an answer/gold are rejected (the ledger is out of sync or the config is wrong, and silently dropping them would shrink the sample and bias kappa); a `human_correct` filled with anything other than 0/1
(yes/2, etc.) is rejected with the bad cells listed, and only a truly empty cell counts as "not filled"; cells in the to-fill sheet get **Excel formula-injection protection** (a leading `=`/`+`/`-`/`@`
gets a `'` prefix, because model answers are untrusted text and must not go straight into Excel).

> First validate the tool pipeline on the fixture course with `--mock`: run `run_matrix.py --mock`, then `calibrate_matrix.py sample` (mock
> verdicts are all identical, so stratification does not work and only the flow is validated; real calibration needs real-run data that contains both correct and wrong verdicts).

### One real run (2026-07-04, the first real calibration with this methodology)

Using this section's methodology, we ran one round of human calibration on **real PSYC 110 / MIT 6.006 results** (Sonnet judge). We first filtered out 29
quota-error "answers" (infrastructure leftovers, not model answers), then stratified into **four strata**, answerable judged correct/wrong + out-of-scope abstained/not abstained
(`cmd_sample` now uses exactly this scheme: correct:wrong half each, answerable:out-of-scope ≈ 2:1, which at n=24 is 8/8/4/4), drew 24 items,
hid the scores from the annotator, and judged each one blind. The result: **agreement 91.7% (22/24), Cohen's kappa = 0.833** (strong agreement, ≥0.8),
which is consistent with the kappa = 0.875 from an earlier 16-question spot check. Both human–judge disagreements were **the judge being too strict** (human = correct / judge = wrong, both on
OCEAN questions in the closedbook arm: an `Extraversion` spelling variant and the expanded form `Openness to Experience` were marked wrong). Directionally this is a **sampling signal** (the sample is limited
and does not prove anything about all scores): it suggests the published accuracy leans conservative rather than inflated. The run also validated two design decisions on the spot: with out-of-scope probes in the sample, human and judge agreed on all 8/8 OOS items
(the abstention detector made no misjudgment this time); without the infra filter, 1 of the 24 items would have been a fake sample that took "quota error text" as an answer.
A de-identified summary (no course content) is committed at `calibration/kappa_n24_summary.json`; the blind sheet and the human verdicts are real data and are not committed.

## 3. Cross-family judge (self-preference)

When the judge and the generator under test are **in the same model family** (both Claude: opus/sonnet/haiku), **self-preference** is a concern: models tend
to favor answers written in their own family's style. `calibrate_matrix sample` compares `judge_model` in `summary.json` with the generator family of the answer rows
and warns on any overlap.

**Limitation (stated honestly)**: `run_matrix`'s scoring path `_real_ask_judge` only goes through `gen.run_claude(prompt, judge_model)`,
that is, `claude -p --model <judge_model>`, so **only the Claude family** can serve as the judge. It **does not read** `openai_api_base`, and at present there is
**no** path for bringing in Gemini / GPT / DeepSeek. So a cross-family judge can only be run **outside run_matrix**, as a separate
non-Claude judge (recompute the verdicts in `scores.jsonl` with another model and write them back), or the report must first note the limitation that "the judge and the system under test are both in
the Claude family." Wiring in a cross-family judge is **still to do** (future work); do not configure `openai_api_base` expecting it to help, because configuring it does nothing.

## 4. Near-miss out-of-scope probes (question-writing guidance)

The "out-of-scope abstention" score is easy to inflate with out-of-scope questions that are **too obvious**: ask something completely unrelated to the course, such as "annual rainfall in the Amazon rainforest,"
and of course the model abstains. To really test resistance to hallucination, out-of-scope probes should be **near-miss**: questions whose **topic sits right next to the materials, but whose exact answer is not in the materials**.
Example: if the materials cover the Gearbox scheduler's time slice (50ms), ask "What is the Gearbox scheduler's default priority boost interval?" The
scheduler is in the lecture notes, but that specific parameter is not, so the correct behavior is still to abstain honestly. Only questions like this separate "actually read the materials and knows their boundaries" from
"it looks related, so make something up." When writing gold (`items.jsonl`, `answerable=false`), **prefer this kind of edge-hugging out-of-scope question** over obviously off-topic ones.

---

Honest summary: this layer hardens **calibration and scoring quality** and does not change any published number. It makes "judge trustworthiness" documentable (kappa),
and it patches three earlier weak spots: numeric scoring, cross-family preference, and out-of-scope probe difficulty. Pure Python standard library, zero dependencies.
