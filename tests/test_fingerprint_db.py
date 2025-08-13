import numpy as np
import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.append(str(Path(__file__).resolve().parents[1]))
from fingerprint import compute_fingerprint, unpack_ndarray
from hash_db import HashDB


def _create_sample_image(path: Path) -> Image.Image:
    """Create and save a simple test image."""
    img = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, 48, 48], fill="black")
    img.save(path)
    return img


def _create_similar_image(original: Image.Image, path: Path) -> Image.Image:
    """Create a slightly modified copy of ``original`` and save it."""
    img = original.copy()
    draw = ImageDraw.Draw(img)
    for x in range(5):
        draw.point((x, x), fill="red")
    img.save(path)
    return img


def test_insert_and_retrieve_fingerprint(tmp_path):
    db_path = tmp_path / "hashes.sqlite"
    img_path = tmp_path / "sample.png"
    image = _create_sample_image(img_path)

    fp = compute_fingerprint(image)
    db = HashDB(str(db_path))
    row_id = db.add_card_from_fp(fp, meta={"name": "sample"})

    cur = db.conn.cursor()
    cur.execute("SELECT phash, dhash, tile_phash FROM cards WHERE id=?", (row_id,))
    row = cur.fetchone()
    assert row is not None

    stored_fp = {
        "phash": unpack_ndarray(row["phash"]),
        "dhash": unpack_ndarray(row["dhash"]),
        "tile_phash": unpack_ndarray(row["tile_phash"]),
    }
    assert np.array_equal(stored_fp["phash"], fp["phash"])
    assert np.array_equal(stored_fp["dhash"], fp["dhash"])
    assert np.array_equal(stored_fp["tile_phash"], fp["tile_phash"])


def test_best_match_returns_inserted_record_for_similar_image(tmp_path):
    db_path = tmp_path / "hashes.sqlite"
    orig_path = tmp_path / "orig.png"
    image = _create_sample_image(orig_path)
    fp = compute_fingerprint(image)
    db = HashDB(str(db_path))
    db.add_card_from_fp(fp, meta={"name": "original"})

    query_path = tmp_path / "query.png"
    query_image = _create_similar_image(image, query_path)

    candidate = db.best_match(str(query_path))
    assert candidate is not None
    assert candidate.meta["name"] == "original"

    fp_query = compute_fingerprint(query_image)
    expected_distance = db._distance(fp, fp_query)
    assert candidate.distance == expected_distance
