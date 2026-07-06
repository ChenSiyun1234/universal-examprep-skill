# -*- coding: utf-8 -*-
"""PR T1 — benchmark / test-flow documentation consistency. Stdlib only.

This guard keeps the benchmark + testing story internally consistent and drift-free,
WITHOUT running any paid benchmark:

1. User-facing docs must not hard-code a TOTAL unittest count (it drifts every PR).
   The live count comes from `python -m unittest discover -s tests -v`.
   (Benchmark item counts like `65 题` / `50 题` are NOT banned — only 测试/tests totals.)
2. Benchmark docs must consistently name the primary matrix arms: closedbook / rawfiles / skill.
3. Benchmark docs must describe material / dump-all as a legacy/stress/footnote arm,
   not the primary fair control.
4. The audit doc must honestly state: Tier 2 behavioral smoke's real-model run is opt-in / not yet
   performed. Because B2 WIRED the --llm harness, the Tier-2 real-LLM line must use a NOT-YET-RUN
   phrasing (opt-in / 尚未实际跑过) and must NOT keep the stale "未实现/尚未实现/not implemented"
   wording (which would contradict the wired harness). The published summary.json is a precomputed
   artifact; T3 added the committed aggregator (aggregate_matrix.py), while the full published
   MIT/PSYC matrix still needs private/intermediate artifacts + paid runs.

This is a doc/test consistency guard only — it adds no Tier 2, no benchmark run, no LLM/paid run.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# docs that must not hard-code a total unittest count
COUNT_FILES = [
    "README.md",
    os.path.join("benchmark", "README.md"),
    os.path.join("benchmark", "docs", "testing-audit.md"),
    os.path.join("benchmark", "docs", "coverage-matrix.md"),
]

# benchmark docs that describe the matrix arms
ARM_FILES = [
    os.path.join("benchmark", "README.md"),
    os.path.join("benchmark", "docs", "测试流程详解.md"),
    os.path.join("benchmark", "docs", "testing-audit.md"),
]

AUDIT = os.path.join("benchmark", "docs", "testing-audit.md")

# total-unittest-count phrasings that drift. NOT benchmark item counts (题 / 道) or tier ordinals.
# A real COUNT carries a quantity connective (个/项/条/道); requiring it avoids matching tier
# references like "Tier 0 单测" / "Tier 1 测试" while still catching 个单测 / 项自动化测试 / 条测试.
BANNED_COUNT = [
    re.compile(r"\d+\s*个\s*单测"),                                 # 109 个单测
    re.compile(r"\d+\s*(?:个|项|条|道)\s*(?:单元|自动化)?测试"),      # 109 个/项/条/道 (单元/自动化) 测试
    re.compile(r"\d+\s+(?:unit\s+|automated\s+)?tests\b", re.I),    # 109 (unit/automated) tests
    re.compile(r"\d+\s+test\s+cases?\b", re.I),                     # 109 test case(s)
]

PRIMARY_ARMS = ["closedbook", "rawfiles", "skill"]
MATERIAL_TOKENS = ["material", "dump-all", "一股脑全塞", "给全材料"]
# the material/dump-all arm must be bound to a legacy/stress framing, not just have the words scattered:
LEGACY_BIND = re.compile(r"(遗留|压力|legacy|stress)[^。\n]{0,16}(臂|脚注|footnote)")

# the three tier docs must agree on the Tier 2 concept = behavioral smoke (not the retired
# "3–5 item benchmark-pipeline smoke"). 行为冒烟 is the shared canonical token.
TIER_FILES = [
    os.path.join("benchmark", "docs", "test_tiers.md"),
    os.path.join("benchmark", "docs", "testing-audit.md"),
    os.path.join("benchmark", "docs", "coverage-matrix.md"),
]
TIERS_DOC = os.path.join("benchmark", "docs", "test_tiers.md")
BEHAVIORAL_SMOKE = "行为冒烟"
# B2 wired the behavior_smoke --llm harness, so the honest Tier-2 status is NO LONGER "unimplemented"
# (the harness exists) but "the real PAID model-validation run is opt-in and has not run yet". The
# Tier-2 real-LLM status line must therefore use a NOT-YET-RUN phrasing (ACCEPT) and must NOT keep the
# stale UNIMPLEMENTED phrasing (STALE) — which would contradict B2's wired harness.
REAL_RUN_ACCEPT = ["尚未实际跑过", "opt-in", "未实际跑过", "尚未付费"]
STALE_UNIMPL = ["未实现", "尚未实现", "not implemented"]
# the retired Tier-2 definition ("3–5 题" benchmark-pipeline smoke) must not come back:
OLD_TIER2_ITEMS = re.compile(r"3\s*[-–—]\s*5\s*题")


def _tier2_real_llm_lines(text):
    """Lines describing Tier 2's real-LLM / behavioral-smoke status, EXCLUDING lines that also discuss
    Tier 4 / long-session (a mixed line's 未实现 belongs to Tier 4, not Tier 2 — don't false-positive)."""
    return [ln for ln in text.splitlines()
            if "Tier 2" in ln and BEHAVIORAL_SMOKE in ln
            and "Tier 4" not in ln and "长会话" not in ln]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class BenchmarkDocsConsistencyTest(unittest.TestCase):
    def test_no_hardcoded_unittest_counts(self):
        offenders = []
        for rel in COUNT_FILES:
            txt = read(rel)
            for pat in BANNED_COUNT:
                for m in pat.finditer(txt):
                    offenders.append(f"{rel} -> {m.group(0)!r}")
        self.assertEqual(
            offenders, [],
            "用户可见文档里仍硬编了单元测试总数（会随每次加测试而漂移，应改为 stdlib 测试套件 + "
            "`python -m unittest discover -s tests -v` 取实时值）: " + "; ".join(offenders),
        )

    def test_benchmark_item_counts_are_not_banned(self):
        # guardrail on the guard: data counts (题 / 道) must stay legal — they are NOT the drift target
        for sample in ("共 65 题", "50 题", "16 题", "共 55 题有标准答案", "10 道越界探针", "Python 3.8/3.12"):
            for pat in BANNED_COUNT:
                self.assertIsNone(pat.search(sample), f"误伤数据计数: {sample!r} 命中 {pat.pattern}")

    def test_banned_count_catches_real_drift(self):
        # guardrail on the guard: the phrasings people actually type MUST be caught
        for sample in ("109 个测试", "109 个单元测试", "98 个自动化测试", "109 项自动化测试",
                       "共 109 个单测", "109 条测试", "109 tests", "109 unit tests", "88 test cases"):
            self.assertTrue(any(p.search(sample) for p in BANNED_COUNT),
                            f"漏网的硬编测试总数措辞: {sample!r}")

    def test_benchmark_docs_name_primary_arms(self):
        # require each arm as a backticked code identifier — a bare substring is trivially satisfied
        # ("skill" is a substring of the project name and `skill_workspace/`).
        for rel in ARM_FILES:
            txt = read(rel)
            for arm in PRIMARY_ARMS:
                self.assertRegex(
                    txt, r"`" + re.escape(arm) + r"`",
                    f"{rel} 未把主对照臂「{arm}」写成反引号代号（应为 `closedbook`/`rawfiles`/`skill`）",
                )

    def test_material_is_legacy_stress_footnote(self):
        for rel in ARM_FILES:
            txt = read(rel)
            has_material = any(tok in txt for tok in MATERIAL_TOKENS)
            self.assertTrue(has_material, f"{rel} 未提到 material/dump-all（应作为遗留/压力脚注存在）")
            self.assertRegex(
                txt, LEGACY_BIND,
                f"{rel} 未把 material/dump-all 绑定为「遗留/压力臂」或「压力脚注/footnote」"
                "（避免被当成主对照臂）",
            )

    def test_audit_states_tier2_not_implemented(self):
        a = read(AUDIT)
        self.assertIn("Tier 2", a, "审计文档未提 Tier 2")
        # tie the status claim to the Tier 2 + 行为冒烟 line, so a Tier-4-only「未实现」别处出现不能蒙混
        t2_lines = _tier2_real_llm_lines(a)
        self.assertTrue(t2_lines, "审计文档无「Tier 2 … 行为冒烟」行")
        # (a) at least one Tier-2 line must carry a NOT-YET-RUN status (opt-in / 尚未实际跑过)
        self.assertTrue(
            any(any(m in ln for m in REAL_RUN_ACCEPT) for ln in t2_lines),
            "审计文档未在 Tier 2 行为冒烟处标明真实模型跑仍 opt-in/尚未实际跑过（不能靠文档别处蒙混）",
        )
        # (b) NO Tier-2 line may still call it unimplemented — B2 wired the --llm harness
        stale = [ln for ln in t2_lines if any(s in ln for s in STALE_UNIMPL)]
        self.assertEqual(
            stale, [],
            "B2 已接通 --llm harness，Tier 2 行为冒烟不能再写「未实现/尚未实现」"
            "（应改为「opt-in/尚未实际跑过真模型」）: " + "; ".join(stale),
        )

    def test_audit_states_summary_is_precomputed(self):
        a = read(AUDIT)
        self.assertIn("summary.json", a, "审计文档未提 summary.json")
        self.assertTrue(
            ("precomputed" in a) or ("预先计算" in a) or ("预计算" in a),
            "审计文档未说明 summary.json 是预先计算（precomputed）的产物",
        )

    def test_audit_states_aggregator_added_in_t3(self):
        # T3 added the committed aggregator (benchmark/aggregate_matrix.py). The audit must now name it,
        # AND still be honest that the FULL published MIT/PSYC matrix needs private/intermediate
        # artifacts + paid runs — the aggregator alone does not reproduce the published numbers.
        a = read(AUDIT)
        self.assertTrue(("aggregator" in a) or ("聚合器" in a), "审计文档未提聚合器（aggregator）")
        self.assertTrue(("aggregate_matrix.py" in a) or ("T3" in a),
                        "审计文档未把聚合器关联到 T3 / aggregate_matrix.py")
        self.assertTrue(
            ("私有" in a) or ("付费" in a) or ("private" in a) or ("paid" in a),
            "审计文档未说明完整发布矩阵仍依赖私有/付费产物",
        )

    # ---- Tier 2 definition must be consistent across the three tier docs ----
    def test_tier2_is_behavioral_smoke_in_all_tier_docs(self):
        # test_tiers.md / testing-audit.md / coverage-matrix.md must share the SAME Tier 2 concept
        for rel in TIER_FILES:
            txt = read(rel)
            self.assertIn(BEHAVIORAL_SMOKE, txt,
                          f"{rel} 未用统一的 Tier 2 概念「{BEHAVIORAL_SMOKE}」（三份分层文档须一致）")

    def test_test_tiers_defines_tier2_as_unimplemented_behavioral_smoke(self):
        t = read(TIERS_DOC)
        # the Tier 2 row itself must name 行为冒烟 AND its not-yet-run status (not a whole-doc search)
        t2_lines = _tier2_real_llm_lines(t)
        self.assertTrue(t2_lines, "test_tiers.md 无「Tier 2 … 行为冒烟」行（Tier 2 应定义为行为冒烟）")
        self.assertTrue(
            any(any(m in ln for m in REAL_RUN_ACCEPT) for ln in t2_lines),
            "test_tiers.md 未在 Tier 2 行为冒烟处标明真实模型跑仍 opt-in/尚未实际跑过",
        )
        stale = [ln for ln in t2_lines if any(s in ln for s in STALE_UNIMPL)]
        self.assertEqual(
            stale, [],
            "B2 已接通 --llm harness，test_tiers.md 的 Tier 2 行为冒烟行不能再写「未实现/尚未实现」: "
            + "; ".join(stale),
        )

    def test_tier2_stale_wording_guard_is_scoped(self):
        # guardrail on the guard: a Tier-2 real-LLM line that still says 尚未实现 MUST be caught; a
        # compliant opt-in line must pass; a Tier-4 「未实现」 on a mixed line must NOT be attributed to Tier 2.
        stale_line = "- Tier 2 行为冒烟的真 LLM 行为验证尚未实现。"
        ok_line = "- Tier 2 行为冒烟真实付费跑仍 opt-in、尚未实际跑过真模型。"
        mixed_t4 = "- Tier 2 行为冒烟确定性层已落地；Tier 4 真 LLM 长会话仍未实现。"
        self.assertTrue(
            _tier2_real_llm_lines(stale_line)
            and any(s in _tier2_real_llm_lines(stale_line)[0] for s in STALE_UNIMPL),
            "守卫漏掉了仍写「尚未实现」的 Tier 2 行",
        )
        self.assertTrue(
            _tier2_real_llm_lines(ok_line)
            and any(m in _tier2_real_llm_lines(ok_line)[0] for m in REAL_RUN_ACCEPT),
            "守卫误判了合规的「opt-in/尚未实际跑过」Tier 2 行",
        )
        self.assertEqual(
            _tier2_real_llm_lines(mixed_t4), [],
            "Tier 4 的「未实现」不应被当成 Tier 2 的过时措辞（混合行须排除）",
        )

    def test_test_tiers_tier2_is_not_the_old_pipeline_item_smoke(self):
        # the retired definition ("3–5 题" benchmark-pipeline smoke) must not be Tier 2 anymore
        t = read(TIERS_DOC)
        self.assertIsNone(
            OLD_TIER2_ITEMS.search(t),
            "test_tiers.md 仍把 Tier 2 定义成「3–5 题」的 benchmark 管线冒烟——应改为行为冒烟，"
            "管线 mock 自检请另命名（benchmark pipeline mock check）",
        )


if __name__ == "__main__":
    unittest.main()
