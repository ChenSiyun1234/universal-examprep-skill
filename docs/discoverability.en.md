# Repository About and topics setup (for the repository owner)

English · [中文](discoverability.md)

When GitHub search, Google and AI assistants look for projects, the first things they read are the **About description** and the **Topics** at the top right of the repository page. Only the repository owner can change these two, and both are currently empty, so a search for “期末复习 / exam prep” ("final exam review / exam prep"), in Chinese or in English, rarely finds this repository. Fixing it takes two minutes:

## 1. About description

Open the repository home page → the gear icon next to About at the top right → enter the line below under Description (it includes both Chinese and English, so searches in either language match):

```text
Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能
```

For Website in the same dialog, the latest release page is recommended: `https://github.com/ZeKaiNie/universal-examprep-skill/releases/latest`.

The command line works too (requires `gh` logged in with the owner account):

```bash
gh repo edit ZeKaiNie/universal-examprep-skill --description "Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能" --homepage "https://github.com/ZeKaiNie/universal-examprep-skill/releases/latest"
```

## 2. Topics

In the Topics field of the same About dialog, enter the following 20 topics one at a time (GitHub allows only lowercase English letters, digits and hyphens, so the Chinese keywords go in the description):

```text
exam-prep, exam, study-tool, ai-tutor, education, students, quiz, cheat-sheet, study-guide, flashcards,
agent-skill, claude-code, codex, cursor, antigravity, gemini-cli, llm, pdf, python, mit-license
```

Add them all at once from the command line:

```bash
gh repo edit ZeKaiNie/universal-examprep-skill \
  --add-topic exam-prep --add-topic exam --add-topic study-tool --add-topic ai-tutor --add-topic education \
  --add-topic students --add-topic quiz --add-topic cheat-sheet --add-topic study-guide --add-topic flashcards \
  --add-topic agent-skill --add-topic claude-code --add-topic codex --add-topic cursor --add-topic antigravity \
  --add-topic gemini-cli --add-topic llm --add-topic pdf --add-topic python --add-topic mit-license
```

## 3. Social preview image (optional, one minute)

The cover image shown when the repository is shared on WeChat, X or Reddit is already made: `assets/social-preview.png` (1280×640). To upload it: Settings → General → Social preview → Upload an image.

Once these three are done, nothing else is needed: the other search-related content (README keywords, the skill description, llms.txt) is already in the repository.
