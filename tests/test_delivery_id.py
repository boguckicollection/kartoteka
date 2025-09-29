import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str((Path(__file__).resolve().parents[1])))
import kartoteka.ui as ui

class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_delivery_field_constant():
    importlib.reload(ui)

    dummy = SimpleNamespace(
        entries={
            "nazwa": DummyVar("Pikachu"),
            "numer": DummyVar("1"),
            "set": DummyVar("Base"),
            "era": DummyVar(""),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "cena": DummyVar(""),
            "psa10_price": DummyVar(""),
            "card_type": DummyVar("C"),
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        card_cache={},
        cards=["/tmp/pika.jpg"],
        index=0,
        folder_name="folder",
        file_to_key={},
        product_code_map={},
        next_free_location=lambda: "K1R1P1",
        generate_location=lambda idx: "K1R1P1",
        output_data=[None],
        get_price_from_db=lambda *a: None,
        fetch_card_price=lambda *a: None,
        fetch_psa10_price=lambda *a, **k: "",
    )

    ui.CardEditorApp.save_current_data(dummy)
    assert dummy.output_data[0]["delivery"] == "3 dni"

