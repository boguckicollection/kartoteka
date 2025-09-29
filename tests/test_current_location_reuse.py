import importlib
import sys
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


def make_dummy():
    return SimpleNamespace(
        entries={
            "nazwa": DummyVar("Card"),
            "numer": DummyVar("1"),
            "set": DummyVar("Set"),
            "era": DummyVar(""),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "cena": DummyVar(""),
            "psa10_price": DummyVar(""),
            "card_type": DummyVar("C"),
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        card_cache={},
        cards=["/tmp/card.jpg"],
        index=0,
        folder_name="folder",
        file_to_key={},
        product_code_map={},
        next_free_location=MagicMock(return_value="K1R1P2"),
        output_data=[None],
        get_price_from_db=lambda *a: None,
        fetch_card_price=lambda *a: None,
        fetch_psa10_price=lambda *a: None,
        current_location="K1R1P1",
    )


def test_current_location_used_without_generating_new():
    importlib.reload(ui)
    dummy = make_dummy()
    ui.CardEditorApp.save_current_data(dummy)
    assert dummy.output_data[0]["warehouse_code"] == "K1R1P1"
    dummy.next_free_location.assert_not_called()
