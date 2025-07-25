import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)

def test_back_to_welcome_requires_confirmation():
    dummy = SimpleNamespace(
        pricing_frame=None,
        shoper_frame=None,
        frame=None,
        magazyn_frame=None,
        location_frame=None,
        setup_welcome_screen=MagicMock(),
        in_scan=True,
    )

    with patch("tkinter.messagebox.askyesno", return_value=False) as ask:
        ui.CardEditorApp.back_to_welcome(dummy)
        ask.assert_called_once_with(
            "Potwierdzenie", "Czy na pewno chcesz przerwać?"
        )
    dummy.setup_welcome_screen.assert_not_called()
    assert dummy.in_scan

