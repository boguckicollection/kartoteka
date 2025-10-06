import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


class DummyOrdersView:
    def __init__(self):
        self.rendered = None
        self.calls = 0
        self.handler = None

    def render_orders(self, orders):
        self.calls += 1
        self.rendered = orders

    def set_order_handler(self, callback):
        self.handler = callback


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

    dummy_output = DummyOrdersView()
    app = SimpleNamespace(
        shoper_client=dummy_client,
        orders_output=dummy_output,
        output_data=[],
        location_from_code=lambda code: code,
    )
    with patch("kartoteka.ui.choose_nearest_locations") as ch:
        ui.CardEditorApp.show_orders(app)
        ch.assert_called_once()
    assert dummy_output.calls == 1
    assert dummy_output.rendered is not None
    assert dummy_output.rendered[0]["title"] == "Zamówienie #1"


def test_show_orders_requests_processing_status():
    orders = {
        "list": [
            {
                "order_id": 2,
                "products": [
                    {"name": "In progress", "quantity": 3, "warehouse_code": "B2"}
                ],
            }
        ]
    }
    captured_filters = {}

    def list_orders(filters):
        captured_filters.update(filters)
        return orders

    dummy_client = SimpleNamespace(list_orders=list_orders)
    dummy_output = DummyOrdersView()
    app = SimpleNamespace(
        shoper_client=dummy_client,
        orders_output=dummy_output,
        output_data=[],
        location_from_code=lambda code: code,
    )
    with patch("kartoteka.ui.choose_nearest_locations"):
        ui.CardEditorApp.show_orders(app)

    status_filter = captured_filters.get("filters[status.type]")
    assert status_filter is not None
    assert set(map(str, status_filter)) >= {"1", "2", "3", "4"}
    assert dummy_output.rendered is not None
    assert dummy_output.rendered[0]["title"] == "Zamówienie #2"


def test_show_orders_handles_runtime_error():
    dummy_client = SimpleNamespace(
        list_orders=MagicMock(side_effect=RuntimeError("boom"))
    )
    dummy_output = DummyOrdersView()
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
    assert dummy_output.calls == 0
    assert dummy_output.rendered is None
