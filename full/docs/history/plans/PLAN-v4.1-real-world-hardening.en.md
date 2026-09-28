# v4.1 Real-World Hardening Plan

English · [中文](PLAN-v4.1-real-world-hardening.md)

> **Historical status: completed and shipped in v4.1.** This document is kept only as a record of the real-use audit and its implementation. It is no longer the current implementation spec.
>
> Status: implementation source of truth. This document was written before any code change; every later implementation, test and PR description must trace back to it.
> Basis: one real one-day cram run for EEC 160. The materials include lecture notes for 9 chapters and several homework sets; chapter 1, `ch01.pdf`, has 95 pages, all of which were visually re-checked page by page.
> Target repository: `ChenSiyun1234/universal-examprep-skill`; the work is submitted as a standalone draft PR against its `main`.

---

## 1. The real usage path in this run

1. Installed v4.0 from GitHub and checked the tag/commit.
2. Ran dependency preflight, material parsing, knowledge-base build, bank validation, visual indexing and alert takeover on the course folder.
3. Initialized `study_state.json`, writing the learning mode, time budget and bilingual preference in one step.
4. Lazy-loaded the chapter 1 wiki, picked one standard bank example, generated a bilingual explanation and wrote it to the notebook.
5. Updated phase progress.
6. After the student noticed that "the whole chapter has no images and far too few examples," re-audited all 95 pages of chapter 1 visually, page by page, and traced the chain of responsibility.

This path covers "install → ingest → workspace → tutor → notebook → progress → audit," which is enough to expose contract gaps between modules. It does not yet cover actual answer grading, mistake review or cheat-sheet compilation.

---

## 2. Defects found

