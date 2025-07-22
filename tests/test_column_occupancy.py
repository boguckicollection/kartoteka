import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui


def test_split_codes_counted():
    importlib.reload(ui)
    dummy = SimpleNamespace(output_data=[{"warehouse_code": "K1R1P1;K1R1P2"}])
    occ = ui.CardEditorApp.compute_column_occupancy(dummy)
    assert occ[1][1] == 2
