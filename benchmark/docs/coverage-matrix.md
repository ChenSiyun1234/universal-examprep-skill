# 能力 × 测试层覆盖矩阵 (Feature × Tier Coverage Matrix)

> 配套 [`testing-audit.md`](testing-audit.md)。一句话结论：**很多能力被「结构/指令」层静态测到，却没有被「行为」层执行验证。**

**图例**：✅ 覆盖　🟡 部分（结构/schema 层，**或** Tier 2 的确定性 mock 探测——非真 LLM 行为）　❌ 未覆盖　— 不适用

> **Tier 2 列说明**：🟡 = 本 PR（T2）的**确定性 mock 探测器**已覆盖该行为的产物断言（进 CI、零成本）；它**不等于**真 LLM 行为已验证——真 agent 冒烟是 opt-in、不进 CI（见 [`../behavior_smoke/`](../behavior_smoke/)）。

| 能力 | Tier 0 单元/静态 | Tier 1 工作区校验器 | Tier 2 行为冒烟 | Tier 3 完整 benchmark | Tier 4 长程漂移 | 当前缺口 | 可加的便宜指标 |
| :-- | :--: | :--: | :--: | :--: | :--: | :-- | :-- |
| LLM Wiki 惰性加载 | ❌（仅指令文本） | — | 🟡（best-effort 占位 `count_wiki_reads`，不在 CI 断言） | 🟡（skill 臂用 wiki，但不验惰性） | ❌ | 真「只读相关一章」需 transcript/LLM 才能验 | scripted transcript 里读文件调用数 = 1 章 |
| 一键 ingest 冷启动 | ✅（ingest 端到端单测） | 🟡（校验产物结构） | — | ❌ | — | 已较充分覆盖 | 维持现状 |
| 无 Python 降级写盘 | ❌ | — | 🟡（mock：手写工作区过 Tier-1 校验） | ❌ | — | 真禁用 Python 的端到端仍未测 | 确定性：手写工作区 → `validate_workspace` 退 0 |
| quiz_bank-only 出题 | 🟡（题库 schema） | 🟡（schema） | 🟡（mock：题号∈题库 + 编造题号被抓） | ❌ | — | 真 LLM 出题未验（opt-in） | scripted 出题 → 断言每题 id ∈ 题库 |
| 六种题型 | ✅（schema 接受 6 型） | ✅（schema 强制） | 🟡（fixture 覆盖全 6 型并过校验） | ❌（题集只有 factual/definition/numeric） | — | 真 LLM 按型出题/判分未验 | 固定题库上每型一题判分冒烟 |
| 画图题先跑算法再画 | ❌ | 🟡（`diagram_type` 告警） | ❌（fixture 有 render_hint，但无「先算后画」行为场景） | ❌ | — | 行为未测 | transcript 先跑算法再渲染 |
| 0 基础重点题精讲 | ❌ | — | 🟡（mock：四小节 考点/步骤/易错/速记） | ❌ | — | 真 LLM 精讲未验（opt-in） | scripted「重点题」请求 → 断言四块 |
| 提示 / 跳过 / 错题归档 | ❌ | 🟡（进度模板含错题区） | 🟡（mock：逃生通道 + 错题行写入） | ❌ | — | 真 LLM 逃生流未验（opt-in） | scripted 连错 2 次 → 断言三选项 + 错题行 |
| confusion-tracker 行为 | 🟡（子技能存在于 `skills/`） | 🟡（进度模板含疑难区） | 🟡（mock：疑难表新增一行） | ❌ | — | 真 LLM 疑难捕获未验（opt-in） | scripted 概念疑问 → 断言疑难行 |
| study_progress 断点恢复 | 🟡（ingest rerun 不覆盖进度） | 🟡（current_phase ∈ plan） | 🟡（mock：从进度读出当前阶段 2） | ❌ | ❌ | 真 LLM 续跑未验（opt-in） | 预置进度@阶段 N → 新会话 → 断言从 N 续 |
| 来源标注 🟢/🟡/⚠️ | ✅（校验器 + 语言测试） | ✅（`ai_generated` 标记强制） | 🟡（mock：输出含全部 canonical 标注） | 🟡（越界弃答间接） | — | 真 LLM 运行时输出未验（opt-in） | scripted「AI 补充」答 → 断言 🟡/⚠️ 出现 |
| AI 生成答案警告 | ✅（校验器拒未标记） | ✅ | 🟡（mock：⚠️ 标注 + fixture 含 ai_generated 项） | 🟡 | — | 真 LLM 运行时输出未验（opt-in） | 同上 |
| 中文学生可见输出 | ✅（语言 / 控制层测试） | — | ❌ | ❌ | — | 运行时语言未测 | scripted → 断言输出为简体中文 |
| 英文控制层 | ✅（control-plane 测试） | — | — | — | — | 已覆盖 | 维持现状 |
| 本地化边界 | ✅（localization 测试） | — | — | — | — | 已覆盖 | 维持现状 |
| web_prompt 兜底 | 🟡（中文优先 + 规则存在） | — | ❌ | ❌ | — | 行为流程未测 | 结构：web_prompt 含分步 + 来源标注 |
| 路径 / 进度安全 | ✅（校验器大量 + ingest） | ✅ | — | — | — | 已覆盖 | 维持现状 |
| 工作区校验器 | ✅（校验器单测） | ✅ | — | — | — | 已覆盖 | 维持现状 |

## 读这张表

- **左两列（Tier 0 / Tier 1）大量 ✅/🟡**：结构、schema、来源标注规则、路径安全、ingest 都被零成本测到。
- **Tier 2 现有确定性 mock 层（🟡）**：本 PR（T2）用自撰 fixture + mock 产物断言覆盖了 7 个行为场景（quiz_bank-only / 来源标注 / 提示·跳过·错题归档 / 疑难追踪 / 断点恢复 / 无 Python 降级 / 0 基础精讲），全部进 CI、零成本。
- **但 🟡 ≠ ✅**：确定性层只证明「探测器对预期产物成立」，**不证明真 LLM agent 一定产出这些行为**——真行为覆盖需 opt-in 的 `--llm` 路径（默认关闭、不进 CI）。惰性加载与画图先算后画仍是 best-effort/未覆盖。
- **多数缺口正是用确定性结构断言补齐的**（对产物文件断言），无需 LLM 裁判。详见 [`testing-audit.md`](testing-audit.md) §9 与 [`../behavior_smoke/README.md`](../behavior_smoke/README.md)。
