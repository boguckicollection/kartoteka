import csv
import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import sys
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
import kartoteka.csv_utils as csv_utils


def test_export_includes_new_fields(tmp_path):
    out_path = tmp_path / "out.csv"

    dummy = SimpleNamespace(
        output_data=[{
            "nazwa": "Pikachu",
            "numer": "1",
            "set": "Base",
            "product_code": 1,
            "cena": "10",
            "category": "Karty",
            "producer": "Pokemon",
            "short_description": "s",
            "description": "d",
            "image1": "img.jpg",
        }]
    )
    dummy.back_to_welcome = lambda: None

    with patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_path)), \
         patch("tkinter.messagebox.showinfo"), \
         patch("tkinter.messagebox.askyesno", return_value=False):
        ui.CardEditorApp.export_csv(dummy)

    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert reader.fieldnames == csv_utils.STORE_FIELDNAMES
        row = rows[0]
        assert row["name"] == "Pikachu"
        assert row["currency"] == "PLN"
        assert row["producer_code"] == "1"
        assert row["stock"] == "1"
        assert row["active"] == "1"
        assert row["vat"] == "23%"
        assert row["images 1"] == "img.jpg"
        assert "psa10_price" not in reader.fieldnames


def test_export_appends_warehouse(tmp_path, monkeypatch):
    out_path = tmp_path / "out.csv"
    inv_path = tmp_path / "inv.csv"
    monkeypatch.setenv("WAREHOUSE_CSV", str(inv_path))
    import importlib
    importlib.reload(csv_utils)
    importlib.reload(ui)

    dummy = SimpleNamespace(
        output_data=[{
            "nazwa": "Pikachu",
            "numer": "1",
            "set": "Base",
            "product_code": 1,
            "cena": "10",
            "category": "Karty",
            "producer": "Pokemon",
            "short_description": "s",
            "description": "d",
            "image1": "img.jpg",
            "warehouse_code": "K1R1P1",
        }]
    )
    dummy.back_to_welcome = lambda: None

    with patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_path)), \
         patch("tkinter.messagebox.showinfo"), \
         patch("tkinter.messagebox.askyesno", return_value=False):
        ui.CardEditorApp.export_csv(dummy)

    with open(inv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert reader.fieldnames == csv_utils.WAREHOUSE_FIELDNAMES
        assert rows[0]["name"] == "Pikachu 1"
        assert rows[0]["image"] == "img.jpg"
        assert rows[0]["warehouse_code"] == "K1R1P1"


