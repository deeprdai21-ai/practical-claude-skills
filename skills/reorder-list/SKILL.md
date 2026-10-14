---
name: reorder-list
description: Works out what a shop, distributor or online seller should reorder today and how many, from a stock export and a sales history (Excel or CSV from Tally, Vyapar, Zoho, Shopify, any POS or a hand-made sheet). Every number is calculated by a bundled script, not estimated. Use whenever the user shares stock and sales files and asks what to reorder, what is out of stock, what is running low, reorder points, days of stock left, or purchase quantities.
---

# Reorder List

Turn two exports, a **stock list** and a **sales history**, into a reorder list: what is out of stock but still selling, what will run out before new stock can arrive, and a suggested order quantity for each.

**The rule that matters: every number comes from the script.** People place real orders from this list, and language models are unreliable at arithmetic over long tables. Never calculate, estimate or round figures yourself. Copy them from `summary.json` or `reorder_list.csv`. If a number you need isn't there, re-run the script with different settings or say you don't have it.

## What you need

1. **Stock file:** quantity on hand per product, plus per warehouse if there are several. A selling price is optional; it lets the script estimate sales lost per day on out-of-stock items.
2. **Sales file:** either one row per item sold, with a date (best), or total units sold per product over a known period (say how many days and the end date).

If either file is missing, ask for it in one sentence. In Tally these are *Stock Summary* (press Alt+F5 for item detail) and *Sales Register* exported with *Export for Pivot table: Yes*. In most other tools, look for "closing stock" and "item-wise sales".

## Step 1: Inspect both files

```bash
python scripts/inspect_columns.py "<stock file>" --role stock
python scripts/inspect_columns.py "<sales file>" --role sales
```

The script finds the header row (exports often have company-name lines above it), lists the columns with sample rows, and guesses which column means what. Check the guess against the samples:
- Use the **closing / on-hand** quantity, not opening, inward or outward quantities.
- If both files have an item code or SKU, use it on both sides; otherwise use the product name on both sides.
- If the data isn't on the first sheet, pass `--sheet`. If the header row is wrong, pass `--header-row N` (0-based).

Ask the user only if something is genuinely ambiguous.

## Step 2: Write mapping.json

```json
{"stock": {"product": "Item Name", "sku": "", "qty": "Closing Qty", "price": "MRP", "warehouse": "Godown"},
 "sales": {"date": "Voucher Date", "product": "Particulars", "sku": "", "qty": "Quantity"}}
```

Use exact column names and leave out fields the file doesn't have.

## Step 3: Run

```bash
python scripts/reorder_list.py --stock "<stock file>" --sales "<sales file>" \
  --map mapping.json --out-dir <folder> [settings]
```

| Setting | Default | Meaning |
|--|--|--|
| `--lead-time` | 7 | Days between ordering and receiving stock. Use the user's real figure if they mention one. |
| `--safety-days` | 7 | Buffer stock, in days of sales |
| `--target-days` | 30 | Extra days of stock to order beyond lead time + safety. Raise it for an upcoming festival or busy season, and say so. |
| `--window` | 90 | Days of sales used for the average |
| `--as-of` | last sale date | Analysis date |
| `--date-format` | auto | `dayfirst` (31-12-2026), `monthfirst` (12-31-2026) or `iso` |
| `--sales-period-days` | — | For a sales file of totals with no dates; also pass `--as-of` |

Check `date_reading` in the output. If dates were read the wrong way round, re-run with `--date-format`. If `notes` in `summary.json` says many sold products are missing from the stock list, the two files name products differently: fix the mapping before going on.

## Step 4: Reply

Write a short answer for a busy owner, using only figures from `summary.json`:

1. One line: how many products are out of stock and how many need reordering, plus the date the data runs to. If that date is more than about a week ago, say the list should be checked against today's stock.
2. **Out of stock:** the total `est_lost_sales_per_day_total` (when prices were given), then the first few out-of-stock items, which are already sorted by lost sales. Give each item's suggested order quantity.
3. **Reorder now:** the first few reorder-now items, sorted by fewest days left, with their order quantities.
4. Attach or point to `reorder_list.csv` for the full list.
5. One line on the settings used (lead time, safety days, matched by code or name).

Describe items in the order the script sorted them: "losing the most sales" or "closest to running out", never "biggest". Report out-of-stock and reorder-now counts separately. Don't add up or count items yourself.

## How the numbers are calculated

| Measure | Calculation |
|--|--|
| Average daily sales | Units sold in the window ÷ days. Days = the window, or the days since the first sale if the product is newer (minimum 7). |
| Days of stock left | On hand ÷ average daily sales |
| Reorder point | Average daily sales × (lead time + safety days), rounded up |
| Status | **Out of stock:** selling, and on hand ≤ 0. **Reorder now:** selling, and on hand ≤ reorder point. |
| Suggested order | Average daily sales × (lead time + safety + target days) − on hand, rounded up |
| Lost sales per day | For out-of-stock items: average daily sales × selling price |

Negative stock counts as 0. Rows starting with "Total" or "Grand Total" are ignored. Quantities like "12 Pcs" and amounts like "1,23,456.00" are read correctly.

## Limits (mention briefly when relevant)

- Order quantities are a starting point: the script doesn't know pack sizes, minimum order quantities or supplier schemes.
- Averages assume the recent past repeats. Festival or seasonal demand isn't in the data, so raise quantities for items the owner knows will jump.
- This skill covers reordering only. It doesn't analyse dead stock, overstock, margins or best sellers.
