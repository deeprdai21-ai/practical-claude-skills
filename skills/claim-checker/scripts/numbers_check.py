"""Check that every figure in a "verified" claim also appears in its quoted evidence.

A real quote copied from the source can still fail to support the claim, most
often because a number differs ("25% faster" claimed, "an estimated 5%" quoted).
This module finds the figures in the claim and looks for each one in the quote.

Rules (kept simple and predictable):
  - A figure is a number not glued to a letter in front, so labels like Q1, FY27,
    H1 or e2W are ignored. Commas are ignored, so 1,29,940 = 129,940 = 129940.
  - Whole numbers below 10 are ignored unless they carry a % sign or a decimal
    point: counts like "3 companies" or dates like "2 October" are too noisy.
  - A claim figure matches if a quote figure is equal to it after rounding the
    quote figure to the claim's precision (claim 2.2 matches quote 2.17; claim
    3.8 does not match 3.10). Round thousands also match (claim 1,800 matches
    1,812), but small round numbers must be exact (claim 10% doesn't match 14%).
  - "525k" counts as 525,000.
  - Claims marked as the writer's own calculation are not checked here.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

NUM = re.compile(r"(?<![A-Za-z\d.,])(\d[\d,]*(?:\.\d+)?)(\s?%|\s?per\s?cent|\s?percent|k\b)?", re.I)
CALC = re.compile(r"\(calculated\)|by this brief's calculation|calculation checked", re.I)


def _plain(text: str) -> str:
    """Drop link targets and bare URLs, whose digits aren't figures."""
    text = re.sub(r"\]\([^)]*\)", "]", text or "")
    return re.sub(r"https?://\S+", " ", text)


def figures(text: str) -> list[tuple[str, Decimal]]:
    """Return (as written, value) for each figure worth checking in the text."""
    out = []
    for m in NUM.finditer(_plain(text)):
        raw, pct = m.group(1).rstrip(",."), m.group(2)
        digits = raw.replace(",", "")
        if not digits or not re.fullmatch(r"\d+(\.\d+)?", digits):
            continue
        val = Decimal(digits)
        if pct and pct.lower() == "k":  # 525k = 525,000
            out.append((raw + "k", val * 1000))
            continue
        if "." not in digits and not pct and val < 10:
            continue
        out.append((raw + ("%" if pct else ""), val))
    return out


def _matches(claim: Decimal, quote: Decimal) -> bool:
    if claim == quote:
        return True
    exp = claim.as_tuple().exponent
    if exp < 0:  # claim has decimals: round the quote figure to the same places
        return quote.quantize(Decimal(1).scaleb(exp), rounding=ROUND_HALF_UP) == claim
    if claim >= 1000:  # round thousands: 1,800 can stand for 1,812
        zeros = len(str(int(claim))) - len(str(int(claim)).rstrip("0"))
        if zeros:
            step = Decimal(10) ** zeros
            return (quote / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step == claim
    return False


def missing_figures(claim_text: str, quote_text: str) -> list[str]:
    """Figures in the claim that don't appear in the quote. Empty list = all found."""
    q = [v for _, v in figures(quote_text)]
    return [raw for raw, v in figures(claim_text) if not any(_matches(v, x) for x in q)]


def is_calculated(text: str) -> bool:
    return bool(CALC.search(text or ""))
