import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def startup():
    if not os.path.exists(csv_utils.WAREHOUSE_CSV):
        csv_utils.download_warehouse_csv()


def test_startup_download(monkeypatch, tmp_path):
    data = b"name;price\n"
    url = "http://example.com/mag.csv"
    path = tmp_path / "magazyn.csv"
    called = {"count": 0}

    monkeypatch.setenv("WAREHOUSE_CSV_URL", url)
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV_URL", url)
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    class DummyResponse:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    def dummy_get(u, timeout=30):
        called["count"] += 1
        return DummyResponse(data)

    monkeypatch.setattr(csv_utils.requests, "get", dummy_get)
    assert not path.exists()

    startup()
    assert path.read_bytes() == data
    assert called["count"] == 1

    startup()
    assert called["count"] == 1
