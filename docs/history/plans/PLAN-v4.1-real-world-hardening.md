# v4.1 真实使用加固计划书

> **历史状态：已完成并由 v4.1 发布。** 本文仅保留为真实使用审计与实施记录，不再是当前实施规范。
>
> 状态：实施事实源。本文先于代码改动建立；后续每项实现、测试与 PR 说明都必须回扣本计划。
> 依据：一次真实的 EEC 160 一天突击流程。材料包含 9 章讲义与多份作业；第 1 章 `ch01.pdf` 共 95 页，已逐页视觉复核。
> 目标仓库：`ChenSiyun1234/universal-examprep-skill`，最终以独立草稿 PR 提交到其 `main`。

---

## 1. 本次真实使用路径

1. 从 GitHub 安装 v4.0，并核对 tag/commit。
2. 对课程目录运行依赖预检、材料解析、建库、题库校验、视觉索引与告警接管。
3. 初始化 `study_state.json`，一次写入学习模式、时间预算与双语偏好。
4. 惰性加载第 1 章 wiki，选择一个标准题库例题，生成双语讲解并写入 notebook。
5. 更新阶段进度。
6. 学生发现“整章没有图片且例题显著不足”后，重新对第 1 章 95 页做逐页视觉审计并追查责任链。

这条路径覆盖了“安装 → ingest → workspace → tutor → notebook → progress → audit”，足以暴露跨模块契约缺口；但尚未覆盖实际答题判分、错题复盘与小抄编译。

---

## 2. 已发现缺陷

