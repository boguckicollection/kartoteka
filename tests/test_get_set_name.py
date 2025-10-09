import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock
import logging

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)  # ensure globals use stubbed modules


def test_get_set_name_unknown_triggers_warning(caplog):
    code = "not_in_map"
    with caplog.at_level(logging.WARNING, logger="kartoteka.ui"):
        result = ui.get_set_name(code)
    assert result == code
    assert "Weryfikacja ręczna wymagana" in caplog.text


def test_get_set_name_from_abbr():
    assert ui.get_set_name("DRI") == "Destined Rivals"
