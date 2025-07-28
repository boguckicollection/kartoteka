from types import SimpleNamespace
from unittest.mock import MagicMock
import importlib
import sys
sys.modules.setdefault("customtkinter", MagicMock())
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)

def test_read_inventory_rows_filters(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(
        "product_code;nazwa_karty;numer_karty;cena_początkowa\n1;A;1;10\n2;B;2;20\n",
        encoding="utf-8",
    )
    dummy = SimpleNamespace()
    rows = ui.CardEditorApp.read_inventory_rows(dummy, ["1"], str(csv_path))
    assert len(rows) == 1
    assert rows[0]["nazwa_karty"] == "A"
    rows_all = ui.CardEditorApp.read_inventory_rows(dummy, [], str(csv_path))
    assert len(rows_all) == 2

def test_read_inventory_rows_alt_headers(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(
        "product_code;name;price\n1;A 1;9\n", encoding="utf-8"
    )
    dummy = SimpleNamespace()
    rows = ui.CardEditorApp.read_inventory_rows(dummy, [], str(csv_path))
    assert rows[0]["nazwa_karty"] == "A"
    assert rows[0]["numer_karty"] == "1"
    assert rows[0]["cena_początkowa"] == "9"
    assert rows[0]["kwota_przebicia"] == "1"
    assert rows[0]["czas_trwania"] == "60"