| ID | 级别 | 缺陷 | 真实证据 | 根因 |
|---|---|---|---|---|
| D1 | P0 | 版本身份漂移 | v4.0 tag 的根 `SKILL.md` 仍声明 `metadata.version=3.0`，首次安装时因此被误判为旧版 | release tag 与 skill metadata 没有一致性门禁 |
| D2 | P0 | wiki 视觉覆盖严重不足 | 第 1 章人工确认 19 个视觉页，wiki 仅嵌入 p58，覆盖率 1/19 | D5 只渲染行首带 `Figure/Table/图/表 + 编号` 的页，不复用通用视觉索引 |
| D3 | P0 | 答案侧视觉缺口不告警 | Example 1.14 p50 的二维样本空间图、Quiz 1.5 pp72–73 的概率表没有答案资产 | `build_visual_index.py` 记录 `answer_pages_visual`，但 suspects 只判断题面 `q_hits` |
| D4 | P0 | `visual_suspects=0` 容易被误读 | 报告为 0，但 wiki 仍缺 18 个视觉页，答案侧也有缺口 | 指标命名和汇总没有声明“仅题面侧、仅当前 canonical bank” |
| D5 | P0 | 教学例题与可判分题混为一层 | 源 PDF 有 25 个编号 Example；后处理把其中 13 个移出 canonical bank，占 52% | 缺少独立教学例题索引；AI takeover 只能选择“留在题库”或“整体排除” |
| D6 | P0 | 阶段完成没有证据门禁 | 只讲一个无图例题后，`set-check` 即可把整章标为完成 | checklist 只有 `done: bool`，没有 wiki/视觉/例题/notebook 证据 |
| D7 | P1 | validator 通过被误当成内容完整 | schema/path 0 错误、视觉 suspects 0，被写成 `overall_status=ready` | validator 不检查源例题保留率、wiki 视觉覆盖率或答案侧资产 |
| D8 | P1 | 视觉文本退化不显式报告 | p50 的矢量图在 wiki 中变成 12 个 NUL 字节和零散坐标字符 | 文本提取成功被等同于页面语义成功，没有二进制/NUL 与空间结构退化检查 |
| D9 | P1 | 视觉启发式存在可解释的误报/漏报 | ch01 索引报 18 页；人工确认 19 页，且存在 6 漏报、5 误报 | 召回优先词面/绘图计数没有 coverage 置信度与人工复核清单 |
| D10 | P1 | 紧迫模式被错误解释为“可以少教” | `≤1天` 被用于支持高度压缩并提前打卡 | 时间预算只定义提问节奏，没有定义各档的最低完成证据 |
| D11 | P0 | 数学公式以 raw LaTeX/伪分隔符暴露给学生 | 实际 notebook 使用 `(A\\cup B)`、`[P(A)=\\frac{...}{...}.]`；本地 Markdown 中直接显示反斜杠命令 | skill 没规定标准数学分隔符，执行代理用普通圆/方括号包 LaTeX；现有 HTML renderer 也不解析数学 |
| D12 | P0 | 把 Markdown 事实源误当成人类教材成品 | `.md` 不能保证宿主支持数学扩展，也没有把 wiki、课件图、例题、quiz 与通俗讲解组织成一个可直接阅读的版面 | 缺少面向学生的独立渲染层与渲染后视觉验收；Markdown 同时承担机器源和最终 UI 两种冲突职责 |
| D13 | P1 | PDF 能力与特定 Agent/供应商耦合 | Codex、Claude Code 与通用 Agent Skills 环境拥有不同的原生 PDF 能力、安装入口和许可证；单一下载指令无法安全覆盖所有运行时 | 缺少能力适配层、官方来源白名单、版本审查记录与“不静默下载”供应链策略 |
| D14 | P1 | 自动生成视觉教材无法尊重额度偏好 | 低额度用户只想沿用 v3 式对话教学，却可能为每章自动组织 HTML/PDF；高额度用户又希望直接得到打印版 | Agent 不能可靠读取订阅等级，框架也没有独立于学习模式的持久化产物偏好与一次性覆盖规则 |
| D15 | P0 | 整页回挂可能提前泄露答案 | 题面与解答共页，或答案专属页曾被旧版/手工嵌入 wiki 时，通用整页截图会在提问前暴露解答 | 视觉索引只有“视觉页”概念，没有全局 prompt/answer 页角色与共享页 fail-closed 门禁 |
| D16 | P0 | 教学例题保留基线可被重写报告缩减 | 只以最近一次 `ingest_report.json` 为保留分母时，较小快照或手工重写报告可让已发现例题从验收中消失 | 缺少独立、append-only 且逐章校验的教学基线事实源 |
| D17 | P1 | 生成文件写入与链接边界不够坚固 | ingest/视觉输出中途失败可能留下半成品；符号链接或硬链接输出可能把工作区写操作传递到外部文件 | 写盘路径没有统一采用原子替换，也没有在最终输出端完整拒绝链接/特殊文件 |
| D18 | P1 | 视觉产物预检会无必要阻断，PDF 能力路由顺序矛盾 | 纯文本章节选择 `visual` 也被强制要求 MathML；已有原生 PDF skill 时仍可能先被 Edge/Chrome 缺失拦住 | 依赖 `needed` 只看 `artifact_mode`，没有读取当前章真实公式内容；说明书在选择 native/browser adapter 前就调用浏览器 `--pdf` 路径 |

### 2.1 责任边界

- 原始 PDF 可正常渲染；不是材料损坏。
- Example/Quiz 行首识别完整；`raw_input` 与 wiki 均保留了第 1 章全部 25 个 Example 和 7 个 Quiz。
- 13 个例题消失发生在 ingest 后的 AI 清理；仓库脚本没有自动要求删除它们。
- v4.0 代码的视觉规则是诱因，但“宣布 ready”与“提前打卡”的直接责任属于执行代理用窄指标替代用户目标验收。

---

## 3. 用上且有价值的功能

