import importlib
import sys
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tkinter as tk
from PIL import Image

sys.modules["customtkinter"] = SimpleNamespace(
    CTkEntry=tk.Entry,
    CTkImage=MagicMock(),
    CTkButton=MagicMock,
    CTkToplevel=MagicMock,
)
sys.modules["pytesseract"] = SimpleNamespace(image_to_string=MagicMock(return_value=""))
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)

SV01_CODE = "sv01"
SV01_NAME = ui.get_set_name(SV01_CODE)


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
    dummy._analyze_and_fill = lambda url, idx: ui.CardEditorApp._apply_analysis_result(
        dummy, ui.analyze_card_image(url), idx
    )

    with patch.object(ui.Image, "open", return_value=MagicMock(thumbnail=lambda *a, **k: None)), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
        patch.object(
            ui, "analyze_card_image", return_value={"name": "Pika", "number": "001", "set": SV01_NAME}
        ) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    mock_analyze.assert_called_once_with(str(img))
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "1")
    set_var.set.assert_called_with(SV01_NAME)


def test_analyze_card_image_api_single_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_text_openai", return_value=("Pikachu", "037", "")), \
         patch.object(ui, "lookup_sets_from_api", return_value=[("sv01", SV01_NAME)]), \
         patch.object(ui, "prompt_set_selection") as mock_prompt, \
         patch.object(ui, "identify_set_by_hash") as mock_hash:
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "037", "total": "", "set": SV01_NAME}
    mock_prompt.assert_not_called()
    mock_hash.assert_not_called()


def test_analyze_card_image_api_multiple_sets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    options = [("a", "Set A"), ("b", "Set B")]

    with patch.object(ui, "extract_card_text_openai", return_value=("Pikachu", "037", "")), \
         patch.object(ui, "lookup_sets_from_api", return_value=options), \
         patch.object(ui, "prompt_set_selection", return_value="b") as mock_prompt, \
         patch.object(ui, "identify_set_by_hash") as mock_hash:
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "037", "total": "", "set": "Set B"}
    mock_prompt.assert_called_once_with(options)
    mock_hash.assert_not_called()


def test_analyze_card_image_api_fallback_hash(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    class DummyImage:
        size = (100, 100)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch.object(ui, "extract_card_text_openai", return_value=("Pikachu", "037", "")), \
         patch.object(ui, "lookup_sets_from_api", return_value=[]), \
         patch.object(ui, "identify_set_by_hash", return_value=[("x", "Set X", 0)]) as mock_hash, \
         patch.object(ui.Image, "open", return_value=DummyImage()):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "037", "total": "", "set": "Set X"}
    mock_hash.assert_called_once()


def test_analyze_card_image_ocr(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(ui, "extract_set_code_ocr", return_value=[SV01_CODE]) as mock_ocr, \
        patch.object(ui, "identify_set_by_hash") as mock_hash, \
        patch.object(ui, "extract_card_text_openai") as mock_extract, \
        patch.object(ui, "lookup_sets_from_api") as mock_lookup:
        result = ui.analyze_card_image(str(logo_path))

    assert result == {"name": "", "number": "", "total": "", "set": SV01_NAME}
    mock_ocr.assert_called_once()
    mock_hash.assert_not_called()
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()


def test_extract_set_code_ocr_filters_single_letter(tmp_path, monkeypatch):
    img = Image.new("RGB", (10, 10), color="white")
    path = tmp_path / "img.png"
    img.save(path)

    with patch("pytesseract.image_to_string", return_value="E\n123\nSV01\n"):
        result = ui.extract_set_code_ocr(str(path), (0, 0, 10, 10))

    assert result == [SV01_CODE]


def test_analyze_card_image_bad_json(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_text_openai", return_value=("", "", "")), \
        patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "", "number": "", "total": "", "set": ""}


def test_analyze_card_image_truncated_code_block(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_text_openai", return_value=("Pikachu", "037", "159")), \
        patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "037", "total": "159", "set": ""}


def test_analyze_card_image_leading_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_text_openai", return_value=("Pikachu", "037", "159")), \
        patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {"name": "Pikachu", "number": "037", "total": "159", "set": ""}


def test_analyze_card_image_local_hash(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"
    with patch.object(ui, "extract_card_text_openai") as mock_extract, patch.object(
        ui, "lookup_sets_from_api"
    ) as mock_lookup:
        result = ui.analyze_card_image(str(logo_path))

    assert result == {"name": "", "number": "", "total": "", "set": SV01_NAME}
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()


def test_analyze_card_image_translate_name(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch.object(
        ui, "extract_card_text_openai", return_value=("\u30d4\u30ab\u30c1\u30e5\u30a6", "037", "159")
    ), patch(
        "openai.chat.completions.create", return_value=resp_translate
    ) as mock_create, patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg", translate_name=True)

    assert result == {"name": "Pikachu", "number": "037", "total": "159", "set": ""}
    mock_create.assert_called_once()


def test_analyze_and_fill_translates_for_jp(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")

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

    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch.object(
        ui, "extract_card_text_openai", return_value=("\u30d4\u30ab\u30c1\u30e5\u30a6", "001", "")
    ), patch(
        "openai.chat.completions.create", return_value=resp_translate
    ), patch.object(ui, "lookup_sets_from_api", return_value=[]):
        ui.CardEditorApp._analyze_and_fill(dummy, "/tmp/x", 0)

    name_entry.insert.assert_called_with(0, "Pikachu")


def test_show_card_fills_from_inventory(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        f"name;numer;set\nPikachu;001;{SV01_NAME}\n",
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
        file_to_key={img.name: f"Pikachu|001|{SV01_NAME}"},
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
    num_entry.insert.assert_called_with(0, "1")
    set_var.set.assert_called_with(SV01_NAME)

