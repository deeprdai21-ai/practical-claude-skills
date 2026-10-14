"""Split a text into sentences and list every sentence that cites a source.

Usage:
  python extract_claims.py DRAFT.md [--out claims.json]

Reads Markdown or plain text. A claim is a sentence with at least one inline
link [text](url) or a bare URL. Sentences that state a number, date or
percentage but cite nothing are listed separately as "uncited", so the reader
can see what was not checked.

Output (claims.json):
  {"source_file": ..., "claims": [{"id": 1, "sentence": ..., "urls": [...]}],
   "uncited": [{"sentence": ...}], "sources_section_urls": [...]}
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_URL = re.compile(r"(?<![(\[])\bhttps?://[^\s)\]>]+")
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|ref$|ref_src$|mc_)", re.I)
# A digit or a number word usually means a figure, date or ranking.
FACTY = re.compile(r"\d|\b(half|third|quarter|dozen|hundred|thousand|million|billion|trillion|crore|lakh|"
                   r"percent|per cent|majority|doubled|tripled|halved)\b", re.I)
SOURCES_HEADING = re.compile(r"^\s{0,3}(#+\s*)?(\*\*)?(sources|references|bibliography)(\*\*)?\s*:?\s*$", re.I)


def clean_url(url: str) -> str:
    """Drop tracking parameters and trailing punctuation."""
    url = url.rstrip(".,;:")
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), ""))


def split_body_and_sources(text: str):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if SOURCES_HEADING.match(line):
            return "\n".join(lines[:i]), "\n".join(lines[i + 1:])
    return text, ""


def sentences(text: str):
    """Rough sentence splitter that keeps markdown links intact."""
    # protect links so their dots don't split sentences
    links = []

    def hold(m):
        links.append(m.group(0))
        return f"\u0000{len(links) - 1}\u0000"

    t = MD_LINK.sub(hold, text)
    t = BARE_URL.sub(hold, t)
    out = []
    for block in re.split(r"\n\s*\n", t):  # paragraphs and list items
        block = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", block, flags=re.M)  # list markers
        block = re.sub(r"^\s{0,3}#+\s*", "", block, flags=re.M)  # headings
        block = " ".join(block.split())
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(\u0000])", block):
            s = re.sub(r"\u0000(\d+)\u0000", lambda m: links[int(m.group(1))], s).strip()
            if len(s) > 3:
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--out", default="claims.json")
    a = ap.parse_args()

    text = Path(a.draft).read_text(encoding="utf-8", errors="replace")
    body, sources = split_body_and_sources(text)
    claims, uncited = [], []
    for s in sentences(body):
        urls = [clean_url(u) for _, u in MD_LINK.findall(s)] + [clean_url(u) for u in BARE_URL.findall(MD_LINK.sub("", s))]
        urls = list(dict.fromkeys(urls))
        if urls:
            claims.append({"id": len(claims) + 1, "sentence": s, "urls": urls})
        elif FACTY.search(s):
            uncited.append({"sentence": s})
    src_urls = list(dict.fromkeys(clean_url(u) for u in re.findall(r"https?://[^\s)\]>]+", sources)))

    result = {"source_file": a.draft, "claims": claims, "uncited": uncited, "sources_section_urls": src_urls}
    Path(a.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    distinct = len({u for c in claims for u in c["urls"]})
    print(json.dumps({"ok": True, "claims": len(claims), "distinct_sources": distinct,
                      "uncited_sentences_with_figures": len(uncited), "out": a.out}))


if __name__ == "__main__":
    main()
