# Practical Claude Skills

[![tests](https://github.com/deeprdai21-ai/practical-claude-skills/actions/workflows/tests.yml/badge.svg)](https://github.com/deeprdai21-ai/practical-claude-skills/actions/workflows/tests.yml)

Two free, open-source [Claude skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) for everyday business work. Both follow one rule: **the numbers come from a script, not from the model's head.** Language models are fluent but unreliable at arithmetic and at remembering what a source said, so the scripts do the counting and Claude does the reading and explaining.

| Skill | What it does |
|--|--|
| [**reorder-list**](skills/reorder-list) | Reads a stock export and a sales history (Tally, Vyapar, Zoho, Shopify or any Excel/CSV) and tells you what is out of stock, what will run out before new stock arrives, and how many to order. |
| [**claim-checker**](skills/claim-checker) | Fact-checks any text against its own links. It opens every cited page and marks each claim verified, partial or unverified, quoting the source as evidence. |

## Examples

**reorder-list** on a sample distributor's Tally exports ([files](skills/reorder-list/examples)):

| Product | Status | On hand | Days left | Order qty | Lost sales/day |
|--|--|--|--|--|--|
| Tata Tea Gold 500g | Out of stock | 0 | 0.0 | 504 | 3,422 |
| Lays Classic 52g | Out of stock | 0 | 0.0 | 337 | 153 |
| Parle-G 800g | Reorder now | 28 | 3.1 | 370 | |
| Maggi Noodles 12pk | Reorder now | 34 | 3.9 | 354 | |

**claim-checker** on a short text about Python releases ([text](skills/claim-checker/examples/sample-draft.md), [report](skills/claim-checker/examples/check.md)):

> **6 claims checked: 3 verified, 3 partial.**
> - "Python 3.12 runs about 25% faster than 3.11": the cited release page says *"an estimated 5% overall performance improvement"*.
> - "distutils… deprecated since Python 3.8": PEP 632 says it was deprecated in 3.10.
> - "Python 3.13 runs without the GIL by default": the docs say it's *"experimental… not enabled by default"*.

## Install

**Claude app (claude.ai or desktop):** download the skill's zip from [Releases](../../releases), then go to **Settings → Capabilities**, turn on **Code execution and file creation**, and under **Skills** choose **Upload skill**. Claude Pro, Max, Team or Enterprise is needed for skills.

**Claude Code:** copy the skill folder into `~/.claude/skills/`, for example:

```bash
git clone https://github.com/deeprdai21-ai/practical-claude-skills
cp -r practical-claude-skills/skills/reorder-list ~/.claude/skills/
```

Then just ask, for example *"What should I reorder? Here are my stock and sales exports"* or *"Fact-check this report against its links"*.

**Requirements:** Python 3.10+ with `pandas` and `openpyxl` (for reorder-list). Claude's code environment usually has these already. claim-checker needs web access to open the cited pages.

## Tests

```bash
pip install pandas openpyxl pytest
python -m pytest tests
```

The reorder calculations are checked against hand-worked examples. The claim-checker scripts are tested for link extraction, tracking-parameter cleanup, the report's refusal to accept a "verified" claim without a quote, its refusal of a fabricated but plausible quote that isn't on the source page, and its refusal of a real quote whose number doesn't match the claim ("25%" claimed, "5%" quoted).

## How they work

Each skill is a `SKILL.md` (instructions Claude follows) plus small Python scripts:

- **reorder-list:** `inspect_columns.py` finds the header row in messy exports and guesses the columns. `reorder_list.py` calculates average daily sales, days of stock left, reorder points and order quantities, and writes `reorder_list.csv` plus a `summary.json` that Claude reports from. The formulas are in the [SKILL.md](skills/reorder-list/SKILL.md#how-the-numbers-are-calculated).
- **claim-checker:** `extract_claims.py` splits the text into sentences and lists every cited claim, plus figures that cite nothing. Claude opens each source and records a status and quote. `make_report.py` downloads each cited page, refuses any quote that isn't actually on it, refuses a "verified" claim whose figures aren't in its quote, validates the results and writes the report with an exact tally.

## Licence

MIT. See [LICENSE](LICENSE). Issues and pull requests are welcome.

---

Made by **Deepak Rode**, who builds AI agents and agent workflows with Claude.
Fuller paid versions exist: [Inventory Health Check](https://deepakrodeai.gumroad.com/l/inventory-health-check) (adds dead stock, overstock, best sellers, margins and a 10-sheet Excel report) and [Verified Market Brief](https://deepakrodeai.gumroad.com/l/verified-market-brief) (researches and writes the brief, then fact-checks it).