| 功能 | 使用结果 | 保留/强化方向 |
|---|---|---|
| GitHub 安装与可追溯 commit | 成功确认安装内容与 v4.0 commit 一致 | 增加版本一致性测试，消除 metadata 歧义 |
| 依赖预检 | PDF 文本、渲染与浏览器依赖在 ingest 前一次确认 | 保留；加入视觉能力级别说明 |
| PDF 文本抽取与页级 provenance | ch01 的 95/95 页均进入 wiki，并保留页码注释 | 保留；视觉退化必须另行报告，不能用文本成功代替 |
| Example/Quiz 标记与 Problem/Solution 配对 | 第 1 章 25 个 Example、7 个 Quiz 全部识别，独立解答页配对正确 | 保留；输出独立教学例题索引 |
| 题面视觉资产门禁 | 明确依赖图的 diagram 项具备题面/答案资产与 fail-closed 规则 | 保留；扩展到答案侧和 wiki 侧 |
| 告警与 AI takeover 清单 | `missing_answer_ids` 成功暴露了 13 个无独立 Solution 的例段 | 保留；接管动作必须区分“不可判分”与“不可教学” |
| `study_state.json` 单一事实源 | 模式、时间、语言与进度可持久化且 md 自动渲染 | 保留；阶段完成增加结构化证据 |
| workspace registry | 材料目录与复习工作区落点明确 | 保留 |
| notebook-first | 双语讲解先落盘、索引可跳转 | 保留；完成门禁校验 notebook 证据 |
| 来源标签与双语派发 | 讲解来源块与中文/英文镜像能够稳定输出 | 保留 |
| exam-audit + PDF 视觉检查 | 用户质疑后能只读追责，最终定位到具体页面和代码路径 | 强化为 ingest 后自动完整性门禁，而不是事后补救 |
| validator、题型/关键词/难度校验 | canonical bank 可判分、字段完整、选择器可运行 | 保留；明确其结论只代表 schema/题库健康 |

---

## 4. 尚未实际使用或尚未验证的功能

下列能力不能因为“存在测试”就宣称在本次真实流程中有效：

- `exam-quiz` 的实际出题、学生作答、判分与连续两次答错分支；
- 错题写入、`mistakes/` 镜像与 `exam-review` 扫雷；
- confusion tracker 的自动捕获与复述回顾；
- knowledge window 在 `3-7天` / `>7天` 档的进出与难题复核；
- 受限 source scope、临时覆盖提示与混合题池恢复；
- diagram “先跑算法再画图”的真实题目链路；
- RAG 检索工具在学生问答中的实际召回（本次主要直接读取当前章 wiki）；
- cheatsheet 编译、指定页数 PDF 渲染与打印视觉验收；
- file-less/web fallback；
- 长会话漂移、重启恢复与多轮学习闭环。

本 PR 只为相关改动补定向回归，不伪造这些功能已经完成真实验证。后续应另开端到端课程实测。

---

## 5. 本 PR 的设计决策

### 5.1 视觉覆盖分成三侧

视觉完整性必须分别统计：

1. **wiki 侧**：材料视觉页是否嵌入对应 wiki，或明确列入待接管清单；
2. **题面侧**：视觉题是否有可展示的 `question_context`；
3. **答案侧**：视觉答案页是否有 `answer_context`，且只在解答阶段展示。

`suspects` 保留为题面兼容字段，同时新增明确命名的 `prompt_suspects`、`answer_suspects` 与 `wiki_visual_coverage`。报告必须写清分母。

### 5.2 wiki 配图复用通用视觉索引

- 不再把 caption regex 当作全部视觉页。
- 在 `build_visual_index.py` 增加幂等的 `--apply-wiki`：把已检测视觉页渲染后，按 `<!-- source.pdf p.N -->` 页锚点回挂到对应 wiki 原位置。
- 默认每章上限 30 页；超限不静默，完整列入 coverage missing/warnings，交给 AI 或用户处理。
- 保留 caption-only builder 行为以兼容旧调用，但 ingest 工作流必须运行 visual index 的 wiki 应用阶段。
- 不把答案资产挂成题面资产；角色与显示顺序保持 fail-closed。

