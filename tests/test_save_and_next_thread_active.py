import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Provide dummy customtkinter before importing UI module
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402


def test_save_and_next_while_analysis_running():
    save_mock = MagicMock()
    show_card_mock = MagicMock()
    app = SimpleNamespace(
        current_analysis_thread=object(),
        save_current_data=save_mock,
        index=0,
        cards=[1, 2],
        show_card=show_card_mock,
    )
    with patch.object(ui.messagebox, "showwarning") as mock_warn:
        ui.CardEditorApp.save_and_next(app)
    mock_warn.assert_called_once()
    save_mock.assert_not_called()
    show_card_mock.assert_not_called()
    assert app.index == 0
