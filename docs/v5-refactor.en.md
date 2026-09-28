# v5 refactor notes: what was removed, what was kept, measured comparison

English · [中文](v5-refactor.md)

Date: 2026-09-01. Every number was measured on this machine (Windows 11, Python 3.12), and the commands are reproducible.

## 1. Problems with the old version (why patching was not enough)

| Metric | v4.3 |
|---|---|
| Python lines | 144,435 lines, 495 files |
| CLI surface | 36 subcommands, 108 arguments |
| Skill text the agent reads before teaching (zh student) | `SKILL.md` + `locales/zh/SKILL.md` + `skills/exam-cram/SKILL.md` + `skills/exam-tutor/SKILL.md` + language pack ≈ 140 KB (about 35k tokens); all skill/AGENTS/locales text is 240 KB |
| Script calls before teaching starts | `workspace-list` → `exam_start confirm` → `lightweight_session init` → `status` → `plan` (5 calls); `confirm` runs two SHA-256 passes over the 110 files (3.8 MB) of the install package and calls git twice; after that, **every** command does its own two passes |
| Who reads the PDF | In lightweight mode the scripts never touch PDF bytes: the agent has to render each page to PNG itself, tile 4 pages into a contact sheet, make a separate "crop review" model call for each cropped block, and write a schema-3 receipt |
| What the code is for (per-file count by a subagent) | About 75% of `exam_start.py` is receipts/hashing/recovery; about 88% of the 5772 lines of `lightweight_session.py` are receipt validation, answer-contamination contracts and state-machine audits |
| Tests | 1000+ cases; `unittest discover` takes 12 min 1 s on this machine |

The result: a large model needed a dozen or more conversation turns to reach the first sentence of the lesson; a small model (short context, weak instruction following) simply could not meet requirements like the "schema-3 visual receipt"; and the student first had to understand four independent switches: lightweight/full, chat/visual, ordinary/isolated, batch/step_by_step.

## 2. What the new version is

```
SKILL.md          about 1100 words; one table maps each kind of student request to its command
coach.py          entry point
coach/            extract · chapters · questions · index · state · figures · cli · text (about 2.5k lines; v5.1 includes figure cropping)
samples/          built-in Chinese Data Structures sample; fetch.py downloads MIT 6.006 + Yale PSYC 110
tests/            8 files, 40+ cases, about 1 second
```

A single `setup` handles the whole course; after that, just 7 commands make up the complete study loop: `next / ask / quiz / check / answer / note / done`.

### Original features kept and improved

| Original feature | Now |
|---|---|
| 🟢/🟡/⚠️ source labels | Kept; the output of `next`, `ask` and `check` carries 🟢 and `文件 p.页码` (file, page number) itself, so the model only has to label its own additions 🟡/⚠️ |
| Quiz only from the materials; never pass off made-up questions as real ones | Kept; `quiz` reads only `quiz_bank.json`; when there are no questions it says clearly that "only AI-written questions, labeled ⚠️, are possible" |
| The distinction between `verified` and `covered_unverified` | Kept as `verified` / `done`: a chapter counts as verified only after a materials question from it has been answered correctly |
| Mistake log, sticking points, notes, cheat sheet | Kept: `answer wrong` adds the question to the mistake log automatically and re-tests it first; `note --type confusion/summary`; `cheatsheet` assembles the cheat sheet |
| Progress across conversations | Kept: a single `study_state.json` file, restored with `status` |
| Chinese and English | Kept: CLI output follows the workspace language, and the language of the materials is detected automatically |
| BM25 search + Chinese character bigrams | Kept and simplified: exit code 4 when nothing matches, which tells the model to say "the materials don't cover this" |
| Chapter detection | Improved: numbers in file names (lec3 / 第3章 ("Chapter 3") / 03-), "Lecture N: Title" at the top of the file, and splitting a whole-book file at "第N章/Chapter N" headings; all three layouts pass real-material tests |
| Question extraction | New: several numbering styles, `Problem N` / `1.` / `第N题` ("question N") / `（1）`; numbering restarts within sections (一、选择题 … 二、填空题, i.e. "I. Multiple choice … II. Fill in the blank"); question files and solution files are paired automatically; multiple-choice options, true/false and fill-in-the-blank types are recognized; point values are extracted |
| PDF reading | Improved: an optional install of `pypdfium2` (or `pypdf`) is enough to read the text, and `pypdfium2` also does the figure cropping (the old version made the agent render every page to an image); scanned/handwritten pages are detected and skipped automatically |
| Small-model support | New: `--slice` controls how many characters each slice has; every output ends with the next command to run; the model is never asked to produce JSON |

