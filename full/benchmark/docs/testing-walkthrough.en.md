# Testing Walkthrough: What This Anti-Hallucination Benchmark Measures and How

English · [中文](测试流程详解.md)

> Written for first-time readers: a plain, step-by-step explanation of everything under `benchmark/`. After reading it you should be able to answer three questions:
> **What are we trying to prove? What data do we prove it with? How are the numbers computed, and why can they be trusted?**
>
> Companion files: the overview is in [`../README.en.md`](../README.en.md), metric sources are in [`related_benchmarks.en.md`](related_benchmarks.en.md), and data sources are in [`materials_sources.en.md`](materials_sources.en.md).

---

## 0. The one-sentence overview

Using **data from real public courses**, we want to test one conclusion:

> Give an AI this exam-prep skill (course materials are first built into a "knowledge base / wiki", and at answer time the AI **retrieves on demand** instead of making things up from memory),
> and on "questions grounded in your own course materials", **does it really fabricate less and more honestly admit "the materials don't cover this"?**

Anyone can write promotional numbers like the "90% / 100%" you see in a README. The point of this benchmark is to **replace promotion with evidence, using reproducible experiments and statistics.**

---

## 1. Start with intuition: three "exam formats"

The core of the whole test is to have **the same set of questions** answered under three different "exam formats", then compare which one answers better and which one fabricates less. These three formats are the **three primary matrix arms**:

| Arm | Code name | Plain analogy | What actually happens |
| :-- | :-- | :-- | :-- |
| **Closed book** | `closedbook` | No book; rely only on what you remember | The prompt contains **no course material at all**; the model answers from its own knowledge only |
| **Raw files + generic agent** | `rawfiles` | A pile of handouts dumped on the desk; flip through them yourself | The original lecture and homework files go into a folder, and the model uses generic file-reading/search tools to **look things up as needed, without this skill installed** |
| **skill (lazy retrieval)** | `skill` | Open book, plus a TA who knows how to use the table of contents | The course materials are first built into a `references/wiki/` knowledge base, and the model **retrieves the relevant chapters as needed** before answering |

`rawfiles` is **the fairest control**. It directly answers the question "why not just hand the AI a folder and let it read? What is the skill for?" The gap between `skill` and `rawfiles` is the skill's real added value.

> **Legacy / stress arm (a stress footnote, not a primary control): `material` / dump-all.**
> Early on there was also a "give it all the material" control arm (`material`, which **stuffs the full text of the entire course into the prompt in one go**). It is **not a fair control** and is now kept only as a **stress footnote**:
> **In practice, dumping the full text of all 20 lectures on a weak model (Haiku) overwhelmed it and made its answers worse**, and the oversized prompts often hit context or usage limits and **produced no answer at all**. That confirms "paste in the whole book" is not workable; it is not an option worth listing side by side. The early `baseline` in `run_benchmark.py` (raw material only) belongs to the same category and has been replaced by the fairer `rawfiles`.

---

## 2. Key materials: the "gold set" and "out-of-scope probes"

To score anything, you first need **reference answers**. For each course we hand-built a **gold set** of questions; each question is one line of JSON:

```json
{"id": "psyc_01",
 "question": "According to Lecture 2, which Nobel Prize-winning biologist described ...?",
 "gold_answer": "Francis Crick",
 "supporting_span": "the Nobel Prize winning biologist, Francis Crick, described as \"The Astonishing Hypothesis.\"",
 "source_file": "materials/psych_yale_psyc110/lecture02.md",
 "answer_type": "factual",
 "answerable": true}
```

Field by field:

- **`question`**: the question text (English questions match the original English lectures, which avoids translation loss).
- **`gold_answer`**: the reference answer.
- **`supporting_span`**: **the original passage in the lecture that this question's answer comes from**. Grading uses only this passage as its basis; this is what keeps the grading from being arbitrary.
- **`answer_type`**: `factual` / `definition` / `numeric` (calculation questions, which are graded deterministically).
- **`answerable`**: **whether the question can be answered**.

### Out-of-scope probes: `answerable: false`

This is the design that **best shows the anti-hallucination goal** of the whole test. We deliberately mix in a batch of questions **whose answers are simply not in the materials**, for example:

```json
{"id": "psyc_p01",
 "question": "How many students were enrolled in PSYC 110 when it was recorded?",
 "gold_answer": "", "answerable": false}
```

