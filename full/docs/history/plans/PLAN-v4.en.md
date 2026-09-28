# v4 Full Refactor Plan: From "Exam-Prep Skill" to "Exam-Prep Engine"

English · [中文](PLAN-v4.md)

> **Historical status: completed and shipped in v4.0.** This document is kept only as a record of design and decisions; it is no longer the current implementation spec. Paths and repository statistics in it reflect the state at the time.
>
> Positioning: this is not a continuation of v3 but a complete refactor held to the standard of a new project. This document is the single source of truth for planning: goals, architecture, the phased roadmap, acceptance criteria and risks are all here.
> Basis: before writing, the existing repository went through a full 5-track audit (scripts internationalization / skill text surface / wiki-RAG / output surface / distribution size). Every "current state" claim in this document is backed by real files and line numbers, not guesswork.

---

## 0. Six Goals (the purpose of this refactor)

| # | Goal | In one sentence |
|---|---|---|
| G1 | **Fully layered language** | At first contact the student picks one of three options (中文 / English / 双语, i.e. Chinese / English / bilingual); from then on all skill text and script output use only the chosen language, and Chinese and English text are physically separated into different folders |
| G2 | **Wiki knowledge base as RAG** | Upgrade from "read whole chapters by file name" to lightweight retrieval "with an index, metadata, scoring and an abstention threshold" |
| G3 | **Answers saved to disk (notebook)** | Explanations and grading no longer "vanish when the chat ends"; all of it goes into a Markdown notebook organized by chapter with a table of contents, and the student can jump back from the contents at any time |
| G4 | **Mistake book with a table of contents** | Mistakes are upgraded from a "status line" to "complete mistake notes written up per chapter", cross-linked with the contents |
| G5 | **Cheatsheet as a compiler + finished PDF** | The pre-exam cheatsheet is no longer generated out of thin air but deterministically "compiled" from the notebook + mistake book + knowledge-point window, and the final output is a **print-quality PDF with the page count the user specifies** |
| G6 | **Slimmer distribution** | Students install a runtime package of ~35 files, not the full 326-file, 3.4 MB development repository |
| G7 | **Controlled workspace location + first-run onboarding** | Workspaces are created only at a path the user explicitly confirms and are remembered persistently; once the skill activates, it proactively asks where the materials folder is / teaches the student how to use it |

**Non-goals** (explicitly out of scope, to keep focus): no third-party dependencies in the core path (heavy backends such as embedding models are optional plugins only); no dropping Codex/Cursor/web compatibility (the AGENTS.md and web prompt routes stay); no breaking old workspaces (always auto-migrate + back up); no rewriting the benchmark (it is reused as the v4 regression gate).

---

## 1. Current-State Checkup (summary of audit findings)

### 1.1 The Actual Structure of the Language Mixing

After auditing all 12 scripts (5,940 lines) and 14 skill text surfaces (1,133 lines), the mixing turned out not to be evenly spread; it falls into three classes:

- **Class A: console messages** (~440 user-visible strings; estimate basis = about 180 funnel call sites × multi-line/multi-string expansion; the exact list is the msgid catalog that P1 produces). All of them go through each script's `_die()/warn()/err()` funnel, so they **can be extracted cleanly**;
- **Class B: persisted schema values.** The Chinese strings are themselves the data contract: `mode="零基础从头讲"` ("start from zero") in `study_state.json`, the window states `在窗口/窗口外/已实测` (in window / out of window / tested), the mistake-row status `待复盘` (to review), and the `阶段 N` (phase N) table in the generated `study_plan.md`, which 3 scripts read back and parse. **These cannot be "translated"; they can only be "replaced with language-neutral codes + migrated"**;
- **Class C: input-recognition vocabularies.** Chinese and English regexes for classifying file names and content (for example `真/假/对/错` (true/false/right/wrong) for true/false questions). **These must always carry both Chinese and English; localizing them would itself be a bug**.

The good news (verified by the audit): all JSON keys are already English, all generated file names are already ASCII, and machine-readable warnings already use ASCII prefixes such as `no_materials:`. **Chinese exists only in "values"**, so the foundation for layering is already in place.

