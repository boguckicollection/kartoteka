import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.modules.setdefault("imagehash", MagicMock())
sys.modules.setdefault("pytesseract", MagicMock())
sys.modules.setdefault("fingerprint", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def test_combined_price():
    card = {"prices": {"cardmarket": {"30d_average": 10, "trendPrice": 14}}}
    assert ui.extract_cardmarket_price(card) == (10 + 14) / 2


def test_single_metric_fallback():
    card = {"prices": {"cardmarket": {"trendPrice": 14}}}
    assert ui.extract_cardmarket_price(card) == 14


def test_lowest_near_mint_fallback():
    card = {"prices": {"cardmarket": {"lowest_near_mint": 5}}}
    assert ui.extract_cardmarket_price(card) == 5


def test_missing_prices():
    card = {}
    assert ui.extract_cardmarket_price(card) is None


def test_none_prices():
    card = {"prices": None}
    assert ui.extract_cardmarket_price(card) is None
