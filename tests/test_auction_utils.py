from types import SimpleNamespace
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
import auction_utils


def test_create_auction_product_builds_payload(monkeypatch):
    captured = {}

    class FakeClient:
        base_url = "https://shop.example.com/webapi/rest"

        def add_product(self, data):
            captured['payload'] = data
            return {'url': 'https://shop.example.com/product/1'}

    monkeypatch.setattr(auction_utils, "ShoperClient", lambda: FakeClient())

    aukcja = SimpleNamespace(nazwa="Pika", numer="1", opis="", cena=9.99, obraz_url="img")
    url = auction_utils.create_auction_product(aukcja)

    assert url == "https://shop.example.com/product/1"
    assert captured['payload']["category"] == "Licytacja"
    assert captured['payload']["price"] == 9.99