### Removed features (and why)

- Full build / lightweight on-demand dual modes and the `.ingest/` generation ledger, `material_build_pending`, recovery log, mutation lock: invisible to students; they only add more ways to fail.
- Study Guide HTML/PDF rendering, page-by-page visual QA, crop receipts, answer-contamination contracts: the agent teaching in chat plus `chapters/*.md` is enough for review; for printing, `cheatsheet.md` can be used directly.
- LangGraph / OpenAI / MinerU / Docling adapters: all were stubs or routing notes for things that were "never available".
- Benchmark matrix, drift, behavior smoke, calibration: unrelated to how students use the tool; the core finding (retrieval over the materials beats closed-book) does not need to be re-run for every release.
- Three-layer language dispatch (root → locales/xx/SKILL → skills/* → locales/xx/skills/*): replaced by one SKILL.md plus bilingual strings built into the CLI.
- 3 study modes × 4 time tiers, the knowledge-point window, `artifact_mode`, `answer_explanation_mode`, `interaction_style`, the workspace registry, runtime hash receipts: all replaced by two arguments, `--days` and `--start`.

## 3. Measured comparison

### 3.1 From startup to the first lesson

Same materials: MIT OCW 6.006 lecture notes for six lectures + Quiz 1 + official solutions (8 PDFs, 1.9 MB).

| | v4.3 | v5 |
|---|---|---|
| Skill text the agent must read | ≈140 KB | 6.5 KB (about 1100 words, including the figure rules) |
| Script calls before teaching | 5 | 1 |
| Total script time | 2.46 s (not counting the agent's own model calls to render PDF pages, build the contact sheet and review each crop) | 1.1–1.4 s (including pypdf extraction of all 8 PDFs) |
| What else the agent must do before teaching | Render 5 pages of lec1 to PNG, build a contact sheet, review each crop, write a schema-3 receipt, `record-visual`, write the notebook, `mark-taught` | Nothing. `next` gives the first slice of source text directly |
| Workspace files generated | `exam_runtime_receipt.json` (16 KB of hashes), `.lightweight/session.json`, `.study_state.lock` | `study_state.json`, `chapters/*.md`, `quiz_bank.json`, `index.json`, `progress.md`, `notebook.md` |

### 3.2 Extraction quality (real open courses, not synthetic data)

**MIT 6.006 (PDF, CIDFontType0 fonts)**

- Chapters: 6/6 numbers and titles detected correctly (Introduction / Data Structures / Sorting / Hashing / Linear Sorting / Binary Trees I).
- Headers and footers: running headers such as `3 6.006 Quiz 1 Name` and `Lecture 1: Introduction` are removed automatically.
- Questions: all 9 questions of Quiz 1 (including the "write your name" one) extracted; 9/9 automatically paired with `q1_sol.pdf` to get the official solutions; the `Solution:` paragraphs of multi-part questions are kept in order, and `Common Mistakes` is kept as well; all point values such as `[8 points]` extracted.
- Chapter assignment: the quiz spans several chapters, so chapters are guessed with BM25 and labeled "chapter guessed automatically"; 6 of the 9 questions land in a sensible chapter (sorting question → Linear Sorting, heap/AVL → Binary Trees), and 3 (including the database design question) land in Introduction. The assignment only affects the default scope of `quiz`; `quiz --all` is unaffected.
- Search: `ask "counting sort radix sort running time"` → the Radix Sort passage on Lecture 5 p.4; `ask "quantum entanglement"` → exit code 4.
- Figure cropping (v5.1): 34 figure regions in the lecture notes (tables, trees, diagrams); each of the 5 Quiz 1 questions with a figure or table gets a cropped problem figure and answer figure (for example the tree in Problem 4 "Transforming Trees"). The two example images in the README come from here.

**Yale PSYC 110 (HTML transcripts converted to Markdown, 20,000–50,000 characters per lecture)**

- Chapters: 4/4, with titles taken from "Lecture N - Title" at the top of the file; the "Chapter 1/2/3…" sections inside a lecture were **not** mistakenly split into chapters.
- Slicing: Lecture 2 is split automatically into 10 slices of about 5000 characters each; `next` emits them one at a time.
- Search: `Descartes dualism argument` → Lecture 2; `id ego superego` → Lecture 3; `operant conditioning reinforcement` → Lecture 4.

**Chinese 《数据结构》 ("Data Structures") sample (Markdown + TXT, bundled with the repo)**

- Language detected automatically as zh; all CLI output is in Chinese.
- All 12 questions extracted (5 homework + 7 mock exam), 10 of them with answers and explanations; multiple-choice options, true/false and fill-in-the-blank types are correct; section headings such as "二、填空题" ("II. Fill in the blank") no longer leak into the previous question's answer; chapter assignment 12/12 correct.

**EEC 160 / EEC 161 Applied Probability (a real course provided by the user, 27 PDFs, about 1000 pages, 30 MB)**

Structure: 9 chapter lecture decks (landscape slides, 47–148 pages per chapter, all figures drawn as vectors), 9 homework sets (page 1 is a list of textbook problem numbers, followed by scans of the student's own handwritten homework), and 9 official solution sets (with small figures). This was the hardest layout to handle in the v4 era.

- `setup` 9.3 s (pypdfium2 text extraction + figure cropping); 9/9 chapter titles correct (such as "Experiments, Models, and Probabilities"; titles that wrap across lines are joined back together).
- Questions: all 89 questions paired automatically by textbook problem number (`Problem 1.3.10`) with solution files whose names are inconsistent (`hw1solution.pdf`, `homework2solutions.pdf`, `hw5-solutions(1).pdf`, etc.); 89/89 have a reference answer; chapter assignment 89/89 from the first part of the problem number (none of it guessed).
- All 140 scanned/handwritten pages detected and skipped: the student's own homework is never treated as a problem statement or an answer.
- Figures: 235 vector figure regions in the lecture notes cropped to PNG (including coordinate transforms across Form XObjects); for the 16 questions whose solutions contain figures, "answer figures" are cropped (such as Venn diagrams and joint PMF scatter plots) and given only on `check`.
- When the problem statement itself is not in the materials (only a textbook problem number): `quiz` says so clearly, and SKILL requires restating the givens from the reference answer, labeled 🟡, instead of inventing a problem statement.

### 3.3 Engineering metrics

| | v4.3 | v5 |
|---|---|---|
| Python lines (excluding tests) | ~120k | about 2,500 (v5.1, including figure cropping) |
| File count (excluding .git) | 495 | about 45 |
| Repo size (excluding .git) | 10 MB | 1.4 MB (0.9 MB of which is README images) |
| Subcommands / arguments | 36 / 108 | 17 / 32 (including v5.1's `figures` and `figure`) |
| Unit tests | 1000+ cases, 12 min | 40+ cases, ≈1 s |
| Dependencies | Claimed to be pure standard library, but PDFs actually need pypdf or PyMuPDF, formulas need latex2mathml, and images need Pillow | Standard library; pypdfium2 optional for PDF text and figure cropping (pypdf also works for text) |

## 4. Reproducing the results

```bash
pip install pypdfium2
python samples/fetch.py                      # download MIT 6.006 and Yale PSYC 110
python coach.py setup samples/mit-6006 --days 2 --name 6.006
python coach.py next
python coach.py quiz && python coach.py check q003
python coach.py ask "counting sort radix sort running time"
python coach.py setup samples/yale-psyc110 --days 5
python coach.py ask "Descartes dualism argument"
python -m unittest discover -s tests -v
```

## 5. Known limitations

- Chapter assignment for exams that span chapters is a guess (and labeled as one); numbers in homework file names are not treated as chapter numbers.
- Question extraction depends on numbering (`Problem N`, `1.`, `第N题`); questions without a number do not enter the question bank, but they are still in the chapter text.
- No OCR for scanned PDFs or images: scanned pages are detected and skipped, and pure image files are listed by chapter for the agent to read with its own vision.
- No built-in Chinese-English glossary; when the materials are in English and the student asks in Chinese, SKILL requires the model to translate the keywords into the language of the materials before running `ask`.
