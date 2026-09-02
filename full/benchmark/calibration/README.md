# calibration/ —— 裁判可信度校准

LLM 裁判可能不准（这次就抓到一个把正确答案误判成幻觉的 bug），所以**在相信任何裁判数字之前**，
先让人工（你）盲标一小批，量一下「人工 vs 裁判」的一致性。一致性够高，报告里的正确率/幻觉率才站得住。

## 已完成的校准结果（两次独立、互相印证）

- **16 题抽查**：Cohen's kappa = **0.875**、一致率 93.8%（早期，见 README 与报告）。
- **24 题四层盲测**（可答判对/判错 + 越界弃答/未弃答四层、判分对人隐藏）：一致率 **91.7%**、
  Cohen's kappa = **0.833**，越界层 8/8 全一致——脱敏摘要在 [`kappa_n24_summary.json`](kappa_n24_summary.json)
  （盲表/答案 key/人工判分等真实数据不入库、该目录 gitignored，摘要为唯一入库）。
  两次分歧**全是裁判偏严**（把正确答案判错）→ 报告数字更可能偏保守而非虚高。

## 两个校准工具

- **`calibrate_matrix.py`（现役，通用三臂矩阵）**：从真实 matrix 结果分层抽样、隐藏判分、算 kappa；
  上面的 24 题校准即用它产出。config 指纹校验 + 自我偏好告警 + 退化 kappa 门控。
- **`calibrate.py`（较早的两臂脚手架，下方示例）**：两臂 baseline/skill 场景的同款流程。

## 用 `calibrate.py`（两臂脚手架）

```bash
cd benchmark

# 1) 抽样：分层（一半判对、一半判错，避免 kappa 退化），生成藏住裁判判分的待填表
python calibrate.py sample --n 24 --course both --seed 7

# 2) 打开 calibration/calibration_sheet.csv（Excel/编辑器），给 human_correct 列填 1（对）/ 0（错）
#    只看 question + gold_answer + reference_span 判 model_answer 对不对；越界题以「是否老实弃答」为准。

# 3) 算 kappa + 列出人机分歧（裁判最可能错的地方）
python calibrate.py kappa
```

- `calibration_sheet.csv`（你填的）和 `.calibration_key.jsonl`（藏起来的裁判判分）都 **gitignored**，含答案细节不入库。
- 数据来源：权威重判缓存 `results/matrix/judge_cache.jsonl`（先跑过 `rejudge.py --llm`）。

## 判定规则

- **kappa ≥ ~0.6** 视为可接受（裁判与人工大体一致），再去信报告里的裁判类指标；
- 偏低就改进裁判提示/题目，或换不同家族模型当裁判（如以后用 Codex/GPT）。
- 标签分布很偏（绝大多数同一类）时 kappa 会偏低，建议同时看 Gwet's AC2（更稳）。底层算法见 [`../stats.py`](../stats.py) `cohen_kappa`。
