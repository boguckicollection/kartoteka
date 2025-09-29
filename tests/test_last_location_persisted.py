import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("dotenv", MagicMock(load_dotenv=lambda *a, **k: None, set_key=lambda *a, **k: None))
sys.modules.setdefault("pydantic", MagicMock(BaseModel=object))
sys.modules.setdefault("pytesseract", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
import kartoteka.storage as storage


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
        next_free_location=MagicMock(return_value="K01R1P0001"),
        output_data=[None],
        get_price_from_db=lambda *a: None,
        fetch_card_price=lambda *a: None,
        fetch_psa10_price=lambda *a: None,
        current_location="",
    )


def test_last_location_persisted(monkeypatch, tmp_path):
    path = tmp_path / "last.txt"
    monkeypatch.setattr(storage, "LAST_LOCATION_FILE", path)
    monkeypatch.setattr(ui.storage, "LAST_LOCATION_FILE", path)

    dummy = make_dummy()
    ui.CardEditorApp.save_current_data(dummy)

    new = SimpleNamespace(output_data=[])
    assert ui.CardEditorApp.next_free_location(new) == "K01R1P0002"

