import os
import requests


class ShoperClient:
    """Minimal wrapper for Shoper REST API."""

    def __init__(self, base_url=None, token=None):
        env_url = os.getenv("SHOPER_API_URL", "").strip()
        self.base_url = (base_url or env_url).rstrip("/")
        # Ensure the URL points to the REST endpoint
        if self.base_url and not self.base_url.endswith("/webapi/rest"):
            self.base_url = f"{self.base_url}/webapi/rest"
        env_token = os.getenv("SHOPER_API_TOKEN", "").strip()
        self.token = token or env_token
        if not self.base_url or not self.token:
            raise ValueError("SHOPER_API_URL or SHOPER_API_TOKEN not set")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })

    def _request(self, method, endpoint, **kwargs):
        """Send a request to the Shoper API.

        Parameters are passed directly to ``requests.Session.request``.
        The returned value is the parsed JSON response or ``{}`` when the
        response body is empty. If the API responds with ``404`` the method
        also returns an empty dictionary instead of raising an exception.

        Any other HTTP error results in a ``RuntimeError`` being raised.
        """

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self.session.request(method, url, timeout=15, **kwargs)
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return {}
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return {}
            raise RuntimeError(f"API request failed: {exc}") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"API request failed: {exc}") from exc

    def get(self, endpoint, **kwargs):
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        return self._request("POST", endpoint, **kwargs)

    def add_product(self, data):
        return self.post("products", json=data)

    def get_inventory(self, page=1, per_page=50):
        """Return products with optional pagination."""
        params = {"page": page, "per-page": per_page}
        return self.get("products", params=params)

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

    # New helper methods for dashboard statistics
    def get_orders(self, status=None, filters=None, page=1, per_page=20):
        """Return orders optionally filtered by status and other criteria."""
        params = {"page": page, "per-page": per_page}
        if filters:
            params.update(filters)
        if status:
            params["filters[status]"] = status
        return self.get("orders", params=params)

    def get_sales_stats(self, params=None):
        """Return sales statistics using the built-in Shoper endpoint."""
        try:
            return self.get("orders/stats", params=params or {})
        except RuntimeError:  # pragma: no cover - network failure
            print("[INFO] orders/stats unavailable")
            return {}

    def import_csv(self, file_path):
        """Upload a CSV file using the Shoper API."""
        with open(file_path, "rb") as fh:
            files = {"file": (os.path.basename(file_path), fh, "text/csv")}
            return self.post("import/csv", files=files)
