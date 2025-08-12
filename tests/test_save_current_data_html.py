import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import datetime

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui

class DummyVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


PSA10_PRICE = "123"


def make_dummy():
    return SimpleNamespace(
        entries={
            "nazwa": DummyVar("Charizard"),
            "numer": DummyVar("4"),
            "set": DummyVar("Base"),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "cena": DummyVar(""),
            "psa10_price": DummyVar("")
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        card_cache={},
        cards=["/tmp/char.jpg"],
        index=0,
        folder_name="folder",
        file_to_key={},
        product_code_map={},
        next_product_code=1,
        next_free_location=lambda: "K1R1P1",
        generate_location=lambda idx: "K1R1P1",
        output_data=[None],
        get_price_from_db=lambda *a: None,
        fetch_card_price=lambda *a: None,
        fetch_psa10_price=MagicMock(return_value=PSA10_PRICE),
    )


def test_html_generated():
    importlib.reload(ui)
    dummy = make_dummy()
    ui.CardEditorApp.save_current_data(dummy)
    data = dummy.output_data[0]
    dummy.fetch_psa10_price.assert_called_once_with("Charizard", "4", "Base")
    assert data["psa10_price"] == PSA10_PRICE
    assert data["active"] == 1
    assert data["vat"] == "23%"
    assert data["seo_title"] == "Charizard 4 Base"
    assert data["short_description"].startswith("<ul")
    assert "<li>" in data["short_description"]
    assert "Zestaw: Base" in data["short_description"]
    assert "Numer karty: 4" in data["short_description"]
    assert "Stan: NM" in data["short_description"]
    assert "Typ:" in data["short_description"]
    assert "PSA" not in data["short_description"]
    assert data["description"].startswith("<div")
    assert '<img src="https://static.rollerbros.com/psa10.png"' not in data["description"]
    today = datetime.date.today().isoformat()
    assert f"Wartość tej karty w ocenie PSA 10 ({today}):" in data["description"]
    assert PSA10_PRICE in data["description"]
    assert "<h2>" in data["description"]
    assert "Czy wiesz, że" in data["description"]
    assert "/szukaj?set=Base" in data["description"]
    assert dummy.product_code_map == {}
    assert dummy.next_product_code == 2
