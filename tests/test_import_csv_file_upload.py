import pytest
from shoper_client import ShoperClient


def test_import_csv_posts_file(tmp_path, monkeypatch):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id;name\n1;test\n", encoding="utf-8")

    client = ShoperClient(base_url="https://shop", token="tok")

    def fake_post(endpoint, files=None):
        assert endpoint == "products/import"
        assert "file" in files
        filename, fileobj, content_type = files["file"]
        assert filename == "data.csv"
        assert content_type == "text/csv"
        assert fileobj.read() == b"id;name\n1;test\n"
        return {}

    monkeypatch.setattr(client, "post", fake_post)
    result = client.import_csv(str(csv_file))
    assert result == {}


def test_import_csv_raises_when_post_fails(tmp_path, monkeypatch):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id;name\n1;test\n", encoding="utf-8")

    client = ShoperClient(base_url="https://shop", token="tok")

    def failing_post(endpoint, files=None):
        raise RuntimeError("post failed")

    monkeypatch.setattr(client, "post", failing_post)

    with pytest.raises(RuntimeError, match="post failed"):
        client.import_csv(str(csv_file))
