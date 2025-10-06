import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

def test_mark_as_sold_updates_group(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n"
        "A;1;S;K1;1;;\n"
        "A;1;S;K2;1;;\n",
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
        DummyCTkCheckBox,
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
        CTkCheckBox=DummyCTkCheckBox,
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
        refresh_magazyn=lambda: None,
        back_to_welcome=lambda: None,
    )

    ui.CardEditorApp.show_magazyn_view(app)

    # Wrap refresh_magazyn to observe calls but still execute logic
    refresh_called: list[bool] = []

    app.reload_mag_cards = lambda: ui.CardEditorApp.reload_mag_cards(app)

    def refresh_wrapper():
        refresh_called.append(True)
        ui.CardEditorApp.refresh_magazyn(app)

    app.refresh_magazyn = refresh_wrapper

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

    assert refresh_called
    # After refresh there should be separate sold and unsold entries
    assert len(app.mag_card_rows) == 2
    unsold = next(r for r in app.mag_card_rows if not r.get("sold"))
    sold = next(r for r in app.mag_card_rows if r.get("sold"))
    assert unsold["warehouse_code"] == "K2"
    assert unsold["_count"] == 1

    # Filtering by sold should display the sold entry
    app.mag_sold_filter_var.set("sold")
    assert len(app.mag_sold_labels) == 1
    assert sold["warehouse_code"] == "K1"