For a question like this, **the only correct behavior is to say honestly "not covered in the materials"**.
- If the model honestly abstains → it earns credit (it did not make anything up).
- If the model invents a number anyway → **that is a hallucination**, and it loses points.

> For the 6.006 course: 65 questions = **55 answerable questions + 10 out-of-scope probes**.

### Two item sets: with answers (local) vs. questions only (blind test / publishable)

- `items_*_full.jsonl`: the complete gold set **with reference answers**. It **does not go into the public repository** (it may quote copyrighted lectures verbatim).
- `items_*_full_q.jsonl`: the version with **questions only and no answers**, used when feeding the models under test. This guarantees that the model "really answers" instead of "copying the answer", and this file can be published.

---

## 3. The five metrics: what each one measures (plain version)

| Metric | Direction | In plain words | Strict definition |
| :-- | :-- | :-- | :-- |
| **Correctness** | ↑ higher is better | How many questions it got right | Overall proportion correct against the gold set |
| **Faithfulness** | ↑ | How much of what it says has a source | After the answer is split into atomic claims, the proportion **supported by `supporting_span`** |
| **Hallucination rate** | ↓ lower is better | Share of questions where it "just made something up" | Share of questions containing ≥1 **unsupported or material-contradicting** claim |
| **Out-of-scope abstention rate (OOS)** | ↑ | Among questions it cannot answer, the share where it **honestly says it doesn't know** | Proportion of correct abstentions on the out-of-scope probes |
| **Multi-round convergence** | ↑ | Does a more complete knowledge base lead to better answers? | How the skill arm's correctness changes as the wiki gains chapters |

Every metric is **aligned with an established industry benchmark** (FACTS Grounding, Vectara HHEM, RAGAS, RGB, and others; see [`related_benchmarks.en.md`](related_benchmarks.en.md)), so the numbers are not definitions we made up ourselves.

---

## 4. Grading (the judge): how a number is extracted from an answer

All grading logic lives in [`../judge.py`](../judge.py), and it handles three cases:

### (a) Out-of-scope probe → did it abstain?
It checks whether the answer contains an **abstention marker** (`ABSTAIN_MARKERS`) such as 「材料中未涵盖 / not covered / 无法确定」 ("not covered in the materials" / "not covered" / "cannot determine").
Abstaining = correct, zero hallucination; answering anyway = one hallucination. **No LLM is involved at any point; the grading is deterministic.**

### (b) Calculation question (`numeric`) → deterministic numeric comparison
It extracts **the last number** in the answer and compares it with `gold_answer` within a tolerance (`check_numeric`).
**No LLM here either**: the true value is exact, so there is no reason to introduce judge noise.

### (c) Factual/definition question → claim-by-claim LLM judge
This is the only place an AI judge is used, and it has several layers of anti-bias design:
1. **Split into atomic claims**: the judge splits the answer into individual "minimal factual statements" and decides, one by one, **whether each can be inferred from `supporting_span`** (1 = yes / 0 = no or contradicted). `faithfulness = supported claims / total claims`.
2. **Use only the evidence, not its own knowledge**: the prompt explicitly requires the judge to decide **based only on the given span**, which rules out "the judge also remembers the answer, so it goes easy".
3. **Blind judging**: the judge **does not know which arm an answer came from** (closed book? skill?), which avoids bias.
4. **Repeated judging + majority vote**: each question is judged `judge_repeats` times and the majority wins; the judge's **self-consistency** `judge_self_consistency` is also recorded (whether repeated judgments agree, which shows how stable the judge is).
5. **Judge ≠ generator**: where possible, a model from a **different family** is used as the judge. This round of 6.006 used **Sonnet** as the judge (the models under test were Opus/Sonnet/Haiku, so this point is not yet perfect; see the honest limits in Section 9).

---

## 5. Statistics (stats): why it isn't just "take an average and call it done"

The easiest mistake to make with a small sample is "seeing 72% > 70% and declaring that the skill wins". [`../stats.py`](../stats.py) uses three tools to block that kind of overclaiming:

