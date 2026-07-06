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
- `references/wiki/` — core conclusions/formulas per chapter. Iterate through **all mastered chapters** — from `study_state.json`'s `current_phase`/`phase_checklist` when it exists (the structured-state source of truth), else `study_progress.md`, against `study_plan.md` — reading each chapter slice one at a time (never dump the whole wiki into context at once) so the sheet covers every mastered chapter.
- `references/quiz_bank.json` — teacher-flagged key items and their answer frameworks.
- `python "${CLAUDE_SKILL_DIR}/scripts/select_hard_questions.py"` — ranks example candidates. Resolve it from the skill package root, NOT the workspace (a student workspace has no `scripts/`). Its output is a FLAT difficulty/mastery-ordered list — grouping by knowledge point is the agent's job (Workflow 3).
- Weak-spot source: `study_state.json` (`mistake_archive` / `confusion_log` / `phase_checklist`) when it exists — the structured-state source of truth; else `study_progress.md` (mistakes, confusion entries, per-chapter mastery; a generated view that may be stale). Read mistakes and confusion entries FIRST.

## Workflow
1. **Load weak spots first.** Read mistakes and confusion entries — from `study_state.json` when it exists, else `study_progress.md` — before anything else, so the cram sheet prioritizes what the user still loses points on.
2. **Extract the skeleton.** For each chapter keep only the highest-frequency / highest-scoring formulas, conclusions, and one-sentence term definitions. Drop everything else.
3. **One hard worked example per key knowledge point (「例题」).** For each mastered chapter run `python "${CLAUDE_SKILL_DIR}/scripts/select_hard_questions.py" --workspace <ws> --chapter <N> --mode 查缺补漏 -n <M> --json`. Always pass BOTH flags: the explicit `--chapter` keeps `某章起步补弱` workspaces from fail-louding on a missing range, and the explicit `--mode 查缺补漏` overrides a saved `零基础从头讲` mode whose ordering is easy-first — the opposite of what the sheet needs. The output is a flat ranked candidate list, NOT grouped, and the explicit -n matters too: set <M> to at least the item count of `references/quiz_bank.json` (read its length first; the default is only the top 10, and any cap below the bank size can starve later knowledge points before grouping). From the list, pick the highest-difficulty candidate for each key knowledge point (knowledge points linked to `mistake_archive`/`confusion_log` entries come first). A key knowledge point with NO linked bank item gets the explicit mark 「无题库例题」 and keeps only its 「必背结论/公式」+「要点解释」 entries — NEVER invent a question to fill the slot. If the chosen item carries `requires_assets=true` / `maybe_requires_assets=true`, the sheet MUST embed ALL its question-side assets (`question_context`/`figure`/`diagram`/`table` — workspace-relative image links into `references/assets/`, labeled 「题面图 / question-side asset」); if any needed asset file is missing or unusable, fail-closed — pick a self-contained item for that knowledge point instead. Items whose `question_text_status` is `stub` / `page_reference` are not self-contained either: embed their original-page render from `references/assets/` the same way, else swap to a `full` item. Never put an item whose figure or original page the student cannot see on the sheet.
4. **Worked solution (「例题解答」).** Substitute the formula with the item's actual values: intermediate arithmetic MAY be skipped, but the base process MUST stay — which formula, what gets substituted, what comes out. When the materials provide no answer, the solution carries ⚠️ AI生成答案，非老师/教材提供.
5. **Takeaway (「要点解释」).** For each example: how to handle same-type / similar-stem questions — the recognition cue first, then which answer framework to apply.
6. **Provenance stays honest, off the layout.** Unlabeled lines mean material-sourced — that default applies ONLY to content actually taken from the wiki/materials. Any AI-supplemented line carries 🟡 AI补充，可能与你老师讲的不完全一致 inline; any AI-generated answer carries ⚠️ AI生成答案，非老师/教材提供 inline; a solution whose answer provenance is missing or unknown in `quiz_bank.json` carries 「来源未知」 explicitly — never let the unlabeled default absorb uncertain provenance (canonical wording in [`docs/language-policy.md`](../../docs/language-policy.md)). Per-line 🟢 tagging is no longer required.
7. **Write output.** Write `walkthrough.md` to the workspace with the four fixed sections per mastered chapter; refresh the progress panel at the end.
8. Never invent teacher emphasis that is not in the materials. If the materials do not flag a point, do not present it as a teacher-flagged item.

## Output Contract
- Write `walkthrough.md`: the four fixed sections per mastered chapter —「必背结论/公式」→「例题」→「例题解答」→「要点解释」— with a refreshed progress panel at the end.
- Provenance is inline and honest: AI-supplemented lines carry 🟡 AI补充，可能与你老师讲的不完全一致; AI-generated answers carry ⚠️ AI生成答案，非老师/教材提供; unlabeled lines are material-sourced (per-line 🟢 tagging not required).
- Keep it to one or two printable, hand-copyable pages.
- Student-facing output defaults to Simplified Chinese; a persisted `study_state.json` `language` (`English`/`双语`) switches it per exam-cram's dispatch rule with single-language purity. (See [`docs/language-policy.md`](../../docs/language-policy.md).)

## Student-facing Output
考前最后一小时速记小抄，固定四段、每章循环（简洁实用，AI 补充/生成的行就地标注）：

```text
【必背结论/公式】
- ……
- ……（🟡 AI补充，可能与你老师讲的不完全一致——只有资料没讲、AI 补的行才标）

【例题】（每个重点知识点配一道有难度的例题；依赖图的题必须先真实展示题面图，展示不了就换题面自足的题）
- 例：……
  ![题面图](references/assets/chNN_pXX_fig.png)

【例题解答】（把公式代入计算：可省略中间计算步骤，但必须保留基础过程——用哪条公式、代什么数、得出什么）
- ……（老师/资料没给答案时标 ⚠️ AI生成答案，非老师/教材提供）

【要点解释】（遇到同类型或类似题干的题怎么办：先认出特征，再套对应的答题框架）
- ……
```

上面代码块只是**版式示例**——写入真实 `walkthrough.md` 时，图片行必须是真正的 Markdown 图片（workspace 相对路径，学生打开 md 即见图）；只写路径文字不算展示，嵌不了图就换题面自足的题。


Render per the persisted `study_state.json` `language` (`中文` default / `English` / `双语`) with single-language purity — `中文` output stays pure Chinese, `English` output uses the EN canonical vocabulary, `双语` composes the zh unit first + a `> EN:` mirror per block; see [`exam-cram`](../exam-cram/SKILL.md) Output Contract and [`docs/language-policy.md`](../../docs/language-policy.md).

## Boundaries
- Do not put content into the cram sheet that the materials do not cover unless it is tagged 🟡 or ⚠️.
- The cram sheet is a compression, not a replacement for systematic review, and not a shortcut around the source-labeling and quiz_bank-only rules.
