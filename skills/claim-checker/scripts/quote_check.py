"""Download a cited page and check that a quote really appears on it.

Used by make_report.py so that a quote can't be invented: a "verified" or
"partial" claim must quote text that is actually on the source page.

Matching ignores case, spaces and punctuation (quote marks, dashes, commas),
but every word and number must match, and the end of a sentence counts: a quote
can't run from one sentence into the next unless it keeps the full stop, so two
pieces of text spliced across a sentence boundary are refused.
Use "…" or "..." between separate parts of a page; each part must appear on
the page (in any order: quoters don't always keep page order, and PDF
layout can scramble it).
"""

from __future__ import annotations

import re
import unicodedata
import urllib.request
import zlib
from html.parser import HTMLParser

MIN_QUOTE_CHARS = 12      # shorter quotes are too weak to count as evidence
MIN_PAGE_CHARS = 200      # less text than this usually means a JavaScript-only page
MAX_BYTES = 40_000_000   # company PDFs (results letters) can be large
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


_SENT_END = re.compile(r"[.!?][\"')\]]*(?=\s|$)")  # a full stop, ! or ? that ends a sentence


def squash(s: str) -> str:
    """Normalise for matching: keep only letters, digits, % and currency signs, lower case.

    Spaces, quote marks, dashes and other punctuation are dropped, so formatting
    differences don't matter, but the words and numbers must match exactly.
    A point or comma between two digits is kept, so 3.12 and 31.2 stay different.
    The end of a sentence is kept as "|", so text from two sentences can't be
    joined into one quote without its full stop.
    """
    s = unicodedata.normalize("NFKC", s).translate(_CHARS).lower()
    s = _SENT_END.sub("\x02", s)
    s = re.sub(r"(?<=\d)[.,](?=\d)", lambda m: "\x00" if m.group() == "." else "\x01", s)
    s = re.sub(r"[^\w%$€£₹¥\x00\x01\x02]|_", "", s)
    return s.replace("\x00", ".").replace("\x01", ",").replace("\x02", "|")


_ELLIPSIS = re.compile(r"\[\.\.\.\]|\[…\]|…|\.\.\.")


def fragments(quote: str) -> list[str]:
    out = []
    for p in _ELLIPSIS.split(quote):
        p = squash(p).strip("|")  # a quote may start or stop at a sentence end
        if p:
            out.append(p)
    return out


def quote_on_page(quote: str, page_text: str) -> bool:
    """True if every part of the quote appears on the page (in any order)."""
    page = squash(page_text)
    return all(f in page for f in fragments(quote))


def quote_long_enough(quote: str) -> bool:
    return sum(len(f.replace("|", "")) for f in fragments(quote)) >= MIN_QUOTE_CHARS


# --- edge check: was a "not" or an "unless" cut off at the edge of the quote? ------
# A quote can be on the page and still say the opposite of the page, because it
# starts just after "not" or stops just before "unless". After a quote is found,
# look at the few words right before and after each part, within its sentence.

LEFT_WORDS = {"not", "no", "never", "only", "unless", "except", "excluding", "without", "fewer", "less",
              "neither", "nor", "hardly", "barely", "cannot", "isnt", "arent", "wasnt", "werent", "dont",
              "doesnt", "didnt", "cant", "couldnt", "wont", "wouldnt", "shouldnt", "hasnt", "havent", "hadnt"}
RIGHT_WORDS = {"if", "unless", "except", "excluding", "when", "but", "until", "only", "provided", "assuming",
               "although", "though", "however", "not"}
EDGE_WINDOW_LEFT = 3
EDGE_WINDOW_RIGHT = 2


def _word_tokens(text: str) -> list[str]:
    """Words in matching form, with "|" for each sentence end."""
    out = []
    for piece in re.split(r"\s+", unicodedata.normalize("NFKC", text).translate(_CHARS)):
        sq = squash(piece)
        if not sq:
            continue
        for i, part in enumerate(sq.split("|")):
            if i:
                out.append("|")
            if part:
                out.append(part)
    return out


def edge_words(quote: str, page_text: str) -> list[str]:
    """Negating or limiting words sitting just outside the quote on the page.

    Returns e.g. ['not (before "enabled by default")']; an empty list means the
    edges are clean, or the quote's words couldn't be lined up with the page's
    (then nothing is claimed either way).
    """
    page = _word_tokens(page_text)
    found = []
    for part in _ELLIPSIS.split(quote):
        q = _word_tokens(part)
        while q and q[0] == "|":
            q = q[1:]
        while q and q[-1] == "|":
            q = q[:-1]
        if not q:
            continue
        hits, clean = [], False
        n = len(q)
        for i in range(len(page) - n + 1):
            if page[i:i + n] != q:
                continue
            here = []
            for t in reversed(page[max(0, i - EDGE_WINDOW_LEFT):i]):
                if t == "|":
                    break
                if t in LEFT_WORDS:
                    here.append(f'"{t}" just before')
            for t in page[i + n:i + n + EDGE_WINDOW_RIGHT]:
                if t == "|":
                    break
                if t in RIGHT_WORDS:
                    here.append(f'"{t}" just after')
            if not here:
                clean = True
                break
            hits = here
        if hits and not clean:
            short = part.strip()
            short = short if len(short) <= 60 else short[:57] + "…"
            found += [f"{h} \"{short}\"" for h in hits]
    return found


SANDBOX_BLOCKED = "the code couldn't reach this site (network access is blocked or limited)"


def describe_error(e: Exception) -> str:
    """Turn a download error into a short plain-English reason."""
    code = getattr(e, "code", None)
    text = str(getattr(e, "reason", "") or e)
    if "tunnel" in text.lower() or "proxy" in text.lower() or "name or service not known" in text.lower() \
            or "temporary failure in name resolution" in text.lower() or "network is unreachable" in text.lower() \
            or "getaddrinfo failed" in text.lower() or "nodename nor servname" in text.lower():
        return SANDBOX_BLOCKED
    if code in (401, 402, 403):
        return f"the site refused the download (error {code}; often a paywall or bot block)"
    if code == 404:
        return "the page wasn't found (error 404)"
    if code:
        return f"the site returned error {code}"
    if "timed out" in text.lower():
        return "the site took too long to respond"
    return f"the page couldn't be downloaded ({e.__class__.__name__})"


PDF_PREFIX = "\x00pdf\x00"  # marks text that came from a PDF (layout can scramble word order)


def pdf_text(raw: bytes) -> tuple[str | None, str]:
    try:
        import io
        import logging
        from pypdf import PdfReader
        logging.getLogger("pypdf").setLevel(logging.ERROR)  # don't flood the output with layout warnings
    except ImportError:
        return None, "the source is a PDF and the pypdf library isn't installed"
    try:
        reader = PdfReader(io.BytesIO(raw))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:60])
    except Exception:
        return None, "the PDF couldn't be read"
    if len(text.strip()) < MIN_PAGE_CHARS:
        return None, "the PDF has no readable text (it may be a scanned image)"
    return PDF_PREFIX + text, ""


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
        return None, describe_error(e)
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
        return pdf_text(raw)
    text = raw.decode(charset, errors="replace")
    if "html" in ctype or "<html" in text[:2000].lower():
        text = html_to_text(text)
    if text.count("\ufffd") > len(text) * 0.02:
        return None, "the downloaded page couldn't be read as text"
    if len(text) < MIN_PAGE_CHARS:
        return None, "the downloaded page has almost no text (it probably needs JavaScript)"
    return text, ""
