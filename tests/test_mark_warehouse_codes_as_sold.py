import csv
import sys
from pathlib import Path


def _setup_csv_utils(tmp_path):
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.csv_utils as csv_utils
    csv_utils.WAREHOUSE_CSV = str(tmp_path / "magazyn.csv")
    return csv_utils


def test_mark_codes_handles_grouped_rows(tmp_path):
    csv_utils = _setup_csv_utils(tmp_path)

    with open(csv_utils.WAREHOUSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "warehouse_code", "price", "sold"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerow({"name": "Card", "warehouse_code": "K1;K2", "price": "1", "sold": ""})

    marked = csv_utils.mark_warehouse_codes_as_sold(["K1"])

    assert marked == 1

    with open(csv_utils.WAREHOUSE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    assert any(r["warehouse_code"] == "K1" and r.get("sold") == "1" for r in rows)
    assert any(r["warehouse_code"] == "K2" and not r.get("sold") for r in rows)


def test_mark_codes_returns_zero_when_missing(tmp_path):
    csv_utils = _setup_csv_utils(tmp_path)

    with open(csv_utils.WAREHOUSE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "warehouse_code", "price", "sold"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerow({"name": "Card", "warehouse_code": "K1", "price": "1", "sold": ""})

    marked = csv_utils.mark_warehouse_codes_as_sold(["K9"])

    assert marked == 0

    with open(csv_utils.WAREHOUSE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    assert rows[0]["sold"] == ""
