import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

def test_mark_as_sold_updates_group(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;era;set;warehouse_code;price;image;sold\n"
        "A;1;E;S;K1;1;;\n"
        "A;1;E;S;K2;1;;\n",
        encoding="utf-8",
    )

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    class _TkMock(SimpleNamespace):
        class TclError(Exception):
            pass

        @staticmethod
        def StringVar(*args, **kwargs):
            raise RuntimeError("tkinter unavailable")

    tk_mod = _TkMock()
    tk_mod.filedialog = SimpleNamespace()
    tk_mod.messagebox = SimpleNamespace()
    tk_mod.simpledialog = SimpleNamespace()
    tk_mod.ttk = SimpleNamespace()
    tk_mod.Canvas = SimpleNamespace()
    sys.modules["tkinter"] = tk_mod
    sys.modules["tkinter.ttk"] = tk_mod.ttk
    sys.modules["tkinter.filedialog"] = tk_mod.filedialog
    sys.modules["tkinter.messagebox"] = tk_mod.messagebox
    sys.modules["tkinter.simpledialog"] = tk_mod.simpledialog
    sys.modules["imagehash"] = MagicMock()
    sys.modules["openai"] = MagicMock()
    sys.modules["requests"] = MagicMock()
    sys.modules["pydantic"] = MagicMock()
    sys.modules["pytesseract"] = MagicMock()
    sys.modules["dotenv"] = MagicMock()
    sys.modules["numpy"] = MagicMock()
    from tests.ctk_mocks import (
        DummyCTkButton,
        DummyCTkEntry,
        DummyCTkFrame,
        DummyCTkLabel,
        DummyCTkOptionMenu,
        DummyCTkScrollableFrame,
        DummyCanvas,
    )

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )

    import kartoteka.ui as ui
    import importlib

    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    monkeypatch.setattr(ui.ImageTk, "PhotoImage", lambda *a, **k: photo_mock)
    monkeypatch.setattr(ui.tk, "Canvas", DummyCanvas)
    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))
    monkeypatch.setattr(ui, "_load_image", lambda path: None)
    refresh_called: list[bool] = []

    dummy_root = SimpleNamespace(minsize=lambda *a, **k: None, title=lambda *a, **k: None)
    app = SimpleNamespace(
        root=dummy_root,
        start_frame=None,
        pricing_frame=None,
        shoper_frame=None,
        frame=None,
        magazyn_frame=None,
        location_frame=None,
        create_button=lambda master, **kwargs: DummyCTkButton(master, **kwargs),
        refresh_magazyn=lambda: refresh_called.append(True),
        back_to_welcome=lambda: None,
    )

    ui.CardEditorApp.show_magazyn_view(app)

    row = app.mag_card_rows[0]
    assert row["warehouse_code"] == "K1;K2"
    assert row["_count"] == 2

    app.update_inventory_stats = lambda: None
    app.show_magazyn_view = lambda: ui.CardEditorApp.show_magazyn_view(app)

    ui.CardEditorApp.mark_as_sold(app, row, warehouse_code="K1")

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    assert any(r["warehouse_code"] == "K1" and r.get("sold") == "1" for r in rows)
    assert any(r["warehouse_code"] == "K2" and not r.get("sold") for r in rows)

    assert row["warehouse_code"] == "K2"
    assert row["_count"] == 1

    assert refresh_called
    assert len(app.mag_card_rows) == 1
    unsold = app.mag_card_rows[0]
    assert not unsold.get("sold")
    assert unsold["warehouse_code"] == "K2"
    assert unsold["_count"] == 1

