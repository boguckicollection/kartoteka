import sys
from pathlib import Path
import logging

sys.path.append(str(Path(__file__).resolve().parents[1]))

from requests import RequestException

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
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV_URL", "")
    path = tmp_path / "mag.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    csv_utils.download_warehouse_csv()

    assert called["init"] == (None, None, None)
    assert called["args"] == (str(path), str(path))


def test_download_warehouse_csv_http(monkeypatch, tmp_path):
    data = b"name;price\n"
    called = {}

    class DummyResponse:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    def dummy_get(url, timeout=30):
        called["url"] = url
        return DummyResponse(data)

    class FailingWebDAVClient:
        def __init__(self, *a, **kw):
            raise AssertionError("WebDAV should not be used when URL is provided")

    monkeypatch.setattr(csv_utils, "WebDAVClient", FailingWebDAVClient)
    monkeypatch.setattr(csv_utils.requests, "get", dummy_get)
    url = "http://example.com/mag.csv"
    monkeypatch.setenv("WAREHOUSE_CSV_URL", url)
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV_URL", url)
    path = tmp_path / "mag.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    csv_utils.download_warehouse_csv()

    assert called["url"] == url
    assert path.read_bytes() == data


def test_download_warehouse_csv_http_error_logs(monkeypatch, tmp_path, caplog):
    def failing_get(url, timeout=30):
        raise RequestException("network down")

    monkeypatch.setattr(csv_utils.requests, "get", failing_get)
    url = "http://example.com/mag.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV_URL", url)
    path = tmp_path / "mag.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    with caplog.at_level(logging.WARNING):
        csv_utils.download_warehouse_csv()

    assert "Failed to download warehouse CSV" in caplog.text
