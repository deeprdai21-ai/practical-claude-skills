"""Hand-calculated checks for skills/reorder-list. Run: python -m pytest tests"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "reorder-list" / "scripts"))
from common import to_number  # noqa: E402
from reorder_list import compute  # noqa: E402

AS_OF = pd.Timestamp("2026-09-30")
MS = {"product": "Item", "qty": "Qty", "price": "MRP"}
MZ = {"date": "Date", "product": "Item", "qty": "Qty"}


def daily_sales(item, per_day, days, end=AS_OF):
    return [{"Date": (end - pd.Timedelta(days=i)).strftime("%d-%m-%Y"), "Item": item, "Qty": str(per_day)}
            for i in range(days)]


@pytest.fixture
def result():
    stock = pd.DataFrame([
        {"Item": "Tea", "Qty": "0 Pcs", "MRP": "250"},        # selling 1/day, none left
        {"Item": "Salt", "Qty": "10 Pcs", "MRP": "20"},       # selling 1/day, 10 left
        {"Item": "Rice", "Qty": "1,000", "MRP": "90"},        # plenty
        {"Item": "Biscuit", "Qty": "5", "MRP": "10"},         # new product, 2/day for 10 days
        {"Item": "Grand Total", "Qty": "1015", "MRP": ""},    # must be ignored
    ])
    sales = pd.DataFrame(daily_sales("Tea", 1, 90) + daily_sales("Salt", 1, 90)
                         + daily_sales("Rice", 1, 90) + daily_sales("Biscuit", 2, 10))
    prod, info = compute(stock, sales, MS, MZ, date_format="dayfirst")
    return prod.set_index("product"), info


def test_out_of_stock(result):
    p, _ = result
    tea = p.loc["Tea"]
    assert tea["status"] == "Out of stock"
    assert tea["avg_daily"] == pytest.approx(1.0)
    assert tea["suggested_order_qty"] == 44          # 1/day x (7 + 7 + 30) - 0
    assert tea["est_lost_sales_per_day"] == pytest.approx(250)


def test_reorder_now(result):
    p, _ = result
    salt = p.loc["Salt"]
    assert salt["reorder_point"] == 14                # 1/day x (7 + 7)
    assert salt["status"] == "Reorder now"
    assert salt["suggested_order_qty"] == 34          # 44 - 10


def test_ok_and_total_row_ignored(result):
    p, _ = result
    assert p.loc["Rice"]["status"] == "OK"
    assert "Grand Total" not in p.index


def test_new_product_averaged_over_days_since_first_sale(result):
    p, _ = result
    b = p.loc["Biscuit"]
    assert b["avg_daily"] == pytest.approx(2.0)       # 20 units / 10 days, not / 90
    assert b["status"] == "Reorder now"               # 5 left < reorder point 28


def test_settings_and_dates(result):
    _, info = result
    assert info["as_of"] == "2026-09-30"
    assert info["matched_on"] == "product name"


def test_number_parsing():
    assert to_number("12 Pcs") == 12
    assert to_number("1,23,456.50") == 123456.5
    assert to_number("(45)") == -45
    assert to_number("₹ 99") == 99
