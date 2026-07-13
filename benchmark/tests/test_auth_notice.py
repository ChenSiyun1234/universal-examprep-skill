# -*- coding: utf-8 -*-
"""v4 复盘回归钉：登录/认证通知是 result 形状的基础设施错误——绝不入 answers。
（真实事故：CLI 登录态过期，整趟 1,251 条"作答"全是 "Not logged in · Please run /login"
且被当合法答案记录、判分、聚合。）"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import gen                # noqa: E402
import run_matrix as RM   # noqa: E402


class AuthNoticeDetection(unittest.TestCase):
    NOTICES = (
        "Not logged in · Please run /login",
        "Please run /login to continue",
        "Invalid API key",
        "authentication_error: token expired",
        "未登录",
    )

    def test_auth_notices_are_infra_not_answers(self):
        for s in self.NOTICES:
            self.assertTrue(RM._is_quota_notice(s),
                            "登录通知必须走 infra 通道，不得当合法答案: %r" % s)

    def test_auth_notices_classify_hard(self):
        for s in self.NOTICES[:2]:
            self.assertEqual(gen.classify(s), "hard",
                             "登录失效需要人工处理——必须 hard（停跑），不是 transient 重试: %r" % s)

    def test_real_answers_mentioning_login_stay_valid(self):
        # 长答案里顺带提到 login 词不误伤（与配额词同一保护逻辑：只拦「短通知形状」）
        long_answer = ("要登录 MIT OCW 下载讲义时，如果页面提示 not logged in，"
                       "点右上角登录即可。" + "这是正文补充说明。" * 30)
        self.assertFalse(RM._is_quota_notice(long_answer))
        self.assertEqual(gen.classify(""), "ok")

    def test_quota_notices_still_detected(self):
        self.assertTrue(RM._is_quota_notice("You've hit your limit · resets 10am"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
