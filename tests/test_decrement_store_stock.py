import csv
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kartoteka.csv_utils as csv_utils


def test_decrement_store_stock_updates_availability(tmp_path):
    csv_path = tmp_path / "store.csv"
    csv_path.write_text(
        "product_code;name;availability;stock\n"
        "PKM-SET-1C;Card A;1;1\n"
        "PKM-SET-2C;Card B;3;3\n",
        encoding="utf-8",
    )

    removed = csv_utils.decrement_store_stock({"PKM-SET-1C": 1, "PKM-SET-2C": 2}, path=str(csv_path))
    assert removed == 3

    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    assert len(rows) == 1
    row = rows[0]
    assert row["product_code"] == "PKM-SET-2C"
    assert row["stock"] == "1"
