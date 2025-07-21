import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))

class DummyVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


def make_dummy():
    return SimpleNamespace(
        entries={
            "nazwa": DummyVar("Charizard"),
            "numer": DummyVar("4"),
            "set": DummyVar("Base"),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "suffix": DummyVar(""),
            "cena": DummyVar("")
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        rarity_vars={},
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
    )


def test_html_generated():
    import main
    importlib.reload(main)
    dummy = make_dummy()
    main.CardEditorApp.save_current_data(dummy)
    data = dummy.output_data[0]
    assert "<ul>" in data["short_description"]
    assert data["short_description"].startswith("<p><strong>")
    assert "<li>" in data["short_description"]
    assert data["description"].count("<p>") >= 2
