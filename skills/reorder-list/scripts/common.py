"""Shared helpers: loading messy exports, finding the header row, cleaning numbers,
names and dates, and guessing which column means what."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# Canonical fields and the column names that usually mean them (lower-case, compared
# after removing punctuation). Order matters: earlier synonyms win.
SYNONYMS = {
    "stock": {
        "sku": ["sku", "item code", "product code", "code", "barcode", "part no", "part number", "item id", "product id", "article no"],
        "product": ["product name", "item name", "product", "item", "particulars", "description", "name of item", "stock item", "title", "product title"],
        "qty": ["qty on hand", "quantity on hand", "closing qty", "closing quantity", "closing stock", "on hand", "available", "stock qty", "current stock", "in stock", "inventory", "quantity", "qty", "stock", "balance"],
        "unit_cost": ["unit cost", "cost price", "purchase price", "cost", "rate", "avg cost", "average cost", "landed cost", "buying price", "pp"],
        "price": ["selling price", "sale price", "sp", "mrp", "price", "retail price", "unit price", "list price"],
        "stock_value": ["stock value", "closing value", "value", "inventory value", "amount"],
        "warehouse": ["warehouse", "godown", "location", "store", "branch", "outlet", "site"],
        "category": ["category", "stock group", "group", "department", "product type", "type", "brand"],
    },
    "sales": {
        "date": ["date", "invoice date", "bill date", "voucher date", "order date", "sale date", "transaction date", "created at", "day"],
        "sku": ["sku", "item code", "product code", "code", "barcode", "part no", "item id", "product id", "lineitem sku"],
        "product": ["product name", "item name", "particulars", "product", "item", "description", "stock item", "lineitem name", "title"],
        "qty": ["qty", "quantity", "qty sold", "units sold", "units", "sold qty", "billed qty", "lineitem quantity", "net quantity"],
        "amount": ["amount", "net amount", "sales amount", "total", "line total", "revenue", "value", "taxable value", "net sales", "gross sales", "lineitem total"],
        "unit_price": ["rate", "unit price", "price", "selling price", "sp", "lineitem price"],
        "warehouse": ["warehouse", "godown", "location", "store", "branch", "outlet"],
    },
}

TOTAL_ROW = re.compile(r"^\s*(grand\s+)?(sub\s*)?total\b", re.I)


def norm_header(h) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(h).lower()).strip().replace("  ", " ")


def norm_name(s) -> str:
    """Normalise a product name or SKU for matching: case, spaces, punctuation-light."""
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def read_raw(path: str | Path, sheet: str | int | None = None) -> pd.DataFrame:
    """Read a CSV or Excel file with no header, everything as text."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".csv", ".txt", ".tsv"):
        sep = "\t" if ext == ".tsv" else None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return pd.read_csv(p, header=None, dtype=str, sep=sep, engine="python", encoding=enc, keep_default_na=False)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Could not decode {p}")
    if ext in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(p, header=None, dtype=str, sheet_name=sheet if sheet is not None else 0, keep_default_na=False)
    raise ValueError(f"Unsupported file type: {ext} (use CSV or Excel)")


def find_header_row(raw: pd.DataFrame, max_scan: int = 30) -> int:
    """The header row is the first row (within max_scan) that has the most text cells
    matching known column names, with real data below it."""
    known = {norm_header(s) for role in SYNONYMS.values() for syns in role.values() for s in syns}
    best_row, best_score = 0, -1
    for i in range(min(max_scan, len(raw))):
        cells = [norm_header(c) for c in raw.iloc[i].tolist() if str(c).strip() != ""]
        if len(cells) < 2:
            continue
        score = sum(1 for c in cells if c in known) * 3 + len(cells)
        if score > best_score:
            best_row, best_score = i, score
    return best_row


