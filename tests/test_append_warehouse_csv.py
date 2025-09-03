import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import date

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def test_append_warehouse_csv_updates_stats(tmp_path):
    path = tmp_path / "magazyn.csv"
    app = SimpleNamespace(
        output_data=[
            {
                "name": "A",
                "number": "1",
                "set": "S",
                "warehouse_code": "K1",
                "price": "2",
                "image": "",
                "sold": "",
            }
        ],
        update_inventory_stats=MagicMock(),
    )
    csv_utils.append_warehouse_csv(app, path=str(path))
    app.update_inventory_stats.assert_called_once()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert reader.fieldnames == csv_utils.WAREHOUSE_FIELDNAMES
        assert rows[0]["warehouse_code"] == "K1"
        assert rows[0]["added_at"]


def test_append_warehouse_csv_writes_variant(tmp_path):
    path = tmp_path / "magazyn.csv"
    app = SimpleNamespace(
        output_data=[
            {
                "name": "A",
                "number": "1",
                "set": "S",
                "warehouse_code": "K1",
                "price": "2",
                "image": "",
                "types": {"Holo": True, "Reverse": False},
            }
        ],
        update_inventory_stats=MagicMock(),
    )
    csv_utils.append_warehouse_csv(app, path=str(path))
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        row = next(reader)
        assert reader.fieldnames == csv_utils.WAREHOUSE_FIELDNAMES
        assert row["variant"] == "holo"


def test_append_warehouse_csv_sets_added_at(tmp_path, monkeypatch):
    path = tmp_path / "magazyn.csv"

    class DummyDate(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 2)

    monkeypatch.setattr(csv_utils, "date", DummyDate)

    app = SimpleNamespace(
        output_data=[
            {
                "name": "A",
                "number": "1",
                "set": "S",
                "warehouse_code": "K1",
                "price": "2",
                "image": "",
            }
        ],
        update_inventory_stats=MagicMock(),
    )
    csv_utils.append_warehouse_csv(app, path=str(path))
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        row = next(reader)
        assert row["added_at"] == "2024-01-02"
