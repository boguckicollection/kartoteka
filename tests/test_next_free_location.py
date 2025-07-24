import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
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
    assert first == "K01R1P0002"
    dummy.output_data.append({"warehouse_code": first})
    second = ui.CardEditorApp.next_free_location(dummy)
    assert second == "K01R1P0004"


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
    seq = iter([2, 1, 5])
    monkeypatch.setattr(ui.simpledialog, "askinteger", lambda *a, **k: next(seq))

    dummy = SimpleNamespace(
        start_frame=None,
        setup_editor_ui=lambda: None,
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        log=lambda *a, **k: None,
        show_card=lambda *a, **k: None,
    )

    ui.CardEditorApp.load_images(dummy)

    expected = (2 - 1) * 4000 + (1 - 1) * 1000 + (5 - 1)
    assert dummy.starting_idx == expected
    assert ui.CardEditorApp.next_free_location(dummy) == "K02R1P0005"