def load_table(path, sheet=None, header_row: int | None = None) -> tuple[pd.DataFrame, int]:
    raw = read_raw(path, sheet)
    h = find_header_row(raw) if header_row is None else header_row
    cols = []
    seen = {}
    for c in raw.iloc[h].tolist():
        c = str(c).strip() or "unnamed"
        seen[c] = seen.get(c, 0) + 1
        cols.append(c if seen[c] == 1 else f"{c}.{seen[c]-1}")
    df = raw.iloc[h + 1:].copy()
    df.columns = cols
    df = df.reset_index(drop=True)
    # drop fully empty rows
    df = df[~(df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1))]
    return df, h


def guess_mapping(columns: list[str], role: str) -> dict[str, str]:
    """Best guess of canonical field -> column name for a 'stock' or 'sales' table."""
    # also split CamelCase / joined names: "StockCode" -> "stock code", "Invoice_Date" -> "invoice date"
    normed = {c: norm_header(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(c))) for c in columns}
    squashed = {c: n.replace(" ", "") for c, n in normed.items()}
    used = set()
    out = {}
    for field, syns in SYNONYMS[role].items():
        for s in syns:
            hit = next((c for c, n in normed.items() if n == s and c not in used), None)
            if hit is None:
                hit = next((c for c, n in squashed.items() if n == s.replace(" ", "") and c not in used), None)
            if hit is None:
                hit = next((c for c, n in normed.items() if c not in used and re.search(rf"\b{re.escape(s)}\b", n)), None)
            if hit is not None:
                out[field] = hit
                used.add(hit)
                break
    return out


NUM_JUNK = re.compile(r"[^\d.\-()]")


def to_number(v):
    """'1,234.50' -> 1234.5 ; '12 Pcs' -> 12 ; '(45)' -> -45 ; '₹ 99' -> 99 ; '' -> NaN"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return float("nan")
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "-", "na", "n/a"):
        return float("nan")
    neg = s.startswith("(") and s.endswith(")")
    s = s.replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", NUM_JUNK.sub(" ", s))
    if not m:
        return float("nan")
    x = float(m.group(0))
    return -abs(x) if neg else x


def parse_dates(series: pd.Series, date_format: str | None) -> tuple[pd.Series, str]:
    """date_format: 'dayfirst', 'monthfirst', 'iso', or None to auto-detect."""
    s = series.astype(str).str.strip()
    def attempt(dayfirst):
        return pd.to_datetime(s, dayfirst=dayfirst, errors="coerce", format="mixed")
    looks_iso = s.str.match(r"^\d{4}-\d{1,2}-\d{1,2}").mean() > 0.9 if len(s) else False
    if date_format == "iso" or (date_format is None and looks_iso):
        return pd.to_datetime(s, errors="coerce", format="mixed"), "iso (YYYY-MM-DD)"
    if date_format == "dayfirst":
        return attempt(True), "dayfirst"
    if date_format == "monthfirst":
        return attempt(False), "monthfirst"
    # Decide from the numbers themselves: a first part above 12 can only be a day
    # (day-first), a second part above 12 can only be a day (month-first).
    # (pandas silently swaps impossible dates, so failure counts alone can't tell.)
    parts = s.str.extract(r"^(\d{1,2})[/\-. ](\d{1,2})[/\-. ]\d{2,4}")
    if parts.notna().all(axis=1).mean() > 0.9:
        a = pd.to_numeric(parts[0], errors="coerce")
        b = pd.to_numeric(parts[1], errors="coerce")
        first_big, second_big = (a > 12).sum(), (b > 12).sum()
        if first_big and not second_big:
            return attempt(True), "dayfirst (auto)"
        if second_big and not first_big:
            return attempt(False), "monthfirst (auto)"
    d1, d2 = attempt(True), attempt(False)
    # still unclear: prefer the reading with fewer failures, then fewer future dates
    today = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    k1 = (d1.isna().sum(), (d1 > today).sum())
    k2 = (d2.isna().sum(), (d2 > today).sum())
    if k1 <= k2:
        return d1, "dayfirst (auto)"
    return d2, "monthfirst (auto)"