### 5.3 教学例题与标准题库分层

- material builder 继续产生现有 `quiz_bank`，保持兼容。
- 同时产生 `teaching_examples` 快照；ingest 写入 `references/teaching_examples.json`。
- 每项标记 `teaching_role=paired_problem|worked_example`、来源页、答案页与资产。
- 没有独立 Solution 的完整演示可以不参与标准判分，但不得从教学索引消失。
- 新增按章列表工具，tutor 只读取当前章条目，不把全课程索引塞进上下文。

### 5.4 阶段完成需要结构化证据

- `study_state.json` 增加向后兼容的 `phase_evidence`。
- 新增官方命令记录当前阶段的 wiki、视觉、教学例题与 notebook 证据。
- 新版工作区存在视觉/教学 manifest 时，`set-check` 不得只凭布尔操作完成阶段；证据不足时 fail-loud。
- 旧工作区没有 manifest 时保持兼容，但输出明确警告。
- `≤1天` 可以免学生问答式 checkpoint，但不能免 wiki/视觉/例题/notebook 覆盖证据。

### 5.5 “可用”与“完整”分开

- validator 的 schema/path 结论继续叫“可运行”。
- 新增完整性摘要：源例题数、教学索引保留率、canonical 可判分率、wiki 视觉覆盖率、题面/答案资产覆盖率、未接管条目。
- 只有完整性 blocker 为 0 才允许上层写 `ready`；否则使用 `usable_with_gaps`。

### 5.6 Markdown 作为事实源，HTML/PDF 作为人类教材

- Markdown 继续承担可检索、可 diff、可溯源的机器事实源，但不再宣称它天然是最终教材。
- 所有新写入的数学统一用标准 `$...$` / `$$...$$` 分隔符；禁止 `(\\frac...)`、`[\\sum...]` 这类伪分隔符。validator 对可疑 raw/伪 LaTeX fail-loud 告警。
- 新增按章渲染器，生成自包含 `study_guide/chNN.html`；离线把 LaTeX 转成浏览器原生 MathML，缺转换依赖时明确退出并给安装命令，绝不静默保留 raw 公式。
- 教材按“通俗概念 → 公式与符号解释 → 当前章 teaching examples → quiz 题面图 → 可展开解答/答案图 → notebook 精讲 → 原页溯源”组织；图片内嵌进 HTML，题面图永远先于答案图。
- 教材界面读取 `study_state.json.language`：中文、English 与双语分别派发标题、空层说明、题面/答案标签和 canonical provenance；渲染器不擅自翻译事实内容，双语正文必须先由 tutor 持久化。
- 可选用本地 Edge/Chrome 打印为舒适阅读版 PDF；HTML/PDF 都要做视觉验收。渲染器只惰性读取指定章节，不把整门课塞进一个产物。

### 5.7 PDF 能力采用 Agent 适配器，而不是复制第三方 skill

- 框架提供自有、供应商无关的 `exam-study-guide` 工作流与确定性渲染脚本，保证即使没有原生 PDF skill 也能生成 HTML，并在本地浏览器可用时输出 PDF。
- 另建机器可读的 PDF capability registry，逐一说明 Codex、Claude Code 与通用 Agent Skills 运行时的首选能力、官方来源、审查版本、许可证边界和后备路径。
- Codex 优先使用已安装的原生 `pdf` skill；Claude Code 指向 Anthropic 官方 `document-skills` 插件；通用实现遵循 Agent Skills 开放规范并使用本仓库 skill。
- 不复制或改写许可证不允许再分发的第三方实现，不把已弃用仓库当成推荐安装源，也不在学生复习过程中执行未经确认、未经固定版本审查的网络下载。
- 外部链接只提供安装/发现能力；本框架的正确性、安全路径校验、题面图先于答案图以及逐页视觉验收不能外包给第三方 skill。

### 5.8 额度友好的教材输出模式

