import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_refresh_magazyn_uses_cached_columns(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text("name;number;set;warehouse_code;price;image;sold\n", encoding="utf-8")

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

    def boom():  # pragma: no cover - ensures no file read
        raise AssertionError("compute_column_occupancy called")

    monkeypatch.setattr(ui.storage, "compute_column_occupancy", boom)

    class DummyBar:
        def __init__(self):
            self.value = None

        def set(self, value):
            self.value = value

    class DummyLabel:
        def __init__(self):
            self.kwargs = {}

        def configure(self, **kwargs):
            self.kwargs.update(kwargs)

    bar1 = DummyBar()
    bar2 = DummyBar()
    lbl1 = DummyLabel()
    lbl2 = DummyLabel()

    app = SimpleNamespace(
        _mag_csv_mtime=os.path.getmtime(csv_path),
        _update_mag_list=lambda: None,
        mag_progressbars={(1, 1): bar1, (1, 2): bar2},
        mag_percent_labels={(1, 1): lbl1, (1, 2): lbl2},
        _mag_column_occ={(1, 1): 500, (1, 2): 1000},
        update_inventory_stats=lambda: None,
    )

    ui.CardEditorApp.refresh_magazyn(app)

    assert bar1.value == 0.5
    assert bar2.value == 1.0
    assert lbl1.kwargs.get("text") == "50%"
    assert lbl2.kwargs.get("text") == "100%"
