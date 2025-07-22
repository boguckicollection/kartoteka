import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_nearest_pair_chosen():
    orders = [{
        "id": 1,
        "products": [{"product_code": "1", "name": "A", "quantity": 2}]
    }]

    output_data = [
        {"product_code": "1", "warehouse_code": "K01R1P0001"},
        {"product_code": "1", "warehouse_code": "K01R1P0050"},
        {"product_code": "1", "warehouse_code": "K05R3P0001"},
    ]

    ui.choose_nearest_locations(orders, output_data)
    codes = orders[0]["products"][0]["warehouse_code"].split(";")
    assert set(codes) == {"K01R1P0001", "K05R3P0001"}