| ID | Severity | Defect | Real evidence | Root cause |
|---|---|---|---|---|
| D1 | P0 | Version identity drift | At the v4.0 tag, the root `SKILL.md` still declared `metadata.version=3.0`, so the first install was misidentified as an old version | No consistency gate between the release tag and the skill metadata |
| D2 | P0 | Severely insufficient visual coverage in the wiki | Chapter 1 has 19 manually confirmed visual pages; the wiki embeds only p58, a coverage of 1/19 | D5 renders only pages whose lines start with `Figure/Table/图/表 + 编号` (a caption word plus a number), and does not reuse the general visual index |
| D3 | P0 | Visual gaps on the answer side raise no alert | The 2-D sample-space figure for Example 1.14 on p50 and the probability tables for Quiz 1.5 on pp72–73 have no answer assets | `build_visual_index.py` records `answer_pages_visual`, but suspects only checks prompt-side `q_hits` |
| D4 | P0 | `visual_suspects=0` is easy to misread | The report says 0, yet the wiki still lacks 18 visual pages and the answer side has gaps too | The metric's name and summary do not state that it covers "the prompt side only, and only the current canonical bank" |
| D5 | P0 | Teaching examples and gradable items are mixed into one layer | The source PDF has 25 numbered Examples; post-processing moved 13 of them (52%) out of the canonical bank | No separate teaching-example index; AI takeover can only choose "keep in the bank" or "exclude entirely" |
| D6 | P0 | Phase completion has no evidence gate | After teaching a single example with no figure, `set-check` could mark the whole chapter complete | The checklist only has `done: bool`, with no wiki/visual/example/notebook evidence |
| D7 | P1 | A validator pass is mistaken for complete content | Zero schema/path errors and zero visual suspects were written up as `overall_status=ready` | The validator does not check source-example retention, wiki visual coverage or answer-side assets |
| D8 | P1 | Degraded visual text is not reported explicitly | The vector figure on p50 turned into 12 NUL bytes and scattered coordinate characters in the wiki | Successful text extraction is treated as successful page semantics; there is no check for binary/NUL content or loss of spatial structure |
| D9 | P1 | The visual heuristic has explainable false positives and false negatives | The ch01 index reports 18 pages; manual review confirms 19, with 6 misses and 5 false positives | The recall-first keyword/drawing-count heuristic has no coverage confidence and no manual review list |
| D10 | P1 | Urgent mode is misread as "it's fine to teach less" | `≤1天` ("≤1 day") was used to justify heavy compression and an early check-off | The time budget only defines questioning cadence, not the minimum completion evidence for each tier |
| D11 | P0 | Math formulas reach the student as raw LaTeX or pseudo-delimiters | The actual notebook used `(A\\cup B)` and `[P(A)=\\frac{...}{...}.]`; local Markdown showed the backslash commands verbatim | The skill did not specify standard math delimiters, so the executing agent wrapped LaTeX in ordinary parentheses/brackets; the existing HTML renderer also does not parse math |
| D12 | P0 | The Markdown source of truth is mistaken for a finished human-facing textbook | A `.md` file cannot guarantee that the host supports math extensions, and nothing arranges the wiki, slide figures, examples, quizzes and plain-language explanations into one directly readable layout | No separate student-facing rendering layer and no post-render visual acceptance; Markdown carries two conflicting jobs at once: machine source and final UI |
| D13 | P1 | PDF capability is coupled to a specific agent/vendor | Codex, Claude Code and generic Agent Skills environments have different native PDF capabilities, install entry points and licenses; a single download instruction cannot safely cover every runtime | No capability adapter layer, official-source allowlist, version review record or "no silent download" supply-chain policy |
| D14 | P1 | Automatically generated visual study materials cannot respect quota preferences | A low-quota user only wants v3-style chat teaching yet might get HTML/PDF built for every chapter automatically; a high-quota user wants a print version straight away | The agent cannot reliably read the subscription tier, and the framework has no persisted artifact preference, independent of learning mode, with a one-shot override rule |
| D15 | P0 | Whole-page re-embedding can leak answers early | When prompt and solution share a page, or when an answer-only page was embedded into the wiki by an older version or by hand, a generic full-page screenshot exposes the solution before the question is asked | The visual index only knows "visual page"; there are no global prompt/answer page roles and no fail-closed gate for shared pages |
| D16 | P0 | The teaching-example retention baseline can be shrunk by rewriting the report | When only the latest `ingest_report.json` serves as the retention denominator, a smaller snapshot or a hand-rewritten report can make already discovered examples drop out of acceptance | No separate, append-only, per-chapter-checked source of truth for the teaching baseline |
| D17 | P1 | Generated-file writes and link boundaries are not robust enough | A failure midway through ingest/visual output can leave half-written files; symlinked or hard-linked outputs can carry workspace writes through to external files | Write paths do not consistently use atomic replacement, and the final output step does not fully reject links/special files |
| D18 | P1 | Visual-artifact preflight blocks unnecessarily, and the PDF capability routing order is contradictory | A text-only chapter that chose `visual` was still forced to require MathML; with a native PDF skill already present, the run could still be stopped first by a missing Edge/Chrome | The dependency `needed` check looks only at `artifact_mode` and does not read the current chapter's actual formula content; the instructions call the browser `--pdf` path before choosing the native/browser adapter |

### 2.1 Where responsibility lies

- The original PDFs render normally; the materials are not damaged.
- Line-start recognition of Example/Quiz is complete: both `raw_input` and the wiki keep all 25 Examples and 7 Quizzes in chapter 1.
- The 13 missing examples disappeared during the AI cleanup after ingest; no repository script required deleting them.
- The v4.0 visual rules were a contributing cause, but direct responsibility for "declaring ready" and "checking off early" lies with the executing agent, which substituted a narrow metric for acceptance against the user's goal.

---

## 3. Features that were used and proved valuable

