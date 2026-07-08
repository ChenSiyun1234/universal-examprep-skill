# 语言策略 / Language Policy

本技能是**双语架构**：控制层用英文求精确可靠，学生可见层按持久化 `language` 单语言输出——**默认英文，学生用中文开场则简体中文**（`English` / `中文` / `双语`）。**不要把整套技能翻译成单一语言**——该用英文的地方保留英文（提升代理执行可靠性），学生真正看到的输出按其语言。

This skill is **bilingual by design**: an English *control plane* for precision and reliability, and a student-facing layer that is single-language per mode. Do **not** translate the whole skill into one language. Keep English where it improves agent reliability; student-visible output follows the persisted `language` mode — **English by default, Simplified Chinese when the student's opening message is in Chinese** (`English` / `中文` / `双语`).

---

## 双语落地范围 / Scope & rollout

The bilingual split lands in two steps and is now realized:
1. **Policy + provenance** — establish the language policy and mirror the canonical provenance labels into every entrypoint.
2. **Control-plane conversion** — the modular `skills/exam-*` files use **English control sections** (Purpose / Activation / Inputs / Workflow / Output Contract / Boundaries) while keeping **Simplified-Chinese student-facing examples** under `Student-facing Output`.
   (A8a) This is now **lint-enforced zero-CJK**: `tests/test_control_plane_language.py` scans every
   non-exempt `## ` section of `skills/*/SKILL.md`, the whole `AGENTS.md`, and every script's argparse
   `description`/`epilog`/`help` contract. Chinese may appear in control text only via three structural
   escapes: 「…」 (verbatim student-visible phrasing), `…` (code spans / persisted values), or the
   canonical-token allowlist (`ALLOWED_TOKENS`). Exempt zones stay Chinese by design: YAML frontmatter
   (trigger surface), `## Student-facing Output` bodies, CJK-headed template sections, the root
   `SKILL.md`, and `prompts/web_prompt.md`.

Root `SKILL.md` stays **Chinese-first** as the compatibility entrypoint, and `prompts/web_prompt.md` stays Chinese-first — neither is rewritten wholesale.

- 模块化 `skills/exam-*`：英文控制段 + `Student-facing Output` 下的中文学生示例（已落地）。
- 根目录 `SKILL.md` / `prompts/web_prompt.md`：维持**中文优先**，不整体改写。

> **阶段 6 rollout（active 入口对齐进行中）**：下文的单语言纯净与 EN 词表是**目标契约**，正在
> 分批落到各入口——C2b 把 `SKILL.en.md` / `prompts/web_prompt.en.md` 重写为零 CJK、清理 `SKILL.md` /
> `prompts/web_prompt.md` 的散英并对齐 `AGENTS.md` 语言条目；C2c 把 `skills/exam-*` 的 SFO 英文渲染块
> 改为纯英文。在对应入口对齐前，其旧的 token+gloss 文字仍可能存在——一律以本文件为准。

---

## Language state & dispatch（A8b：回复语言）

- 持久化：`study_state.json.language`，canonical `中文` / `English` / `双语`（别名经 `update_progress.py`
  `--language` 归一；未知值保留 + 告警）。**首问时技能默认持久化 `English`（学生用中文开场则 `中文`）**；脚本层空值兜底仍取 `中文`，仅作旧工作区（建于本改动前、`language` 未设）的兼容安全网，不影响新会话的英文默认。
- 首问：并入 A6 的**一次合并首问**（模式 × 时间宽裕度 × 语言）。语言行三语呈现——
  「语言 / Language：中文 / English / 双语」——这是学生可见输出里**唯一允许的混语言点**。
  紧迫开场按学生开场语言静默推断，**绝不推断 `双语`**。会话中途 `set --language <值>` 随时切换，
  下一条回复生效。

### 单语言纯净（SINGLE-LANGUAGE PURITY，MUST）

学生可见 prose **严格单语言**——按模式派发：

- **`中文` 模式**：学生可见 prose 零英文，全部固定话术用本文下方「常用中文标签」与
  「来源标注用词」的 zh canonical 词表。
- **`English` 模式**：学生可见 prose 零 CJK，全部固定话术用下方 **EN canonical 词表**——
  不再是 token+gloss（中文锚点 + 英文括注）形态，而是整句纯英文输出。
- **`双语` 模式**：组合规则（见下），每一侧各自单语言纯净。

**永久豁免（任何模式都不算违规）**：代码 span `…` 内容、文件名/路径、命令行、JSON 键值、
CLI flag、emoji 与圈号（🟢🟡⚠️①…⑦✅❌📊 等）、数学/单位记号与单 token 术语符号
（O(n)、DNA、pH 这类按符号对待，不算 prose）。