The bad news: the enum vocabularies are hard-coded separately in three places, `update_progress.py`, `select_hard_questions.py` and `show_question_assets.py` (there is no shared constants module), and they have started to drift; about **1,035 test assertions pin the exact Chinese message text**; and the policy currently locked in by `docs/localization.md` + `tests/test_localization_boundary.py` is precisely "defer the locales/ split". The first step of v4 is to formally rewrite that policy.

### 1.2 8 Gaps in the Wiki as RAG

1. **Chunk granularity = a whole chapter**. Measured on the PSYC workspace, each chapter is 22,000–56,000 characters; worse, each chapter is **a single line of unstructured text** that even starts with scraper leftovers like `p { font-size: 14px; }`, so there is not even the fallback of "read the relevant section".
2. **No retrieval index at all**. Choosing a chapter = file name (`ch01.md`…`ch20.md`, zero semantics) + the phase pointer + whatever the agent improvises.
3. **No chunk-level metadata**. Page-number tracing exists only on question-bank items; a wiki paragraph cannot answer "which page did this sentence come from".
4. **No cross-language bridge**. The materials are in English and the student asks in Chinese (「旁观者效应」 → "bystander effect"); it all rests on the model's implicit knowledge, which can be neither measured nor controlled.
5. **No scoring and no second hop**. When the current chapter has no answer, there is no sanctioned second hop (SKILL.md actually forbids leaving the current chapter); the only retrieval contract in the repository with a `min_score` abstention threshold sits unwired in `spike/llamaindex_rag/`.
6. **Ingest does no noise handling**. It writes to disk verbatim, so CSS leftovers, verbal filler and repeated headings all end up in the knowledge base.
7. **No incremental rebuild**. Adding one piece of material = a full overwrite, and the existing 🟢/🟡 paragraph labels in the wiki are silently destroyed.
8. **No retrieval evaluation hook**. The benchmark records only final answers; which chapter the agent actually opened has never been logged, even though the gold labels already carry `source_file` and a verbatim `supporting_span`, so the retrieval hit rate **could be measured right now**.

### 1.3 Output Surface: Every Answer Evaporates

Conclusion after an item-by-item inventory: **everything a student most wants to look back at while reviewing lives only in the chat**. Seven-step walkthroughs, grading feedback, hints and review checklists are all chat-only; the only "Markdown file with answers" written to disk is `walkthrough.md`, generated at the very last moment. In `study_state.json` a mistake is reduced to one row, `{"id","chapter","note","status"}`; the question text, the student's wrong answer and the correct explanation are all gone.

### 1.4 Distribution: 83.6% Is Dead Weight

git tracks 326 files / 3.4 MB, of which the runtime actually needs only **35 files / 564 KB (16.4%)**. The three largest shares are all things students never use: benchmark/ 30.2%, mascot PNGs 27.4%, tests/ 24.0%. The v3.0 release attached no build artifact, and the automatic source zip is about 1.8 MB; a runtime package at the same compression ratio is only **223 KB (8 times smaller)**.

---

## 2. v4 Target Architecture

### 2.1 New Directory Tree (proposal)

```
universal-examprep-skill/
├── SKILL.md                      # Single trigger entry: thin router (language-neutral, see 2.2)
├── AGENTS.md                     # Fallback contract for generic agents (kept, repointed to the new structure)
├── skills/                       # "Control layer" of the 9 sub-skills: pure-English logic, language-neutral
│   └── exam-tutor/
│       ├── SKILL.md              # Trigger frontmatter + Workflow/Boundaries (no student-visible copy at all)
│       └── ...
├── locales/                      # ★ New: language packs, Chinese and English in fully separate folders
│   ├── zh/
│   │   ├── skills/exam-tutor.md  # All student-visible copy for this skill: seven-step template, source block, closing block...
│   │   ├── messages.json         # All script messages (msgid → Chinese)
│   │   └── templates/            # Chinese Markdown templates (notebook/progress/cheatsheet skeletons)
│   └── en/                       # English pack with the same structure (en skill copy / messages.json / templates)
├── scripts/                      # Language-neutral engine (directory name kept: renaming it core/ is purely cosmetic and would touch 34
│   │                             #   skill references + hundreds of test paths, a huge amount of review noise; "core" is only a logical label)
│   ├── i18n.py                   # ★ Shared constants + language-pack loading (canonical code ↔ display text)
│   ├── ingest.py                 # v2: chunking/cleaning/metadata/index/term list/incremental
│   ├── retrieve.py               # ★ BM25 retrieval + top-k scoring + min_score abstention threshold (standard library only)
│   ├── notebook.py               # ★ Notebook engine: append entries/rebuild contents/anchors/backlinks
│   ├── cheatsheet_render.py      # ★ Print HTML + headless-browser PDF + page-count fitting
│   ├── update_progress.py        # State machine (all enums switched to canonical codes + workspaces registry)
│   └── ... (validate/select/visual families kept)
├── prompts/ docs/                # Kept (prompts as two copies, one per language + structural alignment test; templates move into locales, see 3.3)
└── ── Development area (not in the distribution package) ──
    benchmark/  tests/  spike/  assets/  .github/
```

