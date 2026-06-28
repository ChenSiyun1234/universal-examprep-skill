# -*- coding: utf-8 -*-
"""PR C — bilingual language policy. Stdlib only.

Locks the language architecture: docs/language-policy.md defines an English control plane
+ a Simplified-Chinese student-facing layer, student-facing subskills default to Chinese,
concrete exam-tutoring labels are present, and V2.1 / web-portability are preserved.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUDENT_FACING = ["exam-tutor", "exam-quiz", "exam-review", "exam-cheatsheet", "exam-help"]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class LanguagePolicyTest(unittest.TestCase):
    def test_policy_doc_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "docs", "language-policy.md")),
                        "缺少 docs/language-policy.md")

    def test_policy_defines_both_planes(self):
        p = read("docs", "language-policy.md")
        self.assertIn("control plane", p.lower(), "未定义英文控制层")
        self.assertIn("Simplified Chinese", p, "未定义简体中文学生层")

    def test_policy_has_provenance_markers(self):
        p = read("docs", "language-policy.md")
        for marker in ("🟢", "来自资料",
                       "🟡", "AI补充，可能与你老师讲的不完全一致",
                       "⚠️", "AI生成答案，非老师/教材提供"):
            self.assertIn(marker, p, f"语言策略缺少来源标注: {marker}")

    def test_student_facing_subskills_default_simplified_chinese(self):
        for s in STUDENT_FACING:
            txt = read("skills", s, "SKILL.md")
            self.assertIn("Simplified Chinese", txt, f"{s} 未声明 student-facing 默认简体中文")

    def test_concrete_chinese_labels_in_tutor(self):
        tutor = read("skills", "exam-tutor", "SKILL.md")
        for label in ("当前阶段", "这题考什么", "标准答题步骤", "易错点", "3分钟速记", "现在轮到你"):
            self.assertIn(label, tutor, f"exam-tutor 缺少具体标签: {label}")

    def test_quiz_feedback_labels(self):
        quiz = read("skills", "exam-quiz", "SKILL.md")
        self.assertIn("已记录到错题本", quiz, "exam-quiz 缺少归档回执措辞")
        # four feedback cases at least mention 对/错 handling
        self.assertIn("连错两次", quiz)

    def test_review_replay_and_confusion_wording(self):
        r = read("skills", "exam-review", "SKILL.md")
        self.assertIn("错题重做", r, "exam-review 缺少错题重做措辞")
        self.assertIn("疑难复述", r, "exam-review 缺少疑难复述措辞")

    def test_cheatsheet_required_sections(self):
        c = read("skills", "exam-cheatsheet", "SKILL.md")
        for sec in ("必背", "老师强调", "易错", "3分钟速记"):
            self.assertIn(sec, c, f"小抄缺少栏目: {sec}")

    def test_root_skill_exists_with_v21_provenance(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "SKILL.md")), "根 SKILL.md 不存在")
        root = read("SKILL.md")
        self.assertIn("知识来源透明化", root, "根 SKILL.md 缺少 V2.1 知识来源透明化协议")
        self.assertIn("AI 生成", root, "根 SKILL.md 缺少 ⚠️ AI 生成答案标注约定")

    def test_web_prompt_remains_chinese_first(self):
        web = read("prompts", "web_prompt.md")
        self.assertIn("网页端", web, "web_prompt 不再是中文优先")
        self.assertIn("备考", web)


if __name__ == "__main__":
    unittest.main()
