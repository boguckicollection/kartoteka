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
    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / "sv01.png"
    expected_name = ui.get_set_name("sv01")
    with Image.open(logo_path) as im:
        w, h = im.size
    matches = ui.identify_set_by_hash(str(logo_path), (0, 0, w, h))
    assert len(matches) >= 4
    code, name, diff = matches[0]
    assert code == "sv01"
    assert name == expected_name
    assert diff == 0


def test_identify_set_by_hash_maps_code_to_name():
    logo_path = Path(__file__).resolve().parents[1] / "set_logos" / "sv01.png"
    expected_name = ui.get_set_name("sv01")
    with Image.open(logo_path) as im:
        w, h = im.size
    matches = ui.identify_set_by_hash(str(logo_path), (0, 0, w, h))
    assert len(matches) >= 4
    code, name, _ = matches[0]
    assert ui.get_set_name(code) == name
    assert name == expected_name
