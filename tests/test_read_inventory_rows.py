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
    assert rows[0]["czas_trwania"] == "30"


def test_read_inventory_rows_name_without_number(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(
        "product_code;name;price\n1;Trainer Card;5\n",
        encoding="utf-8",
    )
    dummy = SimpleNamespace()
    rows = ui.CardEditorApp.read_inventory_rows(dummy, [], str(csv_path))
    assert rows[0]["nazwa_karty"] == "Trainer Card"
    assert rows[0]["numer_karty"] == ""


def test_read_inventory_rows_normalized_headers(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(
        "Product_Code;Nazwa_Karty;Numer_Karty;Cena_Początkowa\n1;A;1;5\n",
        encoding="utf-8",
    )
    dummy = SimpleNamespace()
    rows = ui.CardEditorApp.read_inventory_rows(dummy, [], str(csv_path))
    assert rows[0]["nazwa_karty"] == "A"
    assert rows[0]["numer_karty"] == "1"
    assert rows[0]["cena_początkowa"] == "5"


def test_read_inventory_rows_extra_values_ignored(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(
        'product_code;nazwa_karty\n"1";"A";"extra"\n', encoding="utf-8"
    )
    dummy = SimpleNamespace()
    rows = ui.CardEditorApp.read_inventory_rows(dummy, [], str(csv_path))
    assert rows == [{"product_code": "1", "nazwa_karty": "A", "price": "0"}]


def test_read_inventory_rows_image_and_defaults(tmp_path):
    csv_path = tmp_path / "inv.csv"
    csv_path.write_text("name;image\nTest 1;img.png\n", encoding="utf-8")
    dummy = SimpleNamespace()
    rows = ui.CardEditorApp.read_inventory_rows(dummy, [], str(csv_path))
    assert rows[0]["images 1"] == "img.png"
    assert rows[0]["price"] == "0"
    assert rows[0]["product_code"] == ""
    assert rows[0]["cena_początkowa"] == "0"

