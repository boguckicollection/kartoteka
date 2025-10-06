import os
import time
from typing import Optional

import requests


class ShoperClient:
    """Minimal wrapper for Shoper REST API."""

    def __init__(self, base_url=None, token=None, client_id=None):
        env_url = os.getenv("SHOPER_API_URL", "").strip()
        raw_url = (base_url or env_url).strip()
        self.base_url = self._normalize_base_url(raw_url)
        env_token = os.getenv("SHOPER_API_TOKEN", "").strip()
        env_client_id = os.getenv("SHOPER_CLIENT_ID", "").strip()
        self.client_id = (client_id or env_client_id).strip() or None
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        raw_token = token or env_token
        if not self.base_url or not raw_token:
            raise ValueError("SHOPER_API_URL or SHOPER_API_TOKEN not set")

        self._client_secret: Optional[str] = None
        self._token_expires_at: float = 0.0
        self.token: Optional[str] = None

        if self.client_id:
            self._client_secret = raw_token
            self._authenticate(force=True)
        else:
            self.token = raw_token
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
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
        self._ensure_token()
        attempt = 0
        while True:
            try:
                resp = self.session.request(method, url, timeout=15, **kwargs)
            except requests.RequestException as exc:
                raise RuntimeError(f"API request failed: {exc}") from exc

            if resp.status_code == 401 and self.client_id and attempt == 0:
                # Access token expired – refresh and retry once.
                self._authenticate(force=True)
                attempt += 1
                continue

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    return {}
                raise RuntimeError(f"API request failed: {exc}") from exc

            if resp.text:
                return resp.json()
            return {}

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

    def list_orders(
        self,
        filters=None,
        page=1,
        per_page=20,
        include_products=True,
    ):
        """Return a list of orders filtered by status or other fields.

        Parameters
        ----------
        filters:
            Optional mapping of query parameters supported by the API.
        page / per_page:
            Pagination arguments forwarded to the API.
        include_products:
            When ``True`` (the default) the request automatically expands the
            response with product data so that the caller has immediate access
            to ordered items without issuing follow-up requests.
        """

        params = {"page": page, "per-page": per_page}
        if filters:
            params.update(filters)
        self._normalise_status_filters(params)
        if include_products:
            includes = params.get("with")
            if not includes:
                includes = "products,delivery_address,billing_address"
            elif isinstance(includes, (list, tuple, set)):
                includes = ",".join(str(part) for part in includes if part)
            params["with"] = includes
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
        self._normalise_status_filters(params)
        return self.get("orders", params=params)

    @staticmethod
    def _normalise_status_filters(params: dict) -> None:
        """Convert list-like status filters to the API ``[in]`` form."""

        if not params:
            return

        status_values = None
        if "filters[status]" in params:
            status_values = params.get("filters[status]")
            key_to_remove = "filters[status]"
        elif "filters[status][in]" in params:
            status_values = params.get("filters[status][in]")
            key_to_remove = "filters[status][in]"
        else:
            return

        if isinstance(status_values, (list, tuple, set)):
            values = [str(value) for value in status_values if value]
        elif isinstance(status_values, str):
            values = [part.strip() for part in status_values.split(",") if part.strip()]
        else:
            values = [str(status_values)] if status_values else []

        if not values:
            params.pop(key_to_remove, None)
            return

        params.pop(key_to_remove, None)
        params["filters[status][in]"] = ",".join(dict.fromkeys(values))

    def get_sales_stats(self, params=None):
        """Return sales statistics using the built-in Shoper endpoint."""
        try:
            return self.get("orders/stats", params=params or {})
        except RuntimeError:  # pragma: no cover - network failure
            print("[INFO] orders/stats unavailable")
            return {}

    def import_csv(self, file_path, poll_interval=2, timeout=120):
        """Upload a CSV file and wait for the import job to finish."""
        with open(file_path, "rb") as fh:
            files = {"file": (os.path.basename(file_path), fh, "text/csv")}
            data = self.post("products/import", files=files)
        job_id = data.get("job_id") or data.get("id")
        if job_id:
            return self._poll_import_job(job_id, poll_interval, timeout)
        return data

    def _poll_import_job(self, job_id, interval=2, timeout=120):
        """Poll the import job until completion or failure."""
        endpoint = f"products/import/{job_id}"
        end_time = time.time() + timeout
        while time.time() < end_time:
            status = self.get(endpoint)
            state = status.get("status") or status.get("state")
            if state in {"completed", "finished", "done", "success"}:
                errors = status.get("errors")
                if errors:
                    raise RuntimeError(f"Import completed with errors: {errors}")
                return status
            if state in {"failed", "error"}:
                raise RuntimeError(f"Import failed: {status}")
            time.sleep(interval)
        raise RuntimeError("Import job timed out")

    def get_attributes(self):
        """Return a list of product attributes."""
        return self.get("attributes")

    def add_product_attribute(self, product_id, attribute_id, values):
        """Assign a product attribute to a product."""
        payload = {
            "product_id": product_id,
            "attribute_id": attribute_id,
            "values": values,
        }
        return self.post("products-attributes", json=payload)

    # ------------------------------------------------------------------
    # Internal helpers

    def _ensure_token(self):
        """Refresh the OAuth token when using client credentials."""

        if not self.client_id:
            return
        if not self.token or time.time() >= (self._token_expires_at - 60):
            self._authenticate(force=True)

    def _authenticate(self, force=False):
        if not self.client_id or not self._client_secret:
            raise RuntimeError("Shoper client credentials are not configured")
        if not force and self.token and time.time() < (self._token_expires_at - 60):
            return

        url = f"{self.base_url}/auth"
        payload = {
            "client_id": self.client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        }
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Failed to authenticate with Shoper API: {exc}") from exc

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError("Shoper API did not return an access token")

        expires_in = data.get("expires_in")
        try:
            expires = float(expires_in)
        except (TypeError, ValueError):
            expires = 3600.0

        self.token = access_token
        self._token_expires_at = time.time() + max(expires, 60.0)
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    @staticmethod
    def _normalize_base_url(url: str) -> str:
        """Return a URL that always points to ``/webapi/rest``.

        Users frequently copy the ``/webapi`` panel address instead of the REST
        entry point.  The API, however, requires requests to be sent to the
        ``/webapi/rest`` sub-path.  To make configuration more forgiving we
        detect such cases and automatically rewrite the URL so that subsequent
        calls hit the correct endpoint regardless of whether the user provided
        ``https://shop/webapi`` or ``https://shop``.
        """

        if not url:
            return ""

        stripped = url.rstrip("/")
        if not stripped:
            return ""

        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(stripped)
        path_parts = [segment for segment in parts.path.split("/") if segment]

        # Remove any trailing ``rest``/``webapi`` components so we can append a
        # single ``webapi/rest`` pair regardless of what the user supplied.
        while path_parts and path_parts[-1] == "rest":
            path_parts.pop()
        if path_parts and path_parts[-1] == "webapi":
            path_parts.pop()

        normalized_path = "/" + "/".join(path_parts + ["webapi", "rest"])

        return urlunsplit(
            parts._replace(path=normalized_path, query="", fragment="")
        )
