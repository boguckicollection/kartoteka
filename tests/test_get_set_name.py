import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)  # ensure globals use stubbed modules


def test_get_set_name_unknown_triggers_warning(capsys):
    code = "not_in_map"
    result = ui.get_set_name(code)
    captured = capsys.readouterr()
    assert result == code
    assert "Weryfikacja ręczna wymagana" in captured.out