**Workspace** additions (student side, generated by ingest):

```
<workspace>/
├── references/
│   ├── wiki/chNN.md              # Chapter files are still written to disk verbatim, one whole chapter each (deviation during execution: section chunks
│   │                             #   became "logical chunks" inside the index rather than physically split files, so no existing contract breaks;
│   │                             #   retrieval returns chunk text directly; physical splitting goes to the backlog for re-evaluation)
│   ├── wiki_meta.json            # ★ Per-chapter metadata: content hash/chunk count/chapter number (foundation for incremental rebuilds)
│   ├── retrieval_index.json      # ★ BM25 inverted index (section-level logical chunks, built at ingest time)
│   ├── terms.json                # ★ Chinese-English term list for this course (cross-language retrieval bridge)
│   └── quiz_bank.json            # Kept
├── notebook/                     # ★ Notebook (G3)
│   ├── index.md                  #   Master contents: chapter → anchor link for each explanation/grading entry
│   └── ch02.md                   #   All saved answers for this chapter (seven-step walkthroughs/grading feedback, with anchors)
├── mistakes/                     # ★ Mistake book (G4)
│   ├── index.md                  #   Mistake contents: grouped by chapter + status overview
│   └── ch02.md                   #   Complete mistake notes: question/wrong answer/cause/correct solution/source
├── cheatsheet.md                 # ★ G5 compiled output (replaces walkthrough.md)
└── study_state.json              # Kept (enums migrated to canonical codes)
```

### 2.2 Key Design Decisions for Language Layering

**Skill text: fully separated by folder (adopted).** Each sub-skill is split into a "control layer" (`skills/<name>/SKILL.md`, pure-English logic the student never sees) + a "language pack" (`locales/zh|en/skills/<name>.md`, all student-visible copy). Once the combined first question at first contact (mode × time × language, keeping the existing design) has settled the language and persisted it, **the control layer loads only the matching language pack**; bilingual = the zh pack + the `> EN:` mirroring composition rule (keeping the existing T5 composition lock; no third set of copy).

Two boundaries are fixed explicitly: ① **triggering is unaffected by language layering**: the frontmatter `description` of each SKILL.md keeps both Chinese and English keywords (it already does; this is a trigger surface, not a student-visible surface, and the purity lint already exempts frontmatter), so a Chinese opening still triggers reliably; ② **"fixed" = a default binding, not a lock**: switching mid-course with `set --language` stays (an existing capability), and from the turn after a switch the new language pack is used.

**Scripts: one copy of the logic + language packs in separate folders (a correction to the original idea, for the reasons below).** Copying the Python logic into zh and en versions is a maintenance trap: the audit has already shown the enum vocabularies hard-coded separately in 3 scripts and starting to drift, and two code trees would only amplify that. The v4 approach:

