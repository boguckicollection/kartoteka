import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Provide dummy customtkinter before importing UI module
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import DummyCTkLabel  # noqa: E402
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402


def test_update_inventory_stats_empty_shows_message(monkeypatch):
    app = SimpleNamespace(
        inventory_count_label=DummyCTkLabel(),
        inventory_value_label=DummyCTkLabel(),
    )
    monkeypatch.setattr(
        ui.csv_utils,
        "get_inventory_stats",
        lambda path=ui.csv_utils.WAREHOUSE_CSV, force=False: (0, 0.0, 0, 0.0),
    )
    with patch.object(ui.messagebox, "showinfo") as mock_info:
        ui.CardEditorApp.update_inventory_stats(app)
    mock_info.assert_called_once()
    assert mock_info.call_args[0][1] == "Brak kart w magazynie"
