import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_repack_after_removal():
    dummy = SimpleNamespace(
        output_data=[
            {"warehouse_code": "K01R1P0001"},
            {"warehouse_code": "K01R1P0003"},
        ],
        mag_canvases=[],
        mag_box_photo=SimpleNamespace(width=lambda: 0, height=lambda: 0),
        refresh_magazyn=lambda: None,
    )
    ui.CardEditorApp.repack_column(dummy, 1, 1)
    assert dummy.output_data[1]["warehouse_code"] == "K01R1P0002"


def test_repack_within_row():
    dummy = SimpleNamespace(
        output_data=[{"warehouse_code": "K01R1P0001;K01R1P0003"}],
        mag_canvases=[],
        mag_box_photo=SimpleNamespace(width=lambda: 0, height=lambda: 0),
        refresh_magazyn=lambda: None,
    )
    ui.CardEditorApp.repack_column(dummy, 1, 1)
    assert dummy.output_data[0]["warehouse_code"] == "K01R1P0001;K01R1P0002"
