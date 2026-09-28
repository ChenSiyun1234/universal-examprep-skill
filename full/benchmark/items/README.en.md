# items/ — Gold Question Set (Ground Truth)

English · [中文](README.md)

This is the core of the test. Each question is one line of JSON (JSONL format) that gives both the "gold answer" and "which sentence of the materials the answer comes from"
(the supporting span). The latter lets the judge decide "is the answer faithful to the materials", and it is also the basis for grading numeric questions.

Copy `items.example.jsonl` to `items.jsonl` and rewrite it from your **own slides/homework**, following the spec below.

## Field spec

| Field | Required | Description |
| :-- | :-: | :-- |
| `id` | ✓ | Unique ID, e.g. `q1` |
| `question` | ✓ | The question (one a student would really ask) |
| `gold_answer` | ✓ | The gold answer (concise, definite). Leave it empty (`""`) for out-of-scope questions (answerable=false) |
| `supporting_span` | ✓* | **Verbatim excerpt from the materials** that supports the answer + its source; leave empty for out-of-scope questions |
| `source_file` | ✓* | Which material file the question comes from, e.g. `materials/ds/ch5_search.pdf` |
| `answer_type` | ✓ | `factual` (fact) / `definition` (definition) / `numeric` (calculation/numeric) |
| `answerable` | ✓ | `true` = the materials can answer it; `false` = **out-of-scope probe** (not in the materials; the correct behavior is to abstain) |
| `tolerance` | For numeric | Allowed error for a numeric question, e.g. `0` (exact) or `0.01` |

## How to write it (suggested process)

1. **Read through your lecture notes/homework**, pick 15~40 frequently tested points, and write them as questions + gold answers.
2. **Annotate every item with `supporting_span`**: copy in the exact sentence from the materials that the answer rests on, and fill in `source_file`.
   (You can have AI draft them, but check every one yourself: AI drafts, a human signs off.)
3. **Deliberately include a few out-of-scope probes** (`answerable:false`): questions a student might ask but your materials never cover
   (such as "which room is the exam in" or "what is the teacher's name"). This is the key test of whether the skill "would rather say it doesn't know than make something up",
   and it maps directly to the skill's claimed "physical anti-hallucination". **Prefer near-miss out-of-scope questions** (on a topic close to the materials, but with
   no exact answer in them, e.g. the materials cover an algorithm and the question asks about a parameter they never mention) over obviously off-topic ones. Obviously out-of-scope questions are too easy to handle;
   only near-misses separate "actually read the materials and knows the boundary" from "it looks related, so make something up". Details in [`docs/judge-calibration.en.md`](../docs/judge-calibration.en.md).
4. **Calculation questions** (`answer_type:"numeric"`): take them from homework where possible, and record the exact value + `tolerance`. These are
   **graded deterministically** by the script (no LLM judge), which is the cleanest.
5. Save it as `items.jsonl`. **Small and fully annotated > large and rough**: about 30 questions, each with a gold answer and a source, is enough for a credible report.

> Platform/English-version plan: the question text is independent of the judge's language. It is in Chinese for now; an English version later can reuse the same harness directly
> and only needs a separate English `items.jsonl`.
