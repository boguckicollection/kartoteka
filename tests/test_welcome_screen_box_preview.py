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
    DummyCTkScrollableFrame,
    DummyCTkEntry,
    DummyCTkOptionMenu,
    DummyCanvas,
)


def test_welcome_screen_shows_box_preview(monkeypatch):
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

    monkeypatch.setattr(ui.csv_utils, "get_inventory_stats", lambda path="": (0, 0.0, 0, 0.0))

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), patch.object(
        ui.tk, "Canvas", DummyCanvas
    ), patch.object(ui.tk, "Frame", DummyCTkFrame), patch.object(
        ui.messagebox, "showinfo", lambda *a, **k: None
    ):
        dummy_root = SimpleNamespace(
            minsize=lambda *a, **k: None,
            cget=lambda *a, **k: "white",
        )
        app = SimpleNamespace(
            root=dummy_root,
            create_button=lambda master, **kwargs: DummyCTkButton(master, **kwargs),
            refresh_magazyn=lambda: None,
            open_config_dialog=lambda: None,
            show_location_frame=lambda: None,
            setup_pricing_ui=lambda: None,
            open_shoper_window=lambda: None,
            open_magazyn_window=lambda: None,
            open_auctions_window=lambda: None,
        )
        ui.CardEditorApp.setup_welcome_screen(app)

    assert hasattr(app, "mag_canvases")
    assert len(app.mag_canvases) == ui.BOX_COUNT + 1
