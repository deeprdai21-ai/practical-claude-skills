---
name: claim-checker
description: Fact-checks a piece of writing against its own cited sources. Opens every linked page and marks each claim verified, partial or unverified, with the supporting quote as evidence, then writes a report with an exact tally. Use whenever the user asks to fact-check, verify sources or check citations, asks "is this accurate?" or "do these links back it up?", or shares an AI-written report, blog draft, research summary or client deliverable that contains links.
---

# Claim Checker

Check whether a text's sources actually say what the text claims. The most common failure in AI-written and hurried human writing isn't a missing link; it's a confident sentence whose linked source says something different: the wrong number, the wrong year, the wrong metric, or a claim stretched further than the source goes.

You are a sceptical editor who did not write this text. Your job is to find claims the sources don't support, and to show your evidence.

## Network access

This skill needs network access for one purpose: to open the pages the user's text cites.
- Claude opens each cited link with its web-fetch tool.
- `scripts/quote_check.py` downloads those same cited URLs (plain HTTP GET, no cookies or credentials) to confirm each quote is on its page.
- No other endpoints are contacted, and nothing from the user's text or files is sent anywhere. The URLs that appear inside this skill's files (for example python.org in the examples) are documentation and sample data only.

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

- **verified:** the page supports the claim. A close paraphrase in the text counts. Copy the supporting sentence from the page, word for word, as the quote, and complete the match check below.
- **partial:** the page supports part of it, but something differs: a number, date, period, metric name or unit, or the claim goes further than the page ("the largest" when the page says "one of the largest"). Quote the page and explain the gap in the note.
- **unverified:** the page doesn't say it, couldn't be opened, or is paywalled. Explain which in the note.

Watch especially for:
- **Numbers attached to the wrong thing:** the right figure for the wrong quarter, region or metric (revenue vs profit, GMV vs revenue, adjusted vs reported).
- **Second-hand sources:** if the page only repeats someone else's figure, note the original organisation so the user can cite it directly.
- **Out-of-date claims:** if the page is older and the claim is about "today", say so in the note.

**Match check (every verified claim).** A real quote with the right number can still be about something else. Before marking a claim verified, answer three narrow questions, comparing the claim with the quote only:
- **period:** is the quote about the same year, quarter or date range as the claim? ("25% in FY27" vs a quote about FY26 → no)
- **measure:** is it the same metric? (revenue vs profit, GMV vs revenue, share of sales vs share of units, adjusted vs reported → no)
- **subject:** is it the same company, product, place or group of people? (adults vs teenagers, India vs global, one brand vs the whole market → no)

Answer each `yes`, `no` or `n/a`: use `n/a` when the claim has no period, number or measure to compare (a description or an opinion), not `yes`. A claim about the present ("still", "now", "today") backed by an older page is a period `no` unless a newer source confirms it. Any `no` means the claim is **partial**, not verified: say in the note what the source actually covers. Answer honestly; the report shows these answers next to each claim as your judgement.

**Quotes are checked.** The report script downloads each source page itself and refuses any quote it can't find there, so copy quotes exactly, word for word, from the page. Spacing, quote marks and dashes don't matter, but every word and number must. To quote two separate parts of a page, put `…` between them. Quote at least a full phrase; very short quotes like "5%" are refused.

**Figures are checked too.** For a `verified` claim, every figure in the linked phrase (amounts, percentages, years, versions) and every period label (FY27, Q2, H1) must also appear in your quote, because a real quote that states a different number doesn't support the claim. The script compares numbers (ignoring commas, so 1,29,940 = 129,940, and rounding the quote to the claim's precision) and period labels (the quote may spell them out: "fiscal 2027" or "2026-27" counts as FY27, "second quarter" as Q2), and refuses a verified claim whose figures or periods aren't in its quote. When that happens:
- quote the part of the page that states the figure (join separate parts with `…`), or
- mark the claim `partial` and say what the source actually says, or
- only if the figure genuinely doesn't need to be in the quote (for example, it names the subject, like the version on that version's own release page), explain why in `"numbers_note"`. The report shows the explanation next to the claim, so never use it to wave a mismatch through.

If a figure is the text's own calculation (marked "(calculated)", or you add `"calculated": true`), it isn't checked this way; check the arithmetic yourself and say so in the note.

When a claim has several links, check the one that carries the fact. When a page is long, search it for the key number or name rather than skimming.

Write the results to `check.json`:

```json
[{"id": 1, "status": "verified", "url": "https://…", "quote": "exact text from the page", "note": "",
  "match": {"period": "yes", "measure": "yes", "subject": "yes"}},
 {"id": 3, "status": "verified", "url": "https://…", "quote": "Release date: Oct. 2, 2023", "numbers_note": "3.12 names the release; this is its own release page.",
  "match": {"period": "yes", "measure": "n/a", "subject": "yes"}},
 {"id": 2, "status": "partial", "url": "https://…", "quote": "…", "note": "Source says 2022, the text says 2023."}]
```

## Step 4: Build the report

```bash
python scripts/make_report.py claims.json check.json --title "Fact-check: <title of the text>" --out check.md
```

The script refuses to write the report if any claim is unchecked, if a status is missing its quote or note, if a verified claim's figures or periods aren't in its quote, if a verified claim is missing its match check or has a "no" in it, or if a quote isn't on its source page. Fix what it lists and run it again:

- **"figures aren't in its quote":** see "Figures are checked too" above. Don't change the claim's numbers to match the quote unless the text really says that; if the source says something different, the claim is partial.
- **"needs the match check" / "about a different …":** answer the three questions; if any is "no", the claim is partial. Never change an answer to "yes" just to get past the check.
- **"the quote was not found":** open the page again and copy the exact text. If you can't find text on the page that supports the claim, change it to unverified. Never reword a quote to get past the check.

PDF sources are read too, when the pypdf library is available (it usually is in Claude's code environment). If the script can't download a page (blocked network, paywall, a page that needs JavaScript), or can't match a quote in a PDF's extracted text, it doesn't fail: the report marks that quote "not machine-checked" with the reason. Don't use `--offline`; it's only for tests.

The tally line ("12 claims checked: 10 verified, 1 partial, 1 unverified") comes from the script. Don't count claims yourself.

## Step 5: Reply

1. The tally line from the script, the line saying how many quotes were found on the downloaded pages, the line about figures in verified claims, and the line about the match check (mention any the checker explained instead of quoting). If some couldn't be machine-checked, say so plainly. If the script reports `quote_check_off_in_sandbox: true`, say in one sentence that the code couldn't reach the source websites, so the quotes were checked by you but not double-checked by the script, and that allowing code to access the web in the Claude app's settings turns that check on.
2. The problems first: each partial or unverified claim in one or two lines, saying what the text says and what the source actually says.
3. If the user wants it, a suggested correction for each problem, worded so the source supports it. Don't change verified sentences.
4. Deliver `check.md` as a file, or paste it if you can't write files.
5. Mention any figures in the "uncited" list, briefly.

Never mark a claim verified without having opened its source in this session, and never invent a quote. If a page can't be opened, the claim is unverified. Say so plainly.
