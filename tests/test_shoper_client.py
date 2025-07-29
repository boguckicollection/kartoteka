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
