import os
from typing import Optional

import requests
from requests import RequestException


class WebDAVClient:
    """Simple WebDAV client for uploading and downloading files."""

    def __init__(self, base_url: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.base_url = base_url or os.getenv("WEBDAV_URL")
        self.user = user or os.getenv("WEBDAV_USER")
        self.password = password or os.getenv("WEBDAV_PASSWORD")
        if not self.base_url or not self.user or not self.password:
            raise ValueError("WebDAV credentials not set")

    def _make_url(self, name: str) -> str:
        return f"{self.base_url.rstrip('/')}/{name}"

    def upload_file(self, local_path: str, remote_name: Optional[str] = None) -> None:
        """Upload a single file via WebDAV."""
        remote_name = remote_name or os.path.basename(local_path)
        url = self._make_url(remote_name)
        try:
            with open(local_path, "rb") as fh:
                response = requests.put(
                    url, data=fh, auth=(self.user, self.password), timeout=30
                )
            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"WebDAV upload failed: {response.status_code} {response.text}"
                )
        except RequestException as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"WebDAV upload failed: {exc}") from exc

    def download_file(self, remote_name: str, local_path: Optional[str] = None) -> None:
        """Download a single file via WebDAV."""
        local_path = local_path or os.path.basename(remote_name)
        url = self._make_url(remote_name)
        try:
            response = requests.get(
                url, auth=(self.user, self.password), timeout=30
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"WebDAV download failed: {response.status_code} {response.text}"
                )
            with open(local_path, "wb") as fh:
                fh.write(response.content)
        except RequestException as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"WebDAV download failed: {exc}") from exc

    def upload_directory(self, directory: str, remote_dir: str = ".") -> None:
        """Upload all files from ``directory`` to ``remote_dir``."""
        for entry in os.listdir(directory):
            path = os.path.join(directory, entry)
            if not os.path.isfile(path):
                continue
            dest = f"{remote_dir.rstrip('/')}/{entry}" if remote_dir not in {"", "."} else entry
            self.upload_file(path, dest)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass
