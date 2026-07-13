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
        self.assertGreater(len(long_answer.strip()), 220)
        # Finding 3 回归钉：gen.main() 直接对生成的**答案正文**调用 classify()——之前是无长度
        # 门槛的子串匹配，这句长答案会被误判 hard、整题静默丢弃。必须和 RM._is_quota_notice 一样
        # 只拦"整个回答就是一条短通知"的形状，长真答案里顺带提到 not logged in 必须保留为 ok。
        self.assertEqual(gen.classify(long_answer), "ok")
        self.assertEqual(gen.classify(""), "ok")

    def test_long_cs_course_answer_mentioning_invalid_api_key_stays_valid(self):
        # Finding 3 的具体场景：CS 课程正当讨论 "invalid API key" 报错处理——不是基础设施通知，
        # 不该被当成认证失效整题丢弃。
        long_answer = (
            "当客户端收到服务端返回的 401 invalid api key 错误时，应当检查请求头里的 "
            "Authorization 令牌是否正确编码、是否已过期，并在日志中记录相关上下文以便排查。"
            + "这段补充说明具体的排查步骤与最佳实践建议，帮助理解认证失败与限流的区别。" * 10)
        self.assertGreater(len(long_answer.strip()), 220)
        self.assertEqual(gen.classify(long_answer), "ok")

    def test_quota_notices_still_detected(self):
        self.assertTrue(RM._is_quota_notice("You've hit your limit · resets 10am"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
