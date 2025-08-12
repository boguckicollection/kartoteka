import time
import pytest
from shoper_client import ShoperClient


def test_env_vars_trimmed(monkeypatch):
    monkeypatch.setenv("SHOPER_API_URL", " https://example.com  ")
    monkeypatch.setenv("SHOPER_API_TOKEN", "  tok  ")
    client = ShoperClient()
    assert client.base_url == "https://example.com/webapi/rest"
    assert client.token == "tok"


def test_client_endpoints(monkeypatch):
    client = ShoperClient(base_url="https://shop", token="tok")
    captured = {}

    def fake_get(endpoint, **kwargs):
        captured["get"] = endpoint
        return {}

    def fake_post(endpoint, **kwargs):
        captured["post"] = (endpoint, kwargs.get("json"))
        return {}

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "post", fake_post)

    client.get_attributes()
    client.add_product_attribute(1, 2, ["val"]) 

    assert captured["get"] == "attributes"
    assert captured["post"][0] == "products-attributes"
    assert captured["post"][1]["product_id"] == 1
    assert captured["post"][1]["attribute_id"] == 2


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
