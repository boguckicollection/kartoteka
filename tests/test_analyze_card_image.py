import importlib
import sys
from pathlib import Path
import os
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import tkinter as tk
from PIL import Image, ImageDraw

sys.modules["customtkinter"] = SimpleNamespace(
    CTkEntry=tk.Entry,
    CTkImage=MagicMock(),
    CTkButton=MagicMock,
    CTkToplevel=MagicMock,
)
sys.path.append(str(Path(__file__).resolve().parents[1]))
from hash_db import HashDB
import kartoteka.ui as ui
importlib.reload(ui)

SV01_CODE = "sv01"
SV01_NAME = ui.get_set_name(SV01_CODE)


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_extract_card_info_openai_maps_set(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    img = tmp_path / "x.jpg"
    img.write_bytes(b"data")

    payload = {
        "name": "Pikachu",
        "number": "037/198",
        "set_name": SV01_CODE,
        "set_format": "text",
        "era_name": ui.get_set_era(SV01_CODE),
    }
    resp = SimpleNamespace(output_text=json.dumps(payload))

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=lambda *a, **k: resp)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img)
    )
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"


def test_show_card_uses_analyzer(tmp_path):
    img = tmp_path / "card.jpg"
    img.write_bytes(b"data")

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    era_var = MagicMock()
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
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": era_var},
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )
    dummy.update_set_area_preview = lambda *a, **k: None
    dummy._analyze_and_fill = lambda url, idx: ui.CardEditorApp._apply_analysis_result(
        dummy, ui.analyze_card_image(url, debug=True), idx
    )

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

        def convert(self, *a, **k):
            return self

    with patch.object(ui.Image, "open", return_value=DummyImage()), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
        patch.object(
            ui,
            "analyze_card_image",
            return_value={
                "name": "Pika",
                "number": "001",
                "total": "",
                "set": SV01_NAME,
                "set_code": SV01_CODE,
                "orientation": 0,
                "set_format": "",
                "era": ui.get_set_era(SV01_CODE),
            },
        ) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    mock_analyze.assert_called_once_with(str(img), debug=True)
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "1")
    set_var.set.assert_called_with(SV01_NAME)


def test_analyze_card_image_api_single_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(
        ui, "extract_card_info_openai", return_value=("Pikachu", "037", "", "", "", "", "")
    ), patch.object(ui, "lookup_sets_from_api", return_value=[("sv01", SV01_NAME)]), patch.object(
        ui, "identify_set_by_hash", return_value=[]
    ) as mock_hash:
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {
        "name": "Pikachu",
        "number": "037",
        "total": "",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era(SV01_CODE),
    }
    mock_hash.assert_called_once()


def test_analyze_card_image_api_multiple_sets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    options = [("a", "Set A"), ("b", "Set B")]

    with patch.object(
        ui, "extract_card_info_openai", return_value=("Pikachu", "037", "", "", "", "", "")
    ), patch.object(ui, "lookup_sets_from_api", return_value=options), patch.object(
        ui, "identify_set_by_hash", return_value=[]
    ) as mock_hash:
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {
        "name": "Pikachu",
        "number": "037",
        "total": "",
        "set": "Set A",
        "set_code": "a",
        "orientation": 0,
        "set_format": "",
        "era": "",
    }
    mock_hash.assert_called_once()


