"""Image fingerprinting utilities.

This module provides helper functions to compute perceptual hashes and ORB
feature descriptors for images.  The goal is to offer lightweight utilities
for identifying scanned cards.  The functions return plain ``numpy`` arrays so
that the results can easily be serialised or further processed.
"""
from __future__ import annotations

from typing import Tuple, Dict

import base64
import io

import numpy as np
from PIL import Image, ImageOps
import imagehash

try:  # ``opencv`` is an optional dependency
    import cv2  # type: ignore
except Exception:  # pragma: no cover - handled gracefully during runtime
    cv2 = None  # type: ignore

# ---------------------------------------------------------------------------
# normalisation helpers
# ---------------------------------------------------------------------------

def normalize_card_image(image: Image.Image, size: Tuple[int, int] = (256, 256)) -> np.ndarray:
    """Return a normalised grayscale representation of ``image``.

    The card images used throughout the project may contain orientation meta
    data and can vary heavily in size.  To make fingerprinting reliable we
    transpose the image according to the EXIF orientation, convert it to
    grayscale and resize it to ``size`` while keeping the aspect ratio.

    Parameters
    ----------
    image:
        Input :class:`PIL.Image.Image` object.
    size:
        Target size for the normalised image.

    Returns
    -------
    :class:`numpy.ndarray`
        A 2‑D array containing the normalised image data in ``uint8`` format.
    """

    image = ImageOps.exif_transpose(image)
    image = ImageOps.fit(image.convert("L"), size, method=Image.Resampling.LANCZOS)
    return np.array(image)


# ---------------------------------------------------------------------------
# hashing utilities
# ---------------------------------------------------------------------------


def _hash_to_array(hash_obj: imagehash.ImageHash) -> np.ndarray:
    """Convert an :class:`imagehash.ImageHash` to a ``numpy`` array."""
    return np.array(hash_obj.hash, dtype=np.uint8)


def compute_fingerprint(
    image: Image.Image,
    *,
    tile_grid: Tuple[int, int] = (2, 2),
    use_orb: bool | None = False,
) -> Dict[str, np.ndarray]:
    """Compute perceptual hashes and optionally ORB descriptors for ``image``.

    Parameters
    ----------
    image:
        Input image from which the fingerprint is generated.
    tile_grid:
        The grid (rows, cols) used for computing tile pHashes.  Each tile is
        hashed individually and the resulting hashes are stacked into a 3‑D
        array of shape ``(rows*cols, 8, 8)``.
    use_orb:
        When ``True`` and OpenCV is available, ORB descriptors are computed and
        returned in the ``"orb"`` field.  When OpenCV is not installed an empty
        array is returned.

    Returns
    -------
    dict
        A dictionary containing the keys ``"phash"``, ``"dhash"``,
        ``"tile_phash"`` and ``"orb"``.
    """

    normalised = normalize_card_image(image)
    pil_gray = Image.fromarray(normalised)

    # global hashes
    phash = _hash_to_array(imagehash.phash(pil_gray))
    dhash = _hash_to_array(imagehash.dhash(pil_gray))

    # tile based hashes
    rows, cols = tile_grid
    h, w = normalised.shape
    tiles: list[np.ndarray] = []
    for r in range(rows):
        for c in range(cols):
            tile = normalised[r * h // rows : (r + 1) * h // rows, c * w // cols : (c + 1) * w // cols]
            tiles.append(_hash_to_array(imagehash.phash(Image.fromarray(tile))))
    tile_phash = np.stack(tiles)

    # ORB descriptors (optional)
    orb_desc = np.empty((0, 32), dtype=np.uint8)
    if use_orb and cv2 is not None:  # pragma: no cover - cv2 might be missing
        detector = cv2.ORB_create()
        keypoints, descriptors = detector.detectAndCompute(normalised, None)
        if descriptors is not None:
            orb_desc = descriptors.astype(np.uint8)

    return {
        "phash": phash,
        "dhash": dhash,
        "tile_phash": tile_phash,
        "orb": orb_desc,
    }


# ---------------------------------------------------------------------------
# ndarray serialisation helpers
# ---------------------------------------------------------------------------


def pack_ndarray(arr: np.ndarray) -> str:
    """Serialise ``arr`` to a base64 encoded string.

    ``numpy.save`` is used internally which preserves dtype and shape.  The
    resulting byte stream is encoded using base64 so that it can easily be
    stored in JSON files.
    """

    buf = io.BytesIO()
    np.save(buf, arr)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def unpack_ndarray(data: str) -> np.ndarray:
    """Inverse operation of :func:`pack_ndarray`."""

    buf = io.BytesIO(base64.b64decode(data.encode("ascii")))
    buf.seek(0)
    return np.load(buf, allow_pickle=False)


# ---------------------------------------------------------------------------
# comparison helpers
# ---------------------------------------------------------------------------


def hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """Return the Hamming distance between two binary arrays."""

    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    if a.shape != b.shape:
        raise ValueError("Array shapes do not match")
    return int(np.count_nonzero(a != b))


def match_orb(des1: np.ndarray, des2: np.ndarray, ratio: float = 0.75) -> int:
    """Count good matches between two sets of ORB descriptors.

    The function applies the ratio test described by D. Lowe to filter the
    matches.  When OpenCV is not installed or either descriptor array is empty
    ``0`` is returned.
    """

    if cv2 is None:  # pragma: no cover - handled gracefully
        return 0
    des1 = np.asarray(des1, dtype=np.uint8)
    des2 = np.asarray(des2, dtype=np.uint8)
    if des1.size == 0 or des2.size == 0:
        return 0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(des1, des2, k=2)
    good = 0
    for m, n in matches:
        if m.distance < ratio * n.distance:
            good += 1
    return good


__all__ = [
    "normalize_card_image",
    "compute_fingerprint",
    "pack_ndarray",
    "unpack_ndarray",
    "hamming_distance",
    "match_orb",
]
