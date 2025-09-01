import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Provide dummy customtkinter before importing UI module
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402


def test_save_and_next_on_last_card():
    show_card_mock = MagicMock()
    app = SimpleNamespace(
        current_analysis_thread=None,
        save_current_data=lambda: None,
        index=0,
        cards=[1],
        show_card=show_card_mock,
    )
    with patch.object(ui.messagebox, "showinfo") as mock_info:
        ui.CardEditorApp.save_and_next(app)
    assert app.index == 0
    mock_info.assert_called_once_with("Info", "To jest ostatnia karta.")
    show_card_mock.assert_not_called()
