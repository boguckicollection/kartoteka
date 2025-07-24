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

def test_add_and_clear_price_pool():
    dummy = SimpleNamespace(
        price_pool_total=0.0,
        price_reverse_var=DummyVar(False),
        current_price_info={"price_pln": 10},
        pool_total_label=MagicMock(config=MagicMock()),
        type_vars={},
    )
    dummy.apply_variant_multiplier = ui.CardEditorApp.apply_variant_multiplier.__get__(dummy, ui.CardEditorApp)
    ui.CardEditorApp.add_to_price_pool(dummy)
    assert dummy.price_pool_total == 10
    dummy.price_reverse_var = DummyVar(True)
    ui.CardEditorApp.add_to_price_pool(dummy)
    assert dummy.price_pool_total == 10 + 10 * ui.HOLO_REVERSE_MULTIPLIER
    ui.CardEditorApp.clear_price_pool(dummy)
    assert dummy.price_pool_total == 0.0