### EN CANONICAL VOCABULARY（`English` 模式词表，MUST 逐字）

`language=English` 时，下列固定话术**逐字**使用 EN canonical（`tests/test_language_purity.py` 逐字钉此表，en 面纯度清单分期至 C2b；
不许自创同义改写）。zh 列为对应的中文 canonical 字面（大多属下节「持久化/判分层词汇表」；进度面板四条源自
web 面板模板，不在十类之内）：

| 类别 | zh canonical | EN canonical |
| --- | --- | --- |
| 来源标签 ×3 | 🟢 来自资料 | 🟢 From your materials |
| | 🟡 AI补充，可能与你老师讲的不完全一致 | 🟡 AI-supplemented — may differ from what your teacher taught |
| | ⚠️ AI生成答案，非老师/教材提供 | ⚠️ AI-generated answer — not from your teacher or textbook |
| 七步块标 | ① 题面图 | ① Question figure |
| | ② 这题在问什么 | ② What's being asked |
| | ③ 图里要读的量 | ③ What to read off the figure |
| | ④ 核心公式 | ④ Core formula |
| | ⑤ 逐步演算 | ⑤ Step-by-step solution |
| | ⑥ 答案自检 | ⑥ Answer self-check |
| | ⑦ 知识点溯源 | ⑦ Source trace |
| 来源块行 | 题目来源：…｜答案来源：…｜<标签> | `Question source: … \| Answer source: … \| <label>` |
| 来源未知形态 | 来源未知 ／ 来源页未知 | Source unknown / Source page unknown |
| 收尾块 ×3 | 易错点 / 3分钟速记 / 现在轮到你 | Common pitfalls / 3-minute mnemonic / Your turn |
| 回执 ×2 | 已记录到错题本 / 已记录到疑难点 | Recorded to the mistake archive / Recorded to the confusion log |
| 阶段引用 | 阶段 N ／ 从 阶段 N 继续 | Stage N / Resuming from Stage N |
| 弃答句 | 资料里没有这道题的答案 | The materials do not contain an answer to this question. |
| 范围覆盖声明 | ⚠️ 临时覆盖你的 <scope> 范围偏好 | ⚠️ Temporarily overriding your <scope> scope preference |
| 资产标签 ×2 | 题面图 ／ 答案图 | Question-side asset / Answer-side asset |
| 进度面板标签 ×4 | 备考科目 / 当前复习 / 进度打卡 / 错题累积 | Subject / Current stage / Progress / Mistake log |

词表使用规则：

- **来源块行**：`English` 模式用 ASCII `|` 分隔（`中文` 模式保持全角 ｜）。`<label>` 段必须是
  三个来源标签的**全文之一，绝不允许只写 emoji**——该禁令在 zh/en 两侧同强度。
  来源未知时对应段写 Source unknown（元数据整体缺失）或 Source page unknown（知道文件、缺页码）。
- **收尾块**：EN 名称照旧**默认不输出**——触发条件与 zh 完全一致（学生主动要求，或已存
  收尾块偏好）。
- **弃答**：弃答句为完整句子；其后如补一句诚实说明（如建议问老师），说明也必须纯英文。
- **窗口复核提示**（zh 的 还记得/复述/做题实测 类）无逐字 EN 钉：用自然、简短、祈使的英文表达
  同一动作（如 Do you still remember … / Say it back in your own words / Prove it on a problem），
  不得夹中文。
- 面板数值、进度条、题号等非语言成分照常输出（豁免区）。

### `双语` composition rule（组合结构不变）

`双语` 仍是**组合规则**而非第三套模板：逐块 zh 在前、`> EN:` 镜像随后。新口径下的唯一变化：
**废除 token+gloss 混排**——zh 行用 zh canonical 词表、`> EN:` 行用上表 EN canonical 词表，
两侧各自单语言纯净；同一锚点在每侧各出现一次（各说各的语言），不再在英文句里内嵌中文 token。
### PERSISTED / JUDGING-LAYER VOCABULARY（持久化/判分层词汇表，MUST）

> 本节**取代**旧的 ANCHOR-INVARIANCE PRINCIPLE（锚点不变性）。旧原则要求十类中文字面在任何
> 语言模式下逐字节输出（英文模式加 gloss）；该要求已废除。十类字面的新身份如下。

