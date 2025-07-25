from shoper_client import ShoperClient


def test_env_vars_trimmed(monkeypatch):
    monkeypatch.setenv("SHOPER_API_URL", " https://example.com  ")
    monkeypatch.setenv("SHOPER_API_TOKEN", "  tok  ")
    client = ShoperClient()
    assert client.base_url == "https://example.com/webapi/rest"
    assert client.token == "tok"
