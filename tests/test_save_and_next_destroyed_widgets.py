import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk

# Provide dummy customtkinter before importing UI module
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class DestroyedVar:
    def winfo_exists(self):
        return False

    def get(self):
        raise tk.TclError("bad window path name")


def make_dummy():
    dummy = SimpleNamespace(
        entries={
            "nazwa": DestroyedVar(),
            "numer": DummyVar("4"),
            "set": DummyVar("Base Set"),
            "era": DummyVar(""),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "cena": DummyVar(""),
            "psa10_price": DummyVar(""),
            "card_type": DummyVar("C"),
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        card_cache={},
        cards=["card1.jpg", "card2.jpg"],
        index=0,
        folder_name="folder",
        file_to_key={},
        product_code_map={},
        next_free_location=lambda: "K1R1P1",
        generate_location=lambda idx: "K1R1P1",
        output_data=[None, None],
        get_price_from_db=lambda *a: None,
        fetch_card_price=lambda *a: None,
        fetch_psa10_price=lambda *a: None,
        show_card=MagicMock(),
    )
    dummy.save_current_data = ui.CardEditorApp.save_current_data.__get__(dummy)
    return dummy


def test_save_and_next_with_destroyed_entries():
    dummy = make_dummy()
    with patch.object(ui.messagebox, "showinfo"), \
        patch.object(ui.messagebox, "showwarning"):
        ui.CardEditorApp.save_and_next(dummy)
    assert dummy.output_data[0]["numer"] == "4"
    assert dummy.output_data[0]["nazwa"] == ""
    assert dummy.index == 1
    dummy.show_card.assert_called_once()
