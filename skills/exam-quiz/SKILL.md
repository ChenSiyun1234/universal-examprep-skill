---
name: exam-quiz
description: >
  从标准题库 references/quiz_bank.json 抽取本章题目对学生测验并判分，支持 6 大题型（选择、主观、
  画图、填空、判断、代码）。主观题用「要点检索制」对照 keywords 判分，连续答错两次给提示/跳过/归档。
  禁止现场编题。当某一阶段学完需要刷题检验、或用户要求测验/模考时使用。
license: MIT
---

# exam-quiz — 抽题判分

只从题库出题、按标准答案判分。**绝不现场编造题目或答案。**

## Activation
- 某阶段学完，需要刷题检验；或用户要求「测一下 / 来几道题 / 模考」。

## Inputs
- `references/quiz_bank.json`（题库；每题**必须带 `chapter`（或 `phase`）**——抽题按它过滤，缺了该题在章节测验里就抽不到；并带 `type`、`answer`、`explanation`、`source`，主观题带 `keywords`）。
- 当前章节号（只抽本章 `chapter` 的题）。

> 若由 `exam-ingest` 生成题库，须保证每道题都带 `chapter`/`phase`，否则即便题库里有题，章节测验也会「找不到题」。

## Workflow
1. **标准抽题**：按当前阶段**匹配题目的 `chapter` 或 `phase`** 过滤出题（题库里两种字段都可能用，只看 `chapter` 会漏掉只标了 `phase` 的题）；题库里有相关题就**绝不**自己编题。
2. **按 6 大题型判分**：
   - `choice` 选择 — 比对 `answer` 选项。
   - `subjective` 主观/计算 — 「要点检索制」：作答是否覆盖该题 `keywords` 与关键步骤，意思对即通过，给相似度反馈。
   - `fill_blank` 填空 — 比对标准填项（容忍同义表述）。
   - `true_false` 判断 — 比对真假并要求简述理由。
   - `code` 代码/改错 — 看关键修改点/输出是否符合 `answer`。
   - `diagram` 画图 — 不靠想象判图：按 `render_hint` **先跑标准算法**得到结构再与学生作答比对；提醒老师画法优先。
3. **逃生通道**：答错先给逻辑漏洞 + 原题 `explanation` + 提示；**连续答错 2 次**主动给「查看提示 / 跳过并归档错题 / 继续」三选一，按选择放行。
4. **归档**：跳过或答错的题写入 `study_progress.md` 错题档案。
5. **来源诚实**：题/答 `source` 为 `ai_generated` 的，判分时提示「⚠️ AI生成答案，非老师/教材提供」（仅供参考，请核对）。

## Output format
- 一次一题，判分给「过/未过 + 要点反馈」；末尾刷新进度面板。
- 更新 `study_progress.md` 打卡与错题档案，交回 `exam-cram`。

## Language & feedback examples
Student-facing output defaults to Simplified Chinese unless the user asks otherwise.（详见 [`docs/language-policy.md`](../../docs/language-policy.md)。）

判分反馈用简短、具体的中文，先点考点再给改进：

- **答对**：✅ 对了。这题考什么：……（一句点考点）。顺手记个易错点：……。
- **部分对**：🟡 思路对了一半——你答到了「……」，但漏了「……」这一步，补上就满分。
- **答错**：❌ 这里错了：……（指出逻辑漏洞）。标准答题步骤：1.… 2.…。再看一眼原题解析。
- **连错两次**：要不要 ① 查看提示　② 跳过并归档错题　③ 再想想？选 ② 我就「已记录到错题本」，考前再扫雷。
- **题/答为 AI 生成**：⚠️ AI生成答案，非老师/教材提供，仅供参考，请和老师/教材核对。

## Boundaries
- 题库有相关题时不自编题；无答案不硬判，标 ⚠️ 或如实说明。
- 画图题不凭记忆判定对错——以程序跑出的标准结构为准。