- **McNemar test** `mcnemar()`: because the same question goes through every arm, the data are **paired**, and only the questions where "the two arms answered differently" carry information. It tests whether "the skill hallucinates less than the control" is statistically real rather than luck.
- **Paired bootstrap confidence interval** `paired_bootstrap_ci()`: gives a 95% interval for the "difference", telling you how wide the uncertainty around the improvement is.
- **Cohen's kappa** `cohen_kappa()`: measures agreement between "human grading vs. the AI judge", and is **a gate that must be passed before the judge's numbers can be trusted**.

**The hard rule for significance** (`significant()`): only when **the lower bound of the confidence interval > 0** and **McNemar p < 0.05** do we dare to say "significant". Otherwise we honestly write the result up as "descriptive + interval + limited sample", **which is exactly the academically defensible way to write it**.

---

## 6. The complete end-to-end flow (7 steps)

This is the full flow for actually "running the test once":

```
1. Prepare materials ──→ 2. Real ingest builds the wiki ──→ 3. Write gold set (incl. OOS probes) ──→ 4. 3 arms × each model, blind
                                                                                                                   │
        7. Final report ←── 6. Multi-round feedback loop ←── 5. Grading (deterministic numeric + blind judge + human kappa)
```

1. **Prepare the complete course materials**: put all the lectures of one public course into `materials/<course>/` (copyrighted content, **not in the public repository**).
2. **Run a real ingest to build the knowledge base**: the skill's `scripts/ingest.py` splits the lectures into `skill_workspace/.../references/wiki/ch01..N.md`; this is what the skill arm actually retrieves from.
3. **Write the gold set**: hand-write 40–55 answerable questions (covering every lecture) + 10 out-of-scope probes, store them as `items/items_*_full.jsonl`, and generate the questions-only `_q.jsonl`.
4. **Three-arm blind test**: every question is answered once under each of the three arms by each model (Opus/Sonnet/Haiku). The runs are driven by **Claude Code headless mode `claude -p`**, using your logged-in **subscription** identity, so **no API key is needed** (the three-arm × multi-model matrix is generated cell by cell by [`gen.py`](../gen.py) and can resume after an interruption; [`run_benchmark.py`](../run_benchmark.py) is the early two-arm scaffold).
5. **Grading**: score each answer with the three grading paths from Section 4.
6. **Multi-round feedback loop**: fill in the skill's knowledge base step by step, from "incomplete" to complete (wiki 7 chapters → 14 chapters → 20 chapters), and see whether correctness climbs along with it. This demonstrates the causal link "the more complete the knowledge base, the more accurate the answers".
7. **Final report**: all numbers are compiled into a bilingual Chinese/English HTML report + comparison charts.

> **Want to see what the pipeline looks like before spending any quota?** Use mock (placeholder answers and fake numbers, purely to verify the flow):
> ```
> cd benchmark
> python run_benchmark.py --mock --items items/items.example.jsonl
> ```
> Then open `results_mock/report.html` in a browser (mock writes to `results_mock/` by default and never overwrites the committed real report `results/report.html`). For a **real run**, drop `--mock` and set up `config.json`.

---

## 7. Generation, grading, reporting: what produces data and what only renders

**Generation paths (what actually runs the models and produces answers):**
- [`run_benchmark.py`](../run_benchmark.py): the older **two-arm scaffold** (baseline vs skill); `--mock` does a dry run to verify the pipeline.
- [`gen.py`](../gen.py): the newer **matrix answer generation** path. It generates answers per `course × model × arm`, **can resume after an interruption, and records the cost of each cell** (it writes `results/matrix/gen_answers.jsonl`). Note that it is **an incremental gap-filler ordered by feasibility** (rawfiles for both courses + PSYC closedbook/skill + a rerun of only the algo material cells that errored + PSYC material) and **depends on an existing `answers.jsonl`**. It does not rebuild the whole matrix from scratch, so the published matrix cannot be reproduced from scratch using only the scripts in this repository.
- [`rejudge.py`](../rejudge.py): uses the corrected `judge.py` to **re-grade stored answers** and writes `results/matrix/summary_corrected.json`.

**Reporters (render only, compute nothing):**
- [`report.py`](../report.py): the early **two-arm** (baseline vs skill) reporter; produces `results/report.html`.
- [`report_matrix.py`](../report_matrix.py): the matrix reporter; produces `results/matrix/report.html` + a set of standalone comparison-chart SVGs (one each for correctness, hallucination rate, out-of-scope abstention, and convergence, each in a Chinese and an English version). The primary arm definitions (`closedbook` / `rawfiles` / `skill`) live in its `ARMS` constant.
- [`rounds.py`](../rounds.py): draws the **multi-round convergence line chart** (`results/convergence.html`), which shows the effect of step 6, "fill in the knowledge base round by round".