def test_analyze_card_image_propagates_openai_era(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(
        ui,
        "extract_card_info_openai",
        return_value=("Pikachu", "037", "", "Test Era", "", "", ""),
    ) as mock_extract, patch.object(
        ui,
        "lookup_sets_from_api",
        return_value=[],
    ), patch.object(
        ui,
        "identify_set_by_hash",
        return_value=[],
    ) as mock_hash, patch.object(
        ui,
        "extract_set_code_ocr",
        return_value=[],
    ):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result["era"] == "Test Era"
    mock_extract.assert_called_once()
    mock_hash.assert_called_once()


def test_analyze_card_image_relaxed_validation(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("STRICT_SET_VALIDATION", "0")
    importlib.reload(ui)

    img = tmp_path / "x.jpg"
    img.write_bytes(b"data")

    payload = {
        "name": "Pikachu",
        "number": "037/198",
        "set_name": f"{SV01_NAME} EN",
        "era_name": "SV EN",
        "set_format": "text",
    }
    resp = SimpleNamespace(output_text=json.dumps(payload))

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=lambda *a, **k: resp)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    with patch.object(ui, "identify_set_by_hash", return_value=[]), patch.object(
        ui, "extract_set_code_ocr", return_value=[]
    ), patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image(str(img))

    assert result == {
        "name": "Pikachu",
        "number": "037",
        "total": "198",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "text",
        "era": ui.get_set_era(SV01_CODE),
    }
    importlib.reload(ui)


def test_analyze_card_image_hash_preempts_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    class DummyImage:
        size = (100, 100)

        def crop(self, *args, **kwargs):
            return self

        def convert(self, *a, **k):
            return self

    with patch.object(
        ui, "extract_card_info_openai", return_value=("Pikachu", "037", "", "", "", "", "")
    ) as mock_openai, patch.object(ui, "lookup_sets_from_api", return_value=[]), patch.object(
        ui, "identify_set_by_hash", return_value=[("x", "Set X", 0)]
    ) as mock_hash, patch.object(ui, "extract_set_code_ocr", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": "Set X",
        "set_code": "x",
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era("x"),
    }
    mock_hash.assert_called_once()
    mock_openai.assert_not_called()


def test_analyze_card_image_ocr(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(ui, "identify_set_by_hash", return_value=[]) as mock_hash, patch.object(
        ui, "extract_set_code_ocr", return_value=[SV01_CODE]
    ) as mock_ocr, patch.object(ui, "extract_card_info_openai") as mock_extract, patch.object(
        ui, "lookup_sets_from_api"
    ) as mock_lookup, patch.object(ui, "extract_name_number_ocr", return_value=("", "", "")):
        result = ui.analyze_card_image(str(logo_path))

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era(SV01_CODE),
    }
    mock_hash.assert_called_once()
    mock_ocr.assert_called_once()
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()


def test_analyze_card_image_step_numbers_after_openai_failure(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(ui, "identify_set_by_hash", return_value=[]), \
        patch.object(ui, "extract_card_info_openai", side_effect=Exception("boom")), \
        patch.object(ui, "extract_set_code_ocr", return_value=[]), \
        patch.object(ui, "extract_name_number_ocr", return_value=("", "", "")):
        ui.analyze_card_image(str(logo_path))

    out, _ = capsys.readouterr()
    assert "Step 3: Performing OCR fallback" in out


def test_analyze_card_image_ocr_unknown_code(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(ui, "identify_set_by_hash", return_value=[]) as mock_hash, patch.object(
        ui, "extract_set_code_ocr", return_value=["XYZ"]
    ) as mock_ocr, patch.object(ui, "extract_card_info_openai") as mock_extract, patch.object(
        ui, "lookup_sets_from_api"
    ) as mock_lookup, patch.object(ui, "extract_name_number_ocr", return_value=("", "", "")):
        result = ui.analyze_card_image(str(logo_path))

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": "",
        "set_code": "",
        "orientation": 0,
        "set_format": "",
        "era": "",
    }
    mock_hash.assert_called_once()
    mock_ocr.assert_called_once()
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()
    out, err = capsys.readouterr()
    assert "OCR produced unknown set code: XYZ" in out


def test_analyze_card_image_hash_shortcircuits_ocr(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(
        ui, "identify_set_by_hash", return_value=[(SV01_CODE, SV01_NAME, 0)]
    ) as mock_hash, patch.object(ui, "extract_set_code_ocr") as mock_ocr, patch.object(
        ui, "extract_card_info_openai"
    ) as mock_extract, patch.object(ui, "lookup_sets_from_api") as mock_lookup, patch.object(
        ui, "extract_name_number_ocr", return_value=("", "", "")
    ):
        result = ui.analyze_card_image(str(logo_path))

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era(SV01_CODE),
    }
    mock_hash.assert_called_once()
    mock_ocr.assert_not_called()
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()


def test_analyze_card_image_ocr_after_hash_failure(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(
        ui, "identify_set_by_hash", return_value=[("x", "Set X", ui.HASH_DIFF_THRESHOLD + 1)]
    ) as mock_hash, patch.object(
        ui, "extract_set_code_ocr", return_value=[SV01_CODE, "other"]
    ) as mock_ocr, patch.object(ui, "extract_card_info_openai") as mock_extract, patch.object(
        ui, "lookup_sets_from_api"
    ) as mock_lookup, patch.object(ui, "extract_name_number_ocr", return_value=("", "", "")):
        result = ui.analyze_card_image(str(logo_path))

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era(SV01_CODE),
    }
    mock_hash.assert_called_once()
    mock_ocr.assert_called_once()
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()


def test_extract_set_code_ocr_filters_single_letter(tmp_path, monkeypatch):
    img = Image.new("RGB", (10, 10), color="white")
    path = tmp_path / "img.png"
    img.save(path)

    with patch("pytesseract.image_to_string", return_value="E\n123\nSV01\n") as ocr:
        result = ui.extract_set_code_ocr(str(path), (0, 0, 10, 10))

    assert result == [SV01_CODE]
    ocr.assert_called_once()
    processed = ocr.call_args.args[0]
    assert processed.mode == "L"
    assert processed.size == (40, 8)
    assert (
        ocr.call_args.kwargs.get("config")
        == "--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ/-"
    )


def test_extract_set_code_ocr_crops_bottom_region(tmp_path):
    img = Image.new("L", (50, 50), color=0)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 40, 49, 49), fill=255)
    path = tmp_path / "img.png"
    img.convert("RGB").save(path)

    def fake_ocr(im, config=""):
        # After cropping bottom 20% (10px) with padding 5/2 and resizing x4
        assert im.size == (160, 24)
        assert all(p == 255 for p in im.getdata())
        return "SV01"

    with patch("pytesseract.image_to_string", side_effect=fake_ocr) as ocr:
        result = ui.extract_set_code_ocr(str(path), (0, 0, 50, 50), h_pad=5, v_pad=2)

    assert result == [SV01_CODE]
    ocr.assert_called_once()


