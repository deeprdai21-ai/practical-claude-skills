# claim-checker

A Claude skill that **fact-checks a text against its own links**. Paste or attach anything with citations (an AI-written report, a blog draft, a client deliverable), and Claude opens every cited page and marks each claim:

- **✅ verified**, with the supporting quote from the page
- **⚠️ partial**: the source says something different (number, year, metric, or the claim goes too far)
- **❌ unverified**: the page doesn't say it or can't be opened

It also lists figures that cite no source at all.

Four scripts keep it honest:
- `scripts/extract_claims.py` splits the text into sentences and lists every cited claim, with tracking parameters removed from URLs.
- `scripts/make_report.py` refuses to write the report if a claim is unchecked or a "verified" claim has no quote, and computes the tally itself.
- `scripts/numbers_check.py` checks that every figure and period label (FY27, Q2, H1) in a "verified" claim also appears in its quote, so a real quote that states a different number ("25%" claimed, "5%" quoted) or a different period ("FY27" claimed, "FY26" quoted) can't pass. The quote may spell a period out ("fiscal 2027", "second quarter").
- Every "verified" claim also needs the checker's **match check**: three yes/no answers to "is the quote about the same period, the same measure (revenue vs profit) and the same subject (company, group of people)?" Any "no" makes the claim partial, and the report shows the answers. These are Claude's judgement, not code, and the report says so; narrow yes/no questions are simply much harder to get wrong than one open "does this support it?".
- `scripts/quote_check.py` downloads each cited page, including PDFs, so `make_report.py` can confirm every quote is really on it. An invented quote is refused. If a page can't be downloaded (blocked network, paywall, JavaScript-only page), or a quote can't be matched in a PDF's extracted text, the report says that quote wasn't machine-checked instead of passing it silently.

In the Claude app, code can only reach the websites your settings allow. With the default setting ("Package managers only"), the report says plainly that the quote check is off. To turn it on, allow code to access the web in **Settings → Capabilities** (network egress / domain allowlist), then start a new chat. In a test of the same quote check inside my Verified Market Brief skill, with web access on, all 27 of 27 quotes were found on their pages. In Claude Code the check normally runs for every page.

**Example:** [`examples/sample-draft.md`](examples/sample-draft.md) → [`examples/check.md`](examples/check.md). Three of its six claims misstate their sources: a 25% speed-up that the page gives as 5%, a deprecation dated to the wrong version, and an experimental feature described as the default.

---

**Want the full workflow?** [Verified Market Brief](https://deepakrodeai.gumroad.com/l/verified-market-brief) is the paid version: it researches a market or competitor question, writes a sourced ~550-word brief, then runs this fact-check on it. Its report opens with what the first draft got wrong.
