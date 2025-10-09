import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import tkinter as tk
import importlib

# provide minimal customtkinter stub before importing modules
sys.modules["customtkinter"] = SimpleNamespace(
    CTkEntry=tk.Entry,
    CTkImage=MagicMock(),
    CTkButton=MagicMock,
    CTkToplevel=MagicMock,
)

sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
import kartoteka.csv_utils as csv_utils
importlib.reload(ui)
importlib.reload(csv_utils)


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _create_store_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_utils.STORE_FIELDNAMES, delimiter=";")
        writer.writeheader()
        writer.writerow({
            "product_code": "PKM-PAL-1C",
            "name": "Pikachu",
            "producer_code": "1",
            "category": "Karty Pokémon > EraX > Paldea Evolved",
            "producer": "",
            "short_description": "",
            "description": "",
            "price": "99",
            "currency": "PLN",
            "availability": "1",
            "unit": "szt.",
            "delivery": "",
            "stock": "1",
            "active": "1",
            "seo_title": "",
            "vat": "23%",
            "images 1": "",
        })


def test_load_store_export(tmp_path):
    csv_path = tmp_path / "store_export.csv"
    _create_store_csv(csv_path)
    data = csv_utils.load_store_export(str(csv_path))
    assert "PKM-PAL-1C" in data
    assert data["PKM-PAL-1C"]["price"] == "99"


def test_analyze_and_fill_uses_store_export(monkeypatch, tmp_path):
    csv_path = tmp_path / "store_export.csv"
    _create_store_csv(csv_path)
    store_data = csv_utils.load_store_export(str(csv_path))

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = DummyVar("")
    era_var = DummyVar("")
    price_entry = MagicMock()
    card_type_var = DummyVar("C")
    for entry in (name_entry, num_entry, price_entry):
        entry.delete = MagicMock()
        entry.insert = MagicMock()

    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func: func()),
        entries={
            "nazwa": name_entry,
            "numer": num_entry,
            "set": set_var,
            "era": era_var,
            "cena": price_entry,
            "card_type": card_type_var,
        },
        index=0,
        update_set_options=lambda: None,
        update_set_area_preview=lambda *a, **k: None,
        store_data=store_data,
        hash_db=None,
        auto_lookup=False,
        card_type_var=card_type_var,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)
    dummy._get_card_type_code = ui.CardEditorApp._get_card_type_code.__get__(dummy, ui.CardEditorApp)
    dummy._set_card_type_code = ui.CardEditorApp._set_card_type_code.__get__(dummy, ui.CardEditorApp)
    dummy._set_card_type_from_mapping = ui.CardEditorApp._set_card_type_from_mapping.__get__(dummy, ui.CardEditorApp)

    monkeypatch.setattr(
        ui,
        "analyze_card_image",
        lambda *a, **k: {"name": "Pikachu", "number": "1", "set": "Paldea Evolved"},
    )

    ui.CardEditorApp._analyze_and_fill(dummy, "x", 0)
    assert era_var.value == "EraX"
    price_entry.insert.assert_called_with(0, "99")