- 新增独立、持久化的 `artifact_mode`，canonical 仅 `chat` / `visual`，不与学习模式、时间预算或语言混在一起。旧工作区缺字段时按 `chat` 处理，保持 v3 式省额度行为。
- `chat`（对话省额）是安全默认：正常授课并保存必要的 state/notebook，但不自动编译章节 HTML/PDF，也不自动打印小抄；用户一次性明确要求 HTML/PDF/打印版时可以临时覆盖，不必永久改偏好。
- `visual`（视觉教材）只能由用户明确选择（如“不在乎 token”“以后每章给我打印版”）；完整章节自动生成 HTML + PDF 并逐页视觉验收。依赖安装仍需单独同意，绝不因该模式静默下载。
- Agent 不读取也不猜订阅套餐；自然语言选择由官方 `update_progress.py set --artifact-mode <chat|visual>` 固化。未知值运行时 fail-safe 回退 `chat` 并告警。

### 5.9 内容感知、后端感知的产物预检

- 首次材料预检只把原材料确实需要的 PDF 读取/页面渲染后端列为硬依赖；尚未落盘的章节公式与尚未选择的 PDF 后端显示为 `unknown`，不诱导安装。
- 当前章事实源就绪后，使用 `--workspace <ws> --chapter <N>` 只扫描该章 wiki、教学例题、quiz 与 notebook；只有标准 `$...$` / `$$...$$` 公式实际存在时才要求固定版 MathML 转换器。
- PDF 先从能力 registry 选定 `native` / `browser` / `html`，再用 `--pdf-backend` 预检；只有 `browser` 路径把 Edge/Chrome 视为硬依赖。探测错误以 `probe_error` 退出，不能伪装成“请安装某依赖”。
- 固定执行顺序为“显式产物偏好 → 后端探测/选择 → 当前章依赖预检 → HTML → PDF → 逐页视觉验收”；原生后端消费已校验 HTML，不得因仓库浏览器后备缺失而失败。
- 行为冒烟同时覆盖 chat 不自动渲染、显式 visual、一次性 PDF 不污染长期状态、订阅名称不触发切换、后端先选后预检等正反轨迹。

---

## 6. 实施步骤

### Step 1 — 计划与红测

- [x] 写入本计划书。
- [x] 为 D1–D17 建立定向失败测试或 fixture。
- [x] 记录现有测试基线，确保不是在已有红灯上开发（全量 `unittest` exit 0）。

### Step 2 — 视觉索引、答案资产与 wiki 回挂

- [x] 扩展 `image_question_index.json`：区分 prompt/answer suspects。
- [x] 让 `--apply` 安全补答案侧资产，角色固定为 `answer_context`。
- [x] 实现幂等 `--apply-wiki` 与每章 cap。
- [x] 写入 `wiki_visual_coverage`，列出 detected/embedded/missing，并把答案专属页分母独立延期。
- [x] 让 validator/audit 对 coverage gap、答案页手工暴露与题解共页发出明确 blocker。
- [x] 增加 NUL/二进制文本退化警告。
- [x] 全局推导 prompt/answer 页角色：答案专属页不进 wiki；题解共页须经审核的题面裁图才能解除阻断。

### Step 3 — 教学例题保留层

- [x] material builder 输出 `teaching_examples`。
- [x] ingest 写入 `references/teaching_examples.json` 与统计。
- [x] 新增 append-only `references/teaching_baseline.json`，使较小快照/报告不能缩减保留分母。
- [x] 新增按章列举工具，避免整库加载。
- [x] validator 检查索引 ID、来源、资产角色与保留率。
- [x] tutor/ingest/audit 契约明确：移出可判分题库不等于移出教学层。

### Step 4 — 阶段完成门禁

- [x] state schema 增加 `phase_evidence`，迁移不丢旧状态。
- [x] 增加官方 evidence 命令和路径安全校验。
- [x] `set-check` 在新版 manifest 存在时验证必需证据，包括答案暴露与题解共页 blocker。
- [x] 更新双语进度渲染、帮助与行为测试。

