# Feature audit: which v4.3 features v5.1 has and which it does not

English · [中文](feature-audit.md)

Every student-facing feature listed in the v4.3 README/SKILL, checked one by one against its status in v5.1.
✅ implemented (and tested on three real course sets: EEC 160 / MIT 6.006 / Yale PSYC 110); 🔶 partly implemented or changed form; ❌ not implemented (with the reason).

## Teaching

| v4.3 feature | v5.1 status | Notes |
|---|---|---|
| Teaches from the materials chapter by chapter, reading only the current chapter | ✅ | `next` emits the current chapter's source text in fixed-size slices, tagged `[文件 p.页码]` (file, page number); other chapters are not preloaded |
| Seven-step problem walkthrough (problem figure → what is asked → read values off the figure → formula → working → answer → source trace) | ✅ | Compressed into the 4 steps of SKILL §3 plus the figure rules in §4; same order (figure first, then the explanation, then the source trace) |
| For a problem with a figure, look at the figure first; do not pose the problem until the figure is shown | ✅ | `quiz` lists the 🖼 problem-figure paths first; SKILL §4 requires putting the figure into the conversation before asking the question |
| Crop figures from the original lecture notes/materials into the conversation | ✅ **new** | `setup` automatically detects vector drawings and embedded images in lecture PDFs and crops them to PNG (EEC 160: 235); when the region of a question or answer contains a figure, it crops a problem figure/answer figure (16); embedded images in PPTX/DOCX are extracted directly; `figure <文件> <页> --crop` (file, page) captures any region by hand |
| Answer figures appear only when the answer is explained | ✅ | `quiz` gives only problem figures; answer figures come only with `check` |
| The student's own scanned homework is never shown as an answer | ✅ | Scanned/handwritten pages are detected and skipped automatically (EEC 160: 140 pages); they do not enter the question bank and are not cropped |
| For drawing problems, compute first, then draw (AVL, etc.) | ✅ | SKILL §3 rule: when the answer is a structure (a tree, a state machine, a traversal order, a table of values), compute it step by step first and only then draw or list it; never draw from memory |
| 3 modes (starting from zero / shoring up weak spots / filling gaps) × 4 time tiers | 🔶 | Replaced by `--days N` (sets the pace) and `--start N` (starting point); SKILL §3 sets the pace from the number of days |
| Knowledge-point window (asks after 3–7 days whether you still remember) | ❌ | Removed. `mistakes` and `note --type confusion` cover the goal of going back to review |
| Problem-by-problem detailed mode step_by_step | 🔶 | Teaching already goes one slice at a time by default; lowering `--slice` makes it one problem at a time |

## Quizzing and grading

| v4.3 feature | v5.1 status | Notes |
|---|---|---|
| Quizzes only from the materials' question bank; never passes off made-up questions as real ones | ✅ | `quiz` reads only `quiz_bank.json`; when there are no questions it says clearly that only ⚠️ AI questions are possible |
| Six question types (multiple choice / open-ended / drawing / fill-in-the-blank / true-false / code) | 🔶 | Automatically detects choice / true_false / fill_blank / subjective; diagram and code are not separate types (treated as open-ended) |
| Automatic pairing of separate question and answer files | ✅ | `hw2 (4)(1).pdf` ↔ `homework2solutions.pdf`, `q1.pdf` ↔ `q1_sol.pdf`, `作业2.txt` ("homework 2") ↔ `作业2答案.txt` ("homework 2 answers"); textbook problem numbers `Problem 1.3.10` ↔ `Problem 1.3.10 Solution` (EEC 160: 89/89 paired) |
| Open-ended questions graded by keywords | 🔶 | Keywords are no longer extracted; the model grades against the reference answer (`check`), which suits small models better |
| Two wrong answers in a row trigger a hint / skip / filing | ✅ | `answer wrong\|skip` adds the question to the mistake log automatically and counts it; `quiz` re-tests mistakes first |
| Difficulty ratings and picking questions by mastery | 🔶 | Pick order: mistakes due for review → questions never attempted → questions already attempted; no difficulty score |
| Scope limits (quiz only one chapter/one source) | ✅ | `quiz --chapter N` / `--all` |
| Distinguishes `verified` from `covered_unverified` | ✅ | On `done`, the chapter is marked `verified` or `done` depending on whether a materials question from it was ever answered correctly |

