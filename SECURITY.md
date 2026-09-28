# Security

English · [中文](#中文)

## What gets installed

`npx skills add ZeKaiNie/universal-examprep-skill` and the release zip install one folder, [`skills/universal-exam-cram-coach/`](skills/universal-exam-cram-coach/). It holds 13 files: `SKILL.md`, `LICENSE`, `coach.py` and the `coach/` Python package. The Claude Code plugin route first clones this repository as a marketplace, then installs only that folder as the plugin.

## What the code does

- **Reads** the course folder you point `setup` at. `figure` and `export` refuse files outside that folder and the workspace.
- **Writes** into its workspace (`exam-cram/` next to your materials, or the folder given with `--workspace`), into the folder you choose with `export --to`, `cheatsheet --out` or `figure --out`, and a one-line pointer to the last workspace used in `~/.exam-cram-coach/last_workspace`.
- **Never** opens network connections, starts other programs, loads native code of its own or sends telemetry.
- **Depends** optionally on [`pypdfium2`](https://pypi.org/project/pypdfium2/) from PyPI, for PDF text and figure cropping.

`tests/test_skill_surface.py` enforces the shape of the folder in CI. It fails if the folder gains other files, if the code imports `subprocess`, `socket`, `urllib` or similar modules, or if `SKILL.md` contains a URL or a token-like string.

## Course files are untrusted data

Slides, homework and answer keys are written by other people and may contain text aimed at an AI ("ignore previous instructions", "如果你是 AI…"). The tool prints everything it takes from your files (text, questions, answers, chapter listings, question previews) between `<<<MATERIAL id` and `MATERIAL>>> id`. The id is derived from the fenced text, and anything inside that looks like a fence marker is removed, whatever its case, width or hidden characters. Chapter titles taken from headings that address an AI are replaced with "Chapter N", and the cheat sheet leaves such excerpts out. `SKILL.md` tells the agent to treat all of it as course content and never act on it.

`coach/guard.py` also flags lines that address an AI, so the agent and the student notice them. That check is a heuristic. It catches common English and Chinese phrasings and sentences split across lines, but it can miss a reworded attack and can flag ordinary text, such as a psychology study quoting such an instruction. The fence and the rule in `SKILL.md` are the actual boundary.

## Developer tools that are not installed

These live in the repository for maintainers and are never run by the skill:

- `eval/agent_smoke.py` drives an agent CLI you choose (Claude Code or Antigravity) through a test session.
- `full/benchmark/` is the v4.3 benchmark harness. Some of its scripts run the agent command you pass with `--agent-cmd`.

Run them only with commands you trust.

## Verifying a download

Each release has `universal-exam-cram-coach-flash.zip` and `SHA256SUMS.txt`. The zip stores its files uncompressed with fixed metadata. Running `python release.py` on the tagged commit therefore produces the same bytes on any operating system.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting on this repository (**Security → Report a vulnerability**). If that button is not available, open an issue titled "Security contact" without details, and a maintainer will reach out.

---

## 中文

**安装的是什么。** 用 `npx skills add ZeKaiNie/universal-examprep-skill` 或发布包安装时，装进智能体的只有 [`skills/universal-exam-cram-coach/`](skills/universal-exam-cram-coach/) 这一个文件夹，共 13 个文件：`SKILL.md`、`LICENSE`、`coach.py` 和 `coach/` 代码包。Claude Code 插件方式会先把本仓库克隆为插件市场，再只把这个文件夹安装为插件。

**代码做什么。**

- **读取：** 只读 `setup` 指定的课程文件夹；`figure` 和 `export` 拒绝该文件夹和工作区以外的文件。
- **写入：** 工作区（资料旁边的 `exam-cram/`，或 `--workspace` 指定的位置）、你为 `export --to`、`cheatsheet --out`、`figure --out` 选的位置，以及 `~/.exam-cram-coach/last_workspace` 里记录上次工作区的一行路径。
- **从不：** 联网、启动其他程序、加载自带的本地二进制代码，也不发送统计数据。
- **依赖：** 唯一的可选依赖是 PyPI 上的 `pypdfium2`，用于读取 PDF 文字和裁图。

CI 里的 `tests/test_skill_surface.py` 会检查这个文件夹：一旦多出别的文件、代码导入了 `subprocess`/`socket`/`urllib` 之类的模块，或 `SKILL.md` 出现网址或类似密钥的字符串，测试就会失败。

**课程文件一律当作不可信数据。** 课件、作业和答案是别人写的，里面可能藏着针对 AI 的句子（“忽略之前的指令”“如果你是 AI…”）。工具从你的文件里打印的所有内容（正文、题目、答案、章节目录、题目预览）都夹在 `<<<MATERIAL id` 和 `MATERIAL>>> id` 之间。id 由框内文字算出；框内任何形似分隔符的文字，不论大小写、全角还是夹了隐藏字符，都会被去掉。对 AI 说话的章节标题会换成“第 N 章”，小抄里也会省略这类摘录。`SKILL.md` 要求智能体只把这些当课程内容，绝不照做。

`coach/guard.py` 还会标出对 AI 说话的句子，提醒智能体和学生注意。这个检查是启发式的：能识别常见的中英文说法和跨行断开的句子，但可能漏掉换了说法的攻击，也可能误报普通文字（例如心理学实验里引用的指令）。真正的边界是分隔标记和 `SKILL.md` 的规则。

**不会被安装的开发者工具。** 这些工具只供维护者使用，技能本身从不调用：

- `eval/agent_smoke.py` 会驱动你指定的智能体命令行跑一轮测试会话。
- `full/benchmark/` 是 v4.3 的评测脚本，其中一些会运行你用 `--agent-cmd` 传入的命令。

只在命令可信时运行它们。

**核对下载。** 每个发布都附带 `universal-exam-cram-coach-flash.zip` 和 `SHA256SUMS.txt`。发布包里的文件不压缩、元数据固定，所以在对应标签的提交上运行 `python release.py`，在任何系统上都会得到完全相同的字节。

**报告漏洞。** 请在本仓库使用 GitHub 的私密漏洞报告（**Security → Report a vulnerability**）。如果没有这个按钮，请开一个标题为 “Security contact” 的 issue，不要写细节，维护者会联系你。
