import io
from pathlib import Path
from PIL import Image

from kartoteka.image_utils import load_rgba_image


def test_load_rgba_image_missing_file(tmp_path):
    assert load_rgba_image(tmp_path / "missing.png") is None


def test_load_rgba_image_invalid_image(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert load_rgba_image(bad) is None


def test_load_rgba_image_valid_image(tmp_path):
    path = tmp_path / "ok.png"
    Image.new("RGB", (1, 1), "white").save(path)
    img = load_rgba_image(path)
    assert img is not None
    assert img.mode == "RGBA"
    assert img.size == (1, 1)
