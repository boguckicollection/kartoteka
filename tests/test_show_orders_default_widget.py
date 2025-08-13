import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_show_orders_uses_default_widget():
    orders = {
        "list": [
            {
                "order_id": 1,
                "products": [
                    {"name": "Prod", "quantity": 1, "warehouse_code": "A1"}
                ],
            }
        ]
    }
    dummy_client = SimpleNamespace(list_orders=lambda params: orders)

    class DummyText:
        def __init__(self):
            self.content = ""

        def delete(self, *args, **kwargs):
            self.content = ""

        def insert(self, idx, txt):
            self.content += txt

    dummy_output = DummyText()
    app = SimpleNamespace(
        shoper_client=dummy_client,
        orders_output=dummy_output,
        output_data=[],
        location_from_code=lambda code: code,
    )
    with patch("kartoteka.ui.choose_nearest_locations") as ch:
        ui.CardEditorApp.show_orders(app)
        ch.assert_called_once()
    assert "Zamówienie #1" in dummy_output.content
