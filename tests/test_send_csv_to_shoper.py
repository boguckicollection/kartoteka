import sys
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka.csv_utils import send_csv_to_shoper


def test_send_csv_shows_status_on_success(tmp_path):
    dummy_client = SimpleNamespace(import_csv=lambda p: {"status": "completed"})
    app = SimpleNamespace(shoper_client=dummy_client)
    with patch("tkinter.messagebox.showinfo") as info, patch(
        "tkinter.messagebox.showerror"
    ) as error:
        send_csv_to_shoper(app, str(tmp_path / "file.csv"))
        info.assert_called_once()
        error.assert_not_called()
        assert "completed" in info.call_args[0][1]


def test_send_csv_shows_errors_and_warnings(tmp_path):
    dummy_client = SimpleNamespace(
        import_csv=lambda p: {"status": "completed", "warnings": ["warn"], "errors": ["err"]}
    )
    app = SimpleNamespace(shoper_client=dummy_client)
    with patch("tkinter.messagebox.showinfo") as info, patch(
        "tkinter.messagebox.showerror"
    ) as error:
        send_csv_to_shoper(app, str(tmp_path / "file.csv"))
        error.assert_called_once()
        info.assert_not_called()
        msg = error.call_args[0][1]
        assert "warn" in msg and "err" in msg


def test_send_csv_uses_webdav(monkeypatch, tmp_path):
    called = {}

    class DummyClient:
        def __init__(self, base_url=None, user=None, password=None):
            called['init'] = (base_url, user, password)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def upload_file(self, path, remote_name=None):
            called['path'] = path

    monkeypatch.setattr('kartoteka.csv_utils.WebDAVClient', DummyClient)
    app = SimpleNamespace(shoper_client=None, WEBDAV_URL='h', WEBDAV_USER='u', WEBDAV_PASSWORD='p')
    with patch('tkinter.messagebox.showinfo') as info, patch('tkinter.messagebox.showerror') as error:
        send_csv_to_shoper(app, str(tmp_path / 'file.csv'))
        info.assert_called_once()
        error.assert_not_called()
    assert called['init'] == ('h', 'u', 'p')
    assert called['path'].endswith('file.csv')

