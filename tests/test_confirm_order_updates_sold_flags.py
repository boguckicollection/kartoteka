import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_confirm_order_updates_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;warehouse_code;price;sold\n"
        "A;K1;1;\n"
        "B;K2;2;\n",
        encoding="utf-8",
    )

    sys.modules.setdefault("customtkinter", MagicMock())
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    import importlib
    importlib.reload(ui)

    monkeypatch.setattr(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path))

    stats_called = []
    refresh_called = []
    app = SimpleNamespace(
        update_inventory_stats=lambda: stats_called.append(True),
        show_magazyn_view=lambda: refresh_called.append(True),
        pending_orders=[{"products": [{"warehouse_code": "K1;K2"}]}],
    )
    app.complete_order = lambda order: ui.CardEditorApp.complete_order(app, order)

    ui.CardEditorApp.confirm_order(app)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    assert all(r.get("sold") == "1" for r in rows)
    assert stats_called
    assert refresh_called
