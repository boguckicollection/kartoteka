import os
import requests


class ShoperClient:
    """Minimal wrapper for Shoper REST API."""

    def __init__(self, base_url=None, token=None):
        self.base_url = (base_url or os.getenv("SHOPER_API_URL", "")).rstrip("/")
        # Ensure the URL points to the REST endpoint
        if self.base_url and not self.base_url.endswith("/webapi/rest"):
            self.base_url = f"{self.base_url}/webapi/rest"
        self.token = token or os.getenv("SHOPER_API_TOKEN")
        if not self.base_url or not self.token:
            raise ValueError("SHOPER_API_URL or SHOPER_API_TOKEN not set")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self.session.request(method, url, timeout=15, **kwargs)
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except requests.RequestException as exc:
            raise RuntimeError(f"API request failed: {exc}") from exc

    def get(self, endpoint, **kwargs):
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        return self._request("POST", endpoint, **kwargs)

    def add_product(self, data):
        return self.post("products", json=data)

    def get_inventory(self):
        return self.get("products")

    def search_products(self, filters=None, sort=None, page=1, per_page=50):
        """Search products with optional filters and sorting."""
        params = {"page": page, "per-page": per_page}
        if filters:
            params.update(filters)
        if sort:
            params["sort"] = sort
        return self.get("products", params=params)

    def list_orders(self, filters=None, page=1, per_page=20):
        """Return a list of orders filtered by status or other fields."""
        params = {"page": page, "per-page": per_page}
        if filters:
            params.update(filters)
        return self.get("orders", params=params)

    def get_order(self, order_id):
        """Retrieve a single order by id."""
        return self.get(f"orders/{order_id}")
