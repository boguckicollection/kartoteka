import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk
import pytest

# Provide dummy modules before importing ui
sys.modules.setdefault("customtkinter", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("dotenv", MagicMock(load_dotenv=lambda *a, **k: None, set_key=lambda *a, **k: None))
sys.modules.setdefault("pydantic", MagicMock(BaseModel=object))
sys.modules.setdefault("pytesseract", MagicMock())

sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.storage as storage
import kartoteka.ui as ui


def test_next_free_location_raises_when_full():
    dummy = SimpleNamespace(output_data=[{"warehouse_code": "K100R2P1000"}])
    with pytest.raises(storage.NoFreeLocationError):
        storage.next_free_location(dummy)


class DummyEntry:
    def delete(self, *a, **k):
        pass

    def focus_set(self):
        pass

    def winfo_exists(self):
        return True


class DummyVar:
    def set(self, *a, **k):
        pass

    def winfo_exists(self):
        return True


class DummyImage:
    size = (100, 100)

    def thumbnail(self, *a, **k):
        pass

    def copy(self):
        return self


def test_show_card_handles_no_space(tmp_path, monkeypatch):
    img = tmp_path / "card.jpg"
    img.write_bytes(b"data")

    tk_mod = SimpleNamespace(
        Entry=DummyEntry,
        StringVar=DummyVar,
        BooleanVar=DummyVar,
        END=0,
        DISABLED="disabled",
        NORMAL="normal",
        TclError=tk.TclError,
    )
    monkeypatch.setattr(ui, "tk", tk_mod)
    monkeypatch.setattr(ui, "load_rgba_image", lambda path: DummyImage())
    monkeypatch.setattr(ui, "_create_image", lambda img: object())
    monkeypatch.setattr(
        ui.storage,
        "next_free_location",
        lambda app: (_ for _ in ()).throw(storage.NoFreeLocationError()),
    )

    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=SimpleNamespace(configure=lambda *a, **k: None),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={
            "nazwa": DummyEntry(),
            "numer": DummyEntry(),
            "set": DummyVar(),
            "era": DummyVar(),
            "język": DummyVar(),
            "stan": DummyVar(),
            "card_type": DummyVar(),
        },
        card_type_var=DummyVar(),
        type_vars={"Reverse": SimpleNamespace(set=lambda *a, **k: None)},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
        root=SimpleNamespace(after=lambda delay, func: func()),
        auto_lookup=False,
        _analyze_and_fill=lambda *a, **k: None,
        location_label=SimpleNamespace(configure=lambda *a, **k: None),
    )
    dummy.next_free_location = lambda: ui.storage.next_free_location(dummy)

    with patch.object(ui.messagebox, "showerror") as mock_error:
        ui.CardEditorApp.show_card(dummy)
    mock_error.assert_called_once()
    assert mock_error.call_args[0][1] == "Brak wolnych miejsc w magazynie"
