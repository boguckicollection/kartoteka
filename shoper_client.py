import os
import requests


class ShoperClient:
    """Minimal wrapper for Shoper REST API."""

    def __init__(self, base_url=None, token=None):
        self.base_url = (base_url or os.getenv("SHOPER_API_URL", "")).rstrip("/")
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

    def list_scans(self):
        return self.get("scans")

    def add_product(self, data):
        return self.post("products", json=data)

    def get_inventory(self):
        return self.get("products")
