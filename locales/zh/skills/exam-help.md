# exam-help — zh 学生侧文案包

> 本文件是学生可见文案的 zh 语言包；行为逻辑在 [skills/exam-help/SKILL.md](../../../skills/exam-help/SKILL.md)（控制层，单一事实源）。

## Student-facing Output
一屏看懂这套备考技能。详细规则见根目录 `SKILL.md` 与各子技能。

### 四步工作流
1. **建库**（`exam-ingest`）：上传资料 → 自动建 `wiki` + 题库 + 进度。
2. **授课**（`exam-tutor`）：按章惰性加载，隐喻讲概念 / 重点题精讲 / 画图先跑算法。
   只有已显式选择 `visual`，或本次明确要求 HTML/PDF/打印版时，才用 `exam-study-guide` 编译完整章节；默认 `chat` 不自动生成。
3. **测验**（`exam-quiz`）：题库抽题判分，错两次给提示/跳过/归档。
4. **复盘 + 小抄**（`exam-review` / `exam-cheatsheet`）：清错题与疑难点。`chat` 下自动进入的最终复习用对话总结；明确要小抄时可编译 `cheatsheet.md`，只有 `visual` 或明确要 PDF/打印版时才渲染 PDF。

### 学习模式 × 时间宽裕度（首次对话须问清）
- **3 学习模式**：`零基础从头讲`（顺讲每个知识点+关联题从易到难）· `某章起步补弱`（已会章节过一遍、不会的展开）· `查缺补漏`（全章知识点各配一道较难题，困惑再展开）。
- **4 时间宽裕度**（叠加）：`≤1天`（跳过开场澄清、偏好确认与反思式追问，直接教学；仍可用标准题库练习或阶段测验验证掌握）· `1-3天`（随机回问困惑点）· `3-7天`（知识点窗口系统：窗口内默认还会、窗口外回问）· `>7天`（窗口外用难题实测）。学生明确说“不要出题 / 不要问我”时才记录 `no_questions=true`、完全不出互动题，并把阶段上限设为 `covered_unverified`。
- 旧 `normal/sprint/panic/mock` 已废弃，`set --mode` 自动迁移并警告（`panic`→零基础从头讲＋≤1天、`sprint`→查缺补漏＋1-3天、`normal`/`mock`→查缺补漏）。

### 输出资源模式（不是首次必问的第四项）
工作区字段是 `artifact_mode`，规范值只有 `chat` / `visual`。
- **`chat`（对话省额，默认）**：旧工作区缺字段或值未知时也按此处理；正常对话教学并保存 `notebook` 与 `state`，不自动生成章节 HTML/PDF，也不自动生成小抄 PDF。
- **`visual`（视觉教材）**：只有学生明确选择后才用 `update_progress.py set --artifact-mode visual` 持久化；完整章节生成 HTML + PDF 并逐页视觉验收，最终小抄也可生成打印版。依赖或外部技能仍不得静默安装。
- 一次性明确要求某章 HTML/PDF/打印版，可临时覆盖 `chat`，但不改持久状态；`set --artifact-mode chat` 可恢复长期省额。智能体绝不读取或猜测订阅套餐，也不因“看起来额度高/低”自行切换。

### 工作区文件
- `references/wiki/chN_*.md` 分章知识库（唯一知识源，按需读） · `references/quiz_bank.json` 标准题库（唯一答案源）
- `study_plan.md` 阶段计划 · `study_progress.md` 进度 + 错题 + 💡疑难点（每轮更新、重启先读）· `study_guide/chNN.html` 可选的人类阅读版章节教材

### 6 大题型
`choice` 选择 · `subjective` 主观/计算 · `diagram` 画图 · `fill_blank` 填空 · `true_false` 判断 · `code` 代码。

### 防幻觉与来源标注
- 只在 `wiki`/题库范围内教学判分；资料没有就如实弃答。
- 🟢 来自资料 · 🟡 AI补充，可能与你老师讲的不完全一致 · ⚠️ AI生成答案，非老师/教材提供。
- 题库有相关题就不自编题；不把 AI 生成内容伪装成老师提供。

### 子技能何时用
`exam-ingest` 建库 · `exam-tutor` 讲 · `exam-study-guide` 编译可视教材 · `exam-quiz` 测 · `exam-review` 复盘 · `exam-cheatsheet` 小抄 · `exam-audit` 只读体检 · `exam-cram` 总编排。

### 语言
学生可见输出默认英文（学生用中文开场则简体中文）；工作区存了 `language`（`中文`/`English`/`双语`）时按派发规则切换；面向代理的控制指令保持英文、精确。详见 [`docs/language-policy.md`](../../../docs/language-policy.md)。