### Step 5 — 版本与结论措辞

- [x] 先修复 v4.0 tag 被 metadata 3.0 误报的问题；v4.1 发版时把 metadata 升为 4.1，并增加 release tag 一致性门禁。
- [x] 把 `visual_suspects=0`、validator 0 warning 的文档措辞限定到真实范围。
- [x] 增加 `ready / usable_with_gaps` 判定契约。

### Step 5B — 可读数学与章节教材产物

- [x] 规定并测试标准 Markdown 数学分隔符，检测 raw/伪 LaTeX。
- [x] 新增按章 HTML 教材 renderer：离线 MathML、题面/答案图片角色、教学例题、quiz、notebook 与来源。
- [x] 增加可选 PDF 输出、缺依赖 fail-loud 与路径/图片安全测试。
- [x] tutor/cram/help 契约改为“先持久化事实源，再生成并视觉验收人类教材”。
- [x] 用第 1 章真实 notebook 的公式形态做只读回归输入，不提交课程内容。
- [x] 覆盖中文 / English / 双语三种教材界面；English UI 零中文，双语同时显示两侧 canonical 标签。

### Step 5C — 跨 Agent PDF 能力适配

- [x] 增加机器可读 capability registry 与面向维护者的适配说明，区分 Codex、Claude Code 和通用 Agent Skills。
- [x] 固定并记录审查过的官方来源 commit；第三方 skill 仅链接，不复制受限实现。
- [x] 规定原生能力优先、框架后备、缺能力 fail-loud、安装需用户确认的路由顺序。
- [x] 增加 registry schema/链接/许可证字段测试，并确保分发包包含适配文件与自有 `exam-study-guide` skill。

### Step 5D — 额度友好的输出模式

- [x] 在 i18n/state/validator 中增加 `artifact_mode=chat|visual`，旧状态默认 chat，显示词与别名可往返。
- [x] 增加 `set --artifact-mode` 与中英帮助；不得把订阅等级当作可探测输入。
- [x] tutor/study-guide/cheatsheet 契约按模式路由，并允许显式请求的一次性覆盖。
- [x] 增加默认、别名、迁移、未知值 fail-safe 与官方 CLI 回归测试。

### Step 5E — 内容/后端感知的依赖路由

- [x] 增加 `--workspace + --chapter` 章节公式探测；无公式章节不要求 MathML，Markdown 代码区不误判。
- [x] 增加 `--pdf-backend auto|native|browser|html`；只有明确浏览器后端才把 Edge/Chrome 列为硬依赖。
- [x] 探测失败使用 `probe_error`/exit 2，不进入 `missing_needed`，也不显示误导性安装命令。
- [x] 统一所有入口为“选后端 → 当前章预检 → HTML → PDF → 逐页验收”，并增加确定性行为冒烟正反例。

### Step 6 — 验证

- [x] 运行视觉、builder、ingest、validator、state 定向测试。
- [x] 运行全量 `unittest`（基于作者 `main` 的 v4.1 干净发布分支最终 1441 tests，27 skipped，exit 0；release-only tag 门禁另以 `v4.1` 环境实跑通过）。
- [x] 接管草稿 PR 首轮 CI：修正符号链接错误分类顺序，以及 Windows 8.3/长路径混用导致的 Markdown 资源路径越界；增加确定性别名回归测试。
- [x] 运行 skill 结构/分发构建检查。
- [x] 用无真实课程内容的合成 PDF/假 backend 做端到端回归。
- [x] 使用新鲜子代理做不泄露预期答案的前向测试，并对 D18 三项 P1 修复做二次复核。

### Step 7 — 发布

