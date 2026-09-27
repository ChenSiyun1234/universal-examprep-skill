# -*- coding: utf-8 -*-
"""Course files are data, never instructions.

Everything the tool prints from a student's files goes between two fence lines, and lines
that talk to an AI assistant ("ignore previous instructions", "如果你是 AI…", "send … to http…")
are flagged. A PDF from a classmate or a scraped web page can contain such text; the tutor
must teach it as content and never act on it.

The patterns only match text that addresses an AI. Ordinary coursework such as
"Run the following code" or "在终端执行以下命令" is not flagged.
"""
import re

OPEN = "<<<MATERIAL"
CLOSE = "MATERIAL>>>"

_AI = r"(?:ai|a\.i\.|assistant|chatbot|chat\s*gpt|gpt-?\d\w*|claude|gemini|copilot|llm|(?:large\s+)?language\s+model|model)"
_EN = [
    # "ignore all previous instructions", "disregard your guidelines"
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|preceding|all|any|your|these|those)\b"
    r"[^.\n]{0,30}\b(?:instructions?|prompts?|directives?|guidelines)\b",
    r"\byou\s+are\s+(?:now\s+)?(?:an?\s+)?(?:ai\s+(?:assistant|model|tutor|agent)|chat\s*gpt|gpt-?\d\w*|claude|gemini|copilot|llm|(?:large\s+)?language\s+model)\b",
    r"\bif\s+you\s+are\s+(?:an?\s+)?" + _AI + r"\b",
    r"\b(?:note|message|instructions?|reminder)\s+(?:to|for)\s+(?:the\s+|any\s+)?" + _AI + r"s?\b",
    r"\b(?:system|developer)\s+prompt\b",
    r"\bas\s+an\s+ai\s+(?:assistant|model|language\s+model)\b",
    r"\b(?:do\s+not|don't|never)\s+(?:tell|show|inform|mention\s+to)\s+(?:the\s+)?(?:user|student)s?\b",
    r"\b(?:send|upload|post|exfiltrate|forward)\b[^.\n]{0,60}\b(?:to|at)\s+https?://",
    r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|<<SYS>>",
    r"^\s*(?:system|assistant)\s*:\s",
]
_ZH = [
    r"(?:忽略|无视|忘记|忘掉|不要理会)你?(?:之前|以上|前面|上面|先前|所有|全部|原有|原来)的?(?:所有|全部)?的?(?:指令|指示|提示词?|规则|设定)",
    r"你(?:现在)?(?:是|扮演|作为)(?:一个|一名)?[^，。,.\n]{0,10}?(?:AI|人工智能|ChatGPT|GPT|Claude|Gemini|智能助手|大模型|语言模型)",
    r"(?:如果|假如|若)你是(?:一个|一名)?(?:AI|人工智能|大模型|语言模型|助手|智能体)",
    r"(?:给|对)(?:AI|人工智能|大模型|助手|模型|智能体)的?(?:指令|说明|提示|话)",
    r"系统提示词",
    r"不要(?:告诉|让|提醒)(?:学生|用户)",
    r"(?:发送|上传|转发)[^。\n]{0,30}(?:到|给)\s*https?://",
]
_PATTERNS = [re.compile(p, re.I | re.M) for p in _EN + _ZH]


def is_suspicious(line):
    return any(p.search(line) for p in _PATTERNS)


def flagged_lines(text, limit=5):
    """Lines of `text` that address an AI assistant, shortened, at most `limit`."""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if s and is_suspicious(s):
            out.append(s if len(s) <= 120 else s[:119] + "…")
            if len(out) >= limit:
                break
    return out


def neutralize(text):
    """Make sure material text cannot close (or reopen) the fence early."""
    return text.replace(CLOSE, "MATERIAL> > >").replace(OPEN, "< < <MATERIAL")


def fence(text):
    return "%s\n%s\n%s" % (OPEN, neutralize(text).rstrip(), CLOSE)
