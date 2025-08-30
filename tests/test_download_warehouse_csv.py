from kartoteka import csv_utils


def test_download_warehouse_csv(monkeypatch, tmp_path):
    called = {}

    class DummyFTPClient:
        def __init__(self, host, user, password):
            called["init"] = (host, user, password)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def download_file(self, remote_path, local_path=None):
            called["args"] = (remote_path, local_path)

    monkeypatch.setattr(csv_utils, "FTPClient", DummyFTPClient)
    monkeypatch.setattr(csv_utils, "FTP_HOST", "h")
    monkeypatch.setattr(csv_utils, "FTP_USER", "u")
    monkeypatch.setattr(csv_utils, "FTP_PASSWORD", "p")
    path = tmp_path / "mag.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    csv_utils.download_warehouse_csv()

    assert called["init"] == ("h", "u", "p")
    assert called["args"] == (str(path), str(path))
