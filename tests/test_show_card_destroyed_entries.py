import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import tkinter as tk

# Provide dummy customtkinter before importing UI module
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402


class DummyEntry:
    def delete(self, *a, **k):
        pass

    def focus_set(self):
        pass

    def winfo_exists(self):
        return True


class DestroyedEntry(DummyEntry):
    def winfo_exists(self):
        return False

    def delete(self, *a, **k):
        raise tk.TclError("bad window path name")


class DummyStringVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def winfo_exists(self):
        return True


class DestroyedStringVar(DummyStringVar):
    def winfo_exists(self):
        return False

    def set(self, value):
        raise tk.TclError("bad window path name")


def test_show_card_handles_destroyed_entries(tmp_path, monkeypatch):
    img = tmp_path / "card.jpg"
    img.write_bytes(b"data")

    # Patch tk classes in ui module
    tk_mod = SimpleNamespace(
        Entry=DummyEntry,
        StringVar=DummyStringVar,
        BooleanVar=DummyStringVar,
        END=0,
        DISABLED="disabled",
        NORMAL="normal",
        TclError=tk.TclError,
    )
    monkeypatch.setattr(ui, "tk", tk_mod)

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

    monkeypatch.setattr(ui, "load_rgba_image", lambda path: DummyImage())
    monkeypatch.setattr(ui, "_create_image", lambda img: object())

    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=SimpleNamespace(configure=lambda *a, **k: None),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={
            "nazwa": DummyEntry(),
            "numer": DestroyedEntry(),
            "set": DestroyedStringVar(),
            "era": DummyStringVar(),
            "język": DummyStringVar(),
            "stan": DummyStringVar(),
            "card_type": DummyStringVar("C"),
        },
        card_type_var=DummyStringVar("C"),
        type_vars={"Reverse": SimpleNamespace(set=lambda *a, **k: None)},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
        root=SimpleNamespace(after=lambda delay, func: func()),
        auto_lookup=False,
        _analyze_and_fill=lambda *a, **k: None,
    )

    ui.CardEditorApp.show_card(dummy)

    assert "numer" not in dummy.entries
    assert "set" not in dummy.entries
