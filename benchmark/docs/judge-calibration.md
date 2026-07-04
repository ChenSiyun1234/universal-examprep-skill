# 判分校准（B5 · Tier-5）

裁判（LLM judge）的数字能不能信，要**校准**才知道。本层给出：① 更稳的数值判分；② 通用的
「人工 vs 裁判」Cohen's kappa 校准工具（读 B4 `run_matrix` 输出，任意课程可用）；③ 跨家族裁判提醒；
④ near-miss 越界探针的出题建议。**诚实前提**：kappa < ~0.6 时别信任裁判数字，先改裁判/题目。

## 1. 数值判分加固（`judge.check_numeric` / `_extract_final_number`）

旧实现用 `-?\d+(?:\.\d+)?` 抓答案里最后一个数字，会把常见写法判错：

| 答案写法 | 旧结果 | 现结果 |
| :-- | :-- | :-- |
| `1,000,000`（千分位逗号） | 抓成 `000` = 0 → 判错 | `1000000` ✓ |
| `1e6` / `1.5e-3`（科学计数） | 抓成 `6` / `3` → 判错 | `1000000` / `0.0015` ✓ |
| `10^6`（乘方） | 抓成 `6` → 判错 | 先算成 `1000000` ✓ |
| `50%` / `$8 KB`（带符号/单位） | 视情况 | 取数值 `50` / `8` ✓ |

`gold_answer` 也做同样归一（去千分位逗号）。取**最后一个**数字（最终答案通常在末尾）。坏 gold（非数字）
不崩、判 `(False, None)`。覆盖见 `tests/test_numeric_extraction.py`。

## 2. 通用判分校准（`calibrate_matrix.py`）

取代 `calibrate.py` 硬编码的 algo/psyc——直接读 B4 `run_matrix` 的 `results_dir`（`answers.jsonl` +
`scores.jsonl`）配 `config.json` 的金标，任意课程可用。两步：

```bash
# 1) 抽分层样本（一半裁判判对、一半判错，避免 kappa 退化），写出**隐藏裁判判定**的待填表
python calibrate_matrix.py sample --results-dir <run_matrix 的 results_dir> --config <config.json> --n 30

# 2) 人工在 calibration/calibration_sheet.csv 的 human_correct 列填 1（对/可接受）/ 0（错），只看
#    question + gold_answer + reference_span 判 model_answer（越界题以「是否老实弃答」为准）。填完：
python calibrate_matrix.py kappa --results-dir <同上>
```

输出 Cohen's kappa(human, judge) + 原始一致率 + **人机分歧清单**（裁判最可能判错的地方）。判定对**盲**：
待填表里不含裁判判定（藏在 `.calibration_key.jsonl`），避免人被裁判带跑。分层样本用 `--seed` 可复现。

> 先用 `--mock` 的 fixture 课程验证工具管线：`run_matrix.py --mock` 再 `calibrate_matrix.py sample`（mock
> 判定全同、分层不成，只验流程；真校准需真跑数据里判对判错都有）。

## 3. 跨家族裁判（自我偏好）

裁判和被测生成器**同一模型家族**（都 Claude：opus/sonnet/haiku）时有**自我偏好**嫌疑——模型倾向
认可自家风格的答案。`calibrate_matrix sample` 会据 `summary.json` 的 `judge_model` 与作答行的生成器家族
比对，重叠即警告。**建议**：用**不同家族**的裁判（如 Gemini / GPT / DeepSeek，经 `run_matrix` 的
`judge_model` + OpenAI 兼容 `openai_api_base` 配）重判一遍再校准，或在报告里注明同家族这一局限。

## 4. near-miss 越界探针（出题建议）

「越界弃答」这项容易被**太明显**的越界题刷高分——如问「亚马逊雨林降水量」这种和课程八竿子打不着的题，
模型当然弃答。要真考验抗幻觉，越界探针该出 **near-miss**：**话题贴着材料、但材料里没有确切答案**的题。
例：材料讲了 Gearbox 调度器的时间片（50ms），就出「Gearbox 调度器的默认优先级提升间隔是多少？」——
调度器在讲义里、但这个具体参数没有，正确行为仍是老实弃答。这类题才分得出「真读了材料并知道边界」和
「看着相关就编」。出金标时（`items.jsonl`，`answerable=false`）**优先出这种贴边的越界题**，而非明显跑题的。

---

诚实小结：本层是**校准与判分质量**的加固，不改变任何已发布数字；它让「裁判可信度」有据可查（kappa），
并把数值判分、跨家族偏好、越界探针难度这三个此前的软肋补上。纯 Python 标准库、零依赖。
