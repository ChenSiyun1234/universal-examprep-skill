# 真·付费 LLM 跑：操作手册（opt-in）

> 面向仓库拥有者（有 Claude Code 订阅、**无独立 API key**）。所有真跑都通过 shell `claude -p` 走你已登录的订阅，不需要 provider API key。
> **先用 `--mock` 免费验证管线，再加 `--real`。** 真跑消耗你的订阅配额；所有 runner 都 resumable + 配额感知，Ctrl-C 安全、`--real` 重跑自动续。
> CI 里这些真跑**永远不开**——全靠显式 flag / env 门控。真实材料、金标、结果都 `.gitignore` 挡住，不进公开仓库。

前提（本地已就绪，均 gitignored）：
- 课程材料 `materials/algorithms_mit6006/`（6.006）、`materials/psych_yale_psyc110/`（PSYC 110）。
- 金标 `items/items_algo_full.jsonl`（69 题）、`items/items_psyc_full.jsonl`（50 题，含 10 道越界探针 `answerable:false`）。
- 各臂工作区 `skill_workspace/{mit6006_full,rawfiles_algo,psyc110_full,rawfiles_psyc}`。
- 已 `claude` 登录（`claude -p "hi"` 能出话）。

---

## 主线：三臂 × 三模型矩阵（`run_matrix.py`）

三臂 = **closedbook**（不给材料，暴露先验知识底噪）/ **rawfiles**（agent 在原始课件目录里 Read/Glob/Grep）/ **skill**（agent 在 skill 工作区，惰性加载 wiki）。三模型 = opus / sonnet / haiku。判分内联（生成完当场判），不用另开判分步骤。

### 第 0 步 · 免费验证管线（不打 claude）
```bash
cd benchmark
python run_matrix.py --config config.matrix.example.json --mock --limit 6
```
应打印 `summary: …/results/matrix_run/summary.json（mock 占位摘要，未测量正确率）`。跑通即证明 config 里的课程/工作区/金标路径都接对了。**跑完删掉占位目录**再真跑（避免 mock 占位被当成已完成）：
```bash
rm -rf results/matrix_run
```

### 第 1 步 · 建你的真跑 config
复制模板（模板已按真实两门课填好路径）：
```bash
cp config.matrix.example.json config.json
```
`config.json` 是 gitignored 的个人配置。**建议改一处**：把 `"judge_model"` 从 `"haiku"` 改成 `"sonnet"`——Sonnet 是人工 kappa 校准过的裁判（human vs Sonnet kappa=0.833，见 [`judge-calibration.md`](judge-calibration.md)），haiku 判分更弱。
> ⚠️ 自判偏好提示：裁判模型也在生成模型集里时，同名那一臂（sonnet 判 sonnet）存在自我偏好嫌疑。已发布方法学用的就是 Sonnet 裁判并如实标注此口径；若要彻底规避，需换一个**不在生成集里**的裁判（如 Codex/GPT），但那需要另一套接入。默认沿用 Sonnet 裁判 + 明示口径。

`results_dir` 默认 `results/matrix_run`；真跑建议单独目录（别覆盖已发布的 `results/matrix/`）：把 config 里 `results_dir` 设为如 `results/matrix_real_2026xxxx`。

### 第 2 步 · 真跑（消耗配额，resumable）
```bash
python run_matrix.py --config config.json --real
```
- 全矩阵 = 2 课 × 3 模型 × 3 臂 × (69+50) 题，量很大；**先小样验证**：`--real --limit 20` 或先把 config 的 `models` 砍成 `["haiku"]`、`arms` 砍成 `["closedbook","skill"]` 跑一轮看通。
- 撞订阅 5 小时配额上限会停并提示「配额未恢复，稍后再跑 --real 续」——过几小时再跑同一条命令自动续，已判分的 `(课,模型,臂,题)` 跳过。
- 产物写在 `results_dir/`：`answers.jsonl`（含 `cost_usd`）、`scores.jsonl`、`.run_meta.json`（config 指纹，防 mock/real 混目录）、`summary.json`（全跑完且无 infra_error 才落）。

### 第 3 步 · 聚合 + 报告
`run_matrix.py` 全跑完会自动聚合出 `summary.json`。若中途续跑或想单独重生成：
```bash
# 聚合（纯 stdlib，不打 claude）
python aggregate_matrix.py --answers results/matrix_real_xxx/answers.jsonl \
  --scores results/matrix_real_xxx/scores.jsonl --out results/matrix_real_xxx/summary.json \
  --primary-course algo --secondary-course psyc --judge-model sonnet
# 渲染中英双语 HTML + SVG（自定义 --summary 时必须给 --out-dir，否则退出码 2 防覆盖已发布报告）
python report_matrix.py --summary results/matrix_real_xxx/summary.json --out-dir results/matrix_real_xxx
# 打开 results/matrix_real_xxx/report.html
```
重判（只对已缓存答案，不重新生成）：`python rejudge.py --deterministic --course both --scores-out … --answers-out …`（`--judge-model` 默认 sonnet；`--llm` 才对判不定项调 claude）。

