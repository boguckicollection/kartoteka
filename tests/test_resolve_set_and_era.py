import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)


def test_resolve_set_and_era_fuzzy_scarlet_violet():
    name, code, era = ui.resolve_set_and_era("Obsidian Flame")
    assert name == "Obsidian Flames"
    assert code == "sv03"
    assert era == "Scarlet & Violet"


def test_resolve_set_and_era_fuzzy_sword_shield():
    name, code, era = ui.resolve_set_and_era("Darkness Ablze")
    assert name == "Darkness Ablaze"
    assert code == "swsh3"
    assert era == "Sword & Shield"


def test_resolve_set_and_era_total_unique():
    name, code, era = ui.resolve_set_and_era("", "", "", "1", "230")
    assert name == "Obsidian Flames"
    assert code == "sv03"
    assert era == "Scarlet & Violet"


def test_resolve_set_and_era_total_ambiguous():
    name, code, era = ui.resolve_set_and_era("", "", "", "1", "75")
    assert name == ""
    assert code == ""
    assert era == ""
