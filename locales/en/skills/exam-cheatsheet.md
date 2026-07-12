# exam-cheatsheet — en student-facing pack
> This file is the en language pack for student-visible wording; behavior logic lives in [skills/exam-cheatsheet/SKILL.md](../../../skills/exam-cheatsheet/SKILL.md) (the control layer, single source of truth).

The last-hour-before-the-exam quick-recall cheat sheet: four fixed sections, repeated per chapter (concise and practical; AI-supplemented or AI-generated lines are labeled inline):

```text
[Must-memorize conclusions & formulas]
- ...
- ... (🟡 AI-supplemented — may differ from what your teacher taught — label only lines the materials did not cover and the AI added)

[Worked example] (one hard worked example per key knowledge point; a figure-dependent item must actually show its question figure first — if it cannot be shown, swap to a self-contained item)
- Example: ...
  ![Question-side asset](references/assets/chNN_pXX_fig.png)

[Worked solution] (substitute the values into the formula: intermediate arithmetic may be skipped, but the base process must stay — which formula, what gets substituted, what comes out)
- ... (when the teacher/materials give no answer, label ⚠️ AI-generated answer — not from your teacher or textbook)

[Takeaway] (how to handle same-type or similar-stem questions: recognize the cue first, then apply the matching answer framework)
- ...
```

The code block above is only a **layout example** — when writing the real `walkthrough.md`, image lines must be actual Markdown images (workspace-relative paths, so the student sees the figure the moment the md is opened); writing the path as plain text does not count as showing it, and if the figure cannot be embedded, swap to a self-contained item.
