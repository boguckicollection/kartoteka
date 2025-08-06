import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_get_symbol_rect_bottom_left():
    w, h = 1000, 1400
    assert ui.get_symbol_rect(w, h) == (0, int(h * 0.75), int(w * 0.35), h)
