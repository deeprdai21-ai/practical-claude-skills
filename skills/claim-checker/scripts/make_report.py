"""Validate the check results and write the fact-check report with an exact tally.

Usage:
  python make_report.py claims.json check.json --title "Fact-check: <title>" [--out check.md]

check.json is written by the assistant after opening each source:
  [{"id": 1, "status": "verified|partial|unverified",
    "url": "the source actually checked", "quote": "exact supporting text from the page",
    "note": "what differs / why it couldn't be confirmed"}]

Rules enforced (the script refuses to write the report otherwise):
  - every claim in claims.json has exactly one result
  - status is one of verified / partial / unverified
  - verified and partial need a quote from the source
  - partial and unverified need a note explaining the gap
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

STATUSES = ("verified", "partial", "unverified")
LABEL = {"verified": "✅ Verified", "partial": "⚠️ Partial", "unverified": "❌ Unverified"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("claims")
    ap.add_argument("check")
    ap.add_argument("--title", default="Fact-check report")
    ap.add_argument("--out", default="check.md")
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
    if problems:
        print(json.dumps({"ok": False, "problems": problems}, indent=1))
        sys.exit(2)

    tally = Counter(by_id[c["id"]]["status"] for c in claims["claims"])
    n = len(claims["claims"])
    parts = [f"{tally.get(s, 0)} {s}" for s in STATUSES if tally.get(s, 0)]
    tally_line = f"{n} claim{'s' if n != 1 else ''} checked: " + (", ".join(parts) if parts else "none")

    lines = [f"# {a.title}", "", f"**{tally_line}.**", ""]
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
                      "uncited": len(claims.get("uncited", [])), "out": a.out}))


if __name__ == "__main__":
    main()
