# exam-cram — en student-facing pack

> This file is the en language pack for the skill's student-visible wording; behavior logic lives in [skills/exam-cram/SKILL.md](../../../skills/exam-cram/SKILL.md) (the control layer, single source of truth).

## Student-facing Output

In `English` mode (and the `> EN:` side of `双语`) use the EN canonical vocabulary on the student side (Current stage / What this tests / Standard answer steps / Common pitfalls / 3-minute mnemonic / Your turn / Recorded to the mistake archive / Must-memorize / Worked example / Worked solution / Takeaway / Mistake replay / Confusion restate / Prep workspace initialized), pinned verbatim in [`docs/language-policy.md`](../../../docs/language-policy.md); in `中文` mode use the zh canonical vocabulary (zh pack: [`../../zh/skills/exam-cram.md`](../../zh/skills/exam-cram.md)). In `English` mode the provenance markers appear verbatim as:

- 🟢 **From your materials**: sourced directly from what the student uploaded; high confidence.
- 🟡 **AI-supplemented**: content the materials do not cover, filled in from the AI's own knowledge — each labelled "🟡 AI-supplemented — may differ from what your teacher taught" (the teacher prevails).
- ⚠️ **AI-generated answer**: the teacher marked the question but gave no answer, so the AI answered — each labelled "⚠️ AI-generated answer — not from your teacher or textbook".

Student-facing output defaults to English (Simplified Chinese if the student opened in Chinese); the persisted `language` switches it per the control layer's Output Contract dispatch rule (each mode single-language pure).

Bilingual composition rule (`language=双语`): NEVER a third template set — compose zh+en per block: the zh unit first (pure Chinese, zh canonical forms), an `> EN:` mirror line immediately after (pure English, EN canonical vocabulary); each side stays single-language pure and each anchor appears once per side. The progress panel, receipts, and source blocks mirror line-by-line the same way. In the `≤1天` tier the EN mirror may compress to the key sentences (time beats completeness there).
