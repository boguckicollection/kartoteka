import importlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image


def test_save_and_reload_variant_flags(tmp_path):
    class DummyVar:
        def __init__(self, value=""):
            self.value = value
        def get(self):
            return self.value
        def set(self, v):
            self.value = v
        def focus_set(self):
            pass
    class DummyEntry:
        def __init__(self, *a, **k):
            self.value = ""
        def delete(self, *a, **k):
            self.value = ""
        def insert(self, *a, **k):
            self.value = a[1] if len(a) > 1 else ""
    tk_mod = ModuleType("tkinter")
    tk_mod.StringVar = DummyVar
    tk_mod.BooleanVar = DummyVar
    tk_mod.Entry = DummyEntry
    tk_mod.END = "end"
    tk_mod.TclError = Exception
    tk_mod.filedialog = MagicMock()
    tk_mod.messagebox = MagicMock()
    tk_mod.simpledialog = MagicMock()
    ttk_mod = ModuleType("tkinter.ttk")
    ctk_mod = ModuleType("customtkinter")
    class DummyCTkEntry:  # pragma: no cover - only for isinstance checks
        pass
    ctk_mod.CTkEntry = DummyCTkEntry
    img_path = tmp_path / "card.jpg"
    Image.new("RGB", (10, 10), "white").save(img_path)
    with patch.dict(sys.modules, {"tkinter": tk_mod, "tkinter.ttk": ttk_mod, "customtkinter": ctk_mod}):
        sys.path.append(str(Path(__file__).resolve().parents[1]))
        import kartoteka.ui as ui
        importlib.reload(ui)
        card_type_var = DummyVar("R")
        dummy = SimpleNamespace(
            entries={
                "nazwa": DummyVar("Charizard"),
                "numer": DummyVar("4"),
                "set": DummyVar("Base Set"),
                "era": DummyVar(""),
                "język": DummyVar("ENG"),
                "stan": DummyVar("NM"),
                "cena": DummyVar(""),
                "psa10_price": DummyVar(""),
                "card_type": card_type_var,
            },
            card_type_var=card_type_var,
            card_cache={},
            cards=[str(img_path)],
            index=0,
            folder_name="folder",
            file_to_key={},
            product_code_map={},
            next_free_location=lambda: "K1R1P1",
            generate_location=lambda idx: "K1R1P1",
            output_data=[None],
            get_price_from_db=lambda *a: None,
            fetch_card_price=lambda *a: None,
            fetch_psa10_price=lambda *a: "0",
            progress_var=SimpleNamespace(set=lambda s: None),
            image_label=SimpleNamespace(configure=lambda **kw: None),
            update_set_options=lambda: None,
            lookup_inventory_entry=lambda key: None,
            failed_cards=[],
            image_objects=[],
            _analyze_and_fill=lambda *a, **k: None,
            auto_lookup=False,
            hash_db=None,
        )
        dummy._get_card_type_code = ui.CardEditorApp._get_card_type_code.__get__(dummy, ui.CardEditorApp)
        dummy._set_card_type_code = ui.CardEditorApp._set_card_type_code.__get__(dummy, ui.CardEditorApp)
        dummy._set_card_type_from_mapping = ui.CardEditorApp._set_card_type_from_mapping.__get__(dummy, ui.CardEditorApp)
        with patch.object(ui.ImageTk, "PhotoImage", return_value=SimpleNamespace()), \
             patch.object(ui.threading, "Thread", lambda *a, **k: SimpleNamespace(start=lambda: None)):
            ui.CardEditorApp.save_current_data(dummy)
            row = dummy.output_data[0]
            assert row["types"] == {"Reverse": True, "Holo": False}
            dummy.card_type_var.set("C")
            key = "Charizard|4|Base Set|"
            dummy.file_to_key[os.path.basename(str(img_path))] = key
            ui.CardEditorApp.show_card(dummy)
            assert dummy.card_type_var.get() == "R"
