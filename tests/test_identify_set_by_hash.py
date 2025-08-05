import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui  # noqa: E402
importlib.reload(ui)  # ensure globals use stubbed modules


def test_identify_set_by_hash_match():
    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / "base1.png"
    with Image.open(logo_path) as im:
        w, h = im.size
    code, diff = ui.identify_set_by_hash(str(logo_path), (0, 0, w, h))
    assert code == "base1"
    assert diff == 0
