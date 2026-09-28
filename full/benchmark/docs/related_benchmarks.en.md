# Survey of Authoritative Hallucination / Factuality Benchmarks (Draft Related Work for the Report)

English · [中文](related_benchmarks.md)

> Working draft for citation in the benchmark report. Each entry has been checked against primary sources (arXiv / ACL·NeurIPS·AAAI / official repo·leaderboard).
> Live leaderboard numbers change (e.g., top models on Vectara at ~2–5%), so treat them as "snapshots" when citing; descriptions of methods and data are more stable.

**Positioning**: this skill's core claim is **file-locked, grounded answering + out-of-scope abstention**. So the main comparison is against two kinds of benchmarks:
**grounding/faithfulness** and **abstention/calibration**.
Pure closed-book factuality (TruthfulQA, FActScore, etc.) serves only as background contrast.

---

## Grounding / faithfulness (closest fit)

- **FACTS Grounding (Google DeepMind, 2025)** — The public benchmark closest to our setting: answer based only on a given long document, scored automatically in two stages ("eligibility first, then grounding"), with multiple judges (Gemini/GPT-4o/Claude) aggregated to reduce bias. 1,719 examples (860 public/859 private). https://arxiv.org/abs/2501.03200 · https://www.kaggle.com/benchmarks/google/facts-grounding
- **Vectara HHEM / Hughes hallucination leaderboard** — Factual consistency for "summarize using only the source text"; hallucination rate = 100 − consistency%. It provides an **open-source classifier, HHEM-2.1-Open**, which we could use directly to score our outputs. https://github.com/vectara/hallucination-leaderboard
- **RAGAS faithfulness (EACL 2024 demo)** — Faithfulness = (number of claims in the answer supported by the context ÷ total number of claims); no reference answer needed; LLM extraction + verification. This is essentially an "operational definition" of our core claim. https://arxiv.org/abs/2309.15217
- **TRUE (NAACL 2022)** — A meta-benchmark for factual-consistency **metrics** (11 datasets), evaluated at the example level; its conclusion is that NLI- and QA-based metrics are strongest. We use it to justify choosing NLI/entailment to judge "whether the answer is faithful to the materials." https://arxiv.org/abs/2204.04991

## Abstention / calibration

- **RGB (AAAI 2024)** — Four RAG abilities: noise robustness, **negative rejection**, information integration, and counterfactual robustness. Negative rejection = our "if the materials don't have it, say you don't know." Chinese and English. https://arxiv.org/abs/2309.01431
- **SimpleQA (OpenAI, 2024)** — Short-answer factuality + **abstention/calibration**: each answer is graded correct/incorrect/**not attempted**, and confidence calibration is measured. We borrow its abstention/calibration protocol (not its question content). https://arxiv.org/abs/2411.04368
- **SelfCheckGPT (EMNLP 2023)** — Zero-resource and black-box: inconsistency across multiple samples serves as a hallucination signal. It could serve as a deployment-level signal for "when to abstain" (no logprobs needed). https://arxiv.org/abs/2303.08896

## Frameworks / methods (terminology and methodology)

- **HalluLens (Meta, ACL 2025)** — A unified benchmark + a clear **taxonomy: intrinsic (unfaithful to the input context) vs. extrinsic (inconsistent with world knowledge)**; it generates test sets dynamically to prevent data contamination. Our goal can be stated precisely as "eliminate intrinsic hallucination, and abstain rather than commit extrinsic hallucination." https://arxiv.org/abs/2504.17550
- **FActScore (EMNLP 2023)** — Long-form factual precision: break the text into **atomic facts** and check each one's support rate. The benchmark itself is closed-book, but its **atomic-fact decomposition method** can be used directly in our grounded scoring. https://arxiv.org/abs/2305.14251
- **FELM (NeurIPS 2023)** — A benchmark that evaluates factuality **evaluators** themselves; if we build our own LLM judge, it is the reference for "how reliable the judge is." https://arxiv.org/abs/2310.00741

## Closed-book factuality (background contrast; a brief mention is enough)

- **TruthfulQA (ACL 2022)** — Resistance to "imitative falsehoods" (common misconceptions), 817 questions. The most-cited "truthfulness" benchmark, used to contrast "closed-book truthfulness vs. our grounded faithfulness." https://arxiv.org/abs/2109.07958
- **HaluEval / HaluEval 2.0 (EMNLP 2023)** — A large-scale hallucination recognition benchmark; its knowledge-grounded dialogue and summarization branches are grounded-type and can be cited. https://arxiv.org/abs/2305.11747
- **FreshQA (Findings of ACL 2024)** — Timeliness + **false premises**; timeliness is irrelevant to us, but the false-premise abstention angle can be cited narrowly. https://arxiv.org/abs/2310.03214

---

## Recommended citations (ranked)

**Tier 1 (core; each maps to one part of our claim)**
1. **FACTS Grounding** — Grounded answering within a document (recent, authoritative, public set reusable).
2. **Vectara HHEM** — Source-only answering + a ready-to-run hallucination-rate classifier.
3. **RAGAS faithfulness** — An operational definition of claim-level faithfulness that can be applied directly.
4. **RGB** — Abstention/negative rejection (the part factuality benchmarks do not cover).

**Tier 2 (methods/frameworks)**
5. **HalluLens** — Intrinsic/extrinsic taxonomy + the state of the field in 2025.
6. **TRUE** — Justifies choosing NLI/entailment metrics.
7. (optional) **SimpleQA** — Abstention/calibration protocol.

**Brief mention**: TruthfulQA, FActScore (also mentioning its atomic-fact method), HaluEval, SelfCheckGPT, FELM, FreshQA.
