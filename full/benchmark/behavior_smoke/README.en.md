# Tier 2 — Behavioral Smoke

English · [中文](README.md)

This tests the skill as a **tutoring workflow**, rather than testing only static files (Tier 0/1) or grounded Q&A (Tier 3 benchmark).
Definitions are in [`../docs/test_tiers.en.md`](../docs/test_tiers.en.md); the current-state audit is in [`../docs/testing-audit.en.md`](../docs/testing-audit.en.md).

## Two paths

| Path | Command | Cost | In CI? |
| :-- | :-- | :-- | :--: |
| **Default (deterministic)** | `--mock` / `--check-fixture` | $0, pure stdlib, no network, no LLM, no API key | ✅ |
| **Optional (real agent)** | `--llm` (requires `RUN_SKILL_BEHAVIOR_LLM=1`) | Runs `claude -p` (subscription, no API key needed) | ❌ Disabled by default |

```bash
# Default: zero cost, can run in CI
python benchmark/behavior_smoke/run_behavior_smoke.py --check-fixture   # validate the mini-course workspace
python benchmark/behavior_smoke/run_behavior_smoke.py --mock            # run the deterministic detectors on mock outputs

# Optional: real-agent smoke (both the env var and the flag are required; otherwise it refuses to run)
RUN_SKILL_BEHAVIOR_LLM=1 python benchmark/behavior_smoke/run_behavior_smoke.py --llm
```

With no arguments it only prints help and **never** calls an LLM.

## What it covers

The self-authored small workspace [`fixtures/mini_course/`](fixtures/mini_course) (**no copyrighted content**, general CS knowledge) covers all 6 question types
and passes `scripts/validate_workspace.py`. Each scenario ([`scenarios.json`](scenarios.json)) has one **deterministic detector**:

| Scenario | Behavior claim | Default (deterministic) check |
| :-- | :-- | :-- |
| `quiz_bank_only` | Quizzes use only the question bank; no improvised questions | Every question ID in the mock output must be in `quiz_bank.json`; the negative example (made-up question IDs) must fail |
| `provenance_labels` | Distinguishes sources and uses the canonical labels | The mock output contains all of the 🟢/🟡/⚠️ canonical labels |
| `hint_skip_mistake_archive` | After two wrong answers in a row, offers a hint/skip/archive | The mock output contains the escape hatch + the mock progress has a mistake row |
| `confusion_tracking` | "Why"-type questions are written to progress | A new row appears in the confusion section of the mock progress |
| `checkpoint_recovery` | Resumes from the current phase instead of restarting | Reads current phase = 2 from progress, and the resume message points to phase 2 |
| `no_python_fallback` | Hand-written output without Python is still complete | The hand-written workspace passes Tier-1 validation |
| `zero_basic_key_question` | A zero-background walkthrough has structured sections | The mock output contains 考点拆解 ("breakdown of the tested point") (or 这题在问什么, "what this question asks") + 标准答题步骤 ("standard answer steps") (or 逐步演算, "step-by-step work"); 易错点 ("common mistakes") / 3分钟速记 ("3-minute memo") are optional closing blocks and are no longer required |
| `teaching_template` | A5 seven-step walkthrough template + a source block for every question | ①-⑦ all present and in order (② before ④), and ⑦ points to the chapter/wiki; the source line has 题目来源 ("question source") ｜ 答案来源 ("answer source") ｜ canonical label; for an AI answer, ⚠️ appears in the source line and in the answer block heading; by default the output stops at the source block, and unrequested closing blocks are caught (exempt if the student asked for them); all 7 negative examples are caught |
| `visual_first_assets` | Visual questions show the question-side asset first | The mock output must first show a real local fixture image carrying the `题面图 / question-side asset` label; the negative examples (answer image shown first / answer image or text leaked before the question / unlabeled answer image / text before the image / image inserted after the question / image arriving late after `问题：` ("Question:") / unsafe or missing path / path printed only) must fail |
| `scope_override` | Quizzing outside the chosen scope must be announced first (A2) | The mock output shows, verbatim and **before** the first question, 「⚠️ 临时覆盖你的 <范围> 范围偏好」 ("⚠️ Temporarily overriding your <scope> scope preference"); the negative examples (announced only after the question / not announced) must fail |
| `language_first_ask` | The first question asks mode × time × language together, once (A6/A8b), with the language line listing all three language options; an urgent opening is inferred silently | Mock good example = language line with all three options + one set call with all three flags; the negative example missing the language line is caught; urgent variant = zero opening clarification/preference questions + `--language` ∈ canonical values, and the urgent negative example that ends with a question is caught |
| `time_budget_no_questions` | ≤1天 (≤1 day) pacing + explicit `no_questions` (A6) | Ordinary ≤1天 allows bank checkpoints that carry a real `[#id]` and a matching prompt; clarifying/preference/reflective follow-up questions must fail. When the scenario prompt explicitly says “别问我问题” ("don't ask me questions"), every interactive question (checkpoints included) is forbidden; rhetorical questions the tutor answers itself are not falsely flagged |
| `knowledge_window_recheck` | Knowledge points outside the window must really be rechecked (A6) | For 3-7天 (3–7 days), the good example may either ask back or actually test, and the negative example is still caught by default; for >7天 (`require_test`), only an actual quiz counts, so the bad example that only asks verbally 「还记得吗」 ("do you still remember?") is caught; negative phrasings (不问/不实测/我就当你会了, "won't ask / won't test / I'll just assume you know it") do not count as a recheck, and negated safety statements (不会默认你会, "I won't assume you know it") are not falsely flagged |
| `artifact_mode_routing` | Quota-friendly `chat` / `visual` artifact gate | Verified on the mock command trace: finishing a chapter in `chat` does not auto-render; `visual` is persisted only after an explicit standing choice; a subscription name alone cannot trigger a switch; after a one-shot PDF the mode is still `chat`; for a PDF, a native/browser backend must be chosen before this chapter's preflight and generation. The negative examples catch, respectively, an automatic PDF, guessing the subscription, and a one-shot request polluting the standing state |
| `notebook_persist_ok` | A teaching turn "writes to disk first, then summarizes" (v4 §2.4 red line) | The mock good example contains both the `notebook.py … add-entry` write command (also recognized inside a code span) and a student-visible `notebook/chNN.md#锚点` (anchor) receipt (the zh canonical form looks like `完整解答：notebook/ch02.md#q13`, "full solution: …"; the receipt's chapter number must match the command's `--chapter` with zero padding); the negative example that explains everything only in chat, with zero write receipts, must fail |
| `workspace_confirm_ok` | Creating a workspace requires confirmation; silently creating one = a violation (v4 §2.5 red line) | In the mock good example, **before** the first create call (`ingest.py --output-dir` / `workspace-register`), the tutor asks to confirm the location and the student affirms the target path; the negative example that silently creates the workspace with `ingest.py --output-dir` right at the start must fail; asking without waiting for the answer, creating first and seeking approval afterward, or creating after the student declined all fail as well |
| `lazy_load_best_effort` | Reads only the current chapter | **best-effort**: skipped in deterministic mode; a real check needs a transcript/LLM |

