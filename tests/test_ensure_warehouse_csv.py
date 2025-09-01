import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def test_ensure_warehouse_csv_downloads_once(monkeypatch, tmp_path):
    data = b"name;price\n"
    path = tmp_path / "magazyn.csv"
    called = {"count": 0}

    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    def dummy_download():
        called["count"] += 1
        path.write_bytes(data)

    monkeypatch.setattr(csv_utils, "download_warehouse_csv", dummy_download)

    assert not path.exists()
    csv_utils.ensure_warehouse_csv()
    assert path.read_bytes() == data
    assert called["count"] == 1

    csv_utils.ensure_warehouse_csv()
    assert called["count"] == 1
