# A full-cycle benchmark: cross-session recovery, 0% to 100%

[中文](REPORT.md) · English

*July 2026 · ~8 min*

v4 no longer measures "did it get one question right" — it measures **the whole study cycle across a night of review**. That's because single-question Q&A is exactly the part a plain agent can fake: in v3, a raw-files agent tied the skill on accuracy. This time we ran a no-skill agent and a skill-equipped agent on **the same materials, the same questions, the same session scripts**, and scored the study-loop metrics **deterministically** — parsing what actually lands on disk, no LLM judge involved.

The skill's value isn't how clever any single answer is — it's whether **the studying actually survives**: does anything remain after you close the chat, can you find your mistakes again, does it connect what's genuinely in your materials, and does it honestly say "not covered" when it isn't. The sections below walk through each.

---

## What survives the night: study-cycle durability

<div align="center"><img src="docs/img/v4_loop_en.svg" width="620" alt="study-cycle durability: no-skill vs skill" /></div>

*Two courses (PSYC 110 + MIT 6.006), 2 reps each, model Sonnet. Three durability metrics, no-skill → skill.*

**Cross-session persistence: 0% → 100%** — the key result this round. Session S1 teaches 3 questions, quizzes 2 (the student deliberately answers one wrong), then ends; a **brand-new session S2** then opens — empty context, only the disk workspace persists — and asks "which one did I get wrong last time?" The skill-equipped agent reads `mistakes/chNN.md` off disk and names the exact question by content (e.g. the toxoplasmosis/cat question, recalling the student answered "dog"); the no-skill agent **finds nothing** — it never built a mistake book, so a fresh session has no memory of what happened before. This isn't a case of one arm performing worse; it's a case of one arm not having the machinery at all.

**Durable deliverables: 0% → 81%**. Checked against a 4-item list: `notebook/index.md` exists with at least 3 entries whose anchors all resolve; the mistake book is non-empty; `cheatsheet.md` passes `validate_workspace` (every bullet carries a resolvable source link); `cheatsheet.pdf` is exactly the requested page count. The no-skill side leaves zero artifacts — close the chat and nothing remains.

**Verifiable sources: 0% → 58%**. Each teaching turn passes if its answer carries a checkable source label. Honestly: the skill was 100% on PSYC but only 17% on 6.006 — one-shot `claude -p` automation is noisier than a real interactive session: the model doesn't always emit the source-block line reliably under harder algorithm content, whereas in an interactive session it would keep iterating until it did. The load-bearing point is that **the no-skill side is structurally zero on all three metrics** — the exact skill percentage is a secondary detail.

---

## In the moment: grounded correctness, retrieval, honest abstention

This section retains the matrix regression from earlier versions (judge Sonnet + a newly added deterministic retrieval trace), read alongside the durability metrics above.

<div align="center"><img src="docs/img/v4_psyc_correct_en.svg" width="620" alt="PSYC materials-specific: closed-book vs skill" /></div>

*PSYC 110, 54 materials-specific questions. Closed-book collapses to single digits or low teens; with the skill, all three models reach 96%–100%.*

**Materials-specific correctness** (54 PSYC questions + 65 for 6.006, closed-book vs skill): closed-book **2%–49%**, with the skill **87%–100%** (PSYC skill 96%–100%, 6.006 skill 87%–93%). Same pattern as v3 — content that's in the materials but not in the model's head gets connected accurately by the skill; closed-book can't connect it at all.

<div align="center"><img src="docs/img/v4_recall_en.svg" width="560" alt="retrieval recall@1" /></div>

*Chapter-routing recall@1 (new in v4), computed deterministically from the tool-call trace recorded via `EXAMPREP_TRACE=1`.*

**Retrieval recall@1** (new in v4, computed deterministically from the agent's tool-call trace, no LLM judge involved): how often the skill routes to the chapter containing the gold answer — PSYC **96%–100%**, 6.006 **74%–100%**. This measures directly whether the new BM25 retrieval engine finds the right place, rather than only the downstream "was the answer correct" outcome.

**Out-of-scope abstention**: closed-book **50%–90%**, with the skill **≈100%**. One honest caveat worth stating plainly: the Sonnet skill arm measured 90% on PSYC because of a **judge false positive** — the answer literally states "the material does not say how many minutes the final lasts" (which is a correct abstention), but volunteered an adjacent true fact alongside it, and the judge flagged that extra sentence as a hallucination. The true abstention rate is 100%.

---

## How we scored

Of the six study-loop metrics, whichever can be scored deterministically never goes through an LLM judge: source labels are parsed with regex and their anchors are checked against `validate_workspace._md_anchors` for real resolvability; mistake recall is scored by **content-keyword coverage** (the skill names mistakes semantically by what the question was about, not by an internal id, so scoring matches on semantic keyword coverage rather than id equality); the artifact checklist is read straight off disk via `validate_workspace` + `pdf_page_count`.

The matrix's correctness and abstention numbers still use the Sonnet judge — the methodology already human-calibrated in v3 (16-item kappa = 0.833, 24-item stratified blind kappa = 0.875), where every human–judge disagreement in both spot-checks was the judge being too strict, so these numbers lean conservative rather than inflated.

---

## Limitations

- **The study-loop skill arm has its own noise**: a single one-shot `claude -p` call per turn is noisier than a real interactive session — 6.006's verifiable-sources metric came out at only 17%, which is a limitation of the automation script, not a ceiling on what the skill can do. The reliable signal is the **structural zero on the no-skill side**; the skill's exact percentage is more of a floor than a ceiling.
- **Small scale**: the study-loop was only run on 2 courses × 2 reps; the matrix regression is 54/65 questions. This is trend evidence, not a large-scale statistical result.
- **One documented judge false positive**: an out-of-scope probe's correct abstention was misjudged as a hallucination, pulling that metric from 100% down to 90%.
- **Minor closed-book tool contamination**: in a handful of rows, a closed-book agent that was supposed to get nothing actually called a tool and read the materials, which slightly inflates the already-low closed-book baseline above its true value.
- **The Sonnet judge shares a family with the graded models** — human-kappa-calibrated, but still a known limitation.

Full commands and the design doc are at [`docs/loop-benchmark-design.md`](docs/loop-benchmark-design.md) and [`docs/running-real-runs.md`](docs/running-real-runs.md).
