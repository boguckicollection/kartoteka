"""Simple SQLite backed storage for card image fingerprints.

This module provides the :class:`HashDB` class which stores perceptual image
hashes and assorted card meta data inside a small SQLite database.  It is used
by the tests as a light‑weight stand in for a real image recognition index.

The database schema is intentionally tiny and mirrors the structure used in the
project's documentation.  Every row represents a single card and stores the
calculated hashes alongside a JSON encoded ``meta`` column containing arbitrary
card information such as the card name, number or set code.  The hashes are
serialised using :func:`fingerprint.pack_ndarray` so they can be stored as text
fields in the database.

Only a couple of high level methods are exposed:

``add_card_from_image``
    Convenience wrapper that computes a fingerprint from an image file and
    stores it together with the supplied meta data.
``add_card_from_fp``
    Store a pre‑computed fingerprint.  The fingerprint format follows the
    output of :func:`fingerprint.compute_fingerprint`.
``candidates``
    Return the best matching entries for the supplied fingerprint or image.
``best_match``
    Return only the single best match from :meth:`candidates`.

The matching algorithm is deliberately uncomplicated – it simply sums the
Hamming distances of the global and tiled pHashes as well as the dHash.  When
ORB descriptors are present the amount of good matches is subtracted from the
distance so that descriptors with more matches rank higher.  This provides
reasonably stable results without having to rely on any external libraries or
extensions in SQLite itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
import threading
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from fingerprint import (
    compute_fingerprint,
    hamming_distance,
    match_orb,
    pack_ndarray,
    unpack_ndarray,
)


# ---------------------------------------------------------------------------
# data containers
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """Result returned by :meth:`HashDB.candidates`.

    Attributes
    ----------
    meta:
        Dictionary of card meta data that was stored alongside the hashes.
    distance:
        Calculated distance – smaller values indicate a better match.
    """

    meta: Mapping[str, str]
    distance: int


# ---------------------------------------------------------------------------
# main database wrapper
# ---------------------------------------------------------------------------


class HashDB:
    """Store and query image fingerprints in an SQLite database."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        # rows as dict-like objects
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    # ------------------------------------------------------------------
    # schema handling
    # ------------------------------------------------------------------
    def _ensure_schema(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phash TEXT NOT NULL,
                    dhash TEXT NOT NULL,
                    tile_phash TEXT NOT NULL,
                    orb TEXT,
                    meta TEXT
                )
                """
            )
            # prevent storing duplicate fingerprints
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_hashes
                ON cards (phash, dhash, tile_phash, orb)
                """
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _serialise_fp(self, fp: Mapping[str, np.ndarray]) -> Tuple[str, str, str, str]:
        """Return serialised fingerprint components."""

        phash = pack_ndarray(np.asarray(fp["phash"], dtype=np.uint8))
        dhash = pack_ndarray(np.asarray(fp["dhash"], dtype=np.uint8))
        tile_phash = pack_ndarray(np.asarray(fp["tile_phash"], dtype=np.uint8))
        orb = pack_ndarray(np.asarray(fp.get("orb", np.empty((0, 32), dtype=np.uint8)), dtype=np.uint8))
        return phash, dhash, tile_phash, orb

    def _prepare_fp(self, source) -> Mapping[str, np.ndarray]:
        """Return a fingerprint for *source*.

        ``source`` may either be a mapping already containing a fingerprint or
        a path/``PIL.Image`` object from which a fingerprint is computed.
        """

        if isinstance(source, Mapping):
            return source
        if isinstance(source, Image.Image):
            try:
                return compute_fingerprint(source, use_orb=True)
            except TypeError:
                return compute_fingerprint(source)
        # otherwise treat the argument as a filesystem path
        with Image.open(source) as img:
            try:
                return compute_fingerprint(img, use_orb=True)
            except TypeError:
                return compute_fingerprint(img)

    # ------------------------------------------------------------------
    # insert methods
    # ------------------------------------------------------------------
    def add_card_from_image(self, image_path: str, meta: Optional[Mapping[str, str]] = None, **kwargs) -> int:
        """Compute the fingerprint for ``image_path`` and store it.

        Additional keyword arguments are merged into ``meta`` before the entry
        is written to the database.  The method returns the database row id of
        the inserted record.
        """

        meta_dict = dict(meta or {})
        meta_dict.update(kwargs)
        with Image.open(image_path) as img:
            try:
                fp = compute_fingerprint(img, use_orb=True)
            except TypeError:
                fp = compute_fingerprint(img)
        return self.add_card_from_fp(fp, meta_dict)

    def add_card_from_fp(self, fp: Mapping[str, np.ndarray], meta: Optional[Mapping[str, str]] = None, **kwargs) -> int:
        """Store a pre-computed fingerprint.

        ``fp`` follows the structure returned by :func:`compute_fingerprint`.
        Meta data is stored as JSON.  The database row id of the inserted
        record is returned.
        """

        meta_dict = dict(meta or {})
        meta_dict.update(kwargs)

        phash, dhash, tile_phash, orb = self._serialise_fp(fp)
        with self._lock:
            cur = self.conn.cursor()
            # return existing row id if the fingerprint is already stored
            cur.execute(
                "SELECT id FROM cards WHERE phash=? AND dhash=? AND tile_phash=? AND orb=?",
                (phash, dhash, tile_phash, orb),
            )
            row = cur.fetchone()
            if row is not None:
                return int(row["id"])

            try:
                cur.execute(
                    "INSERT INTO cards (phash, dhash, tile_phash, orb, meta) VALUES (?, ?, ?, ?, ?)",
                    (phash, dhash, tile_phash, orb, json.dumps(meta_dict, ensure_ascii=False)),
                )
                self.conn.commit()
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                # another process might have inserted the same fingerprint concurrently
                cur.execute(
                    "SELECT id FROM cards WHERE phash=? AND dhash=? AND tile_phash=? AND orb=?",
                    (phash, dhash, tile_phash, orb),
                )
                row = cur.fetchone()
                if row is None:
                    raise
                return int(row["id"])

    # ------------------------------------------------------------------
    # query helpers
    # ------------------------------------------------------------------
    def _distance(self, fp_a: Mapping[str, np.ndarray], fp_b: Mapping[str, np.ndarray]) -> int:
        """Return a distance score between two fingerprints."""

        score = 0
        score += hamming_distance(fp_a["phash"], fp_b["phash"])
        score += hamming_distance(fp_a["dhash"], fp_b["dhash"])

        tiles_a = fp_a["tile_phash"]
        tiles_b = fp_b["tile_phash"]
        score += sum(hamming_distance(a, b) for a, b in zip(tiles_a, tiles_b))

        orb_matches = match_orb(
            fp_a.get("orb", np.empty((0, 32), dtype=np.uint8)),
            fp_b.get("orb", np.empty((0, 32), dtype=np.uint8)),
        )
        # more ORB matches should reduce the distance
        score -= orb_matches

        return max(0, int(score))

    def candidates(
        self, source, limit: int = 4, max_distance: Optional[int] = None
    ) -> List[Candidate]:
        """Return best matching candidates for ``source``.

        ``source`` may either be a fingerprint mapping or any value accepted by
        :func:`PIL.Image.open`.

        Parameters
        ----------
        max_distance:
            Optional maximum allowed distance for returned candidates.  Once
            ``limit`` candidates within this distance have been found the
            search stops early.
        """

        fp_query = self._prepare_fp(source)

        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT phash, dhash, tile_phash, orb, meta FROM cards")
            rows = cur.fetchall()

        results: List[Candidate] = []
        for row in rows:
            fp_row = {
                "phash": unpack_ndarray(row["phash"]),
                "dhash": unpack_ndarray(row["dhash"]),
                "tile_phash": unpack_ndarray(row["tile_phash"]),
                "orb": unpack_ndarray(row["orb"]) if row["orb"] else np.empty((0, 32), dtype=np.uint8),
            }
            dist = self._distance(fp_query, fp_row)
            if max_distance is not None and dist > max_distance:
                continue
            meta = json.loads(row["meta"] or "{}")
            results.append(Candidate(meta=meta, distance=dist))
            if max_distance is not None and len(results) >= limit:
                break

        results.sort(key=lambda c: c.distance)
        return results[:limit]

    def best_match(self, source, max_distance: Optional[int] = None) -> Optional[Candidate]:
        """Return the single best match for ``source`` or ``None``.

        Parameters
        ----------
        source:
            Fingerprint mapping or image path used for the lookup.
        max_distance:
            Optional maximum allowed distance for a match.  If the best
            candidate exceeds this distance, ``None`` is returned instead.
        """

        candidates = self.candidates(source, limit=1, max_distance=max_distance)
        if not candidates:
            return None
        best = candidates[0]
        if max_distance is not None and best.distance > max_distance:
            return None
        return best


__all__ = ["HashDB", "Candidate"]

