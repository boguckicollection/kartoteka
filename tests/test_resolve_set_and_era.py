import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock
import logging

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)  # ensure mappings are loaded


def test_resolve_set_and_era_empty_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="kartoteka.ui"):
        result = ui.resolve_set_and_era("", "", "")
    assert result == ("", "", "")
    assert not caplog.records


def test_resolve_set_and_era_unknown_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="kartoteka.ui"):
        result = ui.resolve_set_and_era("Nonexistent Set", "", "")
    assert result == ("Nonexistent Set", "Nonexistent Set", "")
    assert "Unknown set or era" in caplog.text