## What is best-effort / not covered

- **`lazy_load`** can verify "read only the current chapter" only with a real tool-call transcript (or a real `--llm` run);
  deterministic mode provides only a placeholder detector, `count_wiki_reads`, which is **not asserted in CI**.
- **Deterministic mode only proves that the detector logic holds on mock outputs**. It does **not** prove that a real agent will produce these behaviors.
  Covering real LLM behavior requires running the optional `--llm` path (off by default, not in CI).
- **The deterministic detectors are smoke heuristics, not semantic graders**: they use structure / question IDs / prompt matching / chapter scope / negation words
  and similar signals to catch **common** fabrications and misjudgments (made-up questions, a valid question ID attached to a made-up prompt, unnumbered questions, negated escape hatches, empty-state placeholder rows,
  drifting to the wrong chapter, listing a label legend without labeling the answer, and so on), but they **cannot exhaust** every rewording an arbitrary LLM might produce. Real semantic judgment is left to the opt-in
  `--llm` path and a future LLM judge (Tier 3/4). That is also why this sits under "behavioral smoke" rather than "behavioral grading".

## Boundaries (what this is not)

- This is **not** a full benchmark and does **not replace** Tier 3 (full matrix) / Tier 4 (long-horizon drift).
- The default path does **not** run a model, does **not** use the network, does **not** read an API key, and does **not** cost anything.
- `--llm` is wired up (B2): it drives a real agent for a single turn (`claude -p`, or any/stub command passed via `--agent-cmd`), applies the **same** detectors as `--mock` to every scenario that can be verified from the reply, writes the transcript, and outputs metrics; opt-in, off by default, not in CI. The wiring is verified deterministically by `tests/test_behavior_smoke_live.py` with a stub agent (state/file scenarios cannot be verified with a one-shot `-p` and are honestly reported as SKIP).
- Outputs go to `results/` (gitignored), and fixtures are copied to a temporary directory before anything modifies them.
