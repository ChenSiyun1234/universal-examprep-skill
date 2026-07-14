---
name: exam-study-guide
description: 将备考工作区中某一章的 wiki、教学例题、题库、图片与 notebook 编译为公式可读、图片可见、自包含且可打印的 HTML/PDF 教材。用户说 Markdown 公式仍是 raw LaTeX、图片缺失、想要更方便阅读的章节讲义/教材/打印版，或要求把当前章整理成含课件、例题、Quiz、答案与通俗解释的视觉教材时使用。
license: MIT
---

# Exam Study Guide

## Purpose

Compile one exam-workspace chapter into a readable, self-contained HTML study guide and an optional printable PDF. Keep Markdown and JSON as the auditable sources of truth. Treat `study_guide/chNN.html` as a derived reading view; never use it to overwrite a source file.

## Activation

Use this module only after the exam workspace and current chapter are confirmed. Restore the current phase and effective `artifact_mode` from `study_state.json` before selecting `<N>`. A missing/legacy/unknown mode is `chat` and does not auto-activate this module. Proceed only for a recognized explicit `visual` standing preference, or for a direct one-shot request for a readable handout/HTML/PDF; a one-shot request does not rewrite the stored preference. Never inspect or infer the student's subscription. Preserve the parent exam-coach language and provenance contracts in all chat summaries.

## Inputs

- Exactly one current-chapter `references/wiki/chNN*.md` file.
- Optional `study_state.json`; its canonical `language` value (`中文` / `English` / `双语`) controls all agent-generated headings, notices, explanations, labels, and summaries. Missing state follows the session default (English unless the student opened in Chinese); the script's Chinese empty-value fallback exists only for legacy workspaces and is not a new-session language decision.
- The current-chapter slice of `references/teaching_examples.json`, when that optional manifest exists.
- The current-chapter slice of `references/quiz_bank.json`.
- `notebook/chNN.md`, when that chapter notebook exists.
- Workspace-local image assets referenced by those sources.

Use only `$...$` and `$$...$$` as formula delimiters in source Markdown. Forms such as `(A\cup B)`, `[P=\frac{...}]`, `\(...\)`, and `\[...\]` are not valid framework input. Confirm and migrate the source explicitly; never guess-rewrite a formula.

## Workflow

1. Persist every new substantive explanation first with `scripts/notebook.py add-entry`. This renderer compiles existing evidence; it does not replace notebook-first and it never invents a quiz.
2. Resolve output intent. `chat` without a direct artifact request stops here and returns to conversational tutoring. `visual` requests the printable path; a one-shot request follows exactly the requested HTML/PDF scope. Persist a standing choice only through `update_progress.py set --artifact-mode chat|visual`.
3. Before rendering, read [`docs/pdf-capability-adapters.md`](../../docs/pdf-capability-adapters.md) and probe the machine-readable routes in [`docs/pdf-capability-adapters.json`](../../docs/pdf-capability-adapters.json). Never infer availability from an agent name. Select exactly one backend:
   - `native`: an already installed host PDF capability can print/convert the exact validated `study_guide/chNN.html` to `study_guide/chNN.pdf` and can render the result for QA;
   - `browser`: use the repository fallback with a detected local Edge/Chrome;
   - `html`: HTML-only request, so no PDF backend is required.
4. Run the content/backend-aware preflight after the chapter sources exist but **before** invoking the renderer:

   ```text
   python scripts/check_deps.py --workspace <ws> --chapter <N> --artifact-mode visual --pdf-backend <native|browser|html>
   ```

   Formula conversion becomes required only when the selected chapter actually contains standard `$...$` / `$$...$$` math. Edge/Chrome becomes required only for `--pdf-backend browser`. On exit 5, explain only the dependency that this exact path needs and obtain consent before installing it.
5. After the preflight succeeds, render the selected chapter HTML:

   ```text
   python scripts/study_guide_render.py --workspace <ws> --chapter <N>
   ```

