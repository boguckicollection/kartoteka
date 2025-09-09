import importlib
import sys
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_refresh_magazyn_skips_reload_if_mtime_unchanged(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n", encoding="utf-8"
    )

    sys.modules.setdefault("customtkinter", MagicMock())
    sys.modules.setdefault("tkinter", MagicMock())
    sys.modules.setdefault("tkinter.ttk", MagicMock())
    sys.modules.setdefault("PIL", MagicMock())
    sys.modules.setdefault("PIL.Image", MagicMock())
    sys.modules.setdefault("PIL.ImageTk", MagicMock())
    sys.modules.setdefault("imagehash", MagicMock())
    sys.modules.setdefault("openai", MagicMock())
    sys.modules.setdefault("requests", MagicMock())
    sys.modules.setdefault("pydantic", MagicMock())
    sys.modules.setdefault("pytesseract", MagicMock())
    sys.modules.setdefault("dotenv", MagicMock())
    sys.modules.setdefault("numpy", MagicMock())
    sys.path.append(str(Path(__file__).resolve().parents[1]))

    import kartoteka.ui as ui
    importlib.reload(ui)

    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))

    mtime = os.path.getmtime(csv_path)
    reload_called = False

    def reload_mock():
        nonlocal reload_called
        reload_called = True

    app = SimpleNamespace(
        _mag_csv_mtime=mtime,
        reload_mag_cards=reload_mock,
        _update_mag_list=lambda: None,
        mag_progressbars={},
    )

    ui.CardEditorApp.refresh_magazyn(app)
    assert not reload_called
