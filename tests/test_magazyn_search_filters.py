import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import (
    DummyCTkButton,
    DummyCTkEntry,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkOptionMenu,
    DummyCTkScrollableFrame,
    DummyCanvas,
)


def _load_app(csv_path, stats):
    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)), \
         patch.object(ui.csv_utils, "get_inventory_stats", return_value=stats):
        dummy_root = SimpleNamespace(
            minsize=lambda *a, **k: None,
            title=lambda *a, **k: None,
        )
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
        ui.CardEditorApp.open_magazyn_window(app)
        return app


def test_search_by_variant(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant\n"
        "A;1;S;K1;10;foo.png;holo\n"
        "B;2;S;K2;5;foo.png;reverse\n",
        encoding="utf-8",
    )
    app = _load_app(csv_path, (2, 15.0, 0, 0))

    app.mag_search_var.set("holo")
    assert len(app.mag_card_labels) == 1
    assert app.mag_card_labels[0].text == "A"


def test_search_by_sold_status(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant;sold\n"
        "A;1;S;K1;1;foo.png;common;\n"
        "B;2;S;K2;1;foo.png;common;1\n",
        encoding="utf-8",
    )
    app = _load_app(csv_path, (1, 1.0, 1, 1.0))

    app.mag_search_var.set("sold")
    assert len(app.mag_sold_labels) == 1
    assert len(app.mag_card_labels) == 0

    app.mag_search_var.set("unsold")
    assert len(app.mag_card_labels) == 1
    assert len(app.mag_sold_labels) == 0

    app.mag_search_var.set("")
    app.mag_sold_filter_var.set("sold")
    assert len(app.mag_sold_labels) == 1
    assert len(app.mag_card_labels) == 0

    app.mag_sold_filter_var.set("unsold")
    assert len(app.mag_card_labels) == 1
    assert len(app.mag_sold_labels) == 0
