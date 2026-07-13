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
        for s in self.NOTICES:
            self.assertEqual(gen.classify(s), "hard",
                             "登录失效需要人工处理——必须 hard（停跑），不是 transient 重试: %r" % s)

    def test_gen_classify_matches_run_matrix_auth_vocabulary(self):
        # Finding 4 回归钉：gen.classify 此前维护一份**不完整**的子串元组，只认下划线形
        # "authentication_error"、漏了 "未登录"/"credentials (expired|invalid)"/空格形
        # "authentication error"——这些短通知会漏网被当合法答案缓存进 gen_answers.jsonl，
        # 重演该文件顶部注释描述的那次登录态过期事故。gen 不能 import run_matrix（会成环），
        # 所以这里逐条核对 gen._AUTH_RESULT_RE 与 run_matrix._AUTH_RESULT_RE 是同一份词表
        # （对同一批探针字符串给出相同的匹配结果）。
        probes = (
            "未登录", "Credentials expired", "credentials invalid",
            "Authentication error", "authentication_error", "Not logged in",
            "Please run /login", "Invalid API key", "这是一段正常答案，不含任何认证词",
        )
        for s in probes:
            self.assertEqual(bool(gen._AUTH_RESULT_RE.search(s)),
                             bool(RM._AUTH_RESULT_RE.search(s)),
                             "gen/_run_matrix 的认证词表对 %r 判定不一致" % s)

    def test_short_chinese_auth_notice_classifies_hard(self):
        # Finding 4 的具体缺口：短「未登录」此前不在 gen._AUTH_HARD 子串元组里，会被 gen.classify
        # 判成 "ok"、当合法答案缓存。
        self.assertEqual(gen.classify("未登录"), "hard")

    def test_short_credentials_expired_notice_classifies_hard(self):
        # Finding 4 的另一处缺口：gen 旧词表完全没有 "credentials (expired|invalid)" 这支——
        # run_matrix._AUTH_RESULT_RE 早就认，gen 这边漏网。
        self.assertEqual(gen.classify("Credentials expired"), "hard")
        self.assertEqual(gen.classify("Credentials invalid"), "hard")

    def test_long_answer_mentioning_new_auth_phrases_stays_ok(self):
        # round-1 的 220 字符门槛必须继续保护新补的词——长真答案里顺带讨论这些认证报错文案
        # 不该被整题丢弃。
        long_answer = (
            "当会话的 credentials expired 或系统提示未登录时，客户端应当引导用户重新认证，"
            "并在服务端日志里记录 authentication error 的具体上下文以便审计。"
            + "这段补充说明具体的排查步骤与最佳实践建议。" * 10)
        self.assertGreater(len(long_answer.strip()), 220)
        self.assertEqual(gen.classify(long_answer), "ok")

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
