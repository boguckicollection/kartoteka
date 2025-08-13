import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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
        assert rows[0]["warehouse_code"] == "K1"
