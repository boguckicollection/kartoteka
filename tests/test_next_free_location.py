import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("dotenv", MagicMock(load_dotenv=lambda *a, **k: None, set_key=lambda *a, **k: None))
sys.modules.setdefault("pydantic", MagicMock(BaseModel=object))
sys.modules.setdefault("pytesseract", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_next_free_location_sequential():
    dummy = SimpleNamespace(
        output_data=[
            {"warehouse_code": "K01R1P0001"},
            None,
            {"warehouse_code": "K01R1P0003"},
        ],
    )
    dummy.generate_location = lambda idx: ui.CardEditorApp.generate_location(dummy, idx)
    first = ui.CardEditorApp.next_free_location(dummy)
    assert first == "K01R1P0004"
    dummy.output_data.append({"warehouse_code": first})
    second = ui.CardEditorApp.next_free_location(dummy)
    assert second == "K01R1P0005"


def test_next_free_location_from_start_idx():
    dummy = SimpleNamespace(
        output_data=[{"warehouse_code": "K01R1P0001"}],
        starting_idx=(2 - 1) * 4000 + (1 - 1) * 1000 + (1 - 1),
    )
    dummy.generate_location = lambda idx: ui.CardEditorApp.generate_location(dummy, idx)
    first = ui.CardEditorApp.next_free_location(dummy)
    assert first == "K02R1P0001"


def test_load_images_sets_start(monkeypatch, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"data")

    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda: str(tmp_path))
    monkeypatch.setattr(
        ui.filedialog, "asksaveasfilename", lambda **k: str(tmp_path / "session.csv")
    )

    dummy = SimpleNamespace(
        start_frame=None,
        setup_editor_ui=lambda: None,
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        log=lambda *a, **k: None,
        show_card=lambda *a, **k: None,
        start_box_var=SimpleNamespace(get=lambda: 2),
        start_col_var=SimpleNamespace(get=lambda: 1),
        start_pos_var=SimpleNamespace(get=lambda: 5),
        scan_folder_var=SimpleNamespace(get=lambda: "", set=lambda v: None),
    )

    ui.CardEditorApp.browse_scans(dummy)

    expected = (2 - 1) * 4000 + (1 - 1) * 1000 + (5 - 1)
    assert dummy.starting_idx == expected
    assert ui.CardEditorApp.next_free_location(dummy) == "K02R1P0005"


def test_browse_scans_box100(monkeypatch, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"data")

    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda: str(tmp_path))
    monkeypatch.setattr(
        ui.filedialog, "asksaveasfilename", lambda **k: str(tmp_path / "session.csv")
    )

    dummy = SimpleNamespace(
        start_frame=None,
        setup_editor_ui=lambda: None,
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        log=lambda *a, **k: None,
        show_card=lambda *a, **k: None,
        start_box_var=SimpleNamespace(get=lambda: 100),
        start_col_var=SimpleNamespace(get=lambda: 1),
        start_pos_var=SimpleNamespace(get=lambda: 5),
        scan_folder_var=SimpleNamespace(get=lambda: "", set=lambda v: None),
    )

    ui.CardEditorApp.browse_scans(dummy)

    expected = ui.BOX_COUNT * ui.BOX_CAPACITY + 4
    assert dummy.starting_idx == expected
    assert ui.CardEditorApp.next_free_location(dummy) == "K100R1P0005"


def test_browse_scans_sets_starting_idx_for_box100(monkeypatch, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"data")

    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda: str(tmp_path))
    monkeypatch.setattr(
        ui.filedialog, "asksaveasfilename", lambda **k: str(tmp_path / "session.csv")
    )

    dummy = SimpleNamespace(
        start_frame=None,
        setup_editor_ui=lambda: None,
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        log=lambda *a, **k: None,
        show_card=lambda *a, **k: None,
        start_box_var=SimpleNamespace(get=lambda: 100),
        start_col_var=SimpleNamespace(get=lambda: 1),
        start_pos_var=SimpleNamespace(get=lambda: 5),
        scan_folder_var=SimpleNamespace(get=lambda: "", set=lambda v: None),
    )

    ui.CardEditorApp.browse_scans(dummy)

    assert dummy.starting_idx == ui.BOX_COUNT * ui.BOX_CAPACITY + 4
    assert ui.CardEditorApp.next_free_location(dummy) == "K100R1P0005"