def test_analyze_card_image_bad_json(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_info_openai", return_value=("", "", "", "", "", "", "")), \
        patch.object(ui, "lookup_sets_from_api", return_value=[]), \
        patch.object(ui, "extract_name_number_ocr", return_value=("", "", "")):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": "",
        "set_code": "",
        "orientation": 0,
        "set_format": "",
        "era": "",
    }


def test_analyze_card_image_ocr_name_number(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"

    with patch.object(ui, "identify_set_by_hash", return_value=[]), \
        patch.object(ui, "extract_card_info_openai", side_effect=Exception("boom")), \
        patch.object(ui, "extract_name_number_ocr", return_value=("Pikachu", "001", "")) as mock_name, \
        patch.object(ui, "lookup_sets_from_api", return_value=[(SV01_CODE, SV01_NAME)]), \
        patch.object(ui, "extract_set_code_ocr", return_value=[]):
        result = ui.analyze_card_image(str(logo_path))

    assert result == {
        "name": "Pikachu",
        "number": "001",
        "total": "",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era(SV01_CODE),
    }
    mock_name.assert_called_once()


def test_analyze_card_image_truncated_code_block(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_info_openai", return_value=("Pikachu", "037", "159", "", "", "", "")), \
        patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {
        "name": "Pikachu",
        "number": "037",
        "total": "159",
        "set": "",
        "set_code": "",
        "orientation": 0,
        "set_format": "",
        "era": "",
    }


def test_analyze_card_image_leading_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with patch.object(ui, "extract_card_info_openai", return_value=("Pikachu", "037", "159", "", "", "", "")), \
        patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg")

    assert result == {
        "name": "Pikachu",
        "number": "037",
        "total": "159",
        "set": "",
        "set_code": "",
        "orientation": 0,
        "set_format": "",
        "era": "",
    }


def test_analyze_card_image_local_hash(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / f"{SV01_CODE}.png"
    monkeypatch.setattr(ui, "extract_name_number_ocr", lambda *a, **k: ("", "", ""))
    with patch.object(ui, "extract_card_info_openai") as mock_extract, patch.object(
        ui, "lookup_sets_from_api"
    ) as mock_lookup:
        result = ui.analyze_card_image(str(logo_path))

    assert result == {
        "name": "",
        "number": "",
        "total": "",
        "set": SV01_NAME,
        "set_code": SV01_CODE,
        "orientation": 0,
        "set_format": "",
        "era": ui.get_set_era(SV01_CODE),
    }
    mock_extract.assert_not_called()
    mock_lookup.assert_not_called()


def test_analyze_card_image_translate_name(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch.object(
        ui,
        "extract_card_info_openai",
        return_value=("\u30d4\u30ab\u30c1\u30e5\u30a6", "037", "159", "", "", "", ""),
    ), patch(
        "openai.chat.completions.create", return_value=resp_translate
    ) as mock_create, patch.object(ui, "lookup_sets_from_api", return_value=[]):
        result = ui.analyze_card_image("/tmp/img.jpg", translate_name=True)

    assert result == {
        "name": "Pikachu",
        "number": "037",
        "total": "159",
        "set": "",
        "set_code": "",
        "orientation": 0,
        "set_format": "",
        "era": "",
    }
    mock_create.assert_called_once()


def test_analyze_card_image_debug_rect(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    img_path = tmp_path / "wide.gif"
    Image.new("RGB", (800, 600), color="white").save(img_path)
    monkeypatch.setattr(ui, "extract_set_code_ocr", lambda *a, **k: [])
    monkeypatch.setattr(ui, "identify_set_by_hash", lambda *a, **k: [])
    monkeypatch.setattr(ui, "extract_name_number_ocr", lambda *a, **k: ("", "", ""))
    result = ui.analyze_card_image(str(img_path), debug=True)
    assert result["orientation"] == 0
    rect = result.get("rect")
    assert isinstance(rect, tuple) and len(rect) == 4


def test_analyze_card_image_orientation(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    img_path = tmp_path / "wide.jpg"
    Image.new("RGB", (200, 100), color="white").save(img_path)

    with patch.object(ui, "extract_set_code_ocr", return_value=[]), \
         patch.object(ui, "identify_set_by_hash", return_value=[]), \
         patch.object(ui, "extract_card_info_openai", return_value=("", "", "", "", "", "", "")), \
         patch.object(ui, "lookup_sets_from_api", return_value=[]), \
         patch.object(ui, "extract_name_number_ocr", return_value=("", "", "")):
        result = ui.analyze_card_image(str(img_path))

    assert result["orientation"] == 0


def test_preview_callback_called(tmp_path, monkeypatch):
    """Ensure preview callback runs for each candidate region."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    img_path = tmp_path / "card.png"
    Image.new("RGB", (200, 300), color="white").save(img_path)

    preview_calls = []

    def preview(rect, img):
        preview_calls.append(rect)

    monkeypatch.setattr(ui, "extract_set_code_ocr", lambda *a, **k: [])
    monkeypatch.setattr(ui, "identify_set_by_hash", lambda *a, **k: [])
    monkeypatch.setattr(ui, "extract_name_number_ocr", lambda *a, **k: ("", "", ""))

    with Image.open(img_path) as im:
        ui.analyze_card_image(
            str(img_path),
            preview_cb=preview,
            preview_image=im,
        )

    rects = ui.get_symbol_rects(200, 300)
    assert preview_calls[: len(rects)] == rects


def test_analyze_card_image_horizontal_scan(tmp_path, monkeypatch):
    """Ensure horizontal scans are rotated and hashed correctly."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    img_path = tmp_path / "horizontal.png"
    Image.new("RGB", (400, 200), color="white").save(img_path)

    expected_rect = ui.get_symbol_rects(400, 200)[0]

    def fake_hash(path, rect):
        assert rect == expected_rect
        return [(SV01_CODE, SV01_NAME, 0)]

    monkeypatch.setattr(ui, "identify_set_by_hash", fake_hash)
    monkeypatch.setattr(ui, "extract_card_info_openai", lambda *a, **k: ("", "", "", "", "", "", ""))
    monkeypatch.setattr(ui, "lookup_sets_from_api", lambda *a, **k: [])
    monkeypatch.setattr(ui, "extract_set_code_ocr", lambda *a, **k: [])
    monkeypatch.setattr(ui, "extract_name_number_ocr", lambda *a, **k: ("", "", ""))

    result = ui.analyze_card_image(str(img_path))

    assert result["set"] == SV01_NAME
    assert result["set_code"] == SV01_CODE
    assert result["orientation"] == 0


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

    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func: func()),
        lang_var=DummyVar("JP"),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": DummyVar("")},
        index=0,
        update_set_options=lambda: None,
        update_set_area_preview=lambda *a, **k: None,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)

    resp_translate = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pikachu"))]
    )

    with patch.object(
        ui,
        "extract_card_info_openai",
        return_value=("\u30d4\u30ab\u30c1\u30e5\u30a6", "001", "", "", "", "", ""),
    ), patch(
        "openai.chat.completions.create", return_value=resp_translate
    ), patch.object(ui, "lookup_sets_from_api", return_value=[]):
        ui.CardEditorApp._analyze_and_fill(dummy, "/tmp/x", 0)

    name_entry.insert.assert_called_with(0, "Pikachu")


def test_analyze_and_fill_uses_hash_db(monkeypatch):
    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    price_entry = MagicMock()
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()
    price_entry.delete = MagicMock()
    price_entry.insert = MagicMock()

    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func: func()),
        lang_var=None,
        entries={
            "nazwa": name_entry,
            "numer": num_entry,
            "set": set_var,
            "era": DummyVar(""),
            "cena": price_entry,
        },
        index=0,
        update_set_options=lambda: None,
        update_set_area_preview=lambda *a, **k: None,
        hash_db=SimpleNamespace(
            best_match=lambda fp, max_distance=None: SimpleNamespace(
                meta={"warehouse_code": "K1", "set_code": SV01_CODE},
                distance=0,
            )
        ),
        auto_lookup=True,
        current_fingerprint=None,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(
        dummy, ui.CardEditorApp
    )
    csv_row = {
        "name": "Pika",
        "number": "001",
        "set": SV01_NAME,
        "variant": None,
        "price": "10",
    }
    monkeypatch.setattr(ui.csv_utils, "get_row_by_code", lambda code: csv_row)

    class DummyImage:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def convert(self, *a, **k):
            return self

    monkeypatch.setattr(ui, "compute_fingerprint", lambda img: "fp")
    with patch.object(ui.Image, "open", return_value=DummyImage()), patch.object(
        ui, "analyze_card_image",
    ) as mock_analyze:
        ui.CardEditorApp._analyze_and_fill(dummy, "/tmp/x", 0)

    mock_analyze.assert_not_called()
    name_entry.insert.assert_called_with(0, "Pika")
    num_entry.insert.assert_called_with(0, "1")
    set_var.set.assert_called_with(SV01_NAME)
    price_entry.insert.assert_called_with(0, "10")
    assert dummy.entries["era"].value == ui.get_set_era(SV01_NAME)


def test_analyze_and_fill_runs_full_pipeline_for_non_matching_card(tmp_path):
    """Ensure analysis is run when fingerprint distance is non-zero."""
    # create and store first card fingerprint
    db = HashDB(str(tmp_path / "hashes.sqlite"))

    def _create_image(path, variant=False):
        img = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(img)
        if variant:
            draw.rectangle([0, 0, 20, 20], fill="black")
        else:
            draw.rectangle([16, 16, 48, 48], fill="black")
        img.save(path)
        return img

    first = tmp_path / "first.png"
    _create_image(first)
    db.add_card_from_image(str(first), meta={"name": "First"})

    second = tmp_path / "second.png"
    _create_image(second, variant=True)

    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()

    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func: func()),
        lang_var=None,
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": DummyVar("")},
        index=0,
        update_set_options=lambda: None,
        update_set_area_preview=lambda *a, **k: None,
        hash_db=db,
        auto_lookup=True,
        current_fingerprint=None,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(
        dummy, ui.CardEditorApp
    )

    with patch.object(
        ui,
        "analyze_card_image",
        return_value={
            "name": "Second",
            "number": "002",
            "total": "",
            "set": "",
            "set_code": "",
            "orientation": 0,
            "set_format": "",
            "era": "",
        },
    ) as mock_analyze:
        ui.CardEditorApp._analyze_and_fill(dummy, str(second), 0)

    mock_analyze.assert_called_once()
    name_entry.insert.assert_called_with(0, "Second")


