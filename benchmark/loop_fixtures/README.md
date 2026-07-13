# loop_fixtures — loop_bench.py --mock 的确定性夹具

`loop_bench.py --mock` 不碰 claude：每轮助手回答来自这里的 `string.Template` 夹具
（`$变量` 占位），端到端打通全部指标判分路径，但**不测量任何东西**。

- `skill/`：技能臂夹具——带溯源块、真实可解析的 notebook/mistakes 锚点与落盘回执；
  mock 还会**真实创建**磁盘产物（走官方 `scripts/notebook.py` 写 notebook/ 与 mistakes/，
  外加 cheatsheet.md 与一个恰含 2 个 `/Type /Page` 对象的最小假 PDF）。
- `bare/`：裸助手臂夹具——流畅、答案正确，但无出处、无跨会话记忆、零磁盘产物
  （对应设计冻结稿「结构性缺失」的预期格局）。
- `mini_course/`：自带 3 章微型课程（材料 + 合法 v4 工作区 + 5 道金标题），
  让 mock 全管线开箱即跑：

      python benchmark/loop_bench.py --config benchmark/loop_fixtures/demo_config.json --mock

  产物落在 `benchmark/results/loop_demo/`（已被 .gitignore 挡住）。skill 臂永远在
  results 下的**工作区拷贝**上落盘，`mini_course/ws` 与真实课程工作区保持只读干净。

测试：`python -m unittest tests.test_loop_bench`（仓库根目录）。
