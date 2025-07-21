import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_split_codes_counted():
    import main
    importlib.reload(main)
    dummy = SimpleNamespace(output_data=[{"warehouse_code": "K1R1P1;K1R1P2"}])
    occ = main.CardEditorApp.compute_column_occupancy(dummy)
    assert occ[1][1] == 2
