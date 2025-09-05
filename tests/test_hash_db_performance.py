import timeit
import numpy as np

from hash_db import HashDB


def _random_fp():
    return {
        "phash": np.random.randint(0, 2, (8, 8), dtype=np.uint8),
        "dhash": np.random.randint(0, 2, (8, 8), dtype=np.uint8),
        "tile_phash": np.random.randint(0, 2, (4, 8, 8), dtype=np.uint8),
        "orb": np.empty((0, 32), dtype=np.uint8),
    }


def _best_match_old(db: HashDB, source, max_distance: int):
    candidates = db.candidates(source, limit=1)
    if not candidates:
        return None
    best = candidates[0]
    if best.distance > max_distance:
        return None
    return best


def test_best_match_performance():
    db = HashDB()
    fp = _random_fp()
    db.add_card_from_fp(fp, meta={"id": "match"})
    for i in range(1000):
        db.add_card_from_fp(_random_fp(), meta={"id": str(i)})

    def run_old():
        assert _best_match_old(db, fp, 5) is not None

    def run_new():
        assert db.best_match(fp, max_distance=5) is not None

    old_time = timeit.timeit(run_old, number=3)
    new_time = timeit.timeit(run_new, number=3)
    assert new_time < old_time
