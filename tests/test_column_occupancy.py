import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ctk_mocks import (
    DummyCTkButton,
    DummyCTkEntry,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkOptionMenu,
    DummyCTkScrollableFrame,
    DummyCanvas,
    DummyCTkProgressBar,
)

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_split_codes_counted(tmp_path, monkeypatch):
    from kartoteka import csv_utils
    from kartoteka import storage
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        'name;warehouse_code\nA;"K1R1P1;K1R1P2"\n', encoding="utf-8"
    )
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))
    import kartoteka.ui as ui
    importlib.reload(ui)
    dummy = SimpleNamespace()
    occ = ui.CardEditorApp.compute_box_occupancy(dummy)
    assert occ[1] == 2
    percent = occ[1] / storage.BOX_CAPACITY[1] * 100
    assert percent == pytest.approx(0.05)
    col_occ = storage.compute_column_occupancy()
    assert col_occ[1][1] == 2


def test_sold_cards_excluded_from_occupancy(tmp_path, monkeypatch):
    from kartoteka import csv_utils
    from kartoteka import storage
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;warehouse_code;sold\nA;K1R1P1;\nB;K1R1P2;1\n", encoding="utf-8"
    )
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))
    import kartoteka.ui as ui
    import importlib
    importlib.reload(ui)
    dummy = SimpleNamespace()
    occ = ui.CardEditorApp.compute_box_occupancy(dummy)
    assert occ[1] == 1
    percent = occ[1] / storage.BOX_CAPACITY[1] * 100
    assert percent == pytest.approx(0.025)
    col_occ = storage.compute_column_occupancy()
    assert col_occ[1][1] == 1


@pytest.mark.parametrize(
    "csv_content, expected",
    [
        (
            "name;warehouse_code\nA;K1R1P1\nB;K1R2P1\n",
            {1: {1: 1, 2: 1, 3: 0, 4: 0}},
        ),
        (
            "name;warehouse_code\nA;K2R3P1\nB;K2R3P2\n",
            {2: {1: 0, 2: 0, 3: 2, 4: 0}},
        ),
        (
            "name;warehouse_code\nA;K3R1P1\nB;K3R4P1\n",
            {3: {1: 1, 2: 0, 3: 0, 4: 1}},
        ),
    ],
)
def test_compute_column_occupancy_various_inputs(
    tmp_path, monkeypatch, csv_content, expected
):
    from kartoteka import csv_utils, storage

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))

    col_occ = storage.compute_column_occupancy()
    for box, cols in expected.items():
        assert col_occ[box] == cols

def test_refresh_colors_columns_based_on_occupancy(tmp_path, monkeypatch):
    from kartoteka import csv_utils

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text("name;warehouse_code\nA;K1R1P0001\n", encoding="utf-8")
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
        CTkProgressBar=DummyCTkProgressBar,
    )
    import kartoteka.ui as ui
    importlib.reload(ui)

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

    bar = app.mag_progressbars[(1, 1)]
    assert bar.get() > 0
    for col in range(2, ui.storage.BOX_COLUMNS[1] + 1):
        assert app.mag_progressbars[(1, col)].get() == 0
