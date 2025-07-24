import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk

sys.modules["customtkinter"] = SimpleNamespace(CTkEntry=tk.Entry)
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_show_card_uses_analyzer(tmp_path):
    img = tmp_path / "card.jpg"
    img.write_bytes(b"data")

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    name_entry.focus_set = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()

    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=MagicMock(),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var},
        rarity_vars={},
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )

    with patch.object(ui.Image, "open", return_value=MagicMock(thumbnail=lambda *a, **k: None)), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
         patch.object(ui, "analyze_card_image", return_value={"name": "Pika", "number": "001", "set": "Base"}) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    mock_analyze.assert_called_once_with(str(img))
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "001")
    set_var.set.assert_called_with("Base")