- [x] 审查完整 diff，确认只包含本计划范围。
- [x] 显式暂存文件、创建单一意图 commit。
- [x] 推送 `codex/eec160-usage-fixes` 到 fork。
- [x] 向 `ChenSiyun1234/universal-examprep-skill:main` 创建草稿 PR。
- [x] PR 正文列出根因、用户影响、兼容性、测试与仍未真实验证的功能。

---

## 7. 验收标准

1. 合成课程含“无 Figure 标题的矢量图页”时，视觉索引能发现并在 `--apply-wiki` 后回挂；未回挂页必须出现在 missing 清单。
2. 题面纯文本、答案页含图时，产生 `answer_suspect`；`--apply` 后只新增 `answer_context`，绝不提前展示。
3. bare Example 没有独立 Solution 时，仍进入 `teaching_examples.json`，且可以按章查询；是否进入 canonical bank 不影响其教学可达性。
4. 从 canonical bank 移除 worked example 后，validator 能证明教学索引仍保留它；若两处都缺失则告警。
5. 新版 manifest 存在时，无 phase evidence 的 `set-check` 失败且不污染 `study_state.json`。
6. `≤1天` 允许无互动 checkpoint，但视觉/例题/notebook 证据仍为必需。
7. 根 `SKILL.md` 声明 4.1，且 release job 会拒绝与 metadata 不一致的 tag。
8. 旧工作区与旧 raw input 继续可读；新增字段均为向后兼容。
9. 全量测试通过，分发包包含新增运行时脚本/契约文件。
10. 含 `\\frac`/`\\sum` 的章节在 HTML 中呈现为 MathML 而非 raw 反斜杠；缺数学转换依赖时命令非零退出且不留下伪成品。
11. 章节教材同时展示通俗讲解、标准公式、teaching examples、quiz 题面/答案资产与可定位溯源（文件 + 页码/题号）；题面资产顺序早于答案资产。为了保持离线、自包含和路径安全，外部 Markdown 链接可退化为可复制的引用文本，而不是强制保留可点击链接。
12. 相同教材任务在 Codex、Claude Code 与通用 Agent 环境中都有明确且不同的能力路由；外部 skill 来源可审计、不会静默下载安装，缺原生能力时仍有本框架后备或明确失败信息。
13. `study_state.language=双语` 时章节教材界面为中英双语；`English` 时界面不混入中文标签。渲染器只编译已持久化正文，不用未标来源的机器翻译冒充教材原文。
14. 缺少 `artifact_mode` 的旧工作区不自动生成 HTML/PDF；`chat` 模式只在显式单次请求时临时产出，`visual` 模式在完整章节后生成并验收 PDF；任何路径都不猜订阅或静默安装。
15. 纯文本章节的 `visual` 预检不要求 MathML；`native` 后端不要求本地浏览器，`browser` 后端缺浏览器时明确阻断；探测错误不会变成安装提示，行为轨迹保证预检早于渲染且单次 PDF 后仍保持 `chat`。

---

## 8. 风险与非目标

- 视觉分类仍是确定性启发式，不能冒充 AI 语义视觉；报告必须保留置信度和人工复核入口。
- `--apply-wiki` 会增加工作区体积，因此需要每章 cap、幂等命名和完整 missing 清单。
- 本 PR 不把所有 worked example 强行变成可判分题，也不生成伪官方答案。
- 本 PR 不重新跑 EEC 160 全课程并把课程材料提交入仓；测试只使用合成 fixture。
- 本 PR 不宣称 quiz/review/cheatsheet 等尚未真实走通的链路已经通过实战验证。
- 第三方 PDF skill 的可用性与上游兼容性不由本仓库担保；registry 记录的是审查快照，升级必须重新核对许可证、安装入口与行为契约。
- `artifact_mode` 是用户声明的资源偏好，不是套餐探测结果；PDF 渲染主要消耗本地计算，但组织更详细教材仍可能增加上下文/生成量，因此默认保守。
- 不改变来源标签、题面先于答案图、范围过滤与 notebook-first 等已有安全契约。
