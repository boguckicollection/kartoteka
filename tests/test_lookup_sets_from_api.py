import types
from kartoteka import ui


class DummyResp:
    def __init__(self, data):
        self.status_code = 200
        self._data = data

    def json(self):
        return self._data


def test_lookup_sets_from_api_sorts_results(monkeypatch):
    data = {
        "cards": [
            {
                "name": "Pikachu",
                "card_number": "25",
                "total_prints": "102",
                "episode": {"name": "Base Set", "code": "BS"},
            },
            {
                "name": "Pikachu",
                "card_number": "25",
                "total_prints": "102",
                "episode": {"name": "Jungle", "code": "JU"},
            },
            {
                "name": "Pikachu",
                "card_number": "3",
                "total_prints": "62",
                "episode": {"name": "Fossil", "code": "FO"},
            },
        ]
    }

    def fake_get(url, params=None, timeout=None, headers=None):
        assert url == "https://www.tcggo.com/api/cards/"
        assert params["name"] == ui.normalize("Pikachu", keep_spaces=True)
        assert params["number"] == "25"
        assert params["total"] == "102"
        assert headers == {"User-Agent": "kartoteka/1.0"}
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    result = ui.lookup_sets_from_api("Pikachu", "25", "102")
    assert result == [("BS", "Base Set"), ("JU", "Jungle"), ("FO", "Fossil")]


def test_lookup_sets_from_api_omits_total(monkeypatch):
    data = {"cards": []}
    captured = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        captured["params"] = params
        captured["headers"] = headers
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    ui.lookup_sets_from_api("Pikachu", "25", None)
    assert captured["params"]["number"] == "25"
    assert "total" not in captured["params"]
    assert captured["headers"] == {"User-Agent": "kartoteka/1.0"}


def test_lookup_sets_from_api_splits_number(monkeypatch):
    data = {"cards": []}
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append({"params": params, "headers": headers})
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    ui.lookup_sets_from_api("Pikachu", "25/102")
    assert len(calls) == 2
    assert calls[0]["params"]["number"] == "25"
    assert calls[0]["params"]["total"] == "102"
    assert calls[0]["headers"] == {"User-Agent": "kartoteka/1.0"}
    assert calls[1]["params"]["number"] == "25"
    assert "total" not in calls[1]["params"]
    assert calls[1]["headers"] == {"User-Agent": "kartoteka/1.0"}


def test_lookup_sets_from_api_sanitizes_number(monkeypatch):
    data = {"cards": []}
    captured = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        captured["params"] = params
        captured["headers"] = headers
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    ui.lookup_sets_from_api("Pikachu", "037")
    assert captured["params"]["number"] == "37"
    assert captured["headers"] == {"User-Agent": "kartoteka/1.0"}


def test_lookup_sets_from_api_filters_results(monkeypatch):
    data = {
        "cards": [
            {
                "name": "Pikachu",
                "card_number": "25",
                "total_prints": "102",
                "episode": {"name": "Base Set", "slug": "base-set"},
            },
            {
                "name": "Charmander",
                "card_number": "4",
                "total_prints": "99",
                "episode": {"name": "Jungle", "code": "JU"},
            },
        ]
    }

    def fake_get(url, params=None, timeout=None, headers=None):
        assert headers == {"User-Agent": "kartoteka/1.0"}
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    result = ui.lookup_sets_from_api("Pikachu", "25", "102")
    assert result == [("base-set", "Base Set")]


def test_lookup_sets_from_api_uses_rapidapi(monkeypatch):
    data = {"cards": []}
    host = "example.p.rapidapi.com"
    key = "secret"

    monkeypatch.setattr(ui, "RAPIDAPI_HOST", host)
    monkeypatch.setattr(ui, "RAPIDAPI_KEY", key)

    def fake_get(url, params=None, timeout=None, headers=None):
        assert url == f"https://{host}/cards/search"
        assert headers == {
            "User-Agent": "kartoteka/1.0",
            "X-RapidAPI-Key": key,
            "X-RapidAPI-Host": host,
        }
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    ui.lookup_sets_from_api("Pikachu", "25", "102")
