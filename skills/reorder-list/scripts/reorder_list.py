"""Reorder List: what to reorder today, and how many, from a stock list and a sales history.

Every number is calculated here, so the assistant never does arithmetic itself.

Usage:
  python reorder_list.py --stock FILE --sales FILE --map mapping.json --out-dir DIR
      [--stock-sheet S] [--sales-sheet S] [--stock-header-row N] [--sales-header-row N]
      [--as-of YYYY-MM-DD] [--window 90] [--lead-time 7] [--safety-days 7]
      [--target-days 30] [--date-format dayfirst|monthfirst|iso]
      [--sales-period-days N]   (sales file is a period summary with no dates)

mapping.json:
  {"stock": {"product": "...", "sku": "...", "qty": "...", "price": "...", "warehouse": "..."},
   "sales": {"date": "...", "product": "...", "sku": "...", "qty": "..."}}
Required: stock.qty, sales.qty, a product or sku on both sides, and sales.date
unless --sales-period-days is given.

Writes:
  DIR/reorder_list.csv   every product that is out of stock or below its reorder point
  DIR/summary.json       counts, settings and the most urgent items, rounded for reading
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import TOTAL_ROW, load_table, norm_name, parse_dates, to_number  # noqa: E402


def die(msg: str):
    print(json.dumps({"error": msg}))
    sys.exit(2)


def pick(df, mapping, field):
    col = mapping.get(field)
    if not col:
        return None
    if col not in df.columns:
        die(f"Column '{col}' (for '{field}') not found. Available: {list(df.columns)}")
    return df[col]


def drop_total_rows(df: pd.DataFrame) -> pd.DataFrame:
    keep = ~df.apply(lambda r: any(isinstance(v, str) and TOTAL_ROW.match(v) for v in r.tolist()), axis=1)
    return df[keep]


def r1(x):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), 1)


def compute(stock: pd.DataFrame, sales: pd.DataFrame, ms: dict, mz: dict, *, window=90, lead_time=7,
            safety_days=7, target_days=30, as_of=None, date_format=None, sales_period_days=None):
    """Core calculation, separated from file handling so it can be tested directly.
    Returns (table of all products, info dict)."""
    notes = []
    stock, sales = drop_total_rows(stock), drop_total_rows(sales)

    # ---- stock
    if pick(stock, ms, "qty") is None:
        die("Stock mapping needs 'qty'.")
    sku_s, prod_s = pick(stock, ms, "sku"), pick(stock, ms, "product")
    if sku_s is None and prod_s is None:
        die("Stock mapping needs 'product' or 'sku'.")
    st = pd.DataFrame(index=stock.index)
    st["sku"] = sku_s.astype(str).str.strip() if sku_s is not None else ""
    st["product"] = prod_s.astype(str).str.strip() if prod_s is not None else st["sku"]
    st["qty"] = pick(stock, ms, "qty").map(to_number).fillna(0)
    price = pick(stock, ms, "price")
    st["price"] = price.map(to_number) if price is not None else float("nan")
    wh = pick(stock, ms, "warehouse")
    st["warehouse"] = wh.astype(str).str.strip() if wh is not None else "(all)"
    st = st[(st["product"] != "") | (st["sku"] != "")]
    use_sku = bool(ms.get("sku")) and bool(mz.get("sku"))
    st["key"] = (st["sku"] if use_sku else st["product"]).map(norm_name)
    neg = st[st["qty"] < 0]
    if len(neg):
        notes.append(f"{len(neg)} stock row{'s have' if len(neg) > 1 else ' has'} negative quantity (counted as 0), e.g. {neg['product'].iloc[0]}")

    # ---- sales
    if pick(sales, mz, "qty") is None:
        die("Sales mapping needs 'qty'.")
    sku_z, prod_z = pick(sales, mz, "sku"), pick(sales, mz, "product")
    if sku_z is None and prod_z is None:
        die("Sales mapping needs 'product' or 'sku'.")
    summary_mode = not mz.get("date")
    if summary_mode and not (sales_period_days and as_of):
        die("Sales file has no date column. Pass --sales-period-days N and --as-of YYYY-MM-DD.")
    sa = pd.DataFrame(index=sales.index)
    sa["sku"] = sku_z.astype(str).str.strip() if sku_z is not None else ""
    sa["product"] = prod_z.astype(str).str.strip() if prod_z is not None else sa["sku"]
    if summary_mode:
        sa["date"], date_mode = pd.Timestamp(as_of), f"no dates: totals for {sales_period_days} days"
        window = sales_period_days
    else:
        sa["date"], date_mode = parse_dates(pick(sales, mz, "date"), date_format)
        sa["date"] = sa["date"].dt.normalize()
    sa["qty"] = pick(sales, mz, "qty").map(to_number)
    sa["key"] = (sa["sku"] if use_sku else sa["product"]).map(norm_name)
    bad = int(sa["date"].isna().sum() + sa["qty"].isna().sum())
    if bad:
        notes.append(f"{bad} sales row{'s' if bad > 1 else ''} had an unreadable date or quantity and {'were' if bad > 1 else 'was'} skipped")
    sa = sa.dropna(subset=["date", "qty"])
    sa = sa[sa["key"] != ""]
    if sa.empty:
        die("No readable sales rows. Check the date and quantity columns.")

    as_of_ts = pd.Timestamp(as_of) if as_of else sa["date"].max().normalize()
    sa = sa[sa["date"] <= as_of_ts]
    win_start = as_of_ts - pd.Timedelta(days=window - 1)

    # ---- per product
    prod = st.groupby("key").agg(product=("product", "first"), sku=("sku", "first"),
                                 price=("price", lambda s: s.dropna().iloc[0] if s.notna().any() else float("nan")))
    prod["on_hand"] = st.assign(q=st["qty"].clip(lower=0)).groupby("key")["q"].sum()
    win = sa[sa["date"] >= win_start]
    prod["first_sale"] = sa.groupby("key")["date"].min()
    prod["qty_window"] = win.groupby("key")["qty"].sum()
    prod["qty_window"] = prod["qty_window"].fillna(0)

    unknown = sa.loc[~sa["key"].isin(prod.index) & (sa["date"] >= win_start), "key"].nunique()
    if unknown:
        notes.append(f"{unknown} product{'s' if unknown > 1 else ''} sold in the last {window} days {'are' if unknown > 1 else 'is'} not in the stock list (often a spelling difference between the files)")

    def days_basis(r):
        if summary_mode or pd.isna(r["first_sale"]):
            return window
        return max(7, min(window, (as_of_ts - r["first_sale"]).days + 1))

    prod["days_basis"] = prod.apply(days_basis, axis=1)
    prod["avg_daily"] = prod["qty_window"] / prod["days_basis"]
    prod["days_of_cover"] = prod.apply(lambda r: r["on_hand"] / r["avg_daily"] if r["avg_daily"] > 0 else math.inf, axis=1)
    lead_safety = lead_time + safety_days
    prod["reorder_point"] = (prod["avg_daily"] * lead_safety).map(lambda x: math.ceil(x) if x > 0 else 0)

    def status(r):
        if r["avg_daily"] > 0 and r["on_hand"] <= 0:
            return "Out of stock"
        if r["avg_daily"] > 0 and r["on_hand"] <= r["reorder_point"]:
            return "Reorder now"
        return "OK"

    prod["status"] = prod.apply(status, axis=1)
    prod["suggested_order_qty"] = prod.apply(
        lambda r: max(0, math.ceil(r["avg_daily"] * (lead_safety + target_days) - r["on_hand"]))
        if r["status"] != "OK" else 0, axis=1)
    prod["est_lost_sales_per_day"] = prod.apply(
        lambda r: r["avg_daily"] * (r["price"] if pd.notna(r["price"]) else 0) if r["status"] == "Out of stock" else 0, axis=1)

    info = {"as_of": str(as_of_ts.date()), "window_days": window, "window_start": str(win_start.date()),
            "lead_time_days": lead_time, "safety_days": safety_days, "target_cover_days": target_days,
            "matched_on": "SKU" if use_sku else "product name", "date_reading": date_mode, "notes": notes}
    return prod, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--sales", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--stock-sheet")
    ap.add_argument("--sales-sheet")
    ap.add_argument("--stock-header-row", type=int)
    ap.add_argument("--sales-header-row", type=int)
    ap.add_argument("--as-of")
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--lead-time", type=int, default=7)
    ap.add_argument("--safety-days", type=int, default=7)
    ap.add_argument("--target-days", type=int, default=30)
    ap.add_argument("--date-format", choices=["dayfirst", "monthfirst", "iso"])
    ap.add_argument("--sales-period-days", type=int)
    a = ap.parse_args()

    mapping = json.loads(Path(a.map).read_text())
    stock, _ = load_table(a.stock, a.stock_sheet, a.stock_header_row)
    sales, _ = load_table(a.sales, a.sales_sheet, a.sales_header_row)
    prod, info = compute(stock, sales, mapping.get("stock", {}), mapping.get("sales", {}),
                         window=a.window, lead_time=a.lead_time, safety_days=a.safety_days,
                         target_days=a.target_days, as_of=a.as_of, date_format=a.date_format,
                         sales_period_days=a.sales_period_days)

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    act = prod[prod["status"] != "OK"].copy()
    act["_o"] = act["status"].map({"Out of stock": 0, "Reorder now": 1})
    act["_v"] = act["avg_daily"] * act["price"].fillna(0)
    act = act.sort_values(["_o", "days_of_cover", "_v"], ascending=[True, True, False])
    cols = ["product", "sku", "status", "on_hand", "avg_daily", "days_of_cover", "reorder_point",
            "suggested_order_qty", "est_lost_sales_per_day"]
    csv = act[cols].rename(columns={
        "product": "Product", "sku": "SKU", "status": "Status", "on_hand": "On hand",
        "avg_daily": "Avg daily sales", "days_of_cover": "Days of stock left", "reorder_point": "Reorder point",
        "suggested_order_qty": "Suggested order qty", "est_lost_sales_per_day": "Est. lost sales per day"})
    csv["Avg daily sales"] = csv["Avg daily sales"].round(2)
    csv["Days of stock left"] = csv["Days of stock left"].round(1)
    csv["Est. lost sales per day"] = [round(v) if st == "Out of stock" else None
                                      for v, st in zip(csv["Est. lost sales per day"], csv["Status"])]
    csv["Est. lost sales per day"] = csv["Est. lost sales per day"].astype("Int64")
    csv["On hand"] = csv["On hand"].map(lambda v: int(v) if float(v).is_integer() else round(v, 2))
    if not csv["SKU"].astype(str).str.strip().any():
        csv = csv.drop(columns="SKU")
    csv.to_csv(out / "reorder_list.csv", index=False)

    def item(r):
        return {"product": r["product"], "status": r["status"], "on_hand": int(r["on_hand"]),
                "avg_daily": r1(r["avg_daily"]), "days_of_cover": r1(r["days_of_cover"]),
                "suggested_order_qty": int(r["suggested_order_qty"]),
                "est_lost_sales_per_day": int(round(r["est_lost_sales_per_day"]))}

    oos, rn = act[act["status"] == "Out of stock"], act[act["status"] == "Reorder now"]
    summary = {
        "settings": info,
        "products": int(len(prod)),
        "out_of_stock_count": int(len(oos)),
        "reorder_now_count": int(len(rn)),
        "est_lost_sales_per_day_total": int(round(oos["est_lost_sales_per_day"].sum())),
        "note": "items: up to 8 most urgent out-of-stock (largest lost sales per day first), then up to 8 reorder-now (fewest days left first)",
        "items": [item(r) for _, r in pd.concat([oos.head(8), rn.head(8)]).iterrows()],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({"ok": True, "csv": str(out / "reorder_list.csv"), "summary": str(out / "summary.json"),
                      "out_of_stock": summary["out_of_stock_count"], "reorder_now": summary["reorder_now_count"],
                      "date_reading": info["date_reading"]}))


if __name__ == "__main__":
    main()
