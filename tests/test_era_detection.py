import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)  # ensure mappings are loaded


def test_get_set_era_by_code():
    assert ui.get_set_era("sv01") == "Scarlet & Violet"
    assert ui.get_set_era("swsh1") == "Sword & Shield"


def test_get_set_era_by_name():
    assert ui.get_set_era("Obsidian Flames") == "Scarlet & Violet"
    assert ui.get_set_era("Darkness Ablaze") == "Sword & Shield"