---

## 可选 A · 行为冒烟真跑（`behavior_smoke --llm`，B2）
确定性 mock 免费，真 agent 单轮冒烟 opt-in：
```bash
python behavior_smoke/run_behavior_smoke.py --mock          # 免费，确定性探测器
RUN_SKILL_BEHAVIOR_LLM=1 python behavior_smoke/run_behavior_smoke.py --llm   # 真跑（默认 claude -p {prompt}）
# 或不设 env、显式给命令：
python behavior_smoke/run_behavior_smoke.py --llm --agent-cmd "claude -p {prompt}"
```
每场景在**含 skill 契约的一次性沙箱**里跑一轮，套用与 `--mock` 相同的确定性探测器；transcript 默认写到仓库外系统临时目录（含答案键，别落工作树）。退出码：0 全过 / 1 有场景不过 / 2 门控或参数错 / 3 中途超时或超输出上限被杀。

## 可选 B · 长会话漂移真跑（`drift/run_live_smoke.py`）
需**同时**给 `--agent-cmd` 和 `RUN_SKILL_DRIFT_LLM=1`：
```bash
RUN_SKILL_DRIFT_LLM=1 python drift/run_live_smoke.py \
  --agent-cmd "claude -p {prompt}" --out-dir /tmp/live_smoke
```
`--turns` 默认自带回合脚本；`--out-dir` 必须显式（不写任何 `results/`）。驱动→记录→T4 判分一条命令。

## 可选 C · 多轮收敛（`rounds.py` + `mit6006_r{1,2,3}` 残缺 wiki）
收敛协议是**人工多轮**：作答→判分→自检缺哪块材料→补 wiki（r1=7章→r2=14章→r3=20章）→下一轮重答。每轮指标喂 `rounds.render_convergence(rounds=[…], out_dir=…, mock=False)` 出 `convergence.html`；faithfulness 连续两轮 Δ<2% 判收敛。

---

## 配额 / 成本 / 诚实口径
- **配额**：订阅有 5 小时滚动上限；大 workflow/矩阵会撞。分批跑、`--limit` 小样先行、撞上限就等恢复续跑。
- **成本**：`answers.jsonl` 每行带 `cost_usd`，`summary.json` 汇总 `total_cost_usd`。
- **诚实**：`infra_error`（配额/超时/判分失败）答案**排除出正确率分母**、单独计 `n_infra_error`，绝不当成「答错/幻觉」——这是之前踩过的坑（120 条配额错误曾把 haiku|material 假压到 2%）。越界探针（`answerable:false`）判「弃答=对 / 硬答=幻觉」。
- **判分可信**：数值题确定性判；事实题先 `contains_gold` 词边界快路径，判不定才调裁判（claim 级蕴含 vs supporting_span）。人工 kappa=0.833/0.875（保守下界，非虚高）。

## 更难金标（压低闭卷正确率）
现有金标里不少题模型靠先验就能答（PSYC 闭卷 ~60%、6.006 部分同理），grounding 考验不够狠。`items/items_psyc_hard.jsonl`（**54 题，gitignored**）是一批**只能从转录里取答**的高 grounding 题——都是 Bloom 教授本人举的具体例子/私人轶事/点名的冷门研究/具体数字（如他小时候的电话号码 514-688-9057、小脑约 300 亿神经元、Pratfall 实验 92%、他儿子说"要娶一头驴和一大袋花生"），**常识答不出、只有看过该讲才知道**。每题的 `supporting_span` 都是从转录里**逐字复制**并经脚本校验确属该讲文件（1 条非逐字的已剔除）。全部标 `answer_type:"factual"`（数字答案也含词/单位/区间，走事实判分而非确定性数值比对）。

用法：真跑时把 config 的 psyc `items` 指向它（或与 `items_psyc_full.jsonl` 合并），**闭卷该明显掉、skill/rawfiles 该守住**——那才坐实 grounding 有用。生成方法：5 个 subagent 分读 20 讲转录挖题 + 逐字 span 校验 + 去重（脚本一次性，非仓库常驻）。其**难度只有真跑才能验证**（离线无法确认模型先验），跑完对比 closedbook vs skill/rawfiles 的正确率差。
