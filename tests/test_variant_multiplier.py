import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)

class DummyVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

def test_apply_variant_multiplier_reverse_holo():
    dummy = SimpleNamespace()
    price = ui.CardEditorApp.apply_variant_multiplier(dummy, 10, is_reverse=True)
    assert price == 10 * ui.HOLO_REVERSE_MULTIPLIER

    price = ui.CardEditorApp.apply_variant_multiplier(dummy, 10, is_holo=True)
    assert price == 10 * ui.HOLO_REVERSE_MULTIPLIER
