import time

import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))
from shoper_client import ShoperClient


class DummyResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        if text:
            self.text = text
        elif self._data:
            import json

            self.text = json.dumps(self._data)
        else:
            self.text = ""
        self.headers = {}

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error

    def json(self):
        return self._data


def test_env_vars_trimmed(monkeypatch):
    monkeypatch.setenv("SHOPER_API_URL", " https://example.com  ")
    monkeypatch.setenv("SHOPER_API_TOKEN", "  tok  ")
    client = ShoperClient()
    assert client.base_url == "https://example.com/webapi/rest"
    assert client.token == "tok"


@pytest.mark.parametrize(
    "provided,expected",
    [
        ("https://shop", "https://shop/webapi/rest"),
        ("https://shop/webapi", "https://shop/webapi/rest"),
        ("https://shop/webapi/", "https://shop/webapi/rest"),
        ("https://shop/webapi/rest", "https://shop/webapi/rest"),
        ("https://shop/webapi/rest/", "https://shop/webapi/rest"),
        ("https://shop/webapi/rest/rest", "https://shop/webapi/rest"),
    ],
)
def test_base_url_normalization(provided, expected):
    assert ShoperClient._normalize_base_url(provided) == expected


def test_client_endpoints(monkeypatch):
    client = ShoperClient(base_url="https://shop", token="tok")
    captured = {}

    def fake_get(endpoint, **kwargs):
        captured.setdefault("get_calls", []).append((endpoint, kwargs))
        return {}

    def fake_post(endpoint, **kwargs):
        captured["post"] = (endpoint, kwargs.get("json"))
        return {}

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "post", fake_post)

    client.get_attributes()
    client.add_product_attribute(1, 2, ["val"])
    client.list_orders()

    assert captured["get_calls"][0][0] == "attributes"
    assert captured["post"][0] == "products-attributes"
    assert captured["post"][1]["product_id"] == 1
    assert captured["post"][1]["attribute_id"] == 2
    orders_call = captured["get_calls"][1]
    assert orders_call[0] == "orders"
    assert orders_call[1]["params"]["with"] == "products,delivery_address,billing_address"
    assert orders_call[1]["params"]["limit"] == 20


def test_import_csv_polls_until_complete(tmp_path, monkeypatch):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id;name\n1;test\n", encoding="utf-8")

    client = ShoperClient(base_url="https://shop", token="tok")

    statuses = iter([
        {"status": "processing"},
        {"status": "completed"},
    ])

    def fake_post(endpoint, files=None):
        assert endpoint == "products/import"
        assert "file" in files
        return {"job_id": "1"}

    def fake_get(endpoint, **kwargs):
        assert endpoint == "products/import/1"
        return next(statuses)

    monkeypatch.setattr(client, "post", fake_post)
    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    result = client.import_csv(str(csv_file))
    assert result["status"] == "completed"


def test_import_csv_raises_on_error(tmp_path, monkeypatch):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id;name\n1;test\n", encoding="utf-8")

    client = ShoperClient(base_url="https://shop", token="tok")

    def fake_post(endpoint, files=None):
        return {"job_id": "1"}

    def fake_get(endpoint, **kwargs):
        return {"status": "error", "errors": ["boom"]}

    monkeypatch.setattr(client, "post", fake_post)
    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError) as exc:
        client.import_csv(str(csv_file))
    assert "boom" in str(exc.value)


def test_list_orders_respects_existing_with(monkeypatch):
    client = ShoperClient(base_url="https://shop", token="tok")

    captured = {}

    def fake_get(endpoint, **kwargs):
        captured["endpoint"] = endpoint
        captured["params"] = kwargs.get("params")
        return {}

    monkeypatch.setattr(client, "get", fake_get)

    client.list_orders(filters={"with": ["products", "payment"]})

    assert captured["endpoint"] == "orders"
    assert captured["params"]["with"] == "products,payment"
    assert captured["params"]["limit"] == 20


def test_list_orders_normalises_status_filters(monkeypatch):
    client = ShoperClient(base_url="https://shop", token="tok")

    captured_params = {}

    def fake_get(endpoint, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return {}

    monkeypatch.setattr(client, "get", fake_get)

    client.list_orders(filters={"filters[status]": ["new", "processing", "new"]})

    assert captured_params["filters[status][in]"] == "new,processing"
    assert "filters[status]" not in captured_params


def test_list_orders_caps_limit(monkeypatch):
    client = ShoperClient(base_url="https://shop", token="tok")

    captured_params = {}

    def fake_get(endpoint, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return {}

    monkeypatch.setattr(client, "get", fake_get)

    client.list_orders(page=3, per_page=100)

    assert captured_params["page"] == 3
    assert captured_params["limit"] == 50


def test_get_orders_accepts_iterable_status(monkeypatch):
    client = ShoperClient(base_url="https://shop", token="tok")

    captured_params = {}

    def fake_get(endpoint, **kwargs):
        captured_params.update(kwargs.get("params", {}))
        return {}

    monkeypatch.setattr(client, "get", fake_get)

    client.get_orders(status={"new", "processing"})

    assert captured_params["filters[status][in]"] in {"new,processing", "processing,new"}
    assert captured_params["limit"] == 20


def test_client_credentials_auth(monkeypatch):
    monkeypatch.setenv("SHOPER_API_URL", "https://shop")
    monkeypatch.setenv("SHOPER_API_TOKEN", "secret")
    monkeypatch.setenv("SHOPER_CLIENT_ID", "client")

    auth_payloads = []
    request_headers = []

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def post(self, url, json=None, timeout=15, **kwargs):
            auth_payloads.append((url, json))
            return DummyResponse(200, {"access_token": "token1", "expires_in": 120})

        def request(self, method, url, timeout=15, **kwargs):
            request_headers.append(self.headers.get("Authorization"))
            return DummyResponse(200, {"ok": True})

    monkeypatch.setattr(requests, "Session", FakeSession)

    client = ShoperClient()
    result = client.get("orders")

    assert auth_payloads[0][0] == "https://shop/webapi/rest/auth"
    assert auth_payloads[0][1]["client_id"] == "client"
    assert request_headers[0] == "Bearer token1"
    assert result == {"ok": True}


def test_reauth_on_401(monkeypatch):
    monkeypatch.setenv("SHOPER_API_URL", "https://shop")
    monkeypatch.setenv("SHOPER_API_TOKEN", "secret")
    monkeypatch.setenv("SHOPER_CLIENT_ID", "client")

    tokens = iter(["token1", "token2"])

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.calls = 0

        def post(self, url, json=None, timeout=15, **kwargs):
            return DummyResponse(200, {"access_token": next(tokens), "expires_in": 120})

        def request(self, method, url, timeout=15, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return DummyResponse(401)
            return DummyResponse(200, {"ok": True})

    session_holder = {}

    def make_session():
        session = FakeSession()
        session_holder["session"] = session
        return session

    monkeypatch.setattr(requests, "Session", make_session)

    client = ShoperClient()
    result = client.get("orders")

    session = session_holder["session"]
    assert session.calls == 2
    assert session.headers["Authorization"] == "Bearer token2"
    assert result == {"ok": True}
