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

