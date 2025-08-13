import csv
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.ui as ui


def test_toggle_sold_updates_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n" "A;1;S1;K1R1P1;10;;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))
    row = {"name": "A", "warehouse_code": "K1R1P1", "sold": ""}
    app = SimpleNamespace(
        open_magazyn_window=lambda: None, update_inventory_stats=MagicMock()
    )

    ui.CardEditorApp.toggle_sold(app, row)
    app.update_inventory_stats.assert_called_once()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert rows[0]["sold"] == "1"

    app.update_inventory_stats.reset_mock()
    ui.CardEditorApp.toggle_sold(app, row)
    app.update_inventory_stats.assert_called_once()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert rows[0]["sold"] == ""
