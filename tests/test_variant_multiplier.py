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

def test_get_set_code_additionals():
    assert ui.get_set_code("Prismatic Evolutions: Additionals") == "xpre"

def test_apply_variant_multiplier_balls():
    dummy = SimpleNamespace(type_vars={
        "Pokeball": DummyVar(True),
        "Masterball": DummyVar(False)
    })
    price = ui.CardEditorApp.apply_variant_multiplier(dummy, 10)
    assert price == 10 * ui.POKEBALL_MULTIPLIER

    dummy = SimpleNamespace(type_vars={
        "Pokeball": DummyVar(False),
        "Masterball": DummyVar(True)
    })
    price = ui.CardEditorApp.apply_variant_multiplier(dummy, 10)
    assert price == 10 * ui.MASTERBALL_MULTIPLIER