def test_show_card_fills_from_inventory(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        f"name;numer;set\nPikachu;001;{SV01_NAME}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WAREHOUSE_CSV", str(csv_path))
    import importlib
    import kartoteka.csv_utils as csv_utils
    importlib.reload(csv_utils)
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
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": MagicMock()},
        type_vars={},
        card_cache={},
        file_to_key={img.name: f"Pikachu|001|{SV01_NAME}|{ui.get_set_era(SV01_CODE)}"},
        _guess_key_from_filename=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )
    dummy._analyze_and_fill = MagicMock()

    dummy.lookup_inventory_entry = ui.CardEditorApp.lookup_inventory_entry.__get__(dummy, ui.CardEditorApp)

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

        def convert(self, *a, **k):
            return self

    with patch.object(ui.Image, "open", return_value=DummyImage()), \
         patch.object(ui.ImageTk, "PhotoImage", return_value=MagicMock()), \
         patch.object(ui, "analyze_card_image", return_value={}) as mock_analyze:
        ui.CardEditorApp.show_card(dummy)

    mock_analyze.assert_not_called()
    name_entry.insert.assert_called_with(0, "Pikachu")
    num_entry.insert.assert_called_with(0, "1")
    set_var.set.assert_called_with(SV01_NAME)


def test_show_card_skips_fingerprint_without_auto_lookup(tmp_path, monkeypatch):
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

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def convert(self, *a, **k):
            return self
    class DummyThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=MagicMock(),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": MagicMock()},
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
        root=SimpleNamespace(after=lambda *a, **k: None),
        auto_lookup=False,
        hash_db=SimpleNamespace(best_match=lambda *a, **k: None),
    )

    dummy._analyze_and_fill = lambda *a, **k: None

    fp_mock = MagicMock()
    monkeypatch.setattr(ui, "compute_fingerprint", fp_mock)
    monkeypatch.setattr(ui, "analyze_card_image", lambda *a, **k: {})
    monkeypatch.setattr(ui.threading, "Thread", DummyThread)
    with patch.object(ui.Image, "open", return_value=DummyImage()), patch.object(
        ui.ImageTk, "PhotoImage", return_value=MagicMock()
    ):
        ui.CardEditorApp.show_card(dummy)

    fp_mock.assert_not_called()


