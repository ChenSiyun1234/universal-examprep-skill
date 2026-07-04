# -*- coding: utf-8 -*-
"""B5 数值抽取加固：judge.check_numeric / _extract_final_number 的边角覆盖。

旧实现（-?\\d+(?:\\.\\d+)?）会把 "1,000,000" 抓成最后一段 "000"、把 "1e6" 抓成 "6"、把 "10^6" 抓成 "6"，
数值题被静默判错。这里锁住修好后的行为。"""
import os
import sys
import unittest

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BENCH)
import judge as J  # noqa: E402


class ExtractFinalNumber(unittest.TestCase):
    def test_comma_grouped(self):
        self.assertEqual(J._extract_final_number("答案是 1,000,000 次操作"), 1000000.0)
        self.assertEqual(J._extract_final_number("12,345.67"), 12345.67)

    def test_scientific(self):
        self.assertEqual(J._extract_final_number("约 1e6"), 1000000.0)
        self.assertAlmostEqual(J._extract_final_number("1.5e-3 秒"), 0.0015)
        self.assertEqual(J._extract_final_number("结果 2E3"), 2000.0)

    def test_caret_power(self):
        self.assertEqual(J._extract_final_number("大约 10^6 次"), 1000000.0)
        self.assertEqual(J._extract_final_number("2 ^ 10"), 1024.0)

    def test_plain_decimal_negative(self):
        self.assertEqual(J._extract_final_number("3.14159"), 3.14159)
        self.assertEqual(J._extract_final_number("温度 -5 度"), -5.0)

    def test_takes_last_number(self):
        self.assertEqual(J._extract_final_number("第 2020 年，最终答案是 42"), 42.0)

    def test_percent_and_units(self):
        self.assertEqual(J._extract_final_number("准确率 50%"), 50.0)
        self.assertEqual(J._extract_final_number("$8 KB"), 8.0)

    def test_none_when_no_number(self):
        self.assertIsNone(J._extract_final_number("这里没有数字"))
        self.assertIsNone(J._extract_final_number(""))
        self.assertIsNone(J._extract_final_number(None))

    def test_huge_scientific_rejected_as_nonfinite(self):
        # 1e400 → inf → 拒绝（否则 abs(inf-inf)=nan 把精确匹配判错）
        self.assertIsNone(J._extract_final_number("1e400"))
        self.assertEqual(J.check_numeric("1e400", "1e400", 0), (False, None))

    def test_ambiguous_comma_rejected_not_fragment(self):
        # 欧式小数/乱逗号 → None（不再落片段 "3,14"→14 / "1,00"→0 造成静默误判）
        for s in ("3,14", "1,00", "12,3", "1,2,3"):
            self.assertIsNone(J._extract_final_number(s), s)
        # 关键：不再假阳（旧实现 "3,14" vs gold 14 会判对）
        self.assertEqual(J.check_numeric("答案约为 3,14", "14", 0), (False, None))
        self.assertEqual(J.check_numeric("元素有 1,2,3,4", "4", 0), (False, None))

    def test_symbolic_power_not_grabbed(self):
        # O(n^2) 的指数 2 不当答案；真数值在同句时取真数值
        self.assertEqual(J._extract_final_number("1,000,000 (即 O(n^2))"), 1000000.0)
        self.assertIsNone(J._extract_final_number("复杂度是 O(n^2)"))
        self.assertTrue(J.check_numeric("答案 1,000,000（即 O(n^2)）", "1000000", 0)[0])

    def test_comma_grouped_caret_base(self):
        self.assertEqual(J._extract_final_number("1,000^2"), 1000000.0)

    def test_ambiguous_final_token_no_fallback(self):
        # 末位 token 是歧义逗号 → None，绝不回退到前面的 42
        self.assertIsNone(J._extract_final_number("题号 42，答案是 3,14"))
        self.assertEqual(J.check_numeric("题号 42，答案是 3,14", "42", 0), (False, None))

    def test_comma_caret_base_rejected(self):
        # 1,00^2 的底数歧义 → 整个乘方作废（不算成 10000）
        self.assertIsNone(J._extract_final_number("1,00^2"))
        self.assertEqual(J.check_numeric("答案 1,00^2", "10000", 0), (False, None))

    def test_bad_final_power_no_fallback(self):
        # 末位是坏乘方 → None，不回退到前面的 42（单遍有序扫，末位无效即 None）
        self.assertIsNone(J._extract_final_number("题号 42，答案是 1,00^2"))
        self.assertEqual(J.check_numeric("题号 42，答案是 1,00^2", "42", 0), (False, None))

    def test_scientific_base_power(self):
        # 科学计数底数的乘方 1e6^2 = (1e6)^2 = 1e12（不再被拆成 1e36.0 落到 0）
        self.assertEqual(J._extract_final_number("1e6^2"), 1e12)


class CheckNumeric(unittest.TestCase):
    def test_comma_gold_and_answer(self):
        ok, parsed = J.check_numeric("答案 1,000,000", "1000000", 0)
        self.assertTrue(ok)
        self.assertEqual(parsed, 1000000.0)
        self.assertTrue(J.check_numeric("是 1000000", "1,000,000", 0)[0])   # gold 带逗号

    def test_scientific_answer_matches_plain_gold(self):
        self.assertTrue(J.check_numeric("约为 1e6 次", "1000000", 0)[0])
        self.assertTrue(J.check_numeric("10^6", "1000000", 0)[0])

    def test_tolerance(self):
        self.assertTrue(J.check_numeric("约 3.14159", "3.14", 0.01)[0])
        self.assertFalse(J.check_numeric("3.20", "3.14", 0.01)[0])

    def test_wrong(self):
        self.assertFalse(J.check_numeric("我认为是 6", "4", 0)[0])

    def test_no_number_or_bad_gold(self):
        self.assertEqual(J.check_numeric("没有数字", "4", 0), (False, None))
        self.assertEqual(J.check_numeric("42", "abc", 0), (False, None))   # 坏 gold 不崩

    def test_negative_tolerance_treated_absolute(self):
        # 负 tolerance 取绝对值（run_matrix 已在 load 时拦，但 judge 层也要稳）
        self.assertTrue(J.check_numeric("5", "5", -1)[0])

    def test_old_bug_regression(self):
        # 旧实现会把这些判错——现在应判对
        self.assertTrue(J.check_numeric("最终 1,000,000", "1000000", 0)[0])
        self.assertTrue(J.check_numeric("答案 1e6", "1000000", 0)[0])


if __name__ == "__main__":
    unittest.main()
