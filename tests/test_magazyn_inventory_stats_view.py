import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import (  # noqa: E402
    DummyCTkButton,
    DummyCTkEntry,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkOptionMenu,
    DummyCTkScrollableFrame,
    DummyCanvas,
)


def test_inventory_stats_display_and_update(tmp_path, monkeypatch):
    from kartoteka import csv_utils

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;warehouse_code;price;sold\n" "A;K1R1P1;1;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))

    first_stats = (5, 123.45, 2, 50.0)
    second_stats = (7, 210.0, 3, 60.0)
    monkeypatch.setattr(
        csv_utils,
        "get_inventory_stats",
        lambda path=str(csv_path), force=False: first_stats,
    )

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
    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), patch.object(
        ui.tk, "Canvas", DummyCanvas
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
        )

        ui.CardEditorApp.show_magazyn_view(app)

    assert app.mag_inventory_count_label.text == f"📊 Łączna liczba kart: {first_stats[0]}"
    assert (
        app.mag_inventory_value_label.text
        == f"💰 Łączna wartość: {first_stats[1]:.2f} PLN"
    )
    assert app.mag_sold_count_label.text == f"Sprzedane karty: {first_stats[2]}"
    assert (
        app.mag_sold_value_label.text
        == f"Wartość sprzedanych: {first_stats[3]:.2f} PLN"
    )

    monkeypatch.setattr(
        ui.csv_utils,
        "get_inventory_stats",
        lambda path=str(csv_path), force=False: second_stats,
    )
    ui.CardEditorApp.update_inventory_stats(app)
    assert app.mag_inventory_count_label.text == f"📊 Łączna liczba kart: {second_stats[0]}"
    assert (
        app.mag_inventory_value_label.text
        == f"💰 Łączna wartość: {second_stats[1]:.2f} PLN"
    )
    assert app.mag_sold_count_label.text == f"Sprzedane karty: {second_stats[2]}"
    assert (
        app.mag_sold_value_label.text
        == f"Wartość sprzedanych: {second_stats[3]:.2f} PLN"
    )
