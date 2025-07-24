import importlib
import sys
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk

sys.modules["customtkinter"] = SimpleNamespace(CTkEntry=tk.Entry, CTkImage=MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_show_card_uses_analyzer(tmp_path):
    img = tmp_path / "card.jpg"
    img.write_bytes(b"data")

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    suffix_var = MagicMock()
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
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "suffix": suffix_var},
        rarity_vars={},
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )

    dummy.start_scan_animation = lambda *a, **k: None
    dummy.stop_scan_animation = lambda *a, **k: None
    dummy._analyze_and_fill = lambda url, idx: ui.CardEditorApp._apply_analysis_result(dummy, ui.analyze_card_image(url), idx)

    with patch.object(ui.Image, "open", return_value=MagicMock(thumbnail=lambda *a, **k: None)), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
         patch.object(ui, "analyze_card_image", return_value={"name": "Pika", "number": "001", "set": "Base", "suffix": "V"}) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    folder = os.path.basename(img.parent)
    expected_url = f"{ui.BASE_IMAGE_URL}/{folder}/{img.name}"
    mock_analyze.assert_called_once_with(expected_url)
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "001")
    set_var.set.assert_called_with("Base")
    suffix_var.set.assert_called_with("V")


def test_analyze_card_image_bad_json(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
    )

    with patch("openai.chat.completions.create", return_value=resp):
        result = ui.analyze_card_image("/tmp/img.jpg")
    output = capsys.readouterr().out

    assert result == {"name": "", "number": "", "set": "", "suffix": ""}
    assert "analyze_card_image failed to decode JSON" in output
    assert "not json" in output


def test_analyze_card_image_code_block(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    content = "```json\n{\"name\": \"Pikachu\", \"number\": \"037/159\", \"set\": \"Base\"}\n```"
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )

    with patch("openai.chat.completions.create", return_value=resp):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "37", "set": "Base", "suffix": ""}