以下十类中文字面是**持久化状态与 zh 模式 transcript 判分的 canonical 词汇**。学生可见输出
**按语言模式渲染**它们：`中文` 模式逐字输出中文；`English` 模式输出上节 EN canonical 词表的
对应句（唯一例外：第 8 类窗口复核提示语无逐字 EN 钉，用自然英文表达同一动作，见词表使用规则）；`双语` 模式 zh 行 + `> EN:` 镜像各出现一次：

1. 三个来源标注 canonical 标签（🟢/🟡/⚠️ 全文）
2. 范围覆盖声明 「⚠️ 临时覆盖你的 <scope> 范围偏好」
3. 七步模板块标（圈号 + canonical 中文名：① 题面图 … ⑦ 知识点溯源）
4. 来源块行 `题目来源：…｜答案来源：…` 与 来源未知/来源页未知
5. 收尾块名 易错点 / 3分钟速记 / 现在轮到你
6. 错题本/错题档案 与回执 已记录到错题本 / 已记录到疑难点
7. 阶段引用 `阶段 N`
8. 窗口复核提示语（还记得 / 复述 / 做题实测 类）
9. 资产标签 题面图 / 答案图
10. 弃答 canonical 资料里没有这道题的答案（及其变体）

这份中文词汇在两层**保持不变、与回复语言模式无关**：

- **持久化层**：`study_state.json` / `study_progress.md` / 全部脚本输出（`update_progress.py`
  回执、`ingest.py` 报告等）在**所有语言模式**下保持中文 canonical——机器词汇不随学生语言漂移。
  持久化 **VALUES**（`零基础从头讲` / `查缺补漏` / `≤1天` / `1-3天` / `中文` / `双语` / `在窗口`、
  偏好值 `七步精讲` / `文科变体` / `收尾块=…` 等）**永远中文**；`English` 模式的 prose 提到它们时
  **只进代码 span**、周围用英文转述（如 your mode `零基础从头讲` (teach from scratch)）。
- **判分层**：benchmark / behavior_smoke / drift 探测器**只解析 zh 模式 transcript**，钉的就是
  这份中文词汇；en 输出不喂 zh 探测器（en 形态由 en 词表与纯度测试覆盖，见 `tests/test_language_purity.py`）。

向非中文学生转述脚本回执/失败时，引用中文原文（代码 span）并附英文复述——
**绝不在转述中丢失 fail-loud 内容**。
### A8c：英文入口面 / English entry surfaces（derived renderings）

- `SKILL.en.md` 与 `prompts/web_prompt.en.md` 是**派生英文渲染（derived renderings）**：行为的
  **source of truth 是对应的中文文件**（根 `SKILL.md` / `prompts/web_prompt.md`）。两者不一致时
  **以中文文件为准**；改行为先改 zh，en 随后同步（PR 内同改或紧随其后）。
- en 面契约（今日由 `tests/test_language_purity.py` 的 EN 词表钉与反向锁钉住、其 T1 零 CJK
  清单分期为空；C2b 重写两个 .en 文件时恢复 T1 清单并把 `tests/test_language_policy.py` 的
  `A8cEnEntrypoints` 从锚点在场钉**反转**为纯度钉）：
  - **无 YAML frontmatter**——en 文件不是可触发的 skill 入口，是英文操作手册 / 可复制 prompt；
  - **零 CJK（zero-CJK purity）**：prose 与标题**零 CJK**；唯一豁免是代码 span——持久化中文
    VALUES / 中文文件名 / 命令示例可在代码 span 内出现。原「…」引用豁免与
    `EN_SURFACE_TOKENS` 锚点白名单**废除**：原先靠中文锚点 + gloss 表达的固定话术，改用
    上文 EN canonical 词表整句给出（三标签、七步块标、来源块行 shape、never-emoji-alone、
    弃答句、范围覆盖行等）；
  - 视觉资产门禁用 en 渲染 "Before asking, explaining, hinting, or solving"（与 zh 门禁
    同义同强度）。
- 这**不是** `locales/` 拆分、也不引入第二套行为——同一仓库、同一安装、同一控制层与状态词汇
  （持久化 vocab 仍为中文 canonical，见上节）。见 [`localization.md`](localization.md) 的 A8c 附记。
- `prompts/web_prompt.en.md` 因 web 端无持久化 `language`，自声明**默认回复语言为 English**（学生可说
  「中文」/「双语」随时切回）——这与本地/有状态形态的新默认**一致**（两者都默认 English，学生用中文
  开场则中文）；`prompts/web_prompt.md` 是中文入口面，默认简体中文。

## English control plane（控制层 = 英文优先）

These instructions are read by the agent (Claude / Codex), **not** the student. Prefer English, and keep them **precise, imperative, and testable**:

