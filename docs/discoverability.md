# 让人和智能体都能搜到这个项目 / Making the project findable by people and agents

（English below）

这份清单给仓库维护者。前半部分是**只有仓库所有者能改的设置**（几分钟），后半部分说明本 PR 已经改了什么、为什么。

## 一、仓库设置（需要所有者操作）

### 1. 仓库描述（About 栏）

GitHub 搜索、Google 和各类 AI 爬虫都优先读这一行。建议中英文都放进去，把最常被搜索的词写全：

```text
Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能
```

命令行一键设置（需要 `gh` 登录所有者账号）：

```bash
gh repo edit ZeKaiNie/universal-examprep-skill --description "Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能"
```

### 2. Topics（标签）

GitHub 的 topic 搜索和“Explore”推荐完全依赖它；现在仓库一个 topic 都没有。topic 只能是小写字母、数字和连字符，最多 20 个，建议：

```bash
gh repo edit ZeKaiNie/universal-examprep-skill \
  --add-topic exam-prep --add-topic exam --add-topic study-tool --add-topic ai-tutor --add-topic education \
  --add-topic students --add-topic quiz --add-topic cheat-sheet --add-topic study-guide --add-topic flashcards \
  --add-topic agent-skill --add-topic claude-code --add-topic codex --add-topic cursor --add-topic antigravity \
  --add-topic gemini-cli --add-topic llm --add-topic pdf --add-topic python --add-topic mit-license
```

### 3. 网站链接与社交预览图

- About 栏的 Website 填 README 的中文锚点或发布页（`https://github.com/ZeKaiNie/universal-examprep-skill/releases/latest`），搜索结果会多一条入口。
- Settings → General → Social preview 上传一张 1280×640 的图：左边 `assets/exam-panic.png`，右边一句话“Your slides → an AI tutor that shows the figures and quizzes you with your homework”。分享到微信、X、Reddit 时这张图决定点击率。

### 4. 仓库名

现在的仓库名 `universal-examprep-skill` 和产品名 “Exam Cram Coach / 期末极速备考教练” 不一致，搜索任一名字都只命中一半。GitHub 重命名后旧链接自动跳转，风险很低。建议改名为 `exam-cram-coach`：

```bash
gh repo rename exam-cram-coach -R ZeKaiNie/universal-examprep-skill
```

改名后把 README、发布说明和这份文档里的链接换成新地址即可（旧地址仍可用）。

### 5. 把项目登记到会被搜索的地方

- **Agent Skills 目录**：向 anthropics/skills、各家 “awesome-claude-code / awesome-codex / awesome-cursor” 列表提交条目，标题用 “Exam Cram Coach — exam prep tutor from your own course files”。
- **Awesome 列表**：awesome-education、awesome-llm-apps、awesome-chatgpt-prompts 类。
- **中文社区**：V2EX、少数派、知乎、B 站的“考试周/期末复习工具”话题；标题直接写用户会搜的话，例如“把课件 PDF 扔给 Claude Code，它按章讲课、用作业考你、图也能看”。
- **Release 通知**：每次发布在 GitHub Discussions 开一帖，标题带版本号和一句人话。

### 6. README 第一屏

搜索引擎和 AI 摘要只看前几百字。本 PR 已把标题行和第一段改成“功能 + 人群 + 关键词”式写法（见下）；请保持这个位置始终是最新、最完整的一句话，不要放徽章以外的图在最前面。

## 二、本 PR 改了什么（不需要额外操作）

| 改动 | 目的 |
|---|---|
| `README.md` / `README.zh.md` 第一段改写，底部新增“关键词 / Keywords”段 | 覆盖人和模型用中英文可能搜索的说法（exam prep tutor、study from lecture slides、quiz from homework、错题本、考前突击、划重点、小抄……） |
| `SKILL.md` 的 `description` 扩充触发词 | 智能体是按 description 匹配是否调用技能的；加入期中/考研/考证/复习/刷题/讲义/课件/真题/小抄、final/midterm/revision/flashcards/past papers/cheat sheet 等 |
| 新增 `llms.txt` | 给 AI 爬虫和智能体的项目摘要（llms.txt 约定），含用途、入口、命令和中英关键词 |
| `docs/discoverability.md`（本文） | 维护者操作清单 |

