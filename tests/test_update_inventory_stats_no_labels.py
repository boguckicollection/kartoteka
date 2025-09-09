import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# Provide dummy customtkinter before importing the UI module
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.ui as ui  # noqa: E402


def test_update_inventory_stats_without_labels(monkeypatch):
    """Calling update_inventory_stats without labels should not error."""
    monkeypatch.setattr(
        ui.csv_utils,
        "get_inventory_stats",
        lambda path=ui.csv_utils.WAREHOUSE_CSV, force=False: (1, 2.0, 3, 4.0),
    )
    app = SimpleNamespace()
    ui.CardEditorApp.update_inventory_stats(app)
