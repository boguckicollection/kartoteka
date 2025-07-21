import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str((Path(__file__).resolve().parents[1])))

class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_delivery_id_used(monkeypatch):
    monkeypatch.setenv("SHOPER_DELIVERY_ID", "7")
    import main
    importlib.reload(main)

    dummy = SimpleNamespace(
        entries={
            "nazwa": DummyVar("Pikachu"),
            "numer": DummyVar("1"),
            "set": DummyVar("Base"),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "suffix": DummyVar(""),
            "cena": DummyVar("")
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        rarity_vars={},
        card_cache={},
        cards=["/tmp/pika.jpg"],
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
    )

    main.CardEditorApp.save_current_data(dummy)
    assert dummy.output_data[0]["delivery"] == 7

