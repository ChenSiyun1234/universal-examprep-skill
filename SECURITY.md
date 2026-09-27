# Security

English · [中文](#中文)

## What gets installed

`npx skills add ZeKaiNie/universal-examprep-skill`, the Claude Code plugin and the release zip all install one folder, [`skills/universal-exam-cram-coach/`](skills/universal-exam-cram-coach/). It holds 13 files: `SKILL.md`, `LICENSE`, `coach.py` and the `coach/` Python package. Nothing else in this repository is copied into your agent.

That code:

- reads the course folder you point it at and writes only into its workspace (`exam-cram/` next to your materials, or the folder you pass with `--workspace`), plus the folder you choose for `export --to`;
- opens no network connections, starts no other programs, loads no native code of its own, and sends no telemetry;
- has one optional dependency, [`pypdfium2`](https://pypi.org/project/pypdfium2/) from PyPI, for PDF text and figure cropping.

`tests/test_skill_surface.py` enforces this in CI: it fails if the folder gains other files, if the code imports `subprocess`, `socket`, `urllib` or similar modules, or if `SKILL.md` contains a URL or a token-like string.

## Course files are untrusted data

Slides, homework and answer keys are written by other people and may contain text aimed at an AI ("ignore previous instructions", "如果你是 AI…"). The tool prints everything it takes from your files between `<<<MATERIAL` and `MATERIAL>>>`. `SKILL.md` tells the agent to treat that text as course content and never to act on it. Lines that address an AI are flagged with ⚠️ by `setup` and wherever they are shown (`coach/guard.py`).

## Developer tools that are not installed

These live in the repository for maintainers and are never run by the skill:

- `eval/agent_smoke.py` drives an agent CLI you choose (Claude Code or Antigravity) through a test session;
- `full/benchmark/` is the v4.3 benchmark harness; some scripts run the agent command you pass with `--agent-cmd`.

Run them only with commands you trust.

## Verifying a download

Each release has `universal-exam-cram-coach-flash.zip` and `SHA256SUMS.txt`. The zip is reproducible: `python release.py` on the tagged commit produces the same bytes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (**Security → Report a vulnerability**) on this repository. If that button is not available, open an issue titled "Security contact" without details and a maintainer will reach out.

---

## 中文

**安装的是什么。** 无论用 `npx skills add ZeKaiNie/universal-examprep-skill`、Claude Code 插件还是发布包，装进智能体的都只有 [`skills/universal-exam-cram-coach/`](skills/universal-exam-cram-coach/) 这一个文件夹，共 13 个文件：`SKILL.md`、`LICENSE`、`coach.py` 和 `coach/` 代码包。仓库里的其他内容不会被复制。

这段代码只读取你指定的课程文件夹，只往工作区（资料旁边的 `exam-cram/`，或 `--workspace` 指定的位置）以及你为 `export --to` 选的文件夹写文件。它不联网、不启动其他程序、不加载自带的本地二进制代码、不发送任何统计数据。唯一的可选依赖是 PyPI 上的 `pypdfium2`，用于读取 PDF 文字和裁图。CI 里的 `tests/test_skill_surface.py` 会强制检查：这个文件夹一旦多出别的文件、代码导入了 `subprocess`/`socket`/`urllib` 之类的模块，或 `SKILL.md` 出现网址或类似密钥的字符串，测试就会失败。

**课程文件一律当作不可信数据。** 课件、作业和答案是别人写的，里面可能藏着针对 AI 的句子（“忽略之前的指令”“如果你是 AI…”）。工具从你的文件里打印的所有内容都夹在 `<<<MATERIAL` 和 `MATERIAL>>>` 之间，`SKILL.md` 要求智能体只把它们当课程内容，绝不照做。对 AI 说话的句子会在 `setup` 和显示它们的地方用 ⚠️ 标出（见 `coach/guard.py`）。

**不会被安装的开发者工具。** `eval/agent_smoke.py` 会驱动你指定的智能体命令行跑一轮测试会话；`full/benchmark/` 是 v4.3 的评测脚本，其中一些会运行你用 `--agent-cmd` 传入的命令。它们只供维护者使用，技能本身从不调用；只在命令可信时运行它们。

**核对下载。** 每个发布都附带 `universal-exam-cram-coach-flash.zip` 和 `SHA256SUMS.txt`；在对应标签的提交上运行 `python release.py` 会得到完全相同的字节。

**报告漏洞。** 请在本仓库使用 GitHub 的私密漏洞报告（**Security → Report a vulnerability**）。如果没有这个按钮，请开一个标题为 “Security contact” 的 issue（不要写细节），维护者会联系你。
