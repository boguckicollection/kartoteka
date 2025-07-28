import logging
from shoper_client import ShoperClient


def create_auction_product(aukcja) -> str | None:
    """Create a Shoper product for the finished auction.

    Returns the product URL or ``None`` when the API is not configured or the
    request fails.
    """

    try:
        client = ShoperClient()
    except Exception as exc:  # pragma: no cover - missing credentials
        logging.info("[AUCTION] ShoperClient init failed: %s", exc)
        return None

    payload = {
        "name": f"{aukcja.nazwa} ({aukcja.numer})",
        "price": aukcja.cena,
        "category": "Licytacja",
        "stock": 1,
        "active": 1,
        "vat": "23%",
        "unit": "szt.",
    }
    if getattr(aukcja, "obraz_url", None):
        payload["images"] = aukcja.obraz_url

    try:
        data = client.add_product(payload)
    except Exception as exc:  # pragma: no cover - network failure
        logging.error("[AUCTION] add_product failed: %s", exc)
        return None

    url = None
    if isinstance(data, dict):
        url = data.get("url") or data.get("product_url")
        if not url:
            prod = data.get("product") or {}
            product_id = data.get("product_id") or prod.get("product_id")
            if product_id:
                base = client.base_url.split("/webapi")[0]
                url = f"{base}/product/{product_id}"
    return url
