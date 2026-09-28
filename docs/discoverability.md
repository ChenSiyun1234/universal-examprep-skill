# 仓库 About 与标签设置（需要仓库所有者操作）

[English](discoverability.en.md) · 中文

GitHub 搜索、Google 和各类 AI 助手找项目时，最先读的是仓库页面右上角的 **About 描述**和 **Topics 标签**。这两项只有仓库所有者能改，目前都是空的，所以无论用中文还是英文搜“期末复习 / exam prep”都很难命中这个仓库。改好只需要两分钟：

## 1. About 描述

打开仓库首页 → 右上角 About 旁的齿轮 → Description 填入下面这句（中英都放进去，搜索哪种语言都能命中）：

```text
Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能
```

同一个对话框里的 Website 建议填最新发布页：`https://github.com/ZeKaiNie/universal-examprep-skill/releases/latest`。

用命令行也可以（需要用所有者账号登录 `gh`）：

```bash
gh repo edit ZeKaiNie/universal-examprep-skill --description "Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能" --homepage "https://github.com/ZeKaiNie/universal-examprep-skill/releases/latest"
```

## 2. Topics 标签

同一个 About 对话框的 Topics 栏，逐个输入下面 20 个（GitHub 只允许小写英文、数字和连字符，所以中文关键词放在描述里）：

```text
exam-prep, exam, study-tool, ai-tutor, education, students, quiz, cheat-sheet, study-guide, flashcards,
agent-skill, claude-code, codex, cursor, antigravity, gemini-cli, llm, pdf, python, mit-license
```

命令行一次加完：

```bash
gh repo edit ZeKaiNie/universal-examprep-skill \
  --add-topic exam-prep --add-topic exam --add-topic study-tool --add-topic ai-tutor --add-topic education \
  --add-topic students --add-topic quiz --add-topic cheat-sheet --add-topic study-guide --add-topic flashcards \
  --add-topic agent-skill --add-topic claude-code --add-topic codex --add-topic cursor --add-topic antigravity \
  --add-topic gemini-cli --add-topic llm --add-topic pdf --add-topic python --add-topic mit-license
```

## 3. 社交预览图（可选，一分钟）

分享到微信、X、Reddit 时显示的封面图已经做好，在 `assets/social-preview.png`（1280×640）。上传路径：Settings → General → Social preview → Upload an image。

改完这三项，其他与搜索有关的内容（README 关键词、技能描述、llms.txt）仓库里已经包含，不需要再做别的。
