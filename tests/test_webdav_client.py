import sys
import types
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import requests
from webdav_client import WebDAVClient


def test_download_file(monkeypatch, tmp_path):
    called = {}

    def fake_get(url, auth, timeout=None):
        called['url'] = url
        called['auth'] = auth
        return types.SimpleNamespace(status_code=200, content=b'data', text='')

    monkeypatch.setattr(requests, 'get', fake_get)
    monkeypatch.setenv('WEBDAV_URL', 'http://example.com')
    monkeypatch.setenv('WEBDAV_USER', 'u')
    monkeypatch.setenv('WEBDAV_PASSWORD', 'p')
    dest = tmp_path / 'file.txt'
    client = WebDAVClient()
    client.download_file('remote.txt', str(dest))
    assert dest.read_bytes() == b'data'
    assert called['url'] == 'http://example.com/remote.txt'
    assert called['auth'] == ('u', 'p')


def test_upload_file(monkeypatch, tmp_path):
    called = {}

    def fake_put(url, data, auth, timeout=None):
        called['url'] = url
        called['auth'] = auth
        called['data'] = data.read()
        return types.SimpleNamespace(status_code=201, text='')

    monkeypatch.setattr(requests, 'put', fake_put)
    monkeypatch.setenv('WEBDAV_URL', 'http://example.com')
    monkeypatch.setenv('WEBDAV_USER', 'u')
    monkeypatch.setenv('WEBDAV_PASSWORD', 'p')
    src = tmp_path / 'local.txt'
    src.write_text('hello')
    client = WebDAVClient()
    client.upload_file(str(src), 'remote.txt')
    assert called['url'] == 'http://example.com/remote.txt'
    assert called['auth'] == ('u', 'p')
    assert called['data'] == b'hello'
