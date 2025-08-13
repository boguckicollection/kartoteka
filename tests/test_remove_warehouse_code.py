import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.ui as ui


def test_remove_warehouse_code_updates_stats():
    app = SimpleNamespace(
        output_data=[{"warehouse_code": "K1R1P1"}],
        repack_column=lambda box, col: None,
        update_inventory_stats=MagicMock(),
    )
    ui.CardEditorApp.remove_warehouse_code(app, "K1R1P1")
    assert app.output_data == []
    app.update_inventory_stats.assert_called_once()