6. Open `study_guide/chNN.html`. Confirm that formulas are native MathML, images are data URIs, all four content layers are present, and every empty layer is described honestly.
7. For PDF/print output, create the PDF only after HTML validation. For `native`, use the installed adapter to print/convert the validated HTML to the canonical `study_guide/chNN.pdf` path without rewriting course content. For `browser`, run:

   ```text
   python scripts/study_guide_render.py --workspace <ws> --chapter <N> --pdf
   ```

   Do not call `--pdf` for `native`; that flag specifically selects the repository's local-browser print implementation.
8. Render every PDF page to an image with the selected adapter and inspect every page. Verify formula layout, glyphs, clipping, image clarity, prompt-before-answer order, expanded print answers, tables, code, margins, page breaks, orphan headings, and abnormal blank space. Fix the source or renderer, regenerate, and restart inspection from page one after any defect.

## Output Contract

- Produce `study_guide/chNN.html` as an offline document with inline CSS, native MathML, and data-URI images. It must require no network, CDN, script, or browser extension.
- Dispatch headings, empty-layer notices, prompt/answer labels, disclosure text, provenance labels, and the HTML language tag from the persisted language. English mode must contain no Chinese control-plane UI. Bilingual mode must mirror both interfaces and both canonical provenance labels.
- Place prompt-side assets before the prompt. Place answer-side assets only in the later answer area. Put quiz answers in expandable `details`; print CSS must expose their contents.
- Retain `source_file`, page numbers, and the canonical provenance labels from the workspace.
- Produce `study_guide/chNN.pdf` only when the selected backend succeeds. On the repository `browser` path, this means `--pdf` exited 0. On a `native` path, require the adapter to confirm the canonical output and then run the same full-page QA. Never claim that a PDF exists merely because HTML generation succeeded.
- After full visual acceptance, return a 3-5 line digest plus links to the HTML and, when present, the PDF.

## Boundaries

- Do not render the entire course to bypass chapter lazy-loading.
- Do not run because a host appears to have a low/high subscription. The only standing switch is canonical `artifact_mode=chat|visual`; missing and unknown values fail safe to `chat`.
- Do not silently machine-translate verbatim source quotations, official question text, or teacher-provided answers. Preserve such quoted evidence in its original language and mark it explicitly as an original-language quotation when it differs from the selected reply language. This exception applies only to faithful source evidence: every agent-generated heading, bridge sentence, explanation, notice, solution, and summary MUST follow the selected `中文` / `English` / `双语` contract. In particular, English purity does not require rewriting a quoted Chinese exam question, but it does forbid Chinese agent prose around that quotation.
- The raw-material preflight (`check_deps.py --materials <dir> --artifact-mode visual`) cannot know the final chapter content or host PDF backend and therefore must not trigger speculative MathML/browser installation. Before visual generation, rerun it with `--workspace <ws> --chapter <N> --pdf-backend <native|browser|html>`. If that chapter contains formula content without the audited `latex2mathml==3.60.0`, the preflight/renderer prints the exact pinned command. Explain the dependency and obtain consent before installation; never install silently. Never present an older `chNN.html` as the result of a failed render.
- Reject URL, absolute, parent-traversal, missing, unreadable, or symlinked assets and paths. The sole compatibility exception is `../assets/<safe-relative-tail>` inside a selected `references/wiki/*.md`, because `build_visual_index --apply-wiki` emits that shape. Resolve it only to `<ws>/references/assets/<safe-relative-tail>`, reject every additional `..` and every symlink component, and never extend this exception to teaching examples, quiz items, or notebook content.
- A missing local browser blocks only the selected `browser` backend. It does not block a successfully probed `native` adapter. Any failed PDF route is an HTML-only degradation, not a PDF success.
- Do not auto-download an untrusted third-party skill. Use only an adapter declared by the repository capability registry and confirmed by a successful probe.
