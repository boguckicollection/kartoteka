import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_split_codes_counted(tmp_path, monkeypatch):
    from kartoteka import csv_utils
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        'name;warehouse_code\nA;"K1R1P1;K1R1P2"\n', encoding="utf-8"
    )
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))
    import kartoteka.ui as ui
    importlib.reload(ui)
    dummy = SimpleNamespace()
    occ = ui.CardEditorApp.compute_column_occupancy(dummy)
    assert occ[1][1] == 2


def test_sold_cards_excluded_from_occupancy(tmp_path, monkeypatch):
    from kartoteka import csv_utils
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
    occ = ui.CardEditorApp.compute_column_occupancy(dummy)
    assert occ[1][1] == 1