def test_show_card_fingerprint_lookup_thread(tmp_path, monkeypatch):
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

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def convert(self, *a, **k):
            return self

    class DummyThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    best_match = MagicMock(
        return_value=SimpleNamespace(
            meta={"nazwa": "Pika", "numer": "001", "set": "Set X"},
            distance=0,
        )
    )
    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=MagicMock(),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": MagicMock()},
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
        root=SimpleNamespace(after=lambda delay, func: func()),
        auto_lookup=True,
        hash_db=SimpleNamespace(best_match=best_match),
    )
    dummy._analyze_and_fill = ui.CardEditorApp._analyze_and_fill.__get__(
        dummy, ui.CardEditorApp
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(
        dummy, ui.CardEditorApp
    )

    fp_mock = MagicMock(return_value="fp")
    analyze_mock = MagicMock(return_value={})
    monkeypatch.setattr(ui, "compute_fingerprint", fp_mock)
    monkeypatch.setattr(ui, "analyze_card_image", analyze_mock)
    monkeypatch.setattr(ui.threading, "Thread", DummyThread)
    with patch.object(ui.Image, "open", return_value=DummyImage()), patch.object(
        ui.ImageTk, "PhotoImage", return_value=MagicMock()
    ):
        ui.CardEditorApp.show_card(dummy)

    fp_mock.assert_called_once()
    best_match.assert_called_once_with("fp", max_distance=ui.HASH_MATCH_THRESHOLD)
    analyze_mock.assert_not_called()
    name_entry.insert.assert_called_with(0, "Pika")


def test_show_card_fingerprint_lookup_no_match_triggers_analyzer(tmp_path, monkeypatch):
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

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def convert(self, *a, **k):
            return self

    class DummyThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    best_match = MagicMock(return_value=None)
    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=MagicMock(),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var, "era": MagicMock()},
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
        root=SimpleNamespace(after=lambda delay, func: func()),
        auto_lookup=True,
        hash_db=SimpleNamespace(best_match=best_match),
    )
    dummy._analyze_and_fill = ui.CardEditorApp._analyze_and_fill.__get__(
        dummy, ui.CardEditorApp
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(
        dummy, ui.CardEditorApp
    )

    fp_mock = MagicMock(return_value="fp")
    analyze_mock = MagicMock(return_value={})
    monkeypatch.setattr(ui, "compute_fingerprint", fp_mock)
    monkeypatch.setattr(ui, "analyze_card_image", analyze_mock)
    monkeypatch.setattr(ui.threading, "Thread", DummyThread)
    with patch.object(ui.Image, "open", return_value=DummyImage()), patch.object(
        ui.ImageTk, "PhotoImage", return_value=MagicMock()
    ):
        ui.CardEditorApp.show_card(dummy)

    assert fp_mock.call_count == 2
    assert best_match.call_args_list == [
        call("fp", max_distance=ui.HASH_MATCH_THRESHOLD),
        call("fp", max_distance=ui.HASH_MATCH_THRESHOLD),
    ]
    analyze_mock.assert_called_once()


def test_fetch_card_data_auto_set(monkeypatch):
    class DummyEntry:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def delete(self, *args, **kwargs):
            self.value = ""

        def insert(self, index, val):
            self.value = str(val)

    class DummyVar:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    entries = {
        "nazwa": DummyEntry("Pikachu"),
        "numer": DummyEntry("037/102"),
        "set": DummyVar(""),
        "cena": DummyEntry(),
        "psa10_price": DummyEntry(),
    }

    dummy = SimpleNamespace(
        entries=entries,
        type_vars={
            "Reverse": SimpleNamespace(get=lambda: False),
            "Holo": SimpleNamespace(get=lambda: False),
        },
        get_price_from_db=lambda *a, **k: None,
        fetch_card_price=lambda *a, **k: None,
        fetch_psa10_price=lambda *a, **k: None,
        apply_variant_multiplier=lambda price, **kw: price,
        log=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
    )

    with patch.object(
        ui, "lookup_sets_from_api", return_value=[("sv01", SV01_NAME)]
    ) as mock_lookup, patch.object(ui.messagebox, "showinfo"):
        ui.CardEditorApp.fetch_card_data(dummy)

    assert entries["set"].get() == SV01_NAME
    mock_lookup.assert_called_once_with("Pikachu", "37", "102")

