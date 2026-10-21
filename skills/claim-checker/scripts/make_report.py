"""Validate the check results and write the fact-check report with an exact tally.

Usage:
  python make_report.py claims.json check.json --title "Fact-check: <title>" [--out check.md] [--offline]

check.json is written by the assistant after opening each source:
  [{"id": 1, "status": "verified|partial|unverified",
    "url": "the source actually checked", "quote": "exact supporting text from the page",
    "note": "what differs / why it couldn't be confirmed"}]

Rules enforced (the script refuses to write the report otherwise):
  - every claim in claims.json has exactly one result
  - status is one of verified / partial / unverified
  - verified and partial need a quote from the source
  - partial and unverified need a note explaining the gap
  - every figure in a "verified" claim must appear in its quote (numbers_check.py),
    unless the claim is the writer's own calculation or the result explains it in
    "numbers_note"; the report shows which applies
  - every quote must really appear on its source page: the script downloads
    each page itself and refuses quotes it can't find there. Pages it can't
    download are marked "not machine-checked" in the report, never passed silently.
    --offline skips the downloads (the report then says quotes weren't checked).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from numbers_check import is_calculated, missing_figures
from quote_check import PDF_PREFIX, SANDBOX_BLOCKED, fetch_text, quote_long_enough, quote_on_page

STATUSES = ("verified", "partial", "unverified")
LABEL = {"verified": "✅ Verified", "partial": "⚠️ Partial", "unverified": "❌ Unverified"}


def claim_text(sentence: str, url: str) -> str:
    """The words that carry the fact: the linked phrase(s) for the checked URL,
    else all linked phrases, else the whole sentence (for bare URLs)."""
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", sentence)
    mine = [t for t, u in links if url and u.split("?")[0].rstrip("/") == url.split("?")[0].rstrip("/")]
    if mine:
        return " ".join(mine)
    if links:
        return " ".join(t for t, _ in links)
    return sentence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("claims")
    ap.add_argument("check")
    ap.add_argument("--title", default="Fact-check report")
    ap.add_argument("--out", default="check.md")
    ap.add_argument("--offline", action="store_true", help="don't download pages to check the quotes")
    a = ap.parse_args()

    claims = json.loads(Path(a.claims).read_text(encoding="utf-8"))
    results = json.loads(Path(a.check).read_text(encoding="utf-8"))
    by_id = {}
    problems = []
    for r in results:
        cid = r.get("id")
        if cid in by_id:
            problems.append(f"claim {cid}: more than one result")
        by_id[cid] = r
        st = str(r.get("status", "")).lower().strip()
        r["status"] = st
        if st not in STATUSES:
            problems.append(f"claim {cid}: status must be one of {STATUSES}, got '{st}'")
        if st in ("verified", "partial") and not str(r.get("quote", "")).strip():
            problems.append(f"claim {cid}: '{st}' needs the supporting quote from the source")
        if st in ("partial", "unverified") and not str(r.get("note", "")).strip():
            problems.append(f"claim {cid}: '{st}' needs a note explaining the gap")
    for c in claims["claims"]:
        if c["id"] not in by_id:
            problems.append(f"claim {c['id']}: no result (every claim must be checked)")
    extra = set(by_id) - {c["id"] for c in claims["claims"]}
    if extra:
        problems.append(f"results for unknown claim ids: {sorted(extra)}")
    sentence = {c["id"]: c["sentence"] for c in claims["claims"]}
    ncheck = {}  # claim id -> ("ok" | "calculated" | "explained", missing figures)
    for cid, r in by_id.items():
        if r.get("status") != "verified" or not str(r.get("quote", "")).strip() or cid not in sentence:
            continue
        text = claim_text(sentence[cid], r.get("url", ""))
        if is_calculated(sentence[cid]) or r.get("calculated"):
            ncheck[cid] = ("calculated", [])
            continue
        miss = missing_figures(text, r["quote"])
        if not miss:
            ncheck[cid] = ("ok", [])
        elif str(r.get("numbers_note", "")).strip():
            ncheck[cid] = ("explained", miss)
        else:
            problems.append(f"claim {cid}: marked verified, but these figures aren't in its quote: {', '.join(miss)}. "
                            "Quote the part of the page that states them (put … between parts), mark the claim partial, "
                            "or say in numbers_note why the figure doesn't need to be in the quote")

    claim_urls = {c["id"]: c["urls"] for c in claims["claims"]}
    qcheck = {}  # claim id -> ("found" | "not checked", reason)
    if not a.offline:
        pages = {}
        for cid, r in by_id.items():
            quote = str(r.get("quote", "")).strip()
            if r.get("status") not in ("verified", "partial") or not quote:
                continue
            if not quote_long_enough(quote):
                problems.append(f"claim {cid}: the quote is too short to count as evidence; "
                                "copy the whole sentence from the page")
                continue
            url = r.get("url") or (claim_urls.get(cid) or [""])[0]
            if url not in pages:
                pages[url] = fetch_text(url)
            text, reason = pages[url]
            if text is None:
                qcheck[cid] = ("not checked", reason)
            elif quote_on_page(quote, text):
                qcheck[cid] = ("found", "")
            elif text.startswith(PDF_PREFIX):
                qcheck[cid] = ("not checked", "the quote couldn't be matched in the PDF's extracted text (PDF layout can scramble word order)")
            else:
                problems.append(f"claim {cid}: the quote was not found on {url}. Copy the exact text from "
                                "the page (put … between separate parts), or mark the claim unverified")
    if problems:
        print(json.dumps({"ok": False, "problems": problems}, indent=1))
        sys.exit(2)

    tally = Counter(by_id[c["id"]]["status"] for c in claims["claims"])
    n = len(claims["claims"])
    parts = [f"{tally.get(s, 0)} {s}" for s in STATUSES if tally.get(s, 0)]
    tally_line = f"{n} claim{'s' if n != 1 else ''} checked: " + (", ".join(parts) if parts else "none")

    quoted = [cid for cid, r in by_id.items() if r["status"] in ("verified", "partial") and r.get("quote")]
    found = sum(1 for cid in quoted if qcheck.get(cid, ("",))[0] == "found")
    sandbox_off = bool(quoted) and found == 0 and all(qcheck.get(cid, ("", ""))[1] == SANDBOX_BLOCKED for cid in quoted)
    if a.offline:
        qline = "Quotes were not machine-checked against the pages (offline run)."
    elif sandbox_off:
        qline = ("**Quote check: off in this environment.** Claude opened every source, but the code couldn't reach "
                 "the source websites, so the script could not download the pages to double-check the quotes word for word. "
                 "In the Claude app, allowing code to access the web (network settings under Settings → Capabilities) "
                 "turns this check on; in Claude Code it normally works.")
    elif quoted:
        qline = f"Quotes found on the downloaded source pages: {found} of {len(quoted)}."
        if found < len(quoted):
            qline += f" {len(quoted) - found} couldn't be machine-checked; see each claim."
    else:
        qline = ""

    nl = ""
    if ncheck:
        ok = sum(st == "ok" for st, _ in ncheck.values())
        nl = f"Figures in verified claims found in their quotes: {ok} of {len(ncheck)} claims."
        ex = sum(st == "explained" for st, _ in ncheck.values())
        ca = sum(st == "calculated" for st, _ in ncheck.values())
        if ex:
            nl += f" {ex} explained by the checker instead (see each claim)."
        if ca:
            nl += f" {ca} {'is a calculation' if ca == 1 else 'are calculations'}, not checked this way."

    lines = [f"# {a.title}", "", f"**{tally_line}.**", ""]
    if qline:
        lines += [qline, ""]
    if nl:
        lines += [nl, "", "_Code checks that each quote is on its page and that a verified claim's figures appear in "
                  "its quote. Whether the quote fully supports the claim's wording is the checker's judgement._", ""]
    order = sorted(claims["claims"], key=lambda c: (STATUSES.index(by_id[c["id"]]["status"]) * -1, c["id"]))
    for c in order:
        r = by_id[c["id"]]
        lines.append(f"### {c['id']}. {LABEL[r['status']]}")
        lines.append("")
        lines.append(f"**Claim:** {c['sentence']}")
        lines.append("")
        lines.append(f"**Source checked:** {r.get('url') or ', '.join(c['urls'])}")
        if r.get("quote"):
            lines.append("")
            lines.append(f"> {r['quote'].strip()}")
            if c["id"] in qcheck and not sandbox_off:
                state, why = qcheck[c["id"]]
                lines.append("")
                lines.append("**Quote check:** found on the page." if state == "found"
                             else f"**Quote check:** not machine-checked: {why}.")
        if c["id"] in ncheck:
            st, miss = ncheck[c["id"]]
            lines.append("")
            if st == "ok":
                lines.append("**Numbers check:** every figure in the claim is in the quote.")
            elif st == "calculated":
                lines.append("**Numbers check:** the claim is the writer's own calculation, so it isn't checked this way.")
            else:
                lines.append(f"**Numbers check:** not in the quote: {', '.join(miss)}. "
                             f"Checker's explanation: {r['numbers_note'].strip()}")
        if r.get("note"):
            lines.append("")
            lines.append(f"**Note:** {r['note'].strip()}")
        lines.append("")
    if claims.get("uncited"):
        lines.append("## Not checked: figures with no source")
        lines.append("")
        lines.append("These sentences state a number or date but cite nothing, so there was nothing to check:")
        lines.append("")
        lines += [f"- {u['sentence']}" for u in claims["uncited"]]
        lines.append("")
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "tally": tally_line, "counts": {s: tally.get(s, 0) for s in STATUSES},
                      "quotes_found_on_page": None if a.offline else found,
                      "quotes_not_machine_checked": None if a.offline else len(quoted) - found,
                      "quote_check_off_in_sandbox": sandbox_off,
                      "numbers_check": {k: sum(st == k for st, _ in ncheck.values()) for k in ("ok", "explained", "calculated")},
                      "uncited": len(claims.get("uncited", [])), "out": a.out}))


if __name__ == "__main__":
    main()