| Feature | Result in use | Keep/strengthen |
|---|---|---|
| GitHub install with a traceable commit | Confirmed that the installed content matched the v4.0 commit | Add a version-consistency test and remove the metadata ambiguity |
| Dependency preflight | PDF text, rendering and browser dependencies were confirmed once, before ingest | Keep; add a description of visual capability levels |
| PDF text extraction and page-level provenance | All 95/95 pages of ch01 reached the wiki, with page-number comments preserved | Keep; visual degradation must be reported separately and cannot be covered by text success |
| Example/Quiz markers and Problem/Solution pairing | All 25 Examples and 7 Quizzes in chapter 1 were recognized, and separate solution pages were paired correctly | Keep; output a separate teaching-example index |
| Prompt-side visual asset gate | Diagram items that clearly depend on a figure have prompt/answer assets and fail-closed rules | Keep; extend to the answer side and the wiki side |
| Alerts and the AI takeover list | `missing_answer_ids` successfully exposed 13 example passages with no separate Solution | Keep; takeover actions must distinguish "not gradable" from "not teachable" |
| `study_state.json` as the single source of truth | Mode, time, language and progress persist, and the md view renders automatically | Keep; add structured evidence for phase completion |
| Workspace registry | The materials folder and the review workspace location are unambiguous | Keep |
| Notebook-first | Bilingual explanations are written to disk first, and the index links work | Keep; the completion gate checks notebook evidence |
| Provenance labels and bilingual dispatch | Explanation provenance blocks and the Chinese/English mirror output reliably | Keep |
| exam-audit + PDF visual check | After the user questioned the result, a read-only audit assigned responsibility and pinpointed the exact pages and code paths | Strengthen into an automatic post-ingest completeness gate instead of an after-the-fact fix |
| Validator and question type/keyword/difficulty checks | The canonical bank is gradable, fields are complete and the selectors run | Keep; state clearly that its verdict covers only schema/bank health |

---

## 4. Features not yet used or not yet verified

The following capabilities cannot be claimed as working in this real run just because "tests exist":

