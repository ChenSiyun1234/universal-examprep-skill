"""Deterministic page-quality scoring and extraction-route selection.

The scorer is deliberately small and dependency-free.  It does not try to
understand a page semantically; it combines explicit text/media signals with
conservative corruption heuristics.  Callers must state zero/false signals
explicitly.  A missing signal is never silently treated as a clean signal.
"""

import math
import re
import unicodedata


QUALITY_INPUT_FIELDS = frozenset(
    (
        "page",
        "text",
        "image_count",
        "image_area_ratio",
        "vector_count",
        "multi_column_hint",
        "table_hint",
        "formula_hint",
    )
)

ROUTES = frozenset(("fast", "recover", "review"))

# Order is part of the serialized contract.  It keeps reports stable even when
# several heuristics fire for the same page.
REASON_ORDER = (
    "missing_signals",
    "no_text",
    "extraction_residue",
    "nul_or_replacement_char",
    "garbled_text",
    "repeated_characters",
    "visual_heavy",
    "multi_column_hint",
    "table_hint",
    "formula_hint",
)

_RESIDUE_PATTERNS = (
    re.compile(r"(?:^|\s)(?:xref|startxref|endobj|endstream)(?:\s|$)", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?:cid|glyph)[\s:#_-]*\d+(?:\s|$)", re.IGNORECASE),
    re.compile(r"<\/?(?:div|span|font|page|text)(?:\s[^>]*)?>", re.IGNORECASE),
    re.compile(r"\{\\(?:rtf|fonttbl|colortbl)\b", re.IGNORECASE),
)

_MOJIBAKE_FRAGMENTS = (
    "Ã",
    "Â",
    "â€",
    "â€™",
    "â€œ",
    "â€�",
    "ï»¿",
    "Ð",
    "Ñ",
)

_REPEATED_CHAR_RE = re.compile(r"([^\s])\1{5,}", re.UNICODE)
_REPEATED_TOKEN_RE = re.compile(r"\b([\w]{2,})\b(?:[\s,;:|]+\1\b){3,}", re.IGNORECASE | re.UNICODE)


class QualityInputError(ValueError):
    """A supplied page signal has an invalid type, range, or unknown key."""


def _is_int(value):
    return type(value) is int


def _validate_present_signals(signals):
    if not isinstance(signals, dict):
        raise QualityInputError("page signals must be an object")

    unknown = sorted(set(signals) - QUALITY_INPUT_FIELDS)
    if unknown:
        raise QualityInputError("unknown page-quality signals: %r" % unknown)

    page = signals.get("page")
    if page is not None and (not _is_int(page) or page < 1):
        raise QualityInputError("page must be an integer >= 1")

    text = signals.get("text")
    if text is not None and not isinstance(text, str):
        raise QualityInputError("text must be a string or null")

    for name in ("image_count", "vector_count"):
        value = signals.get(name)
        if value is not None and (not _is_int(value) or value < 0):
            raise QualityInputError("%s must be an integer >= 0 or null" % name)

    area = signals.get("image_area_ratio")
    if area is not None:
        if isinstance(area, bool) or not isinstance(area, (int, float)):
            raise QualityInputError("image_area_ratio must be a number in [0, 1] or null")
        area = float(area)
        if not math.isfinite(area) or area < 0.0 or area > 1.0:
            raise QualityInputError("image_area_ratio must be a finite number in [0, 1]")

    for name in ("multi_column_hint", "table_hint", "formula_hint"):
        value = signals.get(name)
        if value is not None and type(value) is not bool:
            raise QualityInputError("%s must be a boolean or null" % name)


def _corruption_stats(text):
    """Return deterministic corruption features without language detection."""

    length = max(len(text), 1)
    nul_or_replacement = text.count("\x00") + text.count("\ufffd")
    suspicious_controls = 0
    private_or_surrogate = 0
    for char in text:
        if char in "\n\r\t":
            continue
        category = unicodedata.category(char)
        if category == "Cc":
            suspicious_controls += 1
        elif category in ("Co", "Cs"):
            private_or_surrogate += 1

    mojibake_hits = sum(text.count(fragment) for fragment in _MOJIBAKE_FRAGMENTS)
    bad_count = nul_or_replacement + suspicious_controls + private_or_surrogate + mojibake_hits
    bad_ratio = float(bad_count) / float(length)

    nonspace = [char for char in text if not char.isspace()]
    symbol_ratio = 0.0
    if nonspace:
        symbols = sum(
            1
            for char in nonspace
            if unicodedata.category(char).startswith(("P", "S"))
        )
        symbol_ratio = float(symbols) / float(len(nonspace))

    return {
        "nul_or_replacement": nul_or_replacement,
        "mojibake_hits": mojibake_hits,
        "bad_count": bad_count,
        "bad_ratio": bad_ratio,
        "symbol_ratio": symbol_ratio,
    }


def _has_extraction_residue(text):
    return any(pattern.search(text) for pattern in _RESIDUE_PATTERNS)


def _has_repetition(text):
    return bool(_REPEATED_CHAR_RE.search(text) or _REPEATED_TOKEN_RE.search(text))


def assess_page(signals):
    """Score one page and choose ``fast``, ``recover``, or ``review``.

    ``signals`` may omit fields so a partially failed detector can still emit a
    report.  Missing or explicit-null fields add ``missing_signals``, cap the
    score, and force the fail-closed ``review`` route.  Invalid values and
    unknown keys raise :class:`QualityInputError`.

    The returned JSON-compatible object has exactly ``score``,
    ``reason_codes``, and ``route``.  ``score`` is in ``[0, 1]``.
    """

    _validate_present_signals(signals)

    missing = sorted(
        name for name in QUALITY_INPUT_FIELDS if name not in signals or signals.get(name) is None
    )
    text = signals.get("text") or ""
    stripped = text.strip()
    image_count = signals.get("image_count")
    image_area_ratio = signals.get("image_area_ratio")
    vector_count = signals.get("vector_count")
    multi_column = signals.get("multi_column_hint")
    table_hint = signals.get("table_hint")
    formula_hint = signals.get("formula_hint")

    image_count_value = image_count if image_count is not None else 0
    image_area_value = float(image_area_ratio) if image_area_ratio is not None else 0.0
    vector_count_value = vector_count if vector_count is not None else 0

    reasons = set()
    if missing:
        reasons.add("missing_signals")
    if not stripped:
        reasons.add("no_text")
    if stripped and _has_extraction_residue(text):
        reasons.add("extraction_residue")

    stats = _corruption_stats(text)
    if stats["nul_or_replacement"]:
        reasons.add("nul_or_replacement_char")

    # A single replacement character is already reported above.  Garbling is a
    # broader signal: multiple mojibake fragments, control/private characters,
    # a material bad-character ratio, or symbol soup on a non-formula page.
    if (
        stats["mojibake_hits"] >= 1
        or stats["bad_ratio"] >= 0.01
        or (len(stripped) >= 24 and stats["symbol_ratio"] >= 0.55 and not formula_hint)
    ):
        reasons.add("garbled_text")

    if stripped and _has_repetition(text):
        reasons.add("repeated_characters")

    visual_heavy = (
        image_area_value >= 0.45
        or image_count_value >= 3
        or (image_count_value >= 1 and image_area_value >= 0.25 and len(stripped) < 120)
        or (vector_count_value >= 100 and len(stripped) < 160)
    )
    if visual_heavy:
        reasons.add("visual_heavy")
    if multi_column is True:
        reasons.add("multi_column_hint")
    if table_hint is True:
        reasons.add("table_hint")
    if formula_hint is True:
        reasons.add("formula_hint")

    score = 1.0
    if "no_text" in reasons:
        score -= 0.85
    if "extraction_residue" in reasons:
        score -= 0.25
    if "nul_or_replacement_char" in reasons:
        score -= min(0.60, 0.20 + stats["bad_ratio"] * 5.0)
    if "garbled_text" in reasons:
        score -= min(0.50, 0.25 + stats["bad_ratio"] * 4.0)
    if "repeated_characters" in reasons:
        score -= 0.20
    if "visual_heavy" in reasons:
        score -= 0.12
    if "multi_column_hint" in reasons:
        score -= 0.08
    if "table_hint" in reasons:
        score -= 0.05
    if "formula_hint" in reasons:
        score -= 0.05
    if missing:
        score = min(score, 0.25)
    score = round(max(0.0, min(1.0, score)), 4)

    if missing:
        route = "review"
    elif "no_text" in reasons:
        has_recovery_evidence = (
            image_count_value > 0
            or image_area_value > 0.0
            or vector_count_value > 0
            or multi_column is True
            or table_hint is True
            or formula_hint is True
        )
        route = "recover" if has_recovery_evidence else "review"
    elif reasons:
        route = "recover"
    else:
        route = "fast"

    ordered_reasons = [reason for reason in REASON_ORDER if reason in reasons]
    return {"score": score, "reason_codes": ordered_reasons, "route": route}


def score_page(signals):
    """Backward-friendly alias for :func:`assess_page`."""

    return assess_page(signals)