- **Workflow** — step order; what each step reads and writes.
- **Activation** — when a (sub)skill triggers.
- **Boundaries** — what the skill must not do.
- **Schema / Inputs / Outputs** — file layout and required fields (e.g. `quiz_bank.json` fields, validator exit codes, the `study_progress.md` contract).
- **Test rules** — exactly what the tests assert.
- **Safety rules** — path safety, progress-file protection, quiz_bank-only quizzing, anti-fabrication.

Write concrete, checkable behavior. **Avoid vague words** like "properly", "comprehensively", "as needed", "appropriately" unless the exact behavior is defined right there.

> 例：不要写「妥善处理越界提问」，要写「越界提问 → 标 🟡 AI 补充，或如实弃答」。

> 注：模块化 `skills/exam-*` 的控制段**已转为英文**；根 `SKILL.md` 维持**中文优先**（兼容入口），不强制逐句改写。新增控制指令一律遵循上面的英文 / 精确 / 可测原则。

---

## Chinese student-facing layer（学生可见层 = 简体中文）

Everything the student actually reads is single-language per the persisted `language` — **English by default, Simplified Chinese when the student's opening message is in Chinese**, and an explicit `中文` / `English` / `双语` choice is honored:

- 讲解（teaching explanations）
- 判分反馈（quiz feedback）
- 错题与疑难复盘（mistake & confusion review）
- 考前小抄（cheat sheet）
- 进度面板与提示（progress messages）
- 网页端提示词（`prompts/web_prompt.md`）

### 中文语气要求（必须）

- **具体**：说清「考什么、怎么答、哪里易错」，不要空泛。
- **简短**：一句能说清就不写一段；考前没时间读长文。
- **应试导向**：围绕「考场上怎么拿分」，给可照写的步骤 / 口诀。
- **不抽象、不翻译腔**：用中国学生平时说话的方式，别用「进行一个……的处理 / 对……加以系统阐述」这类生硬表达。

反例（别这样写）：「请对该知识点进行全面且系统的阐述。」
正例（这样写）：「这题考什么：……；标准答题步骤：1.… 2.… 3.…；易错点：……。」

### 常用中文标签（统一用词，便于学生扫读）

| 标签 | 用在哪里 |
| --- | --- |
| `当前阶段` | 进度面板 / 每轮开头点位置 |
| `这题考什么` | 讲题 / 判分时先点考点 |
| `标准答题步骤` | 给可照写的解题 / 得分步骤 |
| `易错点` | 提醒最容易丢分的地方 |
| `3分钟速记` | 口诀 / 极简记忆法 |
| `现在轮到你` | 把球抛回给学生练 |
| `已记录到错题本` | 归档错题后的回执 |
| `资料里没有明确答案` | 诚实弃答 |
| `🟡 AI补充，可能与你老师讲的不完全一致` | AI 补充内容的提醒（与下方 canonical 🟡 一致） |

### 来源标注用词（防幻觉，全技能统一）

本节是来源标注用词的**唯一权威来源（canonical）**：根目录 `SKILL.md`、`AGENTS.md`、`skills/exam-*` 各入口都以这里为准，避免不同入口出现「竞争性」标注。

- 🟢 **来自资料** — 直接源自学生上传的老师重点 / 教材 / 真题，可信度高。
- 🟡 **AI补充，可能与你老师讲的不完全一致** — 资料没覆盖、AI 用自身知识补的背景，提醒以老师为准。
- ⚠️ **AI生成答案，非老师/教材提供** — 老师只勾了题没给答案、由 AI 代答的，每一个都要标。

各入口可在上述标记后追加说明（如「以老师为准」），但**核心标记与措辞须与本节一致**；**绝不**把 AI 生成 / 补充的内容写得像老师给的标准答案——那本身就是一种幻觉。

---

## 不要做的事（Out of scope for this policy）

- 不要把整套技能翻成纯英文或纯中文。
- 不要为了「统一语言」把英文控制指令改成中文而牺牲精确性。
- 不要把学生看的中文写成翻译腔 / 学术腔。
- 不要借语言改写**削弱以下行为**：知识来源标注、零基础重点题精讲、画图先跑算法、6 大题型、quiz_bank 抽题、`study_progress.md` 进度断点、疑难追踪、路径 / 进度安全、网页可移植。

> 相关文档：[`skill-architecture.md`](skill-architecture.md)（技能结构）· [`agent-portability.md`](agent-portability.md)（跨 host 可移植）· [`localization.md`](localization.md)（本地化边界：为何暂不拆 `locales/`、将来怎么拆）· 根目录 `SKILL.md` / `AGENTS.md`（完整 / 浓缩规则）。
