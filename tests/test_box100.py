import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from ctk_mocks import (  # noqa: E402
    DummyCTkButton,
    DummyCTkEntry,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkOptionMenu,
    DummyCTkScrollableFrame,
    DummyCanvas,
    DummyCTkProgressBar,
)

import pytest


def test_compute_box_occupancy_box100(tmp_path, monkeypatch):
    from kartoteka import csv_utils, storage

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text("name;warehouse_code\nA;K100R1P0001\n", encoding="utf-8")
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    occ = storage.compute_box_occupancy()
    assert occ[100] == 1
    percent = occ[100] / storage.BOX_CAPACITY[100] * 100
    assert percent == pytest.approx(0.05)


def test_generate_and_next_free_location_box100():
    from kartoteka import storage

    idx = storage.BOX_COUNT * storage.BOX_CAPACITY[1]
    assert storage.generate_location(idx) == "K100R1P0001"

    app = SimpleNamespace(output_data=[{"warehouse_code": "K100R1P0001"}], starting_idx=idx)
    assert storage.next_free_location(app) == "K100R1P0002"


def test_mag_box_order_contains_100(tmp_path, monkeypatch):
    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
        CTkProgressBar=DummyCTkProgressBar,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text("name;warehouse_code\nA;K100R1P0001\n", encoding="utf-8")
    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))
    monkeypatch.setattr(ui.csv_utils, "INVENTORY_CSV", str(csv_path))

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), patch.object(
        ui.messagebox, "showinfo", lambda *a, **k: None
    ):
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
            update_inventory_stats=lambda: None,
        )

        ui.CardEditorApp.show_magazyn_view(app)
        ui.CardEditorApp.build_box_preview(app, app.magazyn_frame)
        ui.CardEditorApp.refresh_magazyn(app)

    assert app.mag_box_order[-1] == 100
    occ = ui.CardEditorApp.compute_box_occupancy(app)
    assert occ[100] == 1
    from kartoteka import storage

    percent = occ[100] / storage.BOX_CAPACITY[100] * 100
    assert percent == pytest.approx(0.05)

    bar = app.mag_progressbars[(100, 1)]
    assert bar.get() == pytest.approx(1 / ui.storage.BOX_COLUMN_CAPACITY)
