"""Download a cited page and check that a quote really appears on it.

Used by make_report.py so that a quote can't be invented: a "verified" or
"partial" claim must quote text that is actually on the source page.

Matching ignores case, spaces and punctuation (quote marks, dashes, commas),
but every word and number must match.
Use "…" or "..." between separate parts of a page; each part must appear on
the page, in order.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.request
import zlib
from html.parser import HTMLParser

MIN_QUOTE_CHARS = 12      # shorter quotes are too weak to count as evidence
MIN_PAGE_CHARS = 200      # less text than this usually means a JavaScript-only page
MAX_BYTES = 8_000_000
TIMEOUT = 20

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "section", "article",
          "header", "footer", "main", "pre", "blockquote", "dt", "dd", "figcaption",
          "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP = {"script", "style", "noscript", "template", "svg"}
_CHARS = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                        "“": '"', "”": '"', "„": '"', "″": '"',
                        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                        "―": "-", "−": "-", " ": " ", "­": ""})


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return re.sub(r"\s+", " ", "".join(p.parts)).strip()


def squash(s: str) -> str:
    """Normalise for matching: keep only letters, digits, % and currency signs, lower case.

    Spaces, quote marks, dashes and other punctuation are dropped, so formatting
    differences don't matter, but the words and numbers must match exactly.
    A point or comma between two digits is kept, so 3.12 and 31.2 stay different.
    """
    s = unicodedata.normalize("NFKC", s).translate(_CHARS).lower()
    s = re.sub(r"(?<=\d)[.,](?=\d)", lambda m: "\x00" if m.group() == "." else "\x01", s)
    s = re.sub(r"[^\w%$€£₹¥\x00\x01]|_", "", s)
    return s.replace("\x00", ".").replace("\x01", ",")


def fragments(quote: str) -> list[str]:
    parts = re.split(r"…|\.\.\.|\[\.\.\.\]|\[…\]", quote)
    out = []
    for p in parts:
        p = squash(p)
        if p:
            out.append(p)
    return out


def quote_on_page(quote: str, page_text: str) -> bool:
    """True if every part of the quote appears on the page, in order."""
    page = squash(page_text)
    pos = 0
    for f in fragments(quote):
        i = page.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def quote_long_enough(quote: str) -> bool:
    return sum(len(f) for f in fragments(quote)) >= MIN_QUOTE_CHARS


def fetch_text(url: str) -> tuple[str | None, str]:
    """Return (page text, "") or (None, reason it couldn't be checked)."""
    if not re.match(r"https?://", url or ""):
        return None, "not a web link"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; claim-checker; +https://github.com/deeprdai21-ai/practical-claude-skills)",
        "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            encoding = resp.headers.get("Content-Encoding", "").lower()
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
    except Exception as e:  # network blocked, 403/404, timeout, bad certificate...
        msg = getattr(e, "reason", None) or getattr(e, "code", None) or e.__class__.__name__
        return None, f"page could not be downloaded ({msg})"
    # Some servers compress the page even when not asked; unpack it before reading.
    try:
        if raw[:2] == b"\x1f\x8b" or "gzip" in encoding:
            raw = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
        elif "deflate" in encoding:
            raw = zlib.decompress(raw) if raw[:1] == b"\x78" else zlib.decompress(raw, -zlib.MAX_WBITS)
        elif encoding not in ("", "identity"):
            return None, f"the page came compressed as '{encoding}', which this check can't unpack"
    except zlib.error:
        return None, "the page came compressed and couldn't be unpacked"
    if "pdf" in ctype or raw[:5] == b"%PDF-":
        return None, "the source is a PDF, which this check doesn't read"
    text = raw.decode(charset, errors="replace")
    if "html" in ctype or "<html" in text[:2000].lower():
        text = html_to_text(text)
    if text.count("\ufffd") > len(text) * 0.02:
        return None, "the downloaded page couldn't be read as text"
    if len(text) < MIN_PAGE_CHARS:
        return None, "the downloaded page has almost no text (it probably needs JavaScript)"
    return text, ""
