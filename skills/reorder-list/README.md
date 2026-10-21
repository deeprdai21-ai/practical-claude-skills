# reorder-list

A Claude skill that tells a shop, distributor or online seller **what to reorder today and how many**, from two exports: a stock list and a sales history.

- Reads messy real-world exports: company-name rows above the header, "12 Pcs", "1,23,456.00", "Grand Total" rows, day-first or month-first dates, several godowns or warehouses.
- Works with dated sales (best) or sales totals for a period.
- Out-of-stock items are sorted by sales lost per day; the rest by fewest days of stock left.
- Every figure is calculated by `scripts/reorder_list.py`. Claude only reports it.

**Try it:** attach `examples/Stock Summary.xlsx` and `examples/Sales Register.xlsx` to a chat and ask "What should I reorder?". Expected output: [`examples/output/reorder_list.csv`](examples/output/reorder_list.csv).

**Run the script yourself:**

```bash
python scripts/reorder_list.py --stock "examples/Stock Summary.xlsx" --sales "examples/Sales Register.xlsx" \
  --map examples/mapping.json --out-dir out --lead-time 7
```

The formulas and settings are in [SKILL.md](SKILL.md). The example data is made up.

---

**Want the full report?** [Inventory Health Check](https://deepakrodeai.gumroad.com/l/inventory-health-check) is the paid version: it adds dead stock, overstock, best sellers, margins and a 10-sheet Excel report to the reorder list.
