import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def test_download_warehouse_csv(monkeypatch, tmp_path):
    called = {}

    class DummyWebDAVClient:
        def __init__(self, base_url=None, user=None, password=None):
            called["init"] = (base_url, user, password)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def download_file(self, remote_path, local_path=None):
            called["args"] = (remote_path, local_path)

    monkeypatch.setattr(csv_utils, "WebDAVClient", DummyWebDAVClient)
    monkeypatch.setenv("WEBDAV_URL", "h")
    monkeypatch.setenv("WEBDAV_USER", "u")
    monkeypatch.setenv("WEBDAV_PASSWORD", "p")
    path = tmp_path / "mag.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    csv_utils.download_warehouse_csv()

    assert called["init"] == (None, None, None)
    assert called["args"] == (str(path), str(path))
