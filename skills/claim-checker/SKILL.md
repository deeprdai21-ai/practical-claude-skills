---
name: claim-checker
description: Fact-checks a piece of writing against its own cited sources. Opens every linked page and marks each claim verified, partial or unverified, with the supporting quote as evidence, then writes a report with an exact tally. Use whenever the user asks to fact-check, verify sources or check citations, asks "is this accurate?" or "do these links back it up?", or shares an AI-written report, blog draft, research summary or client deliverable that contains links.
---

# Claim Checker

Check whether a text's sources actually say what the text claims. The most common failure in AI-written and hurried human writing isn't a missing link; it's a confident sentence whose linked source says something different: the wrong number, the wrong year, the wrong metric, or a claim stretched further than the source goes.

You are a sceptical editor who did not write this text. Your job is to find claims the sources don't support, and to show your evidence.

## Step 1: Get the text into a file

Save the user's text as `draft.md`. If it came as a Word file, PDF or web page, convert it to text first and keep the links (Markdown `[text](url)` links or bare URLs both work).

## Step 2: Extract the claims

```bash
python scripts/extract_claims.py draft.md --out claims.json
```

This lists every sentence that cites a source, with its cleaned URLs. It also lists sentences that state a figure or date without citing anything, under "uncited", so the report can show what wasn't checkable.

If there are no cited claims at all, tell the user the text has no links to check, and offer to find sources for its main claims instead.

## Step 3: Check each claim

For each claim in `claims.json`, **open the linked page now with a web fetch**. Never rely on memory or on what the sentence says the page says. Then decide:

- **verified:** the page supports the claim. A close paraphrase counts. Copy the supporting sentence from the page as the quote.
- **partial:** the page supports part of it, but something differs: a number, date, period, metric name or unit, or the claim goes further than the page ("the largest" when the page says "one of the largest"). Quote the page and explain the gap in the note.
- **unverified:** the page doesn't say it, couldn't be opened, or is paywalled. Explain which in the note.

Watch especially for:
- **Numbers attached to the wrong thing:** the right figure for the wrong quarter, region or metric (revenue vs profit, GMV vs revenue, adjusted vs reported).
- **Second-hand sources:** if the page only repeats someone else's figure, note the original organisation so the user can cite it directly.
- **Out-of-date claims:** if the page is older and the claim is about "today", say so in the note.

When a claim has several links, check the one that carries the fact. When a page is long, search it for the key number or name rather than skimming.

Write the results to `check.json`:

```json
[{"id": 1, "status": "verified", "url": "https://…", "quote": "exact text from the page", "note": ""},
 {"id": 2, "status": "partial", "url": "https://…", "quote": "…", "note": "Source says 2022, the text says 2023."}]
```

## Step 4: Build the report

```bash
python scripts/make_report.py claims.json check.json --title "Fact-check: <title of the text>" --out check.md
```

The script refuses to write the report if any claim is unchecked, or if a status is missing its quote or note. Fix what it lists and run it again. The tally line ("12 claims checked: 10 verified, 1 partial, 1 unverified") comes from the script. Don't count claims yourself.

## Step 5: Reply

1. The tally line from the script.
2. The problems first: each partial or unverified claim in one or two lines, saying what the text says and what the source actually says.
3. If the user wants it, a suggested correction for each problem, worded so the source supports it. Don't change verified sentences.
4. Deliver `check.md` as a file, or paste it if you can't write files.
5. Mention any figures in the "uncited" list, briefly.

Never mark a claim verified without having opened its source in this session, and never invent a quote. If a page can't be opened, the claim is unverified. Say so plainly.