- actual question drawing, student answers, grading and the two-wrong-answers-in-a-row branch in `exam-quiz`;
- mistake recording, the `mistakes/` mirror and the `exam-review` mine-sweeping pass;
- automatic capture and restatement review in the confusion tracker;
- entering and leaving the knowledge window, plus hard-item rechecks, in the `3-7天` ("3–7 days") and `>7天` ("more than 7 days") tiers;
- restricted source scope, the temporary-override notice and restoring the mixed pool;
- the real item chain for diagrams: "run the algorithm first, then draw";
- actual recall of the RAG retrieval tool during student Q&A (this run mostly read the current chapter's wiki directly);
- cheat-sheet compilation, PDF rendering to a set page count, and print visual acceptance;
- the file-less/web fallback;
- long-session drift, restart recovery and multi-round learning loops.

This PR adds targeted regression tests only for the related changes; it does not pretend these features have passed real verification. A separate end-to-end course run should follow.

---

## 5. Design decisions in this PR

### 5.1 Visual coverage is split into three sides

Visual completeness must be counted separately for:

1. **The wiki side**: whether each visual page in the materials is embedded in the matching wiki, or explicitly placed on the takeover list;
2. **The prompt side**: whether each visual item has a displayable `question_context`;
3. **The answer side**: whether each visual answer page has an `answer_context` that is shown only at the solution stage.

`suspects` stays as the prompt-side compatibility field, and new, explicitly named fields `prompt_suspects`, `answer_suspects` and `wiki_visual_coverage` are added. The report must state each denominator.

### 5.2 Wiki figures reuse the general visual index

- Stop treating the caption regex as the full set of visual pages.
- Add an idempotent `--apply-wiki` to `build_visual_index.py`: render the detected visual pages and re-embed them at their original positions in the matching wiki, using the `<!-- source.pdf p.N -->` page anchors.
- Default cap of 30 pages per chapter; going over the cap is never silent: the overflow is listed in full in coverage missing/warnings and handed to the AI or the user.
- Keep the caption-only builder behavior for compatibility with old callers, but the ingest workflow must run the wiki-apply stage of the visual index.
- Never attach answer assets as prompt assets; roles and display order stay fail-closed.

### 5.3 Separate layers for teaching examples and the standard bank

- The material builder keeps producing the existing `quiz_bank` for compatibility.
- It also produces a `teaching_examples` snapshot; ingest writes it to `references/teaching_examples.json`.
- Each entry is tagged with `teaching_role=paired_problem|worked_example`, source pages, answer pages and assets.
- A complete worked demonstration without a separate Solution may stay out of standard grading, but it must not disappear from the teaching index.
- Add a per-chapter listing tool; the tutor reads only the current chapter's entries and does not load the whole-course index into context.

### 5.4 Phase completion requires structured evidence

- Add a backward-compatible `phase_evidence` to `study_state.json`.
- Add an official command that records the current phase's wiki, visual, teaching-example and notebook evidence.
- In a new workspace that has visual/teaching manifests, `set-check` must not complete a phase on a boolean alone; it fails loudly when evidence is insufficient.
- Old workspaces without manifests stay compatible but get an explicit warning.
- `≤1天` may skip the student Q&A-style checkpoint, but it may not skip the wiki/visual/example/notebook coverage evidence.

### 5.5 "Usable" and "complete" are kept apart

- The validator's schema/path verdict is still called "runnable."
- Add a completeness summary: number of source examples, teaching-index retention rate, canonical gradable rate, wiki visual coverage, prompt/answer asset coverage, and items not yet taken over.
- The upper layer may write `ready` only when completeness blockers are 0; otherwise it uses `usable_with_gaps`.

### 5.6 Markdown as the source of truth, HTML/PDF as the human-facing textbook

- Markdown remains the searchable, diffable, traceable machine source of truth, but it no longer claims to be the finished textbook by default.
- All newly written math uses the standard `$...$` / `$$...$$` delimiters; pseudo-delimiters such as `(\\frac...)` and `[\\sum...]` are banned. The validator warns loudly on suspicious raw/pseudo LaTeX.
- Add a per-chapter renderer that produces a self-contained `study_guide/chNN.html`; it converts LaTeX offline into browser-native MathML, and when the conversion dependency is missing it exits explicitly with the install command, never silently leaving raw formulas in place.
- The textbook is organized as "plain-language concepts → formulas and symbol explanations → the current chapter's teaching examples → quiz prompt figures → expandable solutions/answer figures → in-depth notebook explanations → original-page provenance"; images are embedded in the HTML, and prompt figures always come before answer figures.
- The textbook UI reads `study_state.json.language`: Chinese, English and bilingual each get their own titles, empty-layer notices, prompt/answer labels and canonical provenance. The renderer does not translate factual content on its own; bilingual body text must first be persisted by the tutor.
- A local Edge/Chrome can optionally print a comfortable reading PDF; both HTML and PDF need visual acceptance. The renderer lazily reads only the specified chapter and does not pack the whole course into one artifact.

### 5.7 PDF capability uses agent adapters instead of copying third-party skills

- The framework provides its own vendor-neutral `exam-study-guide` workflow and deterministic render scripts, so HTML can be produced even without a native PDF skill, and a PDF is output when a local browser is available.
- Add a separate, machine-readable PDF capability registry that spells out, for each of Codex, Claude Code and generic Agent Skills runtimes, the preferred capability, official source, reviewed version, license boundary and fallback path.
- Codex prefers an installed native `pdf` skill; Claude Code points to Anthropic's official `document-skills` plugin; the generic implementation follows the Agent Skills open specification and uses this repository's skill.
- Do not copy or adapt third-party implementations whose licenses do not allow redistribution, do not treat deprecated repositories as recommended install sources, and do not run network downloads during a student's review session unless they are confirmed and pinned to a reviewed version.
- External links only provide install/discovery; this framework's correctness, safe path checks, prompt-figures-before-answer-figures ordering and page-by-page visual acceptance cannot be outsourced to a third-party skill.

### 5.8 Quota-friendly textbook output modes

- Add a separate, persisted `artifact_mode` whose only canonical values are `chat` / `visual`, kept apart from learning mode, time budget and language. When an old workspace lacks the field, it is treated as `chat`, preserving v3-style quota-saving behavior.
- `chat` (chat, quota-saving) is the safe default: teach normally and save the necessary state/notebook, but do not automatically compile chapter HTML/PDF or automatically print a cheat sheet. When the user explicitly asks once for HTML/PDF/a print version, that can override temporarily without permanently changing the preference.
- `visual` (visual study materials) can only be chosen explicitly by the user (e.g. "I don't care about tokens," "give me a print version for every chapter from now on"); each completed chapter automatically gets HTML + PDF with page-by-page visual acceptance. Installing dependencies still needs separate consent; this mode never triggers a silent download.
- The agent neither reads nor guesses the subscription plan; a natural-language choice is persisted through the official `update_progress.py set --artifact-mode <chat|visual>`. At run time an unknown value fails safe back to `chat` with a warning.

### 5.9 Content-aware, backend-aware artifact preflight

- The first materials preflight lists as hard dependencies only the PDF reading/page rendering backends the raw materials actually need; chapter formulas not yet on disk and PDF backends not yet chosen are shown as `unknown` and do not prompt an install.
- Once the current chapter's source of truth is ready, use `--workspace <ws> --chapter <N>` to scan only that chapter's wiki, teaching examples, quizzes and notebook; the pinned MathML converter is required only when standard `$...$` / `$$...$$` formulas are actually present.
- For PDF, first choose `native` / `browser` / `html` from the capability registry, then preflight with `--pdf-backend`; only the `browser` path treats Edge/Chrome as a hard dependency. A probe error exits as `probe_error` and must not masquerade as "please install some dependency."
- The fixed execution order is "explicit artifact preference → backend probe/selection → current-chapter dependency preflight → HTML → PDF → page-by-page visual acceptance"; the native backend consumes the validated HTML and must not fail because the repository's browser fallback is missing.
- The behavior smoke tests cover both positive and negative traces: chat does not auto-render, explicit visual, a one-shot PDF does not pollute the long-term state, a subscription name does not trigger a switch, and the backend is chosen before preflight.

---

## 6. Implementation steps

### Step 1 — Plan and failing tests

- [x] Write this plan.
- [x] Add targeted failing tests or fixtures for D1–D17.
- [x] Record the existing test baseline to make sure development does not start on top of existing red tests (full `unittest` exit 0).

### Step 2 — Visual index, answer assets and wiki re-embedding

- [x] Extend `image_question_index.json`: distinguish prompt/answer suspects.
- [x] Let `--apply` safely add answer-side assets, with the role fixed to `answer_context`.
- [x] Implement an idempotent `--apply-wiki` with a per-chapter cap.
- [x] Write `wiki_visual_coverage`, listing detected/embedded/missing, and defer answer-only pages to their own denominator.
- [x] Make the validator/audit raise explicit blockers for coverage gaps, manual exposure of answer pages, and prompts and solutions sharing a page.
- [x] Add a warning for NUL/binary text degradation.
- [x] Derive prompt/answer page roles globally: answer-only pages stay out of the wiki; a page shared by prompt and solution can only be unblocked by a reviewed prompt crop.

### Step 3 — Teaching-example retention layer

- [x] The material builder outputs `teaching_examples`.
- [x] Ingest writes `references/teaching_examples.json` and its statistics.
- [x] Add an append-only `references/teaching_baseline.json` so that a smaller snapshot/report cannot shrink the retention denominator.
- [x] Add a per-chapter listing tool to avoid loading the whole index.
- [x] The validator checks index IDs, sources, asset roles and the retention rate.
- [x] The tutor/ingest/audit contracts state clearly: moving an item out of the gradable bank does not mean moving it out of the teaching layer.

### Step 4 — Phase completion gate

- [x] Add `phase_evidence` to the state schema; migration does not lose old state.
- [x] Add an official evidence command and path-safety checks.
- [x] When new manifests exist, `set-check` verifies the required evidence, including the answer-exposure and shared prompt/solution page blockers.
- [x] Update the bilingual progress rendering, help text and behavior tests.

### Step 5 — Version and verdict wording

- [x] First fix the v4.0 tag being misreported as metadata 3.0; when v4.1 ships, bump the metadata to 4.1 and add a release-tag consistency gate.
- [x] Limit the documentation wording for `visual_suspects=0` and validator 0 warnings to their actual scope.
- [x] Add the `ready / usable_with_gaps` decision contract.

### Step 5B — Readable math and chapter textbook artifacts

- [x] Specify and test standard Markdown math delimiters; detect raw/pseudo LaTeX.
- [x] Add a per-chapter HTML textbook renderer: offline MathML, prompt/answer image roles, teaching examples, quizzes, notebook and sources.
- [x] Add optional PDF output, fail-loud behavior on missing dependencies, and path/image safety tests.
- [x] Change the tutor/cram/help contracts to "persist the source of truth first, then generate and visually accept the human-facing textbook."
- [x] Use the formula shapes from the real chapter 1 notebook as read-only regression input, without committing course content.
- [x] Cover all three textbook UIs, Chinese / English / bilingual; the English UI contains zero Chinese, and the bilingual UI shows the canonical labels for both sides.

### Step 5C — Cross-agent PDF capability adapters

- [x] Add a machine-readable capability registry and adapter notes for maintainers, distinguishing Codex, Claude Code and generic Agent Skills.
- [x] Pin and record the reviewed official source commits; third-party skills are only linked, and restricted implementations are not copied.
- [x] Specify the routing order: native capability first, framework fallback next, fail loudly when the capability is missing, and install only with user confirmation.
- [x] Add tests for the registry schema, links and license fields, and make sure the distribution package includes the adapter files and the in-house `exam-study-guide` skill.

### Step 5D — Quota-friendly output modes

- [x] Add `artifact_mode=chat|visual` to i18n/state/validator; old state defaults to chat, and display words and aliases round-trip.
- [x] Add `set --artifact-mode` and Chinese/English help; the subscription tier must never be treated as a detectable input.
- [x] Route the tutor/study-guide/cheatsheet contracts by mode, and allow an explicitly requested one-shot override.
- [x] Add regression tests for the default, aliases, migration, fail-safe handling of unknown values, and the official CLI.

### Step 5E — Content- and backend-aware dependency routing

- [x] Add chapter formula detection via `--workspace + --chapter`; chapters without formulas do not require MathML, and Markdown code regions are not misdetected.
- [x] Add `--pdf-backend auto|native|browser|html`; only an explicit browser backend lists Edge/Chrome as a hard dependency.
- [x] Probe failures use `probe_error`/exit 2, do not enter `missing_needed`, and do not show a misleading install command.
- [x] Unify every entry point as "choose backend → current-chapter preflight → HTML → PDF → page-by-page acceptance," and add deterministic positive and negative behavior smoke cases.

### Step 6 — Verification

- [x] Run the targeted visual, builder, ingest, validator and state tests.
- [x] Run the full `unittest` suite (on the clean v4.1 release branch based on the author's `main`, the final count was 1441 tests, 27 skipped, exit 0; the release-only tag gate was run separately and passed in a `v4.1` environment).
- [x] Take over the first CI round of the draft PR: fix the classification order for symlink errors, and the Markdown resource path escaping its root caused by mixing Windows 8.3 and long paths; add a deterministic alias regression test.
- [x] Run the skill structure/distribution build checks.
- [x] Run end-to-end regression with synthetic PDFs/fake backends that contain no real course content.
- [x] Use fresh subagents for forward tests that do not leak the expected answers, and re-review the three D18 P1 fixes a second time.

### Step 7 — Release

- [x] Review the full diff and confirm it contains only the scope of this plan.
- [x] Stage files explicitly and create a single-purpose commit.
- [x] Push `codex/eec160-usage-fixes` to the fork.
- [x] Open a draft PR against `ChenSiyun1234/universal-examprep-skill:main`.
- [x] The PR body lists the root causes, user impact, compatibility, tests, and the features still not verified in real use.

---

## 7. Acceptance criteria

1. When a synthetic course contains "a vector-figure page with no Figure caption," the visual index finds it and re-embeds it after `--apply-wiki`; any page not re-embedded must appear on the missing list.
2. When the prompt is plain text and the answer page contains a figure, an `answer_suspect` is produced; after `--apply`, only an `answer_context` is added, and it is never shown early.
3. A bare Example without a separate Solution still goes into `teaching_examples.json` and can be queried by chapter; whether it enters the canonical bank does not affect its teaching reachability.
4. After a worked example is removed from the canonical bank, the validator can prove that the teaching index still keeps it; if it is missing from both, it warns.
5. When new manifests exist, `set-check` without phase evidence fails and does not pollute `study_state.json`.
6. `≤1天` allows a checkpoint without interaction, but visual/example/notebook evidence is still required.
7. The root `SKILL.md` declares 4.1, and the release job rejects a tag that does not match the metadata.
8. Old workspaces and old raw input remain readable; all new fields are backward compatible.
9. The full test suite passes, and the distribution package includes the new runtime scripts/contract files.
10. A chapter containing `\\frac`/`\\sum` appears as MathML in the HTML, not as raw backslashes; when the math conversion dependency is missing, the command exits nonzero and leaves no fake finished product behind.
11. The chapter textbook shows plain-language explanations, standard formulas, teaching examples, quiz prompt/answer assets and locatable provenance (file + page/item number) together; prompt assets come before answer assets. To stay offline, self-contained and path-safe, external Markdown links may degrade into copyable reference text instead of being kept as clickable links.
12. The same textbook task has an explicit and distinct capability route in Codex, Claude Code and generic agent environments; external skill sources are auditable and never downloaded or installed silently, and when no native capability exists there is still this framework's fallback or a clear failure message.
13. When `study_state.language=双语` ("bilingual"), the chapter textbook UI is bilingual Chinese/English; with `English`, the UI contains no Chinese labels. The renderer only compiles persisted body text and does not pass off unlabeled machine translation as the textbook's original text.
14. An old workspace without `artifact_mode` does not automatically generate HTML/PDF; `chat` mode produces output temporarily only on an explicit one-shot request, and `visual` mode generates and accepts the PDF after each completed chapter; no path guesses the subscription or installs silently.
15. `visual` preflight for a text-only chapter does not require MathML; the `native` backend does not require a local browser, while the `browser` backend blocks explicitly when the browser is missing; probe errors do not turn into install prompts, and the behavior traces guarantee that preflight runs before rendering and that the state stays `chat` after a one-shot PDF.

---

## 8. Risks and non-goals

- Visual classification is still a deterministic heuristic and cannot pose as AI semantic vision; the report must keep a confidence value and an entry point for manual review.
- `--apply-wiki` makes the workspace larger, so it needs a per-chapter cap, idempotent naming and a complete missing list.
- This PR does not force every worked example into a gradable item, and it does not generate fake official answers.
- This PR does not rerun the full EEC 160 course or commit course materials to the repository; tests use only synthetic fixtures.
- This PR does not claim that chains not yet exercised for real, such as quiz/review/cheatsheet, have passed hands-on verification.
- This repository does not guarantee the availability or upstream compatibility of third-party PDF skills; the registry records a reviewed snapshot, and any upgrade must recheck the license, install entry point and behavior contract.
- `artifact_mode` is a resource preference declared by the user, not the result of detecting a plan; PDF rendering mostly uses local compute, but organizing more detailed study materials can still increase context/generation volume, so the default is conservative.
- The existing safety contracts stay unchanged: provenance labels, prompt figures before answer figures, scope filtering, notebook-first, and so on.
