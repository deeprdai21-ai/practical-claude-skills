"""Look inside a stock or sales export before analysis.

Prints the detected header row, the column names, a few sample rows and a guessed
mapping of columns to the fields the analysis needs. Claude uses this to write
mapping.json (and to ask the user only when a guess is genuinely unclear).

Usage:
  python inspect_columns.py FILE --role stock|sales [--sheet NAME] [--header-row N]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import guess_mapping, load_table, read_raw  # noqa: E402

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--role", choices=["stock", "sales"], required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--header-row", type=int, default=None, help="0-based row index of the header, if auto-detect is wrong")
    a = ap.parse_args()

    p = Path(a.file)
    if p.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        sheets = pd.ExcelFile(p).sheet_names
    else:
        sheets = None
    df, h = load_table(p, a.sheet, a.header_row)
    guess = guess_mapping(list(df.columns), a.role)
    out = {
        "file": str(p),
        "sheets": sheets,
        "header_row_0_based": h,
        "rows_below_header": int(len(df)),
        "columns": list(df.columns),
        "sample_rows": df.head(4).to_dict(orient="records"),
        "last_rows": df.tail(2).to_dict(orient="records"),
        "guessed_mapping": guess,
        "missing_required": [f for f in (["product", "qty"] if a.role == "stock" else ["date", "qty"]) if f not in guess]
        + ([] if ("product" in guess or "sku" in guess) else ["product or sku"]),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
