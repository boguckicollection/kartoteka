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
        reader = csv.DictReader(fh, delimiter=";")
        rows = list(reader)

    assert len(rows) == 2
    assert reader.fieldnames == ["product_code", "name", "availability", "stock"]

    result = {row["product_code"]: row for row in rows}
    assert result["PKM-SET-1C"]["availability"] == "0"
    assert result["PKM-SET-1C"]["stock"] == "0"
    assert result["PKM-SET-2C"]["availability"] == "1"
    assert result["PKM-SET-2C"]["stock"] == "1"


def test_decrement_store_stock_adds_availability_column(tmp_path):
    csv_path = tmp_path / "store.csv"
    csv_path.write_text(
        "product_code;name;stock\n"
        "PKM-SET-1C;Card A;2\n",
        encoding="utf-8",
    )

    removed = csv_utils.decrement_store_stock({"PKM-SET-1C": 1}, path=str(csv_path))
    assert removed == 1

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        rows = list(reader)

    assert reader.fieldnames == ["product_code", "name", "stock", "availability"]
    assert rows[0]["availability"] == "1"
    assert rows[0]["stock"] == "1"
