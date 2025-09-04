import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import time
from PIL import Image

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
        ui.CardEditorApp.show_magazyn_view(app)
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
    app._update_mag_list()
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
    app._update_mag_list()
    assert len(app.mag_sold_labels) == 1
    assert len(app.mag_card_labels) == 0

    app.mag_search_var.set("unsold")
    app._update_mag_list()
    assert len(app.mag_card_labels) == 1
    assert len(app.mag_sold_labels) == 0

    app.mag_search_var.set("")
    app._update_mag_list()
    app.mag_sold_filter_var.set("sold")
    assert len(app.mag_sold_labels) == 1
    assert len(app.mag_card_labels) == 0

    app.mag_sold_filter_var.set("unsold")
    assert len(app.mag_card_labels) == 1
    assert len(app.mag_sold_labels) == 0


def test_search_with_accents(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image\n"
        "Pokémon Café;1;S;K1;1;foo.png\n"
        "Pokemon Base;1;S;K2;1;foo.png\n",
        encoding="utf-8",
    )
    app = _load_app(csv_path, (2, 2.0, 0, 0))

    app.mag_search_var.set("pokemon cafe")
    app._update_mag_list()
    assert len(app.mag_card_labels) == 1
    assert app.mag_card_labels[0].text == "Pokémon Café"


def test_search_multiple_terms_across_fields(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image\n"
        "Pikachu;1;Base;K1;1;foo.png\n"
        "Pikachu;1;Jungle;K2;1;foo.png\n",
        encoding="utf-8",
    )
    app = _load_app(csv_path, (2, 2.0, 0, 0))

    app.mag_search_var.set("pikachu base")
    app._update_mag_list()
    assert len(app.mag_card_labels) == 1
    assert app.mag_card_labels[0].text == "Pikachu"


def _load_app_with_delay(csv_path, stats):
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

    placeholder_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)
    photo_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)
    def _photo_side_effect(*a, **k):
        _photo_side_effect.calls += 1
        return placeholder_mock if _photo_side_effect.calls == 1 else photo_mock
    _photo_side_effect.calls = 0

    def slow_load(path):
        time.sleep(0.1)
        return Image.new("RGB", (10, 10), "white")

    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(ui, "_load_image", side_effect=slow_load))
    stack.enter_context(patch.object(ui.ImageTk, "PhotoImage", side_effect=_photo_side_effect))
    stack.enter_context(patch.object(ui.tk, "Canvas", DummyCanvas))
    stack.enter_context(patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)))
    stack.enter_context(patch.object(ui.csv_utils, "get_inventory_stats", return_value=stats))

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
        show_card_details=lambda *a, **k: None,
    )
    ui.CardEditorApp.show_magazyn_view(app)
    return app, photo_mock, stack


def test_search_clear_keeps_thumbnails(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image\n"
        "Card;1;S;K1;1;https://example.com/image.png\n",
        encoding="utf-8",
    )
    app, photo, stack = _load_app_with_delay(csv_path, (1, 1.0, 0, 0))
    try:
        app.mag_search_var.set("x")
        app._update_mag_list()
        app.mag_search_var.set("")
        app._update_mag_list()
        for t in app._image_threads:
            t.join()
        assert app.mag_card_image_labels[0] is not None
        assert app.mag_card_image_labels[0].image is photo
    finally:
        stack.close()
