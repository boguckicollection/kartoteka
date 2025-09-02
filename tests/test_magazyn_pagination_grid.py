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
        ui.CardEditorApp.show_magazyn_view(app)
        return app


def test_magazyn_page_navigation(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    header = "name;number;era;set;warehouse_code;price;image;variant\n"
    rows = [
        f"Card{i:02d};{i};E;S;K{i};1;img{i}.png;common\n" for i in range(25)
    ]
    csv_path.write_text(header + "".join(rows), encoding="utf-8")

    app = _load_app(csv_path, (25, 25.0, 0, 0))

    assert app.mag_page == 0
    assert len(app.mag_card_labels) == 20

    app.mag_next_button.kwargs["command"]()
    assert app.mag_page == 1
    assert len(app.mag_card_labels) == 5
    assert app.mag_card_labels[0].text == "Card20"

    app.mag_prev_button.kwargs["command"]()
    assert app.mag_page == 0
    assert len(app.mag_card_labels) == 20


def test_magazyn_grid_positions(tmp_path):
    class RecordingFrame(DummyCTkFrame):
        def grid(self, **kwargs):
            self.grid_kwargs = kwargs
            return self

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=RecordingFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;era;set;warehouse_code;price;image;variant\n"
        "A;1;E;S;K1;1;foo1.png;common\n"
        "B;2;E;S;K2;1;foo2.png;common\n"
        "C;3;E;S;K3;1;foo3.png;common\n",
        encoding="utf-8",
    )

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)), \
         patch.object(ui.csv_utils, "get_inventory_stats", return_value=(3, 3.0, 0, 0)):
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

    frames = app.mag_card_frames
    assert frames[0].grid_kwargs["row"] == 0
    assert frames[0].grid_kwargs["column"] == 0
    assert frames[1].grid_kwargs["row"] == 0
    assert frames[1].grid_kwargs["column"] == 1

