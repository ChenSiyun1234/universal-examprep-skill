import re


SOURCE_UNIT_LANGUAGE_CODES = frozenset(("zh", "en", "zxx"))
MATERIAL_TEXT_LANGUAGE_CODES = frozenset(("zh", "en"))

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_TEX_COMMAND = re.compile(r"\\(?:begin|end)\{[A-Za-z*]+\}|\\[A-Za-z]+")
_TEX_PROSE = re.compile(
    r"\\(?:text|textrm|textsf|texttt|textnormal|mbox)\s*\{", re.I)
_WORD = re.compile(r"[A-Za-z]+")
_ENGLISH_PROSE = frozenset(
    "the a an and or of to in for with from by is are was were what which why how "
    "find calculate compute determine derive explain show prove given assume using "
    "answer solution true false".split()
)
_ENGLISH = _ENGLISH_PROSE | frozenset(
    "chapter section example quiz problem overview course note parser output".split())
_FORMULA_PROSE = _ENGLISH_PROSE | frozenset(
    "if where otherwise use let be when then else such that equals result case".split())
_MATH_SIGNAL = re.compile(
    r"\\[A-Za-z]+|[0-9=+*/^<>≤≥∑∏∫√±×÷≠≈∈∉⊂⊆⊃⊇∅∀∃∪∩(){}\[\]|_]"
)
_BARE_MATH_WORDS = frozenset(
    "sin cos tan log ln exp min max lim det rank arg argmin argmax var cov dx dy dt".split()
)
_KINDS = frozenset((
    None, "text", "list", "table", "formula", "question", "answer", "other",
))


def is_language_neutral_formula(text=None, latex=None, kind=None):
    if kind not in _KINDS:
        return False
    values = [v for v in (text, latex) if isinstance(v, str) and v.strip()]
    if not values:
        return False
    value = "\n".join(values)
    if _CJK.search(value) or _TEX_PROSE.search(value):
        return False
    symbolic = bool(_MATH_SIGNAL.search(value)) and (
        kind == "formula" or isinstance(latex, str) and bool(latex.strip()))
    visible = _TEX_COMMAND.sub("", value)
    for token in _WORD.findall(visible):
        lowered = token.lower()
        if len(token) == 1:
            continue
        if lowered in _FORMULA_PROSE:
            return False
        if (lowered in _BARE_MATH_WORDS
                or (token.isupper() and len(token) <= 4)):
            continue
        if symbolic and token.islower() and len(token) <= 4:
            continue
        return False
    return bool(
        kind == "formula"
        or any(isinstance(v, str) and v.strip() for v in (latex,))
        or _MATH_SIGNAL.search(value)
    )


def source_language_evidence(value, kind=None, latex=None):
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    words = [token.lower() for token in _WORD.findall(value)]
    cjk = bool(_CJK.search(value))
    if cjk:
        return "mixed" if sum(map(len, words)) >= 3 and any(
            token in _ENGLISH_PROSE for token in words) else "zh"
    if is_language_neutral_formula(value, latex=latex, kind=kind):
        return "zxx"
    return "en" if any(token in _ENGLISH for token in words) else "unknown"
