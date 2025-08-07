import csv
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))


def _prepare_csv(tmp_path, content):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(content, encoding="utf-8")
    from kartoteka import csv_utils
    csv_utils.INVENTORY_CSV = csv_utils.WAREHOUSE_CSV = str(csv_path)
    import kartoteka.ui as ui
    importlib.reload(ui)
    return csv_path, ui


def test_repack_after_removal(tmp_path):
    csv_path, ui = _prepare_csv(
        tmp_path,
        "name;warehouse_code\nA;K01R1P0001\nB;K01R1P0003\n",
    )
    dummy = SimpleNamespace(refresh_magazyn=lambda: None)
    ui.CardEditorApp.repack_column(dummy, 1, 1)
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert rows[1]["warehouse_code"] == "K01R1P0002"


def test_repack_within_row(tmp_path):
    csv_path, ui = _prepare_csv(
        tmp_path,
        'name;warehouse_code\nA;"K01R1P0001;K01R1P0003"\n',
    )
    dummy = SimpleNamespace(refresh_magazyn=lambda: None)
    ui.CardEditorApp.repack_column(dummy, 1, 1)
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert rows[0]["warehouse_code"] == "K01R1P0001;K01R1P0002"