- `scripts/i18n.py` becomes the single source of vocabulary: canonical codes (English snake_case, e.g. `mode=from_scratch`, `window=in_window`, `status=to_review`) + display text rendered from `locales/<lang>/messages.json`;
- The user-visible messages of the **study-loop scripts** (update_progress / validate_workspace / select_hard_questions / show_question_assets: run repeatedly while the student reviews, with output that sits next to the student) go through msgid + language pack; the console messages of the **one-off knowledge-base build scripts** (ingest / build_raw_input / the visual family: purely agent-facing, the agent reads them and restates them in the student's language) stay zh, with the exemption recorded in localization.md (narrowed during execution: converting all 440 messages to msgids was not worth the regression risk; the `no_materials:` ASCII-prefix pattern stays as the machine-readable seam);
- Scripts read `study_state.json.language` automatically to decide the output language (keeping the `--lang` override);
- **From now on persisted files store only canonical codes**; Chinese is no longer the schema. Old workspaces migrate automatically during `update_progress init/load` (following the `_MODE_MIGRATION` precedent: recognize the old Chinese enum → write the code → back up the original file).

This way Chinese and English are still fully separated "at the folder level" (`locales/zh/` vs `locales/en/`), with zero duplication of logic.

**Controlling the test blast radius (important)**: most of the ~1,035 Chinese assertions check the **exact Chinese message text**. As long as the zh language pack's copy is word-for-word identical to the current copy, and zh is the default rendering when there is no state, **most of these assertions survive untouched**. What truly must be rewritten are the assertions tied to the enum/schema migration (about 200–300) and the 12 test files that pin paths (the skills-tree audit has already listed them one by one). The "defer the split" policy in `docs/localization.md` and `test_localization_boundary.py` is formally repealed and rewritten in P0.

### 2.3 RAG Upgrade Design (mapped to the 8 gaps)

| Gap | v4 approach | Where it lands |
|---|---|---|
| 1 Granularity | ingest v2 chunks by `##` section (target 800–1,500 characters/chunk); **rebuilding structure for unstructured long text is a separate deliverable, R-slice** (see below the table) | `scripts/ingest.py` |
| 6 Noise | Clean before chunking: strip CSS/HTML leftovers, drop consecutive duplicate lines, filter verbal filler (conservative, whitelist style: better to delete too little than too much) | Same as above |
| 3 Metadata | Per-chapter metadata goes into `wiki_meta.json` (chapter number/chunk count/content hash); section titles + word-window snippets are served directly by the retrieval index (end-to-end page-level tracing goes to the backlog) | Same as above |
| 2 Index | `retrieval_index.json`: a standard-library-only BM25 inverted index + a TOC made of a one-sentence summary per section of each chapter; the agent checks the index first and reads only the sections that hit | ★ `scripts/retrieve.py` |
| 5 Scoring/abstention | Adopt the contract the spike already defined: `retrieve(q) → [Chunk{text,score,source}]`, top-k + a `min_score` threshold; below the threshold → "not covered in the materials", before any generation | Same as above (the spike's LlamaIndex embedding backend stays as an optional plugin; the core has zero dependencies) |
| 4 Cross-language | Generate `terms.json` at ingest time (a Chinese-English term list for the course, produced once by the AI during the build and open to human proofreading); expand the query before retrieval | `scripts/ingest.py` + `retrieve.py` |
| 7 Incremental | Per-chapter content hash goes into `wiki_meta.json`; rerunning ingest rebuilds only the chapters that changed, protecting existing paragraph labels | `scripts/ingest.py` |
| 8 Evaluation | Add retrieval metrics to the benchmark: the gold labels already carry `source_file` + a verbatim span → **the harness adds tool-trace logging (an explicit P3 deliverable; the current harness records only final answers)**, producing recall@k and a "chapter hit" rate; the before/after-chunking A/B runs directly on the existing three arms | `benchmark/` (reused, not rewritten) |

**R-slice (the hardest part of P3, tracked as its own item)**: the critical review pointed out that "chunk by `##`" would not fire even once on the flagship data. The PSYC chapters are degenerate text with **zero headings and a single line of 20,000–50,000 characters**, so the so-called fallback (rebuilding paragraphs/sentence groups) is actually the main path. Design: first do deterministic cleaning (strip CSS/HTML leftovers, restore line breaks), then cut chunks by sentence-group + sliding-window clustering (standard library only), with chunk boundaries preferably placed at topic-shift words or at the punctuation around lecture filler; **separate acceptance**: all 20 PSYC chapters cut into chunks of ≤2,000 characters, every chunk locatable back to its offset in the original transcript, and 100% of gold verbatim spans falling inside a single chunk (never cut across chunks).

**Old workspace compatibility**: when `retrieve.py` cannot find `retrieval_index.json`, it **degrades gracefully** to the current behavior (reading chapter files directly) and suggests rerunning ingest to upgrade; it does not force a rebuild (the original materials may no longer be on disk).

### 2.4 Notebook-Based Output (one design for G3/G4/G5)

**Core contract change**: "**save to disk first, then give a summary + link in the chat**" becomes **the default Output Contract of every student-visible skill**, not just tutor/quiz/review. Exemptions go through a whitelist and must be declared explicitly: they are limited to content that "can be regenerated deterministically from state" (the progress panel, the exam-help static quick-reference card, one-off escape-hatch hints). Any other substantive answer (including casual concept Q&A, confusion explanations and review conclusions) is always saved to disk. The saving chain works as follows:

1. Every seven-step walkthrough/grading feedback → `scripts/notebook.py add-entry --chapter 2 --type walkthrough|feedback --id q13`; the content is appended to the end of `notebook/ch02.md` (with anchor `#q13`, source block and timestamp), and the contents file `notebook/index.md` is rebuilt deterministically;
2. The chat reply = a 3–5 line summary + `完整解答：notebook/ch02.md#q13 ｜ 目录：notebook/index.md` ("full answer: … | contents: …");
3. When a mistake triggers `add-mistake`, a complete entry is written to `mistakes/chNN.md` **at the same time** (question/student answer/cause/correct solution/source block), and the mistake row in `study_state.json` gets a new `entry` field pointing to the anchor, so the status row and the note index each other. **Migrating old mistakes**: a v3 status row holds only `{id,chapter,note,status}` (the question text and the wrong answer can no longer be recovered), so migration creates a "stub entry": it is marked `（旧版错题，无原始题面）` ("legacy mistake, no original question text") + the question text is filled in by looking up the id in the question bank, and the next time the student reviews that question, exam-review completes it on the spot into a full entry;
4. **Cheatsheet compiler** (G5): input = `mistakes/` (highest weight) + the knowledge-point window (out-of-window first) + frequently used `notebook/` chapters + wiki must-memorize points; output = `cheatsheet.md` (with its own contents; the four-part layout carries over from v3; **it replaces and retires `walkthrough.md`**: the old file is kept, not deleted, and the pointers in the skill text are updated). "Generating" becomes "compiling", and **traceability gets a mechanical check**: validate_workspace adds a lint "every cheatsheet point must carry a resolvable `notebook/`, `mistakes/` or wiki anchor; a broken anchor is red";
5. **Web fallback**: clients without a file system (the web prompt route) keep the existing chat-only + text-breakpoint mode; the notebook contract applies only to agents that can write to disk (the control layer dispatches by capability, reusing exam-cram's existing file-less fallback check);
6. **Finished cheatsheet PDF** (the end state of G5): the compiled `cheatsheet.md` is rendered by `scripts/cheatsheet_render.py` into **print-optimized HTML** (compact multi-column layout, adjustable font size/line spacing, `@page` margins ≥12 mm because printers eat the edges), then turned into a PDF by a headless browser (detects the local Edge/Chrome, `--headless --print-to-pdf`, zero new dependencies); **page-count fitting loop**: first estimate a starting value with a "characters per page" heuristic; after output, the agent checks the result with its vision capability: if it runs over, shrink the font/merge columns; if the last page is >15% blank, enlarge the font to fill it, until the result is **exactly the page count the user specified and as dense as possible**; when no headless browser is available, fall back to "open the HTML → Ctrl+P" with guidance on print settings.

### 2.5 Workspace Location and First-Run Onboarding (G7)

Verified current state: exam-ingest's workspace location is **"default: current workspace root"**. Without asking, it lands in the current directory, which is exactly the root cause of "the model created a workspace somewhere the user didn't know about". The v4 contract:

1. **Creating a workspace requires confirmation**: before any workspace is created, the user must explicitly confirm the target path (a suggested default may be offered, but **silent creation = a contract violation**, added as a behavior_smoke red-line scenario);
2. **Persistent registry**: `~/.exam-cram/workspaces.json` (in the user's home directory, across sessions) records course → absolute workspace path + materials folder + last-used time; it is maintained by new `workspace-register / workspace-list` subcommands in `scripts/update_progress.py`;
3. **Onboarding on activation**: after the skill is downloaded and activated, if the registry is empty, run first-run onboarding: first ask "where is your materials folder"; if there are no materials, switch to a usage tutorial (30-second version: a three-step demo of add materials → build the knowledge base → start reviewing); if the registry is not empty, ask "which course do you want to continue" and mount that workspace directly;
4. **No getting lost**: the progress panel at the start of every session includes a line with the absolute workspace path, so the student always knows where their files are.

### 2.6 Distribution (G6)

**Dependency preflight list (added during execution; user feedback: a missing library only showed up on the first run after installing)**: `scripts/check_deps.py` is the single list + detector for optional dependencies (PDF text backend / PyMuPDF rendering / local browser). Step 0 of the exam-ingest Workflow runs a mandatory preflight: based on the actual content of the materials it decides "needed / not needed yet / optional with fallback"; if something is missing, it gives the exact install command, asks for the student's consent in one sentence, and then the agent installs it (never silently, and never waiting for it to blow up at runtime). The list exists in only this one place and the skill text only points to the tool, to prevent drift between two places.

Three progressive tiers, not mutually exclusive:

1. **Do now (a small one-time change)**: add `.gitattributes` marking benchmark/ tests/ spike/ assets/ .github/ as `export-ignore` → GitHub's automatic source zip shrinks straight to runtime size, at zero tooling cost;
2. **Standard in v4**: `scripts/build_dist.py` (standard-library zipfile only) builds the runtime package (~223 KB) from an explicit manifest, and CI attaches it to every release; the manifest itself is tested, so "a new script left out of the manifest" turns red; the README install section changes to "download the release package and unzip it into `.claude/skills/`" as the main path, with git clone as the developer path;
3. **Optional enhancement**: package it as a plugin with `.claude-plugin/plugin.json` (the existing skills/ directory structure matches the plugin conventions almost exactly), giving Claude Code users a native install/update experience; `${CLAUDE_SKILL_DIR}` at script call sites needs to work with `${CLAUDE_PLUGIN_ROOT}` as well (about 28 places in the runtime Markdown: 7 in the three root entry points + 21 in sub-skills). **No** separate runtime repository (it would split stars/issues, has the highest sync cost, and does not fit a collaborator's role).

---

## 3. Disposition of Existing Assets

### 3.1 The Nine Sub-Skills

| Sub-skill | v4 disposition |
|---|---|
| exam-cram | Kept as the main router: combined first question (mode × time × **language**) → persist → language-pack dispatch + notebook capability detection |
| exam-ingest | Rewritten around ingest v2: chunking/cleaning/metadata/index/term list/incremental |
| exam-tutor | Teaching logic kept (the seven-step template is a core v3 asset); Output Contract changed to "save to disk → summary" |
| exam-quiz | Grading for the six question types kept; feedback saved to `notebook/`, mistakes written to `mistakes/` at the same time |
| exam-review | Changed to review from the `mistakes/` directory; review conclusions written back to the notebook (no longer evaporating in chat) |
| exam-cheatsheet | Rewritten as a compiler (item 4 of 2.4) |
| exam-audit | Extended: add consistency checks for the notebook/index/term list |
| exam-help | One quick-reference card generated per language pack |
| confusion-tracker | Kept; confusion entries are also saved to `notebook/` at the same time (with anchor backlinks) |

### 3.2 The Twelve Scripts

| Script | v4 disposition |
|---|---|
| ingest.py | **Rewrite** (v2; where the whole 2.3 table lands) |
| update_progress.py | **Major rework**: canonical enums + state migration + msgids (the heaviest change, done first) |
| build_raw_input_from_workspace.py | Kept (its 147 KB parsing engine is an asset); part of the cleaning logic moves forward into it; messages converted to msgids |
| validate_workspace.py | Extended: validate the notebook/ structure, index-wiki consistency and canonical enums |
| select_questions.py / select_hard_questions.py / score_difficulty.py | Kept; vocabularies now imported from `scripts/i18n.py` (eliminating drift among the three hard-coded copies) |
| build_knowledge_index.py | Retired after being **merged into** the retrieval index (the quiz-tag index is a subset of the new index) |
| build_visual_index.py / list_figure_pages.py / list_image_questions.py | Kept; messages converted to msgids |
| show_question_assets.py | Kept; its existing inline zh/en bilingual text moves to the language packs (removing, along the way, its private copy of the language mapping) |
| (new) | `scripts/i18n.py`, `scripts/retrieve.py`, `scripts/notebook.py`, `scripts/build_dist.py` |

### 3.3 Other Assets (filled in after the critical review: everything that previously had no disposition is here)

| Asset | v4 disposition |
|---|---|
| SKILL.en.md (root English rendering) | **Retired and merged into `locales/en/`**: the root keeps only a single SKILL.md router; literal file-name pointers in README/AGENTS/portability are updated at the same time (the related discoverability test pins are rewritten together in P2) |
| prompts/web_prompt.md + .en.md | Both copies kept (the web client has no file system, so each must be self-contained); **add a structural alignment test**: the two copies must have equal sets of anchors/sections (the anti-drift argument for scripts applies equally to this pair of hand-mirrored files) |
| templates/ (3 Chinese templates) | **Moved into `locales/<lang>/templates/`** with en versions added; the root templates/ is retired; the new notebook/mistake book/cheatsheet templates are born directly in the language packs |
| docs/file-format.md | **Heavily revised in each of P1/P3/P4 as the schema evolves** (canonical enums, `_meta.json`, `retrieval_index.json` and the notebook/mistakes structure all need to be documented); every phase's acceptance includes "docs consistent with the schema" |
| docs/language-policy.md + localization.md | P0 rewrites the policy (repealing "defer the split"); P2 rewrites them as the language-pack spec |
| README / README.zh.md | P6 rewrites the install section (release package as the main path); the rest follows the release |

---

## 4. Roadmap (7 phases, each independently deliverable and revertible)

| Phase | Content | Main deliverables | Acceptance criteria |
|---|---|---|---|
| **P0 Decision freeze** (1 PR) | Review and finalize this plan; repeal the "defer locales" policy (rewrite docs/localization.md + test_localization_boundary); land `.gitattributes` export-ignore first | Finalized PLAN-v4 + policy rewrite + slimmer zip in effect immediately | All tests green; source zip size ≤ 700 KB |
| **P1 Vocabulary and state layer** (2–3 PRs) | Shared vocabulary in `scripts/i18n.py`; canonical `study_state.json` enums + automatic migration; unify the three hard-coded vocabularies | i18n module + migration path + migration tests | Old workspaces migrate automatically after init, with a backup; each enum has exactly one point of definition |
| **P2 Language-pack separation** (3–4 PRs) | Set up `locales/zh|en/`; convert ~440 script messages to msgids (moving the zh copy word for word keeps migration cost down); split the 9 sub-skills into control layer/language pack; rework routing; rewrite the 12 path-pinning tests; repoint the purity lint at the language packs | Full locales/ tree + msgid list + new lint | **Gate**: two-way purity lint all green (zero CJK in the en pack, zero English prose in the zh pack) + full suite green; "≥90% of the existing 1,035 Chinese assertions survive unchanged" is a cost budget, not a gate: going over budget means the move was not word for word and needs checking |
| **P3 RAG upgrade** (3–4 PRs) | ingest v2 (chunking/cleaning/metadata/incremental) + **R-slice structure rebuild for unstructured long text (separate acceptance in 2.3)** → BM25 index and TOC → terms.json cross-language bridge → retrieval contract + abstention threshold + **benchmark harness tool-trace logging** (the current harness records only final answers, so this is prerequisite engineering, not an existing capability) | scripts/retrieve.py + new workspace structure + harness trace logging | recall@k measurable, with actual numbers; R-slice passes its separate acceptance; chunking A/B shows lower token cost with no drop in accuracy; out-of-scope abstention stays at 100% |
| **P4 Notebooks + location onboarding** (2–3 PRs, **depends on P2**: the rewritten Output Contract and the notebook templates both live in the control layer/language packs that P2 produces; split first, then change, to avoid doing the work twice) | scripts/notebook.py; default save-to-disk contract for all skills (whitelist-based exemptions); mistake book with contents + stub migration for old mistakes; **workspace registry + mandatory confirmation before creating a workspace + onboarding on activation (all of G7)**; add "save-to-disk contract" and "silent workspace creation red line" scenarios to behavior_smoke | Full notebook/ + mistakes/ chain + workspaces registry | 100% of substantive answers saved to disk and reachable from the contents (no exemptions outside the whitelist); the silent-workspace-creation scenario must go red; no regression in the web fallback path |
| **P5 Cheatsheet compiler + PDF** (1–2 PRs) | Cheatsheet switched from generating to compiling (mistakes first + out-of-window first + anchor backlinks); walkthrough.md retired; **cheatsheet_render.py (print HTML + headless-browser PDF + page-count fitting loop)** | New exam-cheatsheet + cheatsheet.md + PDF renderer + traceability lint | Traceability lint all green; N pages requested → PDF of exactly N pages, margins ≥12 mm, last page ≤15% blank (visual-check contract); fallback path works in an environment without a browser |
| **P6 Distribution and release** (1–2 PRs) | build_dist.py + manifest test + CI attaching the release asset; README install rewrite; (optional) plugin.json | ~223 KB runtime package | The skill installed from the zip is fully functional; manifest drift is caught by a test |
| **P7 Regression and release** (1 PR) | Rerun the full benchmark on v4 (three arms × three models); write the numbers, compared with v3, into the report; publish the v4.0 release | v4.0 release notes (same bilingual format as v3) | Grounding metrics no lower than the v3 baseline (**the baseline is explicitly the matrix numbers in REPORT: two courses, PSYC + 6.006, Sonnet as judge, human calibration κ=0.833/0.875**; material-specific ≥ current value, out-of-scope abstention = 100%); retrieval recall added as a new headline metric |

Dependencies: P1 → P2 → P4 (vocabulary → language packs → save-to-disk contract, **serial**: the contract and templates that P4 rewrites live in P2's output); P3 can run in parallel with P2/P4; P5 depends on P4; P6/P7 wrap up. Estimated total: **14–20 PRs**, each passing CI + Codex review on its own.

---

## 5. Risks and Mitigations

| Risk | Level | Mitigation |
|---|---|---|
| Test blast radius (1,035 Chinese assertions + 12 path-pinning files) | High | Move the zh copy word for word so the assertions survive; the path-test list was already itemized in the audit and is rewritten in one go in P2; run full CI on every PR |
| A state-migration bug destroys student progress | High | Keep the existing O_EXCL atomic write + a mandatory backup before migration; migration tests cover three generations of state format (v2 Chinese enums / old four modes / v4 codes) |
| The agent does not follow the new "save to disk" contract (writes the chat, forgets the file) | Medium | Add deterministic scenarios to behavior_smoke (no notebook entry = red); add save-to-disk drift detection to T4 long-horizon drift |
| BM25 index quality is worse than "let the model browse on its own" | Medium | P3 decides by measuring with an A/B on the existing benchmark: if recall does not improve, the index is downgraded to "TOC navigation + direct section reads", while chunking and metadata stay (they have value on their own) |
| Content drift between the two language packs (zh changed, en forgotten) | Medium | Structural alignment test: the two packs must have equal msgid sets and equal skill-copy anchor sets (anything missing = red) |
| Scope creep | Medium | Each phase is independently deliverable; any new idea goes into this document's "backlog" section first instead of straight into work |

## 6. Backlog (not done this round, kept on record)

- **Per-language rendering of the generated study_progress.md view**: the view is an agent-mediated surface (what the student sees in the chat is a progress panel restated in their language), while its zh structure is parsed jointly by four chains: the parse_md round trip, the validator, drift and T4. Changing it this round has a small payoff and a large regression surface; keep the zh view + coded state for now, and re-evaluate once the notebooks (the surface students read directly) have settled
- Embedding-based semantic retrieval backend (the spike already has the contract; let measured BM25 data decide)
- Notebook export to PDF / Anki cards
- Managing workspaces for multiple courses in parallel
- Community language packs (a third language: the locales/ structure extends to it naturally)

---

*This plan is the single source of truth for the v4 refactor; any deviation during execution must be written into this document first. The original audit reports (5 of them) are archived in the session transcripts.*