## Sources and honest labeling

| v4.3 feature | v5.1 status | Notes |
|---|---|---|
| 🟢/🟡/⚠️ three-level source labels | ✅ | CLI output carries 🟢 itself; SKILL §5 says when to use 🟡/⚠️ |
| Says "the materials don't cover this" when the materials don't support something | ✅ | `ask` exits with code 4 when nothing matches and prints a notice |
| Does not invent a problem statement when the statement is not in the materials (only a textbook problem number) | ✅ **new** | `quiz/check` print a "problem statement is not in the materials" notice and require restating the givens from the reference answer, labeled 🟡 |
| Fixed source block for each question (question source \| answer source) | ✅ | `check` prints where the question and the answer come from (file + page) |

## Progress, notes and outputs

| v4.3 feature | v5.1 status | Notes |
|---|---|---|
| Progress saved across conversations (study_state.json) | ✅ | One file; `status` restores it; re-running `setup` keeps progress |
| Notebook / mistake log / sticking points | ✅ | `note`, `mistakes`, `notebook.md`, `progress.md` |
| Pre-exam cheat sheet (four sections) | 🔶 | `cheatsheet` generates Markdown: chapter summaries + sticking points + mistakes (with problem-figure links and reference answers); no more PDF layout |
| Web Study Guide (HTML/PDF) | ❌ | Removed. `chapters/*.md` + `figures/` can already be read directly |
| Workspace health check exam-audit | 🔶 | `doctor` (environment) + `status` (progress); no more .ingest consistency audit (there is no .ingest anymore) |
| One-screen quick reference exam-help | ✅ | `help` (Chinese or English, following the workspace language) |
| Chinese / English / bilingual | 🔶 | zh / en auto-detected + `--lang`; the block-by-block bilingual mirror mode is gone; the model simply replies in the student's language |
| Fallback without Python | ✅ | SKILL §7 |

## Material processing

| v4.3 feature | v5.1 status | Notes |
|---|---|---|
| PDF / DOCX / PPTX / TXT / MD | ✅ | HTML added; XLSX removed (course materials rarely use it) |
| PDF text extraction | ✅ | `pypdfium2` (fast, about 3 seconds for 1000 pages) or `pypdf`, either one an optional install |
| Scans / handwriting | 🔶 | Detected and skipped; no OCR. SKILL has the model look at those pages directly |
| Lecture figure index (figure_page_index) | ✅ | `figures.json` + the `figures` command, listed by chapter/file/page |
| Chapter detection | ✅ | Numbers in file names, "Chapter N + title line" at the top of a file, and whole-book files split at "第N章/Chapter N" ("Chapter N") |
| Search (BM25, Chinese and English) | ✅ | `ask`; matching passages come with the figures from the same page |
| Full build / lightweight on-demand, generation ledger, receipts, locks | ❌ | Removed (invisible to students) |
| MinerU / Docling / LangGraph / OpenAI adapters | ❌ | Removed (the original implementations were stubs) |

## Conclusion

The core promises students can see (teach from the materials, show the figure first, quiz only with materials questions, keep progress, label honestly) all work in v5.1, and the figure support is more concrete than in v4.3: v4.3 required the agent to render pages itself and write receipts, while in v5.1 the script crops the figures and gives the paths.
Computing before drawing now has a rule in SKILL §3. The knowledge-point window and the HTML/PDF Study Guide are not implemented, and only four of the six question types are recognized; these three are heavyweight features deliberately dropped or simplified in the Flash edition. Users who need them can use the complete v4.3 edition, kept unchanged in the repository's `full/` folder.
