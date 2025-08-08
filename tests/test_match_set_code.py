import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock


sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)  # ensure globals use stubbed modules


def test_match_set_code_exact():
    assert ui.match_set_code("swsh11") == "swsh11"
    assert ui.match_set_code("SWSH11") == "swsh11"


def test_match_set_code_fuzzy():
    assert ui.match_set_code("swsh-11") == "swsh11"


def test_match_set_code_weak_match_rejected():
    assert ui.match_set_code("sws-111") == ""


def test_match_set_code_unknown():
    assert ui.match_set_code("unknown") == ""

