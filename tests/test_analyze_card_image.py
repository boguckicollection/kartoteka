import importlib
import sys
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk
import pytest

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
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )

    dummy.start_scan_animation = lambda *a, **k: None
    dummy.stop_scan_animation = lambda *a, **k: None
    dummy._analyze_and_fill = lambda url, idx: ui.CardEditorApp._apply_analysis_result(dummy, ui.analyze_card_image(url), idx)

    with patch.object(ui.Image, "open", return_value=MagicMock(thumbnail=lambda *a, **k: None)), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
        patch.object(ui, "analyze_card_image", return_value={"name": "Pika", "number": "001", "set": "Base"}) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    folder = os.path.basename(img.parent)
    expected_url = f"{ui.BASE_IMAGE_URL}/{folder}/{img.name}"
    mock_analyze.assert_called_once_with(expected_url)
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "001")
    set_var.set.assert_called_with("Base")


def test_analyze_card_image_bad_json(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    resp = SimpleNamespace(output=[])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp)))

    with patch("openai.OpenAI", return_value=client):
        result = ui.analyze_card_image("/tmp/img.jpg")

    output = capsys.readouterr().out
    assert result == {"name": "", "number": "", "set": ""}
    assert "analyze_card_image failed to parse response" in output


def test_analyze_card_image_truncated_code_block(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    parsed = ui.CardData(name="Pikachu", number="037/159", set="")
    resp = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp)))

    with patch("openai.OpenAI", return_value=client):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "37", "set": ""}


def test_analyze_card_image_leading_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    parsed = ui.CardData(name="Pikachu", number="037/159", set="")
    resp = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp)))

    with patch("openai.OpenAI", return_value=client):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "37", "set": ""}


def test_analyze_card_image_with_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    parsed = ui.CardData(name="Pikachu", number="001", set="swsh11")
    resp = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp)))

    with patch("openai.OpenAI", return_value=client):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "1", "set": "Lost Origin"}


def test_analyze_card_image_includes_logo_labels(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    logos = {"ABC": "http://logo"}
    parsed = ui.CardData(name="", number="", set="")
    resp = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    mock_parse = MagicMock(return_value=resp)
    client = SimpleNamespace(responses=SimpleNamespace(parse=mock_parse))

    with patch.object(ui, "load_set_logo_uris", return_value=logos), patch(
        "openai.OpenAI", return_value=client
    ):
        ui.analyze_card_image("http://example.com/img.jpg")

    content = mock_parse.call_args.kwargs["input"][0]["content"]
    assert content[2] == {"type": "input_text", "text": "Set ABC"}
    assert content[3] == {"type": "input_image", "image_url": "http://logo"}


@pytest.mark.parametrize("letter", ["E", "F"])
def test_analyze_card_image_sanitizes_single_letter_set(monkeypatch, letter):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    parsed = ui.CardData(name="Pikachu", number="001", set=letter)
    resp = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp)))

    with patch("openai.OpenAI", return_value=client):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "1", "set": ""}


def test_analyze_card_image_unknown_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    parsed = ui.CardData(name="Pikachu", number="001", set="unknown-set")
    resp = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp)))

    with patch("openai.OpenAI", return_value=client):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "1", "set": ""}


def test_analyze_card_image_translate_name(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    parsed = ui.CardData(name="\u30d4\u30ab\u30c1\u30e5\u30a6", number="037/159", set="")
    resp_parse = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp_parse)))
    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch("openai.OpenAI", return_value=client), patch(
        "openai.chat.completions.create", return_value=resp_translate
    ) as mock_create:
        result = ui.analyze_card_image("/tmp/img.jpg", translate_name=True)

    assert result == {"name": "Pikachu", "number": "37", "set": ""}
    mock_create.assert_called_once()


def test_analyze_and_fill_translates_for_jp(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()

    class DummyVar:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value

    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func: func()),
        lang_var=DummyVar("JP"),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var},
        index=0,
        stop_scan_animation=lambda: None,
        update_set_options=lambda: None,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)

    parsed = ui.CardData(name="\u30d4\u30ab\u30c1\u30e5\u30a6", number="001", set="")
    resp_parse = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(parsed=parsed)])])
    client = SimpleNamespace(responses=SimpleNamespace(parse=MagicMock(return_value=resp_parse)))
    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch("openai.OpenAI", return_value=client), patch(
        "openai.chat.completions.create", return_value=resp_translate
    ):
        ui.CardEditorApp._analyze_and_fill(dummy, "http://x", 0)

    name_entry.insert.assert_called_with(0, "Pikachu")


def test_show_card_fills_from_inventory(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;numer;set\nPikachu;001;Base\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("INVENTORY_CSV", str(csv_path))
    import importlib
    import kartoteka.csv_utils as csv_utils
    importlib.reload(csv_utils)
    import kartoteka.ui as ui
    importlib.reload(ui)

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
        type_vars={},
        card_cache={},
        file_to_key={img.name: "Pikachu|001|Base"},
        _guess_key_from_filename=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )

    dummy.lookup_inventory_entry = ui.CardEditorApp.lookup_inventory_entry.__get__(dummy, ui.CardEditorApp)

    dummy.start_scan_animation = lambda *a, **k: None
    dummy.stop_scan_animation = lambda *a, **k: None

    with patch.object(ui.Image, "open", return_value=MagicMock(thumbnail=lambda *a, **k: None)), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
         patch.object(ui, "analyze_card_image", return_value={}) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    mock_analyze.assert_not_called()
    name_entry.insert.assert_called_with(0, "Pikachu")
    num_entry.insert.assert_called_with(0, "001")
    set_var.set.assert_called_with("Base")

