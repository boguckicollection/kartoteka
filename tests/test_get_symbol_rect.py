import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_get_symbol_rects_all_corners():
    w, h = 1000, 1400
    rects = ui.get_symbol_rects(w, h)
    assert rects[0] == (0, int(h * 0.75), int(w * 0.35), h)
    assert rects[1] == (int(w * 0.65), int(h * 0.75), w, h)
    assert rects[2] == (0, 0, int(w * 0.35), int(h * 0.25))
    assert rects[3] == (int(w * 0.65), 0, w, int(h * 0.25))


def test_get_symbol_rects_small_image():
    w, h = 80, 90
    assert ui.get_symbol_rects(w, h) == [(0, 0, w, h)]
