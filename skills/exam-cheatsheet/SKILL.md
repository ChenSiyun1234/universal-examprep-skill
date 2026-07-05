---
name: exam-cheatsheet
description: >
  全员通关后生成考前极简速记小抄（Cheat Sheet）与总复习走查 walkthrough.md：按「必背结论/公式 →
  有难度例题（必要时含题面图）→ 例题解答（代入公式、保留基础过程）→ 要点解释（同类题怎么办）」
  四段压缩成考场能默写的一两页。当复习收尾、用户要「考前小抄/速记/总结」时使用。
license: MIT
---

# exam-cheatsheet — pre-exam cheatsheet

## Purpose
Compress everything already mastered into a one-to-two-page, printable, copy-by-hand cram sheet, written to `walkthrough.md` in the workspace. Summarize only mastered content. Do not teach new material and do not invent new questions.

## Activation
Trigger when all study phases are basically cleared and review is wrapping up, OR when the user asks for 「给我一份考前小抄 / 速记 / 总复习」 (a pre-exam cheat sheet, quick-recall sheet, or final review).

## Inputs
- `references/wiki/` — core conclusions/formulas per chapter. Iterate through **all mastered chapters** — from `study_state.json`'s `current_phase`/`phase_checklist` when it exists (the A4 source of truth), else `study_progress.md`, against `study_plan.md` — reading each chapter slice one at a time (never dump the whole wiki into context at once) so the sheet covers every mastered chapter.
- `references/quiz_bank.json` — teacher-flagged key items and their answer frameworks.
- `scripts/select_hard_questions.py` — picks the hard worked example per knowledge point (difficulty-first ordering; knowledge points tied to recorded mistakes/confusions come first).
- Weak-spot source: `study_state.json` (`mistake_archive` / `confusion_log` / `phase_checklist`) when it exists — the A4 source of truth; else `study_progress.md` (mistakes, confusion entries, per-chapter mastery; a generated view that may be stale). Read mistakes and confusion entries FIRST.

## Workflow
1. **Load weak spots first.** Read mistakes and confusion entries — from `study_state.json` when it exists, else `study_progress.md` — before anything else, so the cram sheet prioritizes what the user still loses points on.
2. **Extract the skeleton.** For each chapter keep only the highest-frequency / highest-scoring formulas, conclusions, and one-sentence term definitions. Drop everything else.
3. **One hard worked example per key knowledge point (「例题」).** Select from `references/quiz_bank.json` via `scripts/select_hard_questions.py` (difficulty-first; knowledge points linked to `mistake_archive`/`confusion_log` entries come first). If the item carries `requires_assets=true` / `maybe_requires_assets=true`, the sheet MUST embed the question-side figure (「题面图」, workspace-relative image link into `references/assets/`); if the figure file is missing or unusable, fail-closed — pick a self-contained item for that knowledge point instead. Items whose `question_text_status` is `stub` / `page_reference` are not self-contained either: embed their original-page render from `references/assets/` the same way, else swap to a `full` item. Never put an item whose figure or original page the student cannot see on the sheet.
4. **Worked solution (「例题解答」).** Substitute the formula with the item's actual values: intermediate arithmetic MAY be skipped, but the base process MUST stay — which formula, what gets substituted, what comes out. When the materials provide no answer, the solution carries ⚠️ AI生成答案，非老师/教材提供.
5. **Takeaway (「要点解释」).** For each example: how to handle same-type / similar-stem questions — the recognition cue first, then which answer framework to apply.
6. **Provenance stays honest, off the layout.** Unlabeled lines are material-sourced by default; any AI-supplemented line carries 🟡 AI补充，可能与你老师讲的不完全一致 inline and any AI-generated answer carries ⚠️ AI生成答案，非老师/教材提供 inline (canonical wording in [`docs/language-policy.md`](../../docs/language-policy.md)). Per-line 🟢 tagging is no longer required.
7. **Write output.** Write `walkthrough.md` to the workspace with the four fixed sections per mastered chapter; refresh the progress panel at the end.
8. Never invent teacher emphasis that is not in the materials. If the materials do not flag a point, do not present it as a teacher-flagged item.

## Output Contract
- Write `walkthrough.md`: the four fixed sections per mastered chapter —「必背结论/公式」→「例题」→「例题解答」→「要点解释」— with a refreshed progress panel at the end.
- Provenance is inline and honest: AI-supplemented lines carry 🟡 AI补充，可能与你老师讲的不完全一致; AI-generated answers carry ⚠️ AI生成答案，非老师/教材提供; unlabeled lines are material-sourced (per-line 🟢 tagging not required).
- Keep it to one or two printable, hand-copyable pages.
- Student-facing output defaults to Simplified Chinese; a persisted `study_state.json` `language` (`English`/`双语`) switches it per exam-cram's dispatch rule (canonical tokens verbatim). (See [`docs/language-policy.md`](../../docs/language-policy.md).)

## Student-facing Output
考前最后一小时速记小抄，固定四段、每章循环（简洁实用，AI 补充/生成的行就地标注）：

```text
【必背结论/公式】
- ……
- ……（🟡 AI补充，可能与你老师讲的不完全一致——只有资料没讲、AI 补的行才标）

【例题】（每个重点知识点配一道有难度的例题；依赖图的题必须先真实展示题面图，展示不了就换题面自足的题）
- 例：……
  ![题面图 / question-side asset](references/assets/chNN_pXX_fig.png)

【例题解答】（把公式代入计算：可省略中间计算步骤，但必须保留基础过程——用哪条公式、代什么数、得出什么）
- ……（老师/资料没给答案时标 ⚠️ AI生成答案，非老师/教材提供）

【要点解释】（遇到同类型或类似题干的题怎么办：先认出特征，再套对应的答题框架）
- ……
```


Render per the persisted `study_state.json` `language` (`中文` default / `English` / `双语`); canonical tokens stay verbatim with a trailing gloss — see [`exam-cram`](../exam-cram/SKILL.md) Output Contract for the dispatch and composition rules.

## Boundaries
- Do not put content into the cram sheet that the materials do not cover unless it is tagged 🟡 or ⚠️.
- The cram sheet is a compression, not a replacement for systematic review, and not a shortcut around the source-labeling and quiz_bank-only rules.
