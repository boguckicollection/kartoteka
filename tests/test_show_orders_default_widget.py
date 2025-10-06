import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


class DummyText:
    def __init__(self):
        self.content = ""

    def delete(self, *args, **kwargs):
        self.content = ""

    def insert(self, idx, txt):
        self.content += txt


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


def test_show_orders_handles_runtime_error():
    dummy_client = SimpleNamespace(
        list_orders=MagicMock(side_effect=RuntimeError("boom"))
    )
    dummy_output = DummyText()
    app = SimpleNamespace(
        shoper_client=dummy_client,
        orders_output=dummy_output,
        output_data=[],
        location_from_code=lambda code: code,
    )
    with (
        patch("kartoteka.ui.choose_nearest_locations") as choose,
        patch("kartoteka.ui.messagebox.showerror") as showerror,
        patch("kartoteka.ui.logger.exception") as log_exception,
    ):
        ui.CardEditorApp.show_orders(app)

    choose.assert_not_called()
    showerror.assert_called_once()
    log_exception.assert_called_once()
    assert dummy_output.content == ""