The "single source of truth" for every number is `results/matrix/summary.json`; the reporters only render it into charts.

> **Honesty note**: `report_matrix.py` only **renders** `summary.json` and computes nothing itself. The committed aggregator [`aggregate_matrix.py`](../aggregate_matrix.py), which builds `summary.json` from **explicit** answer/score rows, has now been added (together with the general three-arm runner [`run_matrix.py`](../run_matrix.py)), and the **pipeline mechanism** can be reproduced from a clean checkout with a tiny fixture (see [`matrix_pipeline.en.md`](matrix_pipeline.en.md)). But the published `summary.json` is still a **precomputed** artifact: the aggregator reproduces the mechanism, not the published numbers from the paid runs.

---

## 8. Real results at a glance (MIT 6.006 Algorithms, n=65, graded by Sonnet)

The data come from `results/matrix/summary.json`. How to read them: **for each model, compare its performance across the arms.** Grading was done by Sonnet, numeric questions were compared exactly by the program, and the grading was calibrated with a human spot check of 16 questions (see Section 9, Cohen's kappa = 0.875).

> **Note (arm definitions)**: the control column in the early at-a-glance tables below is the **legacy/stress arm "Full material" (`material`)**, not a primary control arm. The current **three primary arms are `closedbook` / `rawfiles` / `skill`**; the complete three-arm × three-model matrix, including `rawfiles` (raw files + generic agent), is in [`../README.en.md`](../README.en.md) and [`../results/matrix/report.html`](../results/matrix/report.html). The numbers here are kept as they were for the record and serve only as a historical quick read.

**Correctness (↑)**

| Model | Closed book | Full material¹ | skill |
| :-- | :-- | :-- | :-- |
| Opus | 16% | 88% | **91%** |
| Sonnet | 49% | 93% | **85%** |
| Haiku | 18% | —² | **93%** |

¹ material is scored only on real answers (rate-limit errors excluded): Opus n=50, Sonnet n=27.　² For Haiku, only 2 of the 65 material questions ran successfully; the sample is too small to list.

**Out-of-scope abstention rate (↑, the share of out-of-scope questions where the model honestly says "I don't know")**

| Model | Closed book | Full material | skill |
| :-- | :-- | :-- | :-- |
| Opus | 60% | 100% | **100%** |
| Sonnet | 50% | —² | **100%** |
| Haiku | 60% | —² | **100%** |

**How to read these two tables (this is the conclusion):**
1. **The skill arm has the highest correctness for all three models (85–93%), and every one is above closed book.**
2. **"Full material" is not a good approach**: **when it does run**, its correctness is comparable to skill (Opus 88%, Sonnet 93%), but stuffing an entire course (~100K tokens) into the prompt **frequently exceeds how much the model can process in one go and triggers usage limits**. On Haiku, only **2 of the 65 questions ran successfully** (the rest could not return a valid answer and so were not scored). This engineering infeasibility is exactly the practical value of the skill's **chapter-based on-demand retrieval** (each query is short, stable, and cheap).
3. **Out-of-scope abstention: skill is at 100% on all three models** (zero fabrication on questions the materials do not cover).
4. **Read the hallucination rate honestly**: the skill's claim-level hallucination rate of 20–29% is not the lowest, because strict grading also counts "correct, but adds details the supporting passage does not mention" as a hallucination. That is not the same as fabrication (for true fabrication, look at the out-of-scope probes, where skill = 100% honest).

**Multi-round convergence**: as the skill arm's knowledge base is filled in from 7→14→20 chapters, correctness goes **28% → 62% → 87%**. The more complete the knowledge base, the more accurate the answers; the causal chain is clear.

**Another course: Yale PSYC 110 (humanities, real runs, three models)** closed book vs skill correctness: Opus **60%→98%**, Sonnet **55%→92%**, Haiku **55%→80%**; out-of-scope abstention for skill is **100% on all three models** (closed book 80–90%). The humanities course shows the same large advantage. (PSYC's material arm, at ~240K tokens, exceeds the context window and cannot run, which itself confirms that "dumping the whole course" is not workable.)

---

## 9. Honest limits (what cannot be treated as settled yet)

This is the most valuable section of any experiment. **Known limitations** of the current results:

- **Grading has been independently calibrated by humans twice**: ① a spot check of 16 questions, comparing human and judge results question by question, gave Cohen's kappa = **0.875**; ② another **24 questions** were labeled with B5's general calibration methodology (the same flow as `calibrate_matrix`: **four strata** of answerable judged correct/incorrect + out-of-scope abstained/did not abstain, with the judge's verdict **hidden** from the human, and quota-error answers filtered out first), giving 91.7% agreement and Cohen's kappa = **0.833**. Both rounds show high agreement (≥0.8) and corroborate each other. The human–judge disagreements observed in both rounds were **all cases of the judge being too strict** (a correct answer judged wrong; for example, a spelling variant of Extraversion on the OCEAN question was marked wrong). This is a sampling signal (not proof about every judgment), and it suggests the numbers lean conservative rather than inflated. **Grading still uses only a single model family (Sonnet)**, which is a known limitation.
- **The hallucination-rate metric is strict**: claim-level strict grading penalizes answers that are "correct but thoroughly elaborated" (see above), so the hallucination rate is not the skill's strong suit; its strengths are correctness + out-of-scope abstention.
- **The samples are small**: 6.006 n=65, PSYC n=50, so statistical power is limited. Results are presented as "descriptive + interval", without forcing claims of significance.
- **A very small number of judge_error cases remain after re-grading** (~9/495 LLM judgments still come back empty and are conservatively counted as incorrect).

> These are not "hidden flaws" but **deliberately stated limits**. A report that spells out "under what conditions my number holds" is far more credible than one that just shouts "100%".

---

## 10. Privacy / copyright boundary: what goes into the repository and what does not

This is enforced by [`../.gitignore`](../.gitignore):

- **Never in the public repository** (kept locally): the original copyrighted lecture text (MIT/Yale transcripts), the complete gold sets with answer keys `items_*_full.jsonl`, the raw per-question logs `raw*.jsonl` / `answers` / `scores`, the knowledge bases generated by the skill, and the human calibration labels.
- **May be committed**: the questions-only gold sets `_q.jsonl`, the aggregate summary `summary.json`, the report `report.html` and the comparison-chart SVGs, and all test code.

The principle: **anything that supports reproduction and backs up the claims is public; anything that might infringe copyright or leak answers stays local.**

---

## 11. File map (one line to remember each file by)

```
benchmark/
  run_benchmark.py     # older two-arm scaffold (baseline vs skill); --mock does a dry run to verify the pipeline
  gen.py               # newer matrix answer generation: incremental gap-filling by feasibility (depends on existing answers.jsonl), resumable, records per-cell cost
  judge.py             # grading: OOS checks abstention / numeric is deterministic / factual uses a claim-by-claim blind LLM judge
  rejudge.py           # re-grades stored answers with the corrected judge → summary_corrected.json
  stats.py             # paired statistics: McNemar + bootstrap confidence interval + Cohen's kappa
  report.py            # two-arm reporter (bilingual Chinese/English HTML + citations)
  report_matrix.py     # matrix reporter: only renders the precomputed summary.json (primary arms closedbook/rawfiles/skill)
  rounds.py            # multi-round convergence line chart (effect of filling in the knowledge base round by round)
  items/               # gold sets (_full with answers = local; _q questions only = publishable)
  materials/           # original course materials (copyrighted, all local)
  skill_workspace/     # working directory for the skill arm (references/wiki + quiz_bank)
  calibration/         # human-labeled subset (for judge kappa calibration)
  results/             # run outputs (summary.json + reports + comparison charts)
  tests/               # script self-tests: cd benchmark && python -m unittest discover -s tests
  docs/                # methodology and citations (this file + metric sources + data sources)
```

---

## 12. The one-sentence summary

> **Same questions, three exam formats, blind-judge grading, paired statistics as the safety net, and out-of-scope probes aimed squarely at catching fabrication.**
> The conclusion rests not on adjectives but on **reproducible numbers + honesty about stated limits**. That is how an "anti-hallucination" claim ought to be backed up.
