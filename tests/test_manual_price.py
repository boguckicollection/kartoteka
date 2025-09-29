import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui

class DummyVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


def make_dummy(price):
    return SimpleNamespace(
        entries={
            "nazwa": DummyVar("Charizard"),
            "numer": DummyVar("4"),
            "set": DummyVar("Base Set"),
            "era": DummyVar(""),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "cena": DummyVar(price),
            "psa10_price": DummyVar(""),
            "card_type": DummyVar("C"),
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        card_cache={},
        cards=["/tmp/char.jpg"],
        index=0,
        folder_name="folder",
        file_to_key={},
        product_code_map={},
        next_free_location=lambda: "K1R1P1",
        generate_location=lambda idx: "K1R1P1",
        output_data=[None],
        get_price_from_db=MagicMock(return_value=None),
        fetch_card_price=MagicMock(return_value=None),
        fetch_psa10_price=MagicMock(return_value="123"),
    )


def test_manual_price_used():
    importlib.reload(ui)
    dummy = make_dummy("15.50")
    ui.CardEditorApp.save_current_data(dummy)
    assert dummy.output_data[0]["cena"] == "15.50"
    dummy.get_price_from_db.assert_not_called()
    dummy.fetch_card_price.assert_not_called()
