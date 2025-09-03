import csv
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image


def test_show_card_details_sprzedano_button(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n" "A;1;S1;K1R1P1;10;;\n",
        encoding="utf-8",
    )

    created = []

    class DummyButton:
        def __init__(self, master=None, **kwargs):
            created.append(kwargs)

        def pack(self, *a, **k):
            return self

    class DummyFrame:
        def __init__(self, *a, **k):
            pass

        def pack(self, *a, **k):
            return self

        def grid(self, *a, **k):
            return self

    class DummyLabel(DummyFrame):
        def __init__(self, master=None, **kwargs):
            pass

    class DummyToplevel(DummyFrame):
        def title(self, *a, **k):
            pass

        def geometry(self, *a, **k):
            pass

        def minsize(self, *a, **k):
            pass

        def destroy(self):
            pass

    sys.modules["tkinter"] = MagicMock()
    sys.modules["tkinter.ttk"] = MagicMock()
    sys.modules["imagehash"] = MagicMock()
    sys.modules["openai"] = MagicMock()
    sys.modules["requests"] = MagicMock()
    sys.modules["pydantic"] = MagicMock()
    sys.modules["pytesseract"] = MagicMock()
    sys.modules["dotenv"] = MagicMock()
    sys.modules["numpy"] = MagicMock()
    sys.modules["customtkinter"] = SimpleNamespace(
        CTkToplevel=DummyToplevel,
        CTkFrame=DummyFrame,
        CTkLabel=DummyLabel,
        CTkButton=DummyButton,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui

    importlib.reload(ui)

    monkeypatch.setattr(ui, "_load_image", lambda p: Image.new("RGB", (10, 10)))
    monkeypatch.setattr(ui, "_create_image", lambda img: SimpleNamespace())
    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))

    refresh_mock = MagicMock()
    stats_mock = MagicMock()
    app = SimpleNamespace(
        root=SimpleNamespace(),
        refresh_magazyn=lambda: (refresh_mock(), stats_mock()),
    )
    app.mark_as_sold = lambda r, w=None, c=None: ui.CardEditorApp.mark_as_sold(
        app, r, w, c
    )

    row = {
        "name": "A",
        "number": "1",
        "set": "S1",
        "price": "10",
        "warehouse_code": "K1R1P1",
        "sold": "",
    }

    ui.CardEditorApp.show_card_details(app, row)

    sprzedano_btn = next(b for b in created if b["text"] == "Sprzedano")

    # Simulate button press
    sprzedano_btn["command"]()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert rows[0]["sold"] == "1"

    refresh_mock.assert_called_once()
    stats_mock.assert_called_once()