## 三、怎么验证

- GitHub 搜索：`exam prep skill`、`期末复习 claude code`、`quiz from homework agent` 应能在前几条看到本仓库。
- 让任一智能体“找一个能把课件 PDF 变成 AI 家教的 Claude Code 技能”，看它是否引用本仓库。
- Google Search Console 或 `site:github.com "exam cram coach"` 观察收录。

---

# English

This checklist is for the repository maintainer. The first half is **settings only the owner can change** (a few minutes); the second half explains what this PR already changed and why.

## 1. Repository settings (owner action)

### 1.1 Description (the About line)

GitHub search, Google and AI crawlers read this line first. Put both languages and the most-searched words in it:

```text
Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能
```

```bash
gh repo edit ZeKaiNie/universal-examprep-skill --description "Exam Cram Coach · AI exam-prep tutor skill for Claude Code / Codex / Cursor / Antigravity: teaches from your lecture PDFs, shows the figures, quizzes from your homework & past papers, cites sources. 期末复习·考前突击·刷题·错题本·小抄的智能体技能"
```

### 1.2 Topics

Topic search and Explore recommendations depend entirely on topics; the repository has none today. Topics are lowercase ASCII, at most 20:

```bash
gh repo edit ZeKaiNie/universal-examprep-skill \
  --add-topic exam-prep --add-topic exam --add-topic study-tool --add-topic ai-tutor --add-topic education \
  --add-topic students --add-topic quiz --add-topic cheat-sheet --add-topic study-guide --add-topic flashcards \
  --add-topic agent-skill --add-topic claude-code --add-topic codex --add-topic cursor --add-topic antigravity \
  --add-topic gemini-cli --add-topic llm --add-topic pdf --add-topic python --add-topic mit-license
```

### 1.3 Website link and social preview

- Set the About “Website” to the latest release page; it adds one more indexed entry point.
- Settings → General → Social preview: upload a 1280×640 image (mascot from `assets/exam-panic.png` on the left, one sentence on the right: “Your slides → an AI tutor that shows the figures and quizzes you with your homework”). This image decides the click-through rate on X, Reddit and WeChat.

### 1.4 Repository name

`universal-examprep-skill` does not match the product name “Exam Cram Coach”, so each search hits only half of the mentions. GitHub redirects old URLs after a rename, so the risk is low. Suggested: `exam-cram-coach`.

```bash
gh repo rename exam-cram-coach -R ZeKaiNie/universal-examprep-skill
```

### 1.5 Register where people and agents look

- Agent-skill directories and awesome lists (awesome-claude-code, awesome-codex, awesome-cursor, awesome-education, awesome-llm-apps) with the title “Exam Cram Coach — exam prep tutor from your own course files”.
- Chinese communities (V2EX, sspai, Zhihu, Bilibili) under exam-week topics, titled the way students search.
- One GitHub Discussions post per release.

### 1.6 The first screen of the README

Search engines and AI summarizers read only the first few hundred characters. This PR rewrote the title line and opening paragraph as “what + for whom + keywords”; keep that spot current and complete.

## 2. What this PR changed (no action needed)

| Change | Purpose |
|---|---|
| `README.md` / `README.zh.md`: rewritten opening paragraph, new “Keywords” section at the end | cover the phrases people and models search in both languages |
| `SKILL.md` `description`: more trigger words | agents match skills on the description; added midterm/final/revision/flashcards/past papers/cheat sheet and 期中/考研/考证/复习/刷题/讲义/课件/真题/小抄 |
| new `llms.txt` | project summary for AI crawlers and agents (llms.txt convention) with purpose, entry points, commands and bilingual keywords |
| `docs/discoverability.md` (this file) | the maintainer checklist |

## 3. How to verify

- GitHub search for `exam prep skill`, `期末复习 claude code`, `quiz from homework agent` should list this repository near the top.
- Ask any agent to “find a Claude Code skill that turns lecture PDFs into an AI tutor” and see whether it cites this repository.
- Watch indexing with `site:github.com "exam cram coach"` or Google Search Console.
