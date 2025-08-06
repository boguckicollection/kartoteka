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

    def fake_get(url, params=None, timeout=None):
        assert url == "https://www.tcggo.com/api/cards/"
        assert params["name"] == ui.normalize("Pikachu", keep_spaces=True)
        assert params["number"] == "25"
        assert params["total"] == "102"
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    result = ui.lookup_sets_from_api("Pikachu", "25", "102")
    assert result == [("BS", "Base Set"), ("JU", "Jungle"), ("FO", "Fossil")]


def test_lookup_sets_from_api_omits_total(monkeypatch):
    data = {"cards": []}
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    ui.lookup_sets_from_api("Pikachu", "25", None)
    assert "total" not in captured["params"]


def test_lookup_sets_from_api_splits_number(monkeypatch):
    data = {"cards": []}
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return DummyResp(data)

    monkeypatch.setattr(ui.requests, "get", fake_get)
    ui.lookup_sets_from_api("Pikachu", "25/102")
    assert captured["params"]["number"] == "25"
    assert captured["params"]["total"] == "102"


def test_lookup_sets_from_api_filters_results(monkeypatch):
    data = {
        "cards": [
            {
                "name": "Pikachu",
                "card_number": "25",
                "total_prints": "102",
                "episode": {"name": "Base Set", "code": "BS"},
            },
            {
                "name": "Charmander",
                "card_number": "4",
                "total_prints": "99",
                "episode": {"name": "Jungle", "code": "JU"},
            },
        ]
    }

    monkeypatch.setattr(
        ui.requests, "get", lambda url, params=None, timeout=None: DummyResp(data)
    )
    result = ui.lookup_sets_from_api("Pikachu", "25", "102")
    assert result == [("BS", "Base Set")]
