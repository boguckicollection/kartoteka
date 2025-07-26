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
        patch.object(ui, "analyze_card_image", return_value={"name": "Pika", "number": "001", "suffix": "V"}) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    folder = os.path.basename(img.parent)
    expected_url = f"{ui.BASE_IMAGE_URL}/{folder}/{img.name}"
    mock_analyze.assert_called_once_with(expected_url)
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "001")
    set_var.set.assert_called_with("")
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

    assert result == {"name": "", "number": "", "suffix": ""}
    assert "analyze_card_image failed to decode JSON" in output
    assert "not json" in output


def test_analyze_card_image_code_block(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    content = "```json\n{\"name\": \"Pikachu\", \"number\": \"037/159\"}\n```"
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )

    with patch("openai.chat.completions.create", return_value=resp):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "37", "suffix": ""}


def test_analyze_card_image_translate_name(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    resp_analyze = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"name": "\u30d4\u30ab\u30c1\u30e5\u30a6", "number": "037/159"}'
                )
            )
        ]
    )
    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch("openai.chat.completions.create", side_effect=[resp_analyze, resp_translate]) as mock_create:
        result = ui.analyze_card_image("/tmp/img.jpg", translate_name=True)

    assert result == {"name": "Pikachu", "number": "37", "suffix": ""}
    assert mock_create.call_count == 2


def test_analyze_and_fill_translates_for_jp(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    suffix_var = MagicMock()
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()
    suffix_var.set = MagicMock()

    class DummyVar:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value

    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func: func()),
        lang_var=DummyVar("JP"),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "suffix": suffix_var},
        index=0,
        stop_scan_animation=lambda: None,
        update_set_options=lambda: None,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)

    resp_analyze = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"name": "\u30d4\u30ab\u30c1\u30e5\u30a6", "number": "001"}'
                )
            )
        ]
    )
    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch("openai.chat.completions.create", side_effect=[resp_analyze, resp_translate]):
        ui.CardEditorApp._analyze_and_fill(dummy, "http://x", 0)

    name_entry.insert.assert_called_with(0, "Pikachu")

