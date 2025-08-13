import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.append(str(Path(__file__).resolve().parents[1]))
from hash_db import HashDB


def _create_sample_image(path: Path) -> None:
    img = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, 48, 48], fill="black")
    img.save(path)


def test_scan_rescan_persists_and_deduplicates(tmp_path):
    db_path = tmp_path / "hashes.sqlite"
    img_path = tmp_path / "sample.png"
    _create_sample_image(img_path)

    db = HashDB(str(db_path))
    first_id = db.add_card_from_image(str(img_path), meta={"name": "sample"})
    db.conn.close()

    db2 = HashDB(str(db_path))
    candidate = db2.best_match(str(img_path))
    assert candidate is not None
    assert candidate.meta["name"] == "sample"

    duplicate_id = db2.add_card_from_image(str(img_path), meta={"name": "sample"})
    assert duplicate_id == first_id

    cur = db2.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM cards")
    assert cur.fetchone()[0] == 1
