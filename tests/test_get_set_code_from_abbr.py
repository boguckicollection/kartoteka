import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)


def test_get_set_code_from_abbreviation():
    assert ui.get_set_code("DRI") == "sv10"


def test_get_set_code_strips_suffixes_to_full_name():
    for suffix in ("", " EN", " JP"):
        code = ui.get_set_code(f"DRI{suffix}")
        assert code == "sv10"
        assert ui.get_set_name(code) == "Destined Rivals"
