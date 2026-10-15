# claim-checker

A Claude skill that **fact-checks a text against its own links**. Paste or attach anything with citations (an AI-written report, a blog draft, a client deliverable), and Claude opens every cited page and marks each claim:

- **✅ verified**, with the supporting quote from the page
- **⚠️ partial**: the source says something different (number, year, metric, or the claim goes too far)
- **❌ unverified**: the page doesn't say it or can't be opened

It also lists figures that cite no source at all.

Three scripts keep it honest:
- `scripts/extract_claims.py` splits the text into sentences and lists every cited claim, with tracking parameters removed from URLs.
- `scripts/make_report.py` refuses to write the report if a claim is unchecked or a "verified" claim has no quote, and computes the tally itself.
- `scripts/quote_check.py` downloads each cited page so `make_report.py` can confirm every quote is really on it. An invented quote is refused. If a page can't be downloaded (blocked network, paywall, JavaScript-only page, PDF), the report says that quote wasn't machine-checked instead of passing it silently.

In the Claude app, the code sandbox may only reach a few sites, depending on your network settings (**Settings → Capabilities**), so some quotes may show as not machine-checked. In Claude Code the check normally runs for every page.

**Example:** [`examples/sample-draft.md`](examples/sample-draft.md) → [`examples/check.md`](examples/check.md). Three of its six claims misstate their sources: a 25% speed-up that the page gives as 5%, a deprecation dated to the wrong version, and an experimental feature described as the default.
