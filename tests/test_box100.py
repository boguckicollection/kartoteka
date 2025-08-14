import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from ctk_mocks import (  # noqa: E402
    DummyCTkButton,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkScrollableFrame,
    DummyCanvas,
)


def test_compute_column_occupancy_box100(tmp_path, monkeypatch):
    from kartoteka import csv_utils, storage

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text("name;warehouse_code\nA;K100R1P0001\n", encoding="utf-8")
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    occ = storage.compute_column_occupancy()
    assert occ[100][1] == 1


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
        ui.tk, "Canvas", DummyCanvas
    ):
        dummy_root = SimpleNamespace(minsize=lambda *a, **k: None)
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

    assert app.mag_box_order[-1] == 100
    occ = ui.CardEditorApp.compute_column_occupancy(app)
    assert occ[100][1] == 1
