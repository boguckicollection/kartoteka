import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)

def test_get_set_abbr_from_json():
    assert ui.get_set_abbr("Paldean Fates") == "PAF"

