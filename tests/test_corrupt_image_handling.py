import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk

sys.modules["customtkinter"] = SimpleNamespace(CTkEntry=tk.Entry, CTkImage=MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_show_card_logs_corrupt_image(tmp_path, capsys):
    img = tmp_path / "bad.jpg"
    img.write_bytes(b"not an image")

    card_type_var = SimpleNamespace(set=lambda *a, **k: None, get=lambda: "C")
    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=MagicMock(),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={"card_type": card_type_var},
        type_vars={},
        card_cache={},
        file_to_key={},
        failed_cards=[],
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        export_csv=lambda *a, **k: None,
        card_type_var=card_type_var,
    )
    dummy.show_card = lambda: ui.CardEditorApp.show_card(dummy)

    with patch.object(ui.Image, "open", side_effect=OSError("bad image")), \
         patch.object(ui.messagebox, "showinfo"), \
         patch.object(ui.messagebox, "showerror") as mock_error:
        ui.CardEditorApp.show_card(dummy)

    err = capsys.readouterr().err
    assert "Failed to load image" in err
    assert str(img) in err
    assert dummy.failed_cards == [str(img)]
    mock_error.assert_called_once()
