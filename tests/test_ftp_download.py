from ftp_client import FTPClient


def test_download_file(tmp_path):
    data = b"hello"

    class DummyFTP:
        def __init__(self):
            self.commands = []

        def retrbinary(self, cmd, callback):
            self.commands.append(cmd)
            callback(data)

    client = FTPClient("h", "u", "p")
    client.ftp = DummyFTP()
    dest = tmp_path / "local.txt"
    client.download_file("remote.txt", str(dest))
    assert dest.read_bytes() == data
    assert client.ftp.commands == ["RETR remote.txt"]


def test_download_file_connects(monkeypatch, tmp_path):
    payload = b"data"

    class DummyFTP:
        def retrbinary(self, cmd, callback):
            callback(payload)

    connected = False

    def fake_connect(self):
        nonlocal connected
        connected = True
        self.ftp = DummyFTP()

    monkeypatch.setattr(FTPClient, "connect", fake_connect)
    client = FTPClient("h", "u", "p")
    dest = tmp_path / "file.txt"
    client.download_file("remote.bin", str(dest))
    assert connected
    assert dest.read_bytes() == payload
