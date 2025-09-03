import csv
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_toggle_sold_updates_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n" "A;1;S1;K1R1P1;10;;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))
    row = {"name": "A", "warehouse_code": "K1R1P1", "sold": ""}
    refresh_called = MagicMock()
    app = SimpleNamespace(refresh_magazyn=refresh_called)

    ui.CardEditorApp.toggle_sold(app, row)
    refresh_called.assert_called_once()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert rows[0]["sold"] == "1"

    refresh_called.reset_mock()
    ui.CardEditorApp.toggle_sold(app, row)
    refresh_called.assert_called_once()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert rows[0]["sold"] == ""
