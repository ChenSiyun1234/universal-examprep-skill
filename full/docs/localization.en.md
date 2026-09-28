# Localization Boundary

English · [中文](localization.md)

This document explains what language packs may and may not do. The core principle: **behavior exists in exactly one copy; wording may exist in several**.

## 1. Directory responsibilities

```text
SKILL.md                         # language-neutral router
skills/*/SKILL.md                # controls behavior: triggers, reads/writes, flow, failures, boundaries
locales/zh/SKILL.md              # Chinese compatibility index, not a full copy of the workflow
locales/en/SKILL.md              # English compatibility index, not a full copy of the workflow
locales/<lang>/skills/*.md       # student-visible wording for each subskill
locales/<lang>/messages.json     # script message catalog
locales/<lang>/templates/*.md    # workspace templates
scripts/                         # single copy of execution logic; renders user-facing text through the message catalog
```

`skills/exam-cram/SKILL.md` and its subskills are the behavioral source of truth. Locale files do not own business rules.
Script logic exists in exactly one copy. The machine schema, persisted domain values, and student views are handled as separate layers, and only student-visible messages are rendered through the language catalogs.

## 2. What may go into a language pack

- Titles, labels, receipts, and progress prompts;
- The block names of the seven-step walkthrough, the shape of the source block, and the honest-abstention sentence;
- Natural-language examples and the wording of cheat-sheet sections;
- Workspace templates that contain only a display skeleton;
- Natural Chinese or English translations of the same message key.

## 3. What must not go into a language pack

- New trigger conditions, phase transitions, or completion criteria;
- A separate set of rules for question-bank selection, grading, or preventing invented questions;
- A separate set of rules for disk writes, error degradation, dependency installation, or path safety;
- Default values that differ from the control layer;
- A copy of the entire `exam-cram` workflow that is then translated and maintained separately.

A behavior change is made first, and only, in `skills/*/SKILL.md`. In the same change, the language packs update only the affected student wording. The two compatibility entries keep only navigation, the canonical fixed phrasing, and the minimum safety floor.

## 4. State and dispatch

- **Machine schema layer**: JSON keys, stable IDs, issue/patch statuses, reason codes, CLI subcommands, and structured JSON output keep their fixed machine spelling and do not go into language packs.
- **Domain value layer**: new state uses the language-neutral canonical codes defined in `scripts/i18n.py`, for example `zh` / `en` / `bilingual` for language, `from_scratch` / `shore_up` / `fill_gaps` for learning mode, and the respective neutral codes for time budget, artifact mode, knowledge window, and row status. Chinese and English display words and compatibility command aliases are normalized to the matching code before they are written. Legacy Chinese display values serve only as migration input and as wording in generated views; they are not the canonical values of new state. Persisted codes must not be rewritten to follow the reply language.
- **Student view layer**: conversation, notebook explanations, study materials, receipts, and summaries are output in the current language. If a legacy renderer can only produce a Chinese-canonical compatibility view, the agent reads it as a state view and restates it in the current language; it does not paste the original text directly into English teaching.
- The canonical values of `study_state.json.language` are `zh`, `en`, and `bilingual`; `中文` (Chinese), `English`, and `双语` (bilingual) are display choices, command aliases, and legacy-state migration values.
- A new conversation defaults to English; if the student opens in Chinese, the default is Simplified Chinese. Bilingual can only be chosen explicitly.
- `双语` does not create a third directory: it combines zh and en block by block, with the Chinese first and the `> EN:` mirror after it.
- A missing selected wording pack is a packaging error. It must be reported explicitly and must not be silently replaced with another reply language. Chinese display values left over from old workspaces or old renderers may be read only as migration input or as compatibility views; agent-generated conversation still uses the selected language, and newly written domain values still use the language-neutral codes.
- `exam-audit` has no fixed student template, so it has no separate locale fragment; it still generates its reports according to the language state.

Machine-readable JSON is not student wording; only student-facing script messages are localized through `messages.json`. Every new output must be explicitly assigned to one of these layers at design time. Blanket rules such as "all script output is in Chinese" or "translate all JSON" are forbidden.

## 5. Translation does not change safety semantics

Translation must preserve:

- Quizzes draw only from `quiz_bank.json`; without a question bank, no substitute checkpoint may be generated;
- The three provenance classes 🟢 来自资料 / 🟡 AI补充，可能与你老师讲的不完全一致 / ⚠️ AI生成答案，非老师/教材提供 (in the English pack: 🟢 From your materials / 🟡 AI-supplemented — may differ from what your teacher taught / ⚠️ AI-generated answer — not from your teacher or textbook);
- For visual questions, the question-side assets are shown first, and the item is skipped if an image is missing;
- `study_state.json` is read first and written with `update_progress.py`;
- When there is no state but Python is available, run `init` first; maintain the md by hand only if Python truly cannot run;
- `≤1天` (≤1 day) does not ask about template preference; when the student explicitly declines questions, a phase can reach at most `covered_unverified`;
- The workspace path must be confirmed by the user; a command's business failure must be surfaced explicitly.

Sentences may be rephrased so they read naturally, but these behaviors must not be weakened.

## 6. Boundary for verbatim source quotes

Verbatim quotations of original sentences from the course materials, of exam question text, and of teacher answers may keep their original language, and must be clearly labeled as original-text quotations. Agent-generated headings, transitions, explanations, solutions, and summaries are still output in the current language. Do not quietly rewrite evidence for the sake of "language purity", and do not use "original-text quotation" as cover for slipping in untranslated agent prose.

## 7. Alignment checks

Every addition or change to language wording should be checked for the following at the same time:

- The zh/en subskill file lists match;
- The key sets of `messages.json` match;
- The fixed labels correspond one to one in meaning;
- Zero CJK on the English student surface, and no English sentences on the Chinese student surface;
- Relative links exist;
- Templates contain no hard-coded sample values such as dates, phase numbers, or a fixed number of lessons.

For the detailed fixed vocabulary and composition rules, see [`language-policy.md`](language-policy.md); for the overall structure, see [`skill-architecture.en.md`](skill-architecture.en.md).
