import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_load_set_logo_uris_limit_none_returns_all():
    expected = {
        os.path.splitext(f)[0]
        for f in os.listdir(ui.SET_LOGO_DIR)
        if os.path.isfile(os.path.join(ui.SET_LOGO_DIR, f))
        and f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
    }
    logos = ui.load_set_logo_uris(limit=None)
    assert set(logos.keys()) == expected
