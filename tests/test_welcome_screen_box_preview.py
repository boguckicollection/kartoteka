import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import (
    DummyCTkButton,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkEntry,
    DummyCTkOptionMenu,
    DummyCanvas,
)


def test_welcome_screen_shows_box_preview(monkeypatch):
    created_buttons = []
    created_labels = []
    created_canvases = []

    class TrackingButton(DummyCTkButton):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            created_buttons.append(self)

    class TrackingLabel(DummyCTkLabel):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            created_labels.append(self)

    class TrackingCanvas(DummyCanvas):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            created_canvases.append(self)

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=TrackingLabel,
        CTkButton=TrackingButton,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    monkeypatch.setattr(
        ui.csv_utils,
        "get_inventory_stats",
        lambda path="", force=False: (0, 0.0, 0, 0.0),
    )

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), patch.object(
        ui.tk, "Frame", DummyCTkFrame
    ), patch.object(ui.tk, "Canvas", TrackingCanvas), patch.object(
        ui.messagebox, "showinfo", lambda *a, **k: None
    ):
        dummy_root = SimpleNamespace(
            minsize=lambda *a, **k: None,
            cget=lambda *a, **k: "white",
        )
        app = SimpleNamespace(
            root=dummy_root,
            create_button=lambda master, **kwargs: TrackingButton(master, **kwargs),
            refresh_magazyn=lambda: None,
            open_config_dialog=lambda: None,
            show_location_frame=lambda: None,
            setup_pricing_ui=lambda: None,
            open_shoper_window=lambda: None,
            show_magazyn_view=lambda: None,
            open_auctions_window=lambda: None,
            open_statistics_window=lambda: None,
        )
        app.refresh_home_preview = lambda: ui.CardEditorApp.refresh_home_preview(app)
        ui.CardEditorApp.setup_welcome_screen(app)

    assert hasattr(app, "home_percent_labels")
    assert len(app.home_percent_labels) == len(app.mag_box_order)
    first = app.home_percent_labels[app.mag_box_order[0]]
    assert first.font == ("Segoe UI", 24, "bold")
    assert first.text_color == ui._occupancy_color(0)

    assert hasattr(app, "home_box_canvases")
    assert len(app.home_box_canvases) == len(app.mag_box_order)
    first_canvas = app.home_box_canvases[app.mag_box_order[0]]
    assert isinstance(first_canvas, TrackingCanvas)
    assert getattr(first_canvas, "image", None) is photo_mock
    overlay_ids = getattr(first_canvas, "overlay_ids", None)
    assert isinstance(overlay_ids, dict)
    assert len(overlay_ids) == ui.storage.BOX_COLUMNS[app.mag_box_order[0]]
    for rid in overlay_ids.values():
        overlay = first_canvas.items[rid]
        assert overlay["fill"] == ui._occupancy_color(0)

    box_frame = first_canvas.master.master
    info_frame = app.inventory_count_label.master
    assert info_frame is app.inventory_value_label.master
    assert info_frame.master is not box_frame
    assert box_frame.pack_params.get("side") in (None, "top")
    assert info_frame.pack_params.get("side") in (None, "top")

    # Verify new layout
    assert app.start_frame._grid_columns[0]["weight"] == 1
    assert app.start_frame._grid_columns[1]["weight"] == 2

    texts = [b.kwargs["text"] for b in created_buttons]
    assert len(texts) == 7
    assert texts[:6] == [
        "\U0001f50d Skanuj",
        "\U0001f4b0 Wyceniaj",
        "\U0001f5c3\ufe0f Shoper",
        "\U0001f4e6 Magazyn",
        "\U0001f528 Licytacje",
        "\U0001F4C8 Statystyki",
    ]
    for b in created_buttons[:6]:
        assert b.pack_params.get("side") in (None, "top")

    assert created_buttons[-1].kwargs["text"] == "\u2699\ufe0f Konfiguracja"
    assert created_buttons[-1].pack_params.get("side") == "bottom"

    author_labels = [l for l in created_labels if l.text == "Twórca: BOGUCKI 2025"]
    assert author_labels
    assert author_labels[0].pack_params.get("side") == "bottom"
