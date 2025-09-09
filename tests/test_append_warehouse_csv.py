import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import date
import pytest

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
    app.update_inventory_stats.assert_called_once_with(force=True)
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


def test_append_warehouse_csv_refreshes_stats_cache(tmp_path):
    path = tmp_path / "magazyn.csv"
    path.write_text(
        "name;number;set;warehouse_code;price;image\n" "A;1;S;K1;1;img\n",
        encoding="utf-8",
    )

    # Populate cache with initial statistics
    assert csv_utils.get_inventory_stats(str(path)) == (1, 1.0, 0, 0.0)

    app = SimpleNamespace(
        output_data=[
            {
                "name": "B",
                "number": "2",
                "set": "S2",
                "warehouse_code": "K2",
                "price": "2",
                "image": "",
                "sold": "",
            }
        ],
        update_inventory_stats=MagicMock(),
    )

    csv_utils.append_warehouse_csv(app, path=str(path))

    # Immediately read stats without forcing; should include new row
    count_unsold, total_unsold, count_sold, total_sold = csv_utils.get_inventory_stats(
        str(path)
    )
    assert count_unsold == 2
    assert total_unsold == pytest.approx(3.0)
    assert count_sold == 0
    assert total_sold == pytest.approx(0.0)
