import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import customtkinter as ctk
import tkinter.ttk as ttk
from PIL import Image, ImageTk, ImageFilter, ImageOps, ImageDraw, UnidentifiedImageError
import imagehash
import os
import csv
import json
import requests
import base64
import mimetypes
import re
import asyncio
import datetime
import time
from collections import defaultdict
from dotenv import load_dotenv, set_key
import unicodedata
from itertools import combinations
import html
import difflib
import sys
from typing import Iterable, Optional
from types import SimpleNamespace
from pydantic import BaseModel
import pytesseract
from pathlib import Path

try:  # pragma: no cover - optional dependency
    import openai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openai = SimpleNamespace(
        OpenAI=lambda *a, **k: SimpleNamespace(),
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None)),
        OpenAIError=Exception,
    )
else:  # pragma: no cover - optional dependency
    # accessing ``openai.chat`` on some versions can trigger network-heavy
    # initialization; provide a simple stub so tests can monkeypatch it
    if not hasattr(openai, "chat") or isinstance(openai.chat, property):
        openai.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda *a, **k: None)
        )

from shoper_client import ShoperClient
from webdav_client import WebDAVClient
from . import csv_utils, storage, stats_utils
import threading
from urllib.parse import urlencode, urlparse
import io
import webbrowser
import logging
from gettext import gettext as _
try:  # pragma: no cover - optional dependency
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except Exception:  # pragma: no cover - optional dependency
    Figure = None  # type: ignore[assignment]
    FigureCanvasTkAgg = None  # type: ignore[assignment]
try:
    from hash_db import HashDB, Candidate
except ImportError as exc:  # pragma: no cover - optional dependency
    logging.getLogger(__name__).info("HashDB import failed: %s", exc)
    HashDB = None  # type: ignore[assignment]
    Candidate = None  # type: ignore[assignment]
from fingerprint import compute_fingerprint
from tooltip import Tooltip
from .image_utils import load_rgba_image
from .storage_config import (
    BOX_COUNT,
    BOX_COLUMN_CAPACITY,
    SPECIAL_BOX_CAPACITY,
    SPECIAL_BOX_NUMBER,
    STANDARD_BOX_CAPACITY,
    STANDARD_BOX_COLUMNS,
)

# Ensure tkinter dialog modules provide the expected functions even when tests
# replace them with simple stubs.  Missing attributes are replaced with no-op
# callables so that downstream monkeypatching can occur reliably.
for _name, _mod, _attrs in (
    ("tkinter.filedialog", filedialog, ["askdirectory", "askopenfilename", "asksaveasfilename"]),
    (
        "tkinter.messagebox",
        messagebox,
        ["showinfo", "showerror", "showwarning", "askyesno"],
    ),
    ("tkinter.simpledialog", simpledialog, ["askstring", "askinteger"]),
):
    for _attr in _attrs:
        if not hasattr(_mod, _attr):
            setattr(_mod, _attr, lambda *a, **k: None)
    sys.modules.setdefault(_name, _mod)

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(ENV_FILE)

logger = logging.getLogger(__name__)

BASE_IMAGE_URL = os.getenv("BASE_IMAGE_URL", "https://sklep839679.shoparena.pl/upload/images")
SCANS_DIR = os.getenv("SCANS_DIR", "scans")

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

SHOPER_API_URL = os.getenv("SHOPER_API_URL", "").strip()
SHOPER_API_TOKEN = os.getenv("SHOPER_API_TOKEN", "").strip()
WEBDAV_URL = os.getenv("WEBDAV_URL")
WEBDAV_USER = os.getenv("WEBDAV_USER")
WEBDAV_PASSWORD = os.getenv("WEBDAV_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_OPENAI_STUB = not OPENAI_API_KEY or os.getenv("OPENAI_TEST_MODE")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
if USE_OPENAI_STUB:
    openai.OpenAI = lambda *a, **k: SimpleNamespace()

PRICE_DB_PATH = "card_prices.csv"
PRICE_MULTIPLIER = 1.23
HOLO_REVERSE_MULTIPLIER = 3.5
SET_LOGO_DIR = "set_logos"
HASH_DIFF_THRESHOLD = 20  # hash difference threshold for accepting matches
HASH_MATCH_THRESHOLD = 5  # maximum allowed fingerprint distance
HASH_SIZE = (32, 32)
PSA_ICON_URL = "https://www.pngkey.com/png/full/231-2310791_psa-grading-standards-professional-sports-authenticator.png"

# toggle automatic fingerprint lookup via environment variable
AUTO_HASH_LOOKUP = os.getenv("AUTO_HASH_LOOKUP", "1") not in {"0", "false", "False"}

# optional path to enable persistent fingerprint storage
HASH_DB_FILE = os.getenv("HASH_DB_FILE")

# minimum similarity ratio for fuzzy set code matching
SET_CODE_MATCH_CUTOFF = 0.8
try:
    SET_CODE_MATCH_CUTOFF = float(
        os.getenv("SET_CODE_MATCH_CUTOFF", SET_CODE_MATCH_CUTOFF)
    )
except ValueError:
    pass

_LOGO_HASHES: dict[str, tuple[imagehash.ImageHash, imagehash.ImageHash, imagehash.ImageHash]] = {}

# simple cache for downloaded remote images; values store the raw bytes (or
# ``None`` for failed downloads) along with the timestamp they were fetched.
# Entries older than ``_IMAGE_CACHE_TTL`` seconds are considered stale and will
# be refreshed on the next access.
_IMAGE_CACHE_TTL = 300  # seconds
_IMAGE_CACHE: dict[str, tuple[Optional[bytes], float]] = {}

# cache for resized thumbnails keyed by source path/URL
_THUMB_CACHE: dict[str, Image.Image] = {}


def draw_box_usage(canvas: "tk.Canvas", box_num: int, occupancy: dict[int, int]) -> float:
    """Draw per-column occupancy of a storage box on ``canvas``.

    Parameters
    ----------
    canvas:
        Target canvas to draw rectangles on.
    box_num:
        Identifier of the storage box.
    occupancy:
        Mapping of ``column -> used slots`` for ``box_num``.

    Returns
    -------
    float
        Overall percentage of used slots in the box.
    """

    box_w = BOX_THUMB_SIZE
    box_h = BOX_THUMB_SIZE
    columns = storage.BOX_COLUMNS.get(box_num, STANDARD_BOX_COLUMNS)
    total_capacity = storage.BOX_CAPACITY.get(
        box_num, columns * storage.BOX_COLUMN_CAPACITY
    )
    col_capacity = total_capacity / columns if columns else storage.BOX_COLUMN_CAPACITY

    # track rectangles for each column so we can update their coordinates/colors
    overlay_ids: dict[int, int] = getattr(canvas, "overlay_ids", {})
    if not isinstance(overlay_ids, dict):
        overlay_ids = {}
    canvas.overlay_ids = overlay_ids

    if box_num == SPECIAL_BOX_NUMBER:
        inner_w = BOX_THUMB_SIZE - 2 * BOX100_X_INSET
        inner_h = BOX_THUMB_SIZE - 2 * BOX100_Y_INSET
        col_w = inner_w / columns if columns else inner_w
    else:
        col_w = box_w / columns if columns else box_w
    total_used = 0
    for col in range(1, columns + 1):
        used = occupancy.get(col, 0)
        total_used += used
        value = used / col_capacity if col_capacity else 0
        if box_num == SPECIAL_BOX_NUMBER:
            fill_h = inner_h * value
            x0 = BOX100_X_INSET + (col - 1) * col_w
            x1 = x0 + col_w
            y1 = BOX_THUMB_SIZE - BOX100_Y_INSET - fill_h
            box_bottom = BOX_THUMB_SIZE - BOX100_Y_INSET
        else:
            fill_h = box_h * value
            y1 = box_h - fill_h
            x0 = (col - 1) * col_w
            x1 = col * col_w
            box_bottom = box_h
        color = _occupancy_color(value)

        rect_id = overlay_ids.get(col)
        if rect_id is None:
            rect_id = canvas.create_rectangle(x0, y1, x1, box_bottom, fill=color, outline="")
            overlay_ids[col] = rect_id
        else:
            canvas.coords(rect_id, x0, y1, x1, box_bottom)
            canvas.itemconfigure(rect_id, fill=color)

    occupied_percent = total_used / total_capacity * 100 if total_capacity else 0
    return occupied_percent


def _load_image(path: str) -> Optional[Image.Image]:
    """Load image from local path or URL with caching.

    Parameters
    ----------
    path:
        Local filesystem path or HTTP(S) URL.

    Returns
    -------
    Optional[Image.Image]
        Loaded PIL Image or ``None`` on failure.
    """

    if not path:
        return None

    if os.path.exists(path):
        img = load_rgba_image(path)
        if img is None:
            logger.warning("Failed to open image %s", path)
        return img

    parsed = urlparse(path)
    if parsed.scheme in ("http", "https"):
        cached = _IMAGE_CACHE.get(path)
        if cached is not None:
            data, ts = cached
            if time.time() - ts < _IMAGE_CACHE_TTL:
                if data is None:
                    return None
                img = load_rgba_image(io.BytesIO(data))
                if img is not None:
                    return img
                return None
            else:
                # expire stale entry
                _IMAGE_CACHE.pop(path, None)
        try:
            resp = requests.get(path, timeout=5)
            resp.raise_for_status()
            data = resp.content
            _IMAGE_CACHE[path] = (data, time.time())
            img = load_rgba_image(io.BytesIO(data))
            if img is not None:
                return img
            return None
        except requests.RequestException as exc:
            logger.warning("Failed to download image %s: %s", path, exc)
            _IMAGE_CACHE[path] = (None, time.time())
            return None

    return None


def _get_thumbnail(path: str, size: tuple[int, int]) -> Optional[Image.Image]:
    """Return a cached resized PIL image for ``path``.

    The image is loaded via :func:`_load_image` and resized using
    :py:meth:`PIL.Image.Image.thumbnail`. Subsequent calls with the same
    ``path`` reuse the stored thumbnail to avoid redundant disk or network
    operations.
    """

    if not path:
        return None
    cached = _THUMB_CACHE.get(path)
    if cached is not None:
        return cached
    img = _load_image(path)
    if img is None:
        return None
    img.thumbnail(size)
    _THUMB_CACHE[path] = img
    return img


def _create_image(img: Image.Image):
    """Return a CTkImage if available, otherwise a PhotoImage."""
    if hasattr(ctk, "CTkImage"):
        return ctk.CTkImage(light_image=img, size=img.size)
    return ImageTk.PhotoImage(img)


def _resize_to_width(img: Image.Image, width: int) -> Image.Image:
    """Return a copy of ``img`` scaled to the given ``width`` preserving aspect.

    The height is calculated from the original image ratio. If the source
    image is already smaller than ``width`` no upscaling is performed.
    """

    if width <= 0 or img.width == 0:
        return img
    if img.width == width:
        return img
    ratio = width / img.width
    height = max(1, int(img.height * ratio))
    return img.resize((width, height), Image.Resampling.LANCZOS)


def _preprocess_symbol(im: Image.Image) -> Image.Image:
    """Normalize symbol/logo image before hashing."""
    im = ImageOps.fit(im.convert("L"), HASH_SIZE, method=Image.Resampling.LANCZOS)
    im = im.filter(ImageFilter.MedianFilter(3))
    im = ImageOps.autocontrast(im)
    return im.convert("1")


def load_logo_hashes() -> bool:
    """Populate the global `_LOGO_HASHES` cache with preprocessed hashes.

    Returns
    -------
    bool
        ``True`` if at least one logo hash was loaded, ``False`` otherwise.
    """

    _LOGO_HASHES.clear()
    if not os.path.isdir(SET_LOGO_DIR):
        logger.warning(
            "Logo directory '%s' does not exist", SET_LOGO_DIR
        )
        return False
    for file in os.listdir(SET_LOGO_DIR):
        if not file.lower().endswith(".png"):
            continue
        code = os.path.splitext(file)[0]
        if ALLOWED_SET_CODES and code not in ALLOWED_SET_CODES:
            continue
        path = os.path.join(SET_LOGO_DIR, file)
        if not os.path.isfile(path):
            continue
        try:
            with Image.open(path) as im:
                im = im.convert("RGBA")
                im = _preprocess_symbol(im)
                _LOGO_HASHES[code] = (
                    imagehash.phash(im),
                    imagehash.dhash(im),
                    imagehash.average_hash(im),
                )
        except (OSError, UnidentifiedImageError) as exc:
            logger.warning("Failed to process logo %s: %s", path, exc)
            continue
    if not _LOGO_HASHES:
        logger.warning(
            "No logos loaded from '%s'; check SET_LOGO_DIR", SET_LOGO_DIR
        )
        return False
    return True

DEFAULT_LOGO_LIMIT = 20
try:
    DEFAULT_LOGO_LIMIT = int(os.getenv("SET_LOGO_LIMIT", DEFAULT_LOGO_LIMIT))
except ValueError:
    pass

# custom theme colors in grayscale
BG_COLOR = "#3A3A3A"
# lighter variant for subtle section backgrounds
LIGHT_BG_COLOR = "#4A4A4A"
FIELD_BG_COLOR = "#5A5A5A"  # even lighter for input fields
ACCENT_COLOR = "#666666"
HOVER_COLOR = "#525252"
TEXT_COLOR = "#FFFFFF"
BORDER_COLOR = "#444444"

# vivid colors for start menu buttons
SCAN_BUTTON_COLOR = "#2ECC71"  # green
PRICE_BUTTON_COLOR = "#3498DB"  # blue
SHOPER_BUTTON_COLOR = "#E67E22"  # orange
MAGAZYN_BUTTON_COLOR = "#9B59B6"  # purple
AUCTION_BUTTON_COLOR = "#E74C3C"  # red
STATS_BUTTON_COLOR = "#1ABC9C"  # teal

# shared colors for common actions
SAVE_BUTTON_COLOR = SCAN_BUTTON_COLOR
FETCH_BUTTON_COLOR = PRICE_BUTTON_COLOR
NAV_BUTTON_COLOR = ACCENT_COLOR

# color highlighting current price labels
CURRENT_PRICE_COLOR = "#FFD700"

# status colors for warehouse items; can be overridden via environment variables
OCCUPIED_COLOR = os.getenv("OCCUPIED_COLOR", "#4caf50")
FREE_COLOR = os.getenv("FREE_COLOR", "#ff9800")
SOLD_COLOR = os.getenv("SOLD_COLOR", "#888888")

# Layout constants to simplify future adjustments
BOX_THUMB_SIZE = 128  # square thumbnail size for warehouse boxes in pixels
BOX100_X_INSET = int(BOX_THUMB_SIZE * 235 / 600)
BOX100_Y_INSET = int(BOX_THUMB_SIZE * 50 / 600)
CARD_THUMB_SIZE = 160  # larger card thumbnails in the warehouse list
# Maximum allowed size for card thumbnails; used to cap dynamic calculations
MAX_CARD_THUMB_SIZE = 160
MAG_CARD_GAP = 3  # spacing between card frames in magazine view
GRID_COLUMNS = STANDARD_BOX_COLUMNS  # number of columns per storage box
WAREHOUSE_GRID_COLUMNS = 5  # number of columns in the warehouse grid
# BOX_COLUMN_CAPACITY, BOX_COUNT, SPECIAL_BOX_NUMBER and SPECIAL_BOX_CAPACITY
# are imported from :mod:`kartoteka.storage_config`.
BOX_CAPACITY = STANDARD_BOX_CAPACITY  # slots in a standard box


def _occupancy_color(value: float) -> str:
    """Return a color representing occupancy level."""
    if value < 0.5:
        return "#4caf50"  # green
    if value < 0.8:
        return "#ffeb3b"  # yellow
    return "#f44336"  # red



def normalize(text: str, keep_spaces: bool = False) -> str:
    """Normalize text for comparisons and API queries."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    for suffix in [
        " shiny",
        " promo",
    ]:
        text = text.replace(suffix, "")
    text = text.replace("-", "")
    if not keep_spaces:
        text = text.replace(" ", "")
    return text.strip()


def norm_header(name: str) -> str:
    """Return a normalized column name."""
    if name is None:
        return ""
    return name.strip().lower()


def sanitize_number(value: str) -> str:
    """Remove leading zeros from a number string.

    Returns
    -------
    str
        ``value`` without leading zeros or ``"0"`` if the result is
        empty.
    """

    return value.lstrip("0") or "0"




# Wczytanie danych setów
def reload_sets():
    """Load set definitions from the JSON files."""
    global tcg_sets_eng_by_era, tcg_sets_eng_map, tcg_sets_eng, tcg_sets_eng_code_map
    global tcg_sets_jp_by_era, tcg_sets_jp_map, tcg_sets_jp, tcg_sets_jp_code_map
    global tcg_sets_eng_abbr_map, tcg_sets_eng_abbr_name_map
    global tcg_sets_jp_abbr_map, tcg_sets_jp_abbr_name_map
    global tcg_sets_name_to_abbr, tcg_sets_jp_name_to_abbr
    global SET_TO_ERA

    tcg_sets_eng_code_map = globals().get("tcg_sets_eng_code_map", {})
    tcg_sets_jp_code_map = globals().get("tcg_sets_jp_code_map", {})
    tcg_sets_eng_abbr_map = globals().get("tcg_sets_eng_abbr_map", {})
    tcg_sets_eng_abbr_name_map = globals().get("tcg_sets_eng_abbr_name_map", {})
    tcg_sets_jp_abbr_map = globals().get("tcg_sets_jp_abbr_map", {})
    tcg_sets_jp_abbr_name_map = globals().get("tcg_sets_jp_abbr_name_map", {})
    tcg_sets_name_to_abbr = globals().get("tcg_sets_name_to_abbr", {})
    tcg_sets_jp_name_to_abbr = globals().get("tcg_sets_jp_name_to_abbr", {})
    SET_TO_ERA = {}

    try:
        with open("tcg_sets.json", encoding="utf-8") as f:
            tcg_sets_eng_by_era = json.load(f)
    except FileNotFoundError:
        tcg_sets_eng_by_era = {}
    tcg_sets_eng_map = {
        item["name"]: item["code"]
        for sets in tcg_sets_eng_by_era.values()
        for item in sets
    }
    tcg_sets_eng_code_map = {
        item["code"]: item["name"]
        for sets in tcg_sets_eng_by_era.values()
        for item in sets
    }
    tcg_sets_eng_abbr_map = {
        item["abbr"]: item["code"]
        for sets in tcg_sets_eng_by_era.values()
        for item in sets
        if "abbr" in item
    }
    tcg_sets_eng_abbr_name_map = {
        item["abbr"]: item["name"]
        for sets in tcg_sets_eng_by_era.values()
        for item in sets
        if "abbr" in item
    }
    tcg_sets_name_to_abbr = {
        item["name"]: item.get("abbr", "")
        for sets in tcg_sets_eng_by_era.values()
        for item in sets
    }
    tcg_sets_eng = [
        item["name"] for sets in tcg_sets_eng_by_era.values() for item in sets
    ]
    for era, sets in tcg_sets_eng_by_era.items():
        for item in sets:
            SET_TO_ERA[item["code"].lower()] = era
            SET_TO_ERA[item["name"].lower()] = era
            if "abbr" in item:
                SET_TO_ERA[item["abbr"].lower()] = era

    try:
        with open("tcg_sets_jp.json", encoding="utf-8") as f:
            tcg_sets_jp_by_era = json.load(f)
    except FileNotFoundError:
        tcg_sets_jp_by_era = {}
    tcg_sets_jp_map = {
        item["name"]: item["code"]
        for sets in tcg_sets_jp_by_era.values()
        for item in sets
    }
    tcg_sets_jp_code_map = {
        item["code"]: item["name"]
        for sets in tcg_sets_jp_by_era.values()
        for item in sets
    }
    tcg_sets_jp_abbr_map = {
        item["abbr"]: item["code"]
        for sets in tcg_sets_jp_by_era.values()
        for item in sets
        if "abbr" in item
    }
    tcg_sets_jp_abbr_name_map = {
        item["abbr"]: item["name"]
        for sets in tcg_sets_jp_by_era.values()
        for item in sets
        if "abbr" in item
    }
    tcg_sets_jp_name_to_abbr = {
        item["name"]: item.get("abbr", "")
        for sets in tcg_sets_jp_by_era.values()
        for item in sets
    }
    tcg_sets_jp = [
        item["name"] for sets in tcg_sets_jp_by_era.values() for item in sets
    ]
    for era, sets in tcg_sets_jp_by_era.items():
        for item in sets:
            SET_TO_ERA[item["code"].lower()] = era
            SET_TO_ERA[item["name"].lower()] = era
            if "abbr" in item:
                SET_TO_ERA[item["abbr"].lower()] = era


reload_sets()

# Allowed eras and set codes used for logo operations
ALLOWED_ERAS = {
    "Scarlet & Violet",
    "Sword & Shield",
    "Sun & Moon",
    "XY",
    "Black & White",
}

ALLOWED_SET_CODES: set[str] = set()


def refresh_logo_cache() -> bool:
    """Regenerate ``ALLOWED_SET_CODES`` and reload logo hashes.

    Returns
    -------
    bool
        ``True`` when logo hashes were loaded successfully.
    """

    global ALLOWED_SET_CODES
    ALLOWED_SET_CODES = {
        item["code"]
        for era, sets in tcg_sets_eng_by_era.items()
        if era in ALLOWED_ERAS
        for item in sets
    }
    success = load_logo_hashes()
    if not success:
        messagebox.showwarning(
            "Logotypy",
            f"Brak logotypów w katalogu '{SET_LOGO_DIR}' lub błędna ścieżka.",
        )
    return success


refresh_logo_cache()


def get_set_code(name: str) -> str:
    """Return the API code for a set name or abbreviation if available."""
    if not name:
        return ""
    search = name.strip()
    # remove trailing language or other short alphabetic suffixes like "EN", "JP"
    search = re.sub(r"[-_\s]+[a-z]{1,3}$", "", search, flags=re.IGNORECASE)
    search = search.strip().lower()
    for mapping in (
        tcg_sets_eng_map,
        tcg_sets_jp_map,
        tcg_sets_eng_abbr_map,
        tcg_sets_jp_abbr_map,
    ):
        for key, code in mapping.items():
            if key.lower() == search:
                return code
    return name


def get_set_name(code: str) -> str:
    """Return the display name for a set code or abbreviation if available."""
    if not code:
        return ""
    search = code.strip().lower()
    for mapping in (
        tcg_sets_eng_code_map,
        tcg_sets_jp_code_map,
        tcg_sets_eng_abbr_name_map,
        tcg_sets_jp_abbr_name_map,
    ):
        for key, name in mapping.items():
            if key.lower() == search:
                return name
    logger.warning(
        "Nie znaleziono nazwy dla setu '%s'. Weryfikacja ręczna wymagana.",
        code,
    )
    return code


def get_set_abbr(name: str) -> str:
    """Return the abbreviation for a set name if available.

    Parameters
    ----------
    name:
        Display name or abbreviation of the set.

    Returns
    -------
    str
        Matching abbreviation or an empty string when not found.
    """

    if not name:
        return ""
    search = name.strip()
    # remove trailing language or other short alphabetic suffixes like "EN", "JP"
    search = re.sub(r"[-_\s]+[a-z]{1,2}$", "", search, flags=re.IGNORECASE)
    lowered = search.lower()
    for mapping in (tcg_sets_name_to_abbr, tcg_sets_jp_name_to_abbr):
        for key, abbr in mapping.items():
            if key.lower() == lowered or (abbr and abbr.lower() == lowered):
                return abbr or ""
    return ""


def get_set_era(code_or_name: str) -> str:
    """Return the era name for a given set code or display name."""
    if not code_or_name:
        return ""
    search = code_or_name.strip()
    search = re.sub(r"[-_\s]+[a-z]{1,3}$", "", search, flags=re.IGNORECASE)
    search = search.strip().lower()
    return SET_TO_ERA.get(search, "")

def lookup_sets_from_api(name: str, number: str, total: Optional[str] = None):
    """Return possible set codes and names for the given card info.

    Parameters
    ----------
    name:
        Card name.
    number:
        Card number within the set.
    total:
        Optional total number of cards in the set (e.g. ``102`` for
        ``25/102``). When provided it is included in the API query.

    Returns
    -------
    list[tuple[str, str]]
        A list of ``(set_code, set_name)`` tuples sorted by relevance.
    """
    if not total:
        number_str = str(number)
        if "/" in number_str:
            num_part, tot_part = number_str.split("/", 1)
            first = lookup_sets_from_api(name, num_part, tot_part)
            second = lookup_sets_from_api(name, num_part, None)
            seen = set()
            merged = []
            for item in first + second:
                if item not in seen:
                    merged.append(item)
                    seen.add(item)
            return merged
    number = sanitize_number(str(number))
    if total is not None:
        total = sanitize_number(str(total))

    name_api = normalize(name, keep_spaces=True)
    params = {"name": name_api, "number": number}
    if total:
        params["total"] = total

    # log input data
    print(
        f"[lookup_sets_from_api] name={name!r}, number={number!r}, total={total!r}"
    )

    headers = {"User-Agent": "kartoteka/1.0"}
    url = "https://www.tcggo.com/api/cards/"
    if RAPIDAPI_KEY and RAPIDAPI_HOST:
        url = f"https://{RAPIDAPI_HOST}/cards/search"
        headers["X-RapidAPI-Key"] = RAPIDAPI_KEY
        headers["X-RapidAPI-Host"] = RAPIDAPI_HOST

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"[ERROR] API error: {response.status_code}")
            return []
        data = response.json()
    except requests.Timeout:
        logger.warning("Request timed out")
        return []
    except requests.RequestException as e:  # pragma: no cover - network/JSON errors
        logger.warning("Fetching sets from TCGGO failed: %s", e)
        return []
    except ValueError as e:
        logger.warning("Invalid JSON from TCGGO: %s", e)
        return []

    if isinstance(data, dict):
        if "cards" in data:
            cards = data["cards"]
        elif "data" in data:
            cards = data["data"]
        else:
            cards = []
    else:
        cards = data

    name_norm = normalize(name)
    number_norm = sanitize_number(str(number).strip().lower())
    total_norm = sanitize_number(str(total).strip().lower()) if total else None

    scores = {}
    for card in cards:
        episode = card.get("episode") or {}
        set_name = episode.get("name")
        set_code = episode.get("code") or episode.get("slug")
        if not (set_name and set_code):
            continue

        card_name_norm = normalize(card.get("name", ""))
        card_number_norm = str(card.get("card_number", "")).strip().lower()
        card_total_norm = str(card.get("total_prints", "")).strip().lower()

        score = 0
        if name_norm:
            if card_name_norm == name_norm:
                score += 2
            elif name_norm in card_name_norm:
                score += 1
        if number_norm:
            if card_number_norm == number_norm:
                score += 2
            elif number_norm in card_number_norm:
                score += 1
        if total_norm and card_total_norm == total_norm:
            score += 1

        key = (set_code, set_name)
        scores[key] = scores.get(key, 0) + score

    sorted_sets = sorted(
        ((key, sc) for key, sc in scores.items() if sc > 0),
        key=lambda item: item[1],
        reverse=True,
    )

    result = [key for key, _ in sorted_sets]
    # log the results
    if result:
        details = ", ".join(f"{c} ({n})" for c, n in result)
    else:
        details = "none"
    print(
        f"[lookup_sets_from_api] found {len(result)} set(s): {details}"
    )

    return result
def choose_nearest_locations(order_list, output_data):
    """Assign the nearest warehouse codes to order items.

    The function modifies the provided ``order_list`` in place, attaching a
    ``warehouse_code`` to each product when possible.  When multiple codes are
    available for the same ``product_code`` the combination with the smallest
    total Manhattan distance is chosen.
    """

    pattern = re.compile(r"K(\d+)R(\d)P(\d+)")
    available = defaultdict(list)

    # Collect available locations grouped by product_code
    for row in output_data:
        if not row:
            continue
        prod = str(row.get("product_code", ""))
        codes = str(row.get("warehouse_code") or "").split(";")
        for code in codes:
            code = code.strip()
            m = pattern.match(code)
            if not m:
                continue
            box, col, pos = map(int, m.groups())
            available[prod].append(((box, col, pos), code))

    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    def best_codes(options, qty):
        if qty <= 1:
            return [options[0][1]]

        best = None
        best_cost = None
        for combo in combinations(options, min(qty, len(options))):
            coords = [c[0] for c in combo]
            cost = 0
            for i in range(len(coords)):
                for j in range(i + 1, len(coords)):
                    cost += manhattan(coords[i], coords[j])
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = [c[1] for c in combo]
        return best or []

    for order in order_list:
        for item in order.get("products", []):
            prod = str(item.get("product_code") or item.get("code") or "")
            qty = int(item.get("quantity", 1))
            options = available.get(prod)
            if not options:
                continue
            options.sort(key=lambda x: x[1])
            chosen = best_codes(options, qty)
            # remove used ones
            remaining = [o for o in options if o[1] not in chosen]
            available[prod] = remaining
            if chosen:
                item["warehouse_code"] = ";".join(chosen)

    return order_list


def extract_cardmarket_price(card):
    """Return an approximate Cardmarket price for a card.

    The function prefers the arithmetic mean of ``30d_average`` and
    ``trendPrice`` when both metrics are present and greater than zero.  If
    only one of them is available the respective value is returned.  When
    neither metric is usable the function falls back to ``lowest_near_mint``.
    ``None`` is returned when no positive price can be determined.
    """

    prices = (card or {}).get("prices") or {}
    cardmarket = prices.get("cardmarket") or {}

    def _get_float(key: str) -> float:
        try:
            return float(cardmarket.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    avg_30d = _get_float("30d_average")
    trend = _get_float("trendPrice") or _get_float("trend_price")

    values = [v for v in (avg_30d, trend) if v > 0]
    if len(values) == 2:
        value = sum(values) / 2
        print(
            f"[DEBUG] Using mean of Cardmarket fields '30d_average' ({avg_30d}) and "
            f"'trendPrice' ({trend}) -> {value}"
        )
        return value
    if len(values) == 1:
        value = values[0]
        field = "30d_average" if avg_30d > 0 else "trendPrice"
        print(f"[DEBUG] Using Cardmarket field '{field}' with value {value}")
        return value

    lowest = _get_float("lowest_near_mint")
    if lowest > 0:
        print(
            f"[DEBUG] Using Cardmarket field 'lowest_near_mint' with value {lowest}"
        )
        return lowest

    return None


def translate_to_english(text: str) -> str:
    """Return an English translation of ``text`` using OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return text

    try:
        openai.api_key = api_key
        resp = openai.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": f"Translate to English: {text}"}],
            max_tokens=50,
        )
        return resp.choices[0].message.content.strip()
    except openai.OpenAIError as exc:
        logger.warning("Translation failed: %s", exc)
        return text


def load_set_logo_uris(
    limit: Optional[int] = DEFAULT_LOGO_LIMIT,
    available_sets: Optional[Iterable[str]] = None,
) -> dict:
    """Return a mapping of set code to data URI for set logos.

    Parameters
    ----------
    limit:
        Maximum number of logos to load. ``None`` loads all available logos.
    available_sets:
        Optional iterable of set codes to include. When provided and ``limit``
        is ``None``, the limit defaults to the number of available sets.
    """
    if available_sets is not None:
        available_sets = set(available_sets)
        if limit is None:
            limit = len(available_sets)
    logos = {}
    if not os.path.isdir(SET_LOGO_DIR):
        return logos
    files = sorted(os.listdir(SET_LOGO_DIR))
    for file in files:
        path = os.path.join(SET_LOGO_DIR, file)
        if not os.path.isfile(path):
            continue
        if not file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            continue
        code = os.path.splitext(file)[0]
        if available_sets is not None and code not in available_sets:
            continue
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            mime, _ = mimetypes.guess_type(path)
            if not mime:
                mime = "image/png"
            logos[code] = f"data:{mime};base64,{b64}"
        except OSError as exc:
            logger.warning("Failed to load logo %s: %s", path, exc)
            continue
        if limit is not None and len(logos) >= limit:
            break
    return logos


def match_set_code(value: str) -> str:
    """Return a set code that matches available logo filenames.

    The function performs an exact match against filenames in ``SET_LOGO_DIR``.
    When no exact match is found, a fuzzy match is attempted.  An empty string
    is returned if no suitable match is identified or when the logo directory
    is missing.
    """

    if not value:
        return ""
    value = value.strip().lower()
    if not value or not os.path.isdir(SET_LOGO_DIR):
        return ""

    codes = {
        os.path.splitext(f)[0].lower()
        for f in os.listdir(SET_LOGO_DIR)
        if os.path.isfile(os.path.join(SET_LOGO_DIR, f))
    }

    if value in codes:
        return value

    match = difflib.get_close_matches(
        value, list(codes), n=1, cutoff=SET_CODE_MATCH_CUTOFF
    )
    if match:
        return match[0]
    return ""


def get_symbol_rects(w: int, h: int) -> list[tuple[int, int, int, int]]:
    """Return possible rectangles around expected set symbol locations.

    The set symbol is usually near the bottom-left corner of a card, but
    rotated or unusually formatted scans may place it in other corners.  This
    helper returns a list of candidate rectangles in the following order:
    bottom-left, bottom-right, top-left and top-right.  For very small images
    (e.g. stand-alone set logos) the entire image is returned to ensure
    matching still works in tests and for direct logo comparisons.
    """

    # Use the full image for tiny logos
    if w <= 100 and h <= 100:
        return [(0, 0, w, h)]

    rects = []
    upper = int(h * 0.75)
    lower = int(h * 0.25)
    right = int(w * 0.35)
    left = w - right

    # Bottom-left
    rects.append((0, upper, right, h))
    # Bottom-right
    rects.append((left, upper, w, h))
    # Top-left
    rects.append((0, 0, right, lower))
    # Top-right
    rects.append((left, 0, w, lower))

    return rects


def identify_set_by_hash(
    scan_path: str, rect: tuple[int, int, int, int]
) -> list[tuple[str, str, int]]:
    """Identify the card set by comparing image hashes of the set symbol.

    Parameters
    ----------
    scan_path:
        Path to the card scan image.
    rect:
        Bounding box ``(left, upper, right, lower)`` containing the set symbol
        within the scan.

    Returns
    -------
    list[tuple[str, str, int]]
        List of up to four tuples containing the best matching set codes,
        their full set names and hash differences, sorted in ascending order.
        When matching fails, an empty list is returned.
    """

    if not _LOGO_HASHES and not load_logo_hashes():
        return []

    try:
        with Image.open(scan_path) as im:
            crop = im.crop(rect)
            crop = _preprocess_symbol(crop)
            crop_hashes = (
                imagehash.phash(crop),
                imagehash.dhash(crop),
                imagehash.average_hash(crop),
            )
    except (OSError, UnidentifiedImageError) as exc:
        logger.warning("Failed to process scan %s: %s", scan_path, exc)
        return []

    results: list[tuple[str, int]] = []
    for code, hashes in _LOGO_HASHES.items():
        diff = sum(h - c for h, c in zip(hashes, crop_hashes))
        results.append((code, int(diff)))

    results.sort(key=lambda x: x[1])
    symbol_hash = str(crop_hashes[0])
    for best_code, diff in results[:4]:
        logger.debug("Hash %s -> %s (%s)", symbol_hash, best_code, diff)
    return [(code, get_set_name(code), diff) for code, diff in results[:4]]


def extract_set_code_ocr(
    scan_path: str,
    rect: tuple[int, int, int, int],
    debug: bool = False,
    h_pad: int = 0,
    v_pad: int = 0,
) -> list[str]:
    """Extract potential set codes from the scan using OCR.

    Parameters
    ----------
    scan_path:
        Path to the card scan image.
    rect:
        Bounding box ``(left, upper, right, lower)`` containing the expected
        location of the set code.
    debug:
        When ``True``, save intermediate crop to ``OCR`` directory for
        diagnostic purposes. Errors during saving are ignored.
    h_pad:
        Optional horizontal padding (in pixels) removed from both left and
        right sides of the cropped region.
    v_pad:
        Optional vertical padding (in pixels) removed from both the top and
        bottom of the cropped region *after* the initial bottom slice.

    Returns
    -------
    list[str]
        List of unique set code strings recognized from the image. When no codes
        are recognized the list is empty.
    """

    try:
        with Image.open(scan_path) as im:
            crop = im.crop(rect)
            h = crop.height
            # Focus on the bottom 20% of the region where the set code appears.
            top = int(h * 0.8)
            crop = crop.crop((0, top, crop.width, h))
            if h_pad or v_pad:
                left = min(max(h_pad, 0), crop.width // 2)
                upper = min(max(v_pad, 0), crop.height // 2)
                right = max(crop.width - left, left)
                lower = max(crop.height - upper, upper)
                crop = crop.crop((left, upper, right, lower))
        if debug:
            try:
                from pathlib import Path

                debug_dir = Path("OCR")
                debug_dir.mkdir(exist_ok=True)
                debug_file = debug_dir / f"{Path(scan_path).stem}_set_crop.png"
                crop.convert("RGB").save(debug_file)
            except OSError as exc:  # pragma: no cover - debug only
                logger.debug("Failed to save debug image for %s: %s", scan_path, exc)
        crop = crop.convert("L")
        crop = ImageOps.autocontrast(crop)
        crop = crop.resize((crop.width * 4, crop.height * 4))
        raw = pytesseract.image_to_string(
            crop,
            config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ/-",
        )
    except (OSError, UnidentifiedImageError, pytesseract.TesseractError) as exc:
        logger.warning("Failed to OCR set code from %s: %s", scan_path, exc)
        return []

    candidates: set[str] = set()
    for token in re.split(r"\s+", raw.upper()):
        token = re.sub(r"[^A-Z0-9]", "", token).strip()
        if len(token) > 1 and not token.isdigit():
            candidates.add(token.lower())

    return list(candidates)


# ZMIANA: Model Pydantic prosi teraz również o `set_name`
class CardInfo(BaseModel):
    """Structured card data returned by the model."""
    name: str = ""
    number: str = ""
    set_name: str = ""
    set_format: str = ""
    era_name: str = ""


# ZMIANA: Funkcja prosi OpenAI o wszystkie dane naraz, w tym o zestaw
def extract_card_info_openai(path: str) -> tuple[str, str, str, str, str, str, str]:
    """Recognize card name, number, set, and its format using OpenAI Vision.

    Returns a tuple ``(name, number, total, era_name, set_name, set_code, set_format)``.
    The ``set_name`` value is normalised to the canonical display name whenever
    a matching ``set_code`` can be resolved. ``set_format`` is ``"text"`` or
    ``"symbol"`` depending on how the set was detected.
    """
    try:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            try:
                r = requests.get(path, timeout=10)
                r.raise_for_status()
                mime = r.headers.get("Content-Type") or mimetypes.guess_type(path)[0] or "image/jpeg"
                encoded = base64.b64encode(r.content).decode("utf-8")
            except requests.RequestException as e:
                logger.warning("extract_card_info_openai failed to fetch image: %s", e)
                return "", "", "", "", "", "", ""
        else:
            mime = mimetypes.guess_type(path)[0] or "image/jpeg"
            try:
                with open(path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
            except OSError as e:
                logger.warning("extract_card_info_openai failed to read image: %s", e)
                return "", "", "", "", "", "", ""
        data_url = f"data:{mime};base64,{encoded}"

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "", "", "", "", "", "", ""
        client = openai.OpenAI(api_key=api_key)

        PROMPT = (
            "You must return a JSON object with the Pokémon card's English name, "
            "card number in the form NNN/NNN, English set name, era name, and whether "
            "the set is written as text or shown as a symbol. The response must strictly "
            'match {"name":"", "number":"", "set_name":"", "era_name":"", "set_format":""}.'
        )

        try:
            resp = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                response_format={"type": "json_object"},
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    }
                ],
                max_output_tokens=150,
            )
            raw = getattr(resp, "output_text", "")
            raw = raw.strip().strip("`")
            if raw.startswith("json"):
                raw = raw[len("json") :].lstrip()
            match = re.search(r"{.*}", raw, re.DOTALL)
            if match:
                raw = match.group(0)
            if not raw:
                logger.error(
                    "extract_card_info_openai got empty response from OpenAI: %r",
                    resp,
                )
                return "", "", "", "", "", "", ""
            try:
                data_dict = json.loads(raw)
            except json.JSONDecodeError:
                logger.error("OpenAI returned non-JSON: %r", raw)
                return "", "", "", "", "", "", ""
        except TypeError:
            resp = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    }
                ],
                max_output_tokens=150,
            )
            raw = getattr(resp, "output_text", "")
            raw = raw.strip().strip("`")
            if raw.startswith("json"):
                raw = raw[len("json") :].lstrip()
            match = re.search(r"{.*}", raw, re.DOTALL)
            if match:
                raw = match.group(0)
            if not raw:
                logger.error(
                    "extract_card_info_openai got empty response from OpenAI: %r",
                    resp,
                )
                return "", "", "", "", "", "", ""
            try:
                data_dict = json.loads(raw)
            except json.JSONDecodeError:
                logger.error("OpenAI returned non-JSON: %r", raw)
                return "", "", "", "", "", "", ""

        data = data_dict

        raw_number = data.get("number") or ""
        number, total = "", ""
        if isinstance(raw_number, str):
            m = re.search(r"(\d+)(?:\s*/\s*(\d+))?", raw_number)
            if m:
                number, total = m.group(1), m.group(2) or ""
            else:
                number = re.sub(r"\D+", "", raw_number)

        name = data.get("name") or ""
        set_name = data.get("set_name") or ""
        set_format = data.get("set_format") or ""
        set_code = ""
        if set_name:
            set_code = get_set_code(set_name)
            mapped = get_set_name(set_code)
            if mapped:
                set_name = mapped
        era_name = data.get("era_name") or ""
        return name, number, total, era_name, set_name, set_code, set_format
    except Exception as e:
        logger.warning("extract_card_info_openai failed: %s", e)
        return "", "", "", "", "", "", ""

# ZMIANA: Całkowicie nowa, hierarchiczna logika analizy obrazu
def analyze_card_image(
    path: str,
    translate_name: bool = False,
    debug: bool = False,
    preview_cb=None,
    preview_image=None,
):
    """Return card details recognized from an image.

    The processing order is:
    1. Local set-symbol hash lookup.
    2. OpenAI Vision for text recognition.
    3. OCR as a final fallback.
    """
    parsed = urlparse(path)
    local_path = path if parsed.scheme not in ("http", "https") else None
    orientation = 0
    rects: list[tuple[int, int, int, int]] = []
    rect: Optional[tuple[int, int, int, int]] = None
    rotated_path = None
    if local_path and os.path.exists(local_path):
        try:
            with Image.open(local_path) as im:
                exif_orientation = im.getexif().get(0x0112, 1)
                im = ImageOps.exif_transpose(im)
                w, h = im.size
                orientation = 90 if exif_orientation in (6, 8) else 0
                if exif_orientation != 1:
                    rotated_path = local_path + ".rot.jpg"
                    im.save(rotated_path)
                    local_path = rotated_path
                    path = rotated_path
                rects = get_symbol_rects(w, h)
                if rects:
                    rect = rects[0]
        except (OSError, UnidentifiedImageError) as exc:
            logger.warning("Failed to preprocess %s: %s", local_path, exc)
            rects = []
            rect = None

    name = number = total = set_name = ""
    set_code = ""
    set_format = ""
    era_name = ""

    try:
        # --- PRIORITY 1: Local hash lookup for the set symbol ---
        if local_path:
            print("[INFO] Step 1: Matching set symbol via hash...")
            try:
                if not rects:
                    rects = [(0, 0, 0, 0)]
                if rect is None and rects:
                    rect = rects[0]

                for candidate in rects:
                    if preview_cb and preview_image is not None:
                        try:
                            preview_cb(candidate, preview_image)
                        except Exception as exc:
                            logger.exception("preview callback failed")
                    potential = identify_set_by_hash(local_path, candidate)
                    if potential:
                        code, name_match, diff = potential[0]
                        if diff <= HASH_DIFF_THRESHOLD:
                            rect = candidate
                            set_code = code
                            set_name = name_match
                            print(
                                f"[SUCCESS] Local hash analysis found a match: {name_match}"
                            )
                            era_name = get_set_era(set_code) or get_set_era(set_name)
                            result = {
                                "name": name,
                                "number": number,
                                "total": total,
                                "set": set_name,
                                "set_code": set_code,
                                "orientation": orientation,
                                "set_format": set_format,
                                "era": era_name,
                            }
                            if debug and rect:
                                result["rect"] = rect
                            return result
            except (OSError, UnidentifiedImageError, ValueError) as e:
                logger.warning("Hash lookup failed: %s", e)

        # --- PRIORITY 2: OpenAI Vision ---
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            print("[INFO] Step 2: Analyzing with OpenAI Vision...")
            try:
                name, number, total, era_name, set_name, set_code, set_format = extract_card_info_openai(path)

                if translate_name and name and not name.isascii():
                    name = translate_to_english(name)

                if name and number and set_name:
                    print(
                        f"[SUCCESS] OpenAI found all data: {name}, {number}, {set_name}"
                    )
                    era = era_name or get_set_era(set_code) or get_set_era(set_name)
                    result = {
                        "name": name,
                        "number": number,
                        "total": total,
                        "set": set_name,
                        "set_code": set_code,
                        "orientation": orientation,
                        "set_format": set_format,
                        "era": era,
                    }
                    if debug and rect:
                        result["rect"] = rect
                    return result

                print(
                    "[INFO] OpenAI returned partial data. Proceeding to fallback methods."
                )

            except Exception as e:
                logger.warning("OpenAI analysis failed: %s", e)
                name = number = total = set_name = ""
                set_code = ""
        else:
            print("[WARN] No OpenAI API key. Skipping to OCR.")

        # --- PRIORITY 3: TCGGO API Lookup (if name and number are known) ---
        if name and number:
            print("[INFO] Step 3: Looking up sets via TCGGO API...")
            try:
                api_sets = lookup_sets_from_api(name, number, total or None)
                if len(api_sets) == 1:
                    set_code, api_set_name = api_sets[0]
                    print(
                        f"[SUCCESS] TCGGO API found a single match: {api_set_name}"
                    )
                    era = get_set_era(set_code) or get_set_era(api_set_name)
                    result = {
                        "name": name,
                        "number": number,
                        "total": total,
                        "set": api_set_name,
                        "set_code": set_code,
                        "orientation": orientation,
                        "set_format": set_format,
                        "era": era,
                    }
                    if debug and rect:
                        result["rect"] = rect
                    return result

                if len(api_sets) > 1:
                    set_code, selected_name = api_sets[0]
                    print(
                        "[INFO] TCGGO API found multiple matches. "
                        f"Selecting first result: {selected_name}"
                    )
                    era = get_set_era(set_code) or get_set_era(selected_name)
                    result = {
                        "name": name,
                        "number": number,
                        "total": total,
                        "set": selected_name,
                        "set_code": set_code,
                        "orientation": orientation,
                        "set_format": set_format,
                        "era": era,
                    }
                    if debug and rect:
                        result["rect"] = rect
                    return result

            except (requests.RequestException, ValueError) as e:
                logger.warning("TCGGO API lookup failed: %s", e)

        # --- PRIORITY 4: OCR fallback ---
        if local_path:
            print("[INFO] Step 4: Performing OCR fallback...")
            try:
                if not rects:
                    rects = [(0, 0, 0, 0)]
                if rect is None and rects:
                    rect = rects[0]

                for candidate in rects:
                    if preview_cb and preview_image is not None:
                        try:
                            preview_cb(candidate, preview_image)
                        except Exception as exc:
                            logger.exception("preview callback failed")
                    ocr_codes = extract_set_code_ocr(local_path, candidate, debug)
                    for code in ocr_codes:
                        name_lookup = get_set_name(code)
                        if name_lookup and name_lookup != code:
                            rect = candidate
                            set_code = code
                            set_name = name_lookup
                            print(f"[SUCCESS] OCR recognized set code: {name_lookup}")
                            era = get_set_era(set_code) or get_set_era(set_name)
                            result = {
                                "name": name,
                                "number": number,
                                "total": total,
                                "set": set_name,
                                "set_code": set_code,
                                "orientation": orientation,
                                "set_format": set_format,
                                "era": era,
                            }
                            if debug and rect:
                                result["rect"] = rect
                            return result
                        else:
                            print(f"[WARN] OCR produced unknown set code: {code}")
            except Exception:
                logger.exception("OCR analysis failed")

        # If all methods fail, return any partial data we might have
        print("[FAIL] All analysis methods failed to find a definitive set.")
        era = era_name or get_set_era(set_code) or get_set_era(set_name)
        result = {
            "name": name,
            "number": number,
            "total": total,
            "set": set_name,
            "set_code": set_code,
            "orientation": orientation,
            "set_format": set_format,
            "era": era,
        }
        if debug and rect:
            result["rect"] = rect
        return result
    finally:
        if rotated_path and os.path.exists(rotated_path):
            try:
                os.remove(rotated_path)
            except OSError:
                pass


class CardEditorApp:
    API_TIMEOUT = 30

    def __init__(self, root):
        self.root = root
        self.root.title("KARTOTEKA")
        # improve default font for all widgets
        self.root.configure(bg=BG_COLOR, fg_color=BG_COLOR)
        self.root.option_add("*Font", ("Segoe UI", 20))
        self.root.option_add("*Foreground", TEXT_COLOR)
        self.index = 0
        self.cards = []
        self.image_objects = []
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.card_cache = {}
        self.file_to_key = {}
        self.product_code_map = {}
        self.store_data = csv_utils.load_store_export()
        try:
            if HashDB and HASH_DB_FILE:
                db_path = Path(HASH_DB_FILE)
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path.touch(exist_ok=True)
                self.hash_db = HashDB(str(db_path))
            else:
                self.hash_db = None
        except Exception as exc:
            logger.warning("Failed to init hash DB: %s", exc)
            self.hash_db = None
        self.auto_lookup = AUTO_HASH_LOOKUP
        self.current_fingerprint = None
        self.selected_candidate_meta = None
        self.price_db = self.load_price_db()
        self.folder_name = ""
        self.folder_path = ""
        self.sets_file = "tcg_sets.json"
        self.progress_var = tk.StringVar(value="0/0 (0%)")
        self.start_box_var = tk.StringVar(value="1")
        self.start_col_var = tk.StringVar(value="1")
        self.start_pos_var = tk.StringVar(value="1")
        self.scan_folder_var = tk.StringVar()
        self.starting_idx = 0
        self.start_frame = None
        self.shoper_frame = None
        self.pricing_frame = None
        self.magazyn_frame = None
        self.location_frame = None
        self.auction_frame = None
        self.mag_progressbars: dict[tuple[int, int], ctk.CTkProgressBar] = {}
        self.mag_percent_labels: dict[tuple[int, int], ctk.CTkLabel] = {}
        self.mag_labels: list[ctk.CTkLabel] = []
        self._mag_csv_mtime: Optional[float] = None
        self.log_widget = None
        self.cheat_frame = None
        self.set_logos = {}
        self.loading_frame = None
        self.loading_label = None
        self.price_pool_total = 0.0
        self.pool_total_label = None
        self.auction_queue = []
        self.in_scan = False
        self.current_image_path = ""
        self.current_analysis_thread = None
        self.current_location = ""
        self.show_loading_screen()
        self.root.after(0, self.startup_tasks)

    def setup_welcome_screen(self):
        """Display a simple welcome screen before loading scans."""
        w, h = 1920, 1080
        if all(
            hasattr(self.root, attr)
            for attr in ("geometry", "winfo_screenwidth", "winfo_screenheight")
        ):
            self.root.geometry(f"{w}x{h}")
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = (screen_w - w) // 2
            y = (screen_h - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Allow resizing but provide a sensible minimum size
        self.root.minsize(1200, 800)
        self.start_frame = ctk.CTkFrame(
            self.root, fg_color=BG_COLOR, corner_radius=10
        )
        self.start_frame.pack(expand=True, fill="both")
        # Divide the start frame into a narrow menu on the left and a wider
        # main content area on the right.  Approximately one third of the
        # width is dedicated to the menu.
        self.start_frame.grid_columnconfigure(0, weight=1)
        self.start_frame.grid_columnconfigure(1, weight=2)

        menu_frame = ctk.CTkFrame(self.start_frame, fg_color=LIGHT_BG_COLOR)
        menu_frame.grid(row=0, column=0, sticky="nsew")
        if hasattr(menu_frame, "pack_propagate"):
            menu_frame.pack_propagate(False)

        main_frame = ctk.CTkFrame(self.start_frame, fg_color=BG_COLOR)
        main_frame.grid(row=0, column=1, sticky="nsew")

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = load_rgba_image(logo_path)
            if logo_img:
                logo_img.thumbnail((200, 200))
                self.logo_photo = _create_image(logo_img)
                logo_label = ctk.CTkLabel(
                    menu_frame,
                    image=self.logo_photo,
                    text="",
                )
                logo_label.pack(pady=(10, 10))

        greeting = ctk.CTkLabel(
            main_frame,
            text="Witaj w aplikacji KARTOTEKA",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
        )
        greeting.pack(pady=5)

        desc = ctk.CTkLabel(
            main_frame,
            text=(
                "Aplikacja KARTOTEKA.SHOP pomaga przygotować skany do sprzedaży."
            ),
            wraplength=1400,
            justify="center",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 18),
        )
        desc.pack(pady=5)
        unsold_count, unsold_total, sold_count, sold_total = csv_utils.get_inventory_stats()
        if unsold_count == 0 and sold_count == 0:
            messagebox.showinfo("Magazyn", "Brak kart w magazynie")
        # Module buttons stacked vertically in the menu
        scan_btn = self.create_button(
            menu_frame,
            text="\U0001f50d Skanuj",
            command=self.show_location_frame,
            fg_color=SCAN_BUTTON_COLOR,
            width=100,
        )
        scan_btn.pack(padx=10, pady=5, fill="x")
        self.create_button(
            menu_frame,
            text="\U0001f4b0 Wyceniaj",
            command=self.setup_pricing_ui,
            fg_color=PRICE_BUTTON_COLOR,
            width=100,
        ).pack(padx=10, pady=5, fill="x")
        self.create_button(
            menu_frame,
            text="\U0001f5c3\ufe0f Shoper",
            command=self.open_shoper_window,
            fg_color=SHOPER_BUTTON_COLOR,
            width=100,
        ).pack(padx=10, pady=5, fill="x")
        self.create_button(
            menu_frame,
            text="\U0001f4e6 Magazyn",
            command=self.show_magazyn_view,
            fg_color=MAGAZYN_BUTTON_COLOR,
            width=100,
        ).pack(padx=10, pady=5, fill="x")
        self.create_button(
            menu_frame,
            text="\U0001f528 Licytacje",
            command=self.open_auctions_window,
            fg_color=AUCTION_BUTTON_COLOR,
            width=100,
        ).pack(padx=10, pady=5, fill="x")

        self.create_button(
            menu_frame,
            text="\U0001F4C8 Statystyki",
            command=getattr(self, "open_statistics_window", lambda: None),
            fg_color=STATS_BUTTON_COLOR,
            width=100,
        ).pack(padx=10, pady=5, fill="x")

        ctk.CTkLabel(
            main_frame,
            text="Podgląd kartonów",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
        ).pack(pady=(20, 0))

        box_frame = ctk.CTkFrame(main_frame, fg_color=LIGHT_BG_COLOR)
        box_frame.pack(anchor="center", padx=10, pady=10)

        CardEditorApp.build_home_box_preview(self, box_frame)
        # Refresh the initial box preview if possible.  The welcome screen does
        # not depend on the full warehouse window, therefore it prefers a
        # lightweight ``refresh_home_preview`` method but falls back to the
        # legacy ``refresh_magazyn`` if needed.
        if hasattr(self, "refresh_home_preview"):
            try:
                self.refresh_home_preview()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to refresh magazyn preview")
        elif hasattr(self, "refresh_magazyn"):
            try:
                self.refresh_magazyn()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to refresh magazyn preview")

        ctk.CTkLabel(
            main_frame,
            text="Statystyki",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
        ).pack(pady=(20, 0))

        info_frame = ctk.CTkFrame(main_frame, fg_color=LIGHT_BG_COLOR)
        info_frame.pack(anchor="center", padx=10, pady=(0, 40))

        self.inventory_count_label = ctk.CTkLabel(
            info_frame,
            text=f"📊 Łączna liczba kart: {unsold_count}",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
            justify="left",
        )
        self.inventory_count_label.pack(anchor="center")

        self.inventory_value_label = ctk.CTkLabel(
            info_frame,
            text=f"💰 Łączna wartość: {unsold_total:.2f} PLN",
            text_color="#FFD700",
            font=("Segoe UI", 24, "bold"),
            justify="left",
        )
        self.inventory_value_label.pack(anchor="center")

        self.inventory_sold_count_label = ctk.CTkLabel(
            info_frame,
            text=f"Sprzedane karty: {sold_count}",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
            justify="left",
        )
        self.inventory_sold_count_label.pack(anchor="center", pady=(0, 5))

        daily = dict(sorted(csv_utils.get_daily_additions().items()))
        if Figure and FigureCanvasTkAgg and daily:
            fig = Figure(figsize=(6, 3), facecolor=BG_COLOR)
            ax = fig.add_subplot(111)
            ax.set_facecolor(BG_COLOR)
            dates = list(daily.keys())
            counts = list(daily.values())
            colors = [
                "#4a90e2",
                "#50b848",
                "#f39c12",
                "#e74c3c",
                "#9b59b6",
                "#1abc9c",
                "#7f8c8d",
            ]
            ax.bar(range(len(dates)), counts, color=colors[: len(dates)])
            ax.set_ylabel("Dodane", color="#BBBBBB")
            ax.set_title("Ostatnie 7 dni", color="#BBBBBB")
            ax.set_xticks(range(len(dates)))
            ax.set_xticklabels(dates, rotation=45, ha="right", color="#BBBBBB")
            ax.tick_params(axis="x", labelsize=8, colors="#BBBBBB")
            ax.tick_params(axis="y", colors="#BBBBBB")
            for spine in ax.spines.values():
                spine.set_color("#BBBBBB")
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=info_frame)
            canvas.draw()
            widget = canvas.get_tk_widget()
            widget.pack(anchor="w", pady=(20, 5))
            if hasattr(widget, "bind"):
                widget.bind("<Button-1>", lambda _e: self.open_statistics_window())
            self.daily_additions_chart = canvas

        config_btn = self.create_button(
            menu_frame,
            text="\u2699\ufe0f Konfiguracja",
            command=self.open_config_dialog,
            fg_color="#404040",
            width=100,
        )
        config_btn.pack(side="bottom", pady=15, padx=10, fill="x", anchor="s")

        author = ctk.CTkLabel(
            menu_frame,
            text="Twórca: BOGUCKI 2025",
            wraplength=1400,
            justify="center",
            font=("Segoe UI", 14),
            text_color="#CCCCCC",
        )
        author.pack(side="bottom", pady=5)

    def update_inventory_stats(self, force: bool = False):
        """Refresh labels showing total item count and value in the UI.

        Parameters
        ----------
        force:
            When ``True`` statistics are recomputed even if cached values are
            available.

        Also refreshes the daily additions bar chart if matplotlib is available.
        """
        # Collect widgets that are available and still exist.  The start screen
        # may not yet be created which would leave these attributes undefined.
        widgets = []
        for attr in [
            "inventory_count_label",
            "inventory_sold_count_label",
            "mag_inventory_count_label",
            "inventory_value_label",
            "mag_inventory_value_label",
            "mag_sold_count_label",
            "mag_sold_value_label",
        ]:
            widget = getattr(self, attr, None)
            if widget and hasattr(widget, "winfo_exists"):
                try:
                    if widget.winfo_exists():
                        widgets.append((attr, widget))
                except tk.TclError:
                    pass

        # No labels found - nothing to update and avoids attribute errors.
        if not widgets:
            return

        unsold_count, unsold_total, sold_count, sold_total = csv_utils.get_inventory_stats(
            force=force
        )
        if unsold_count == 0 and sold_count == 0:
            messagebox.showinfo("Magazyn", "Brak kart w magazynie")
        unsold_count_text = f"📊 Łączna liczba kart: {unsold_count}"
        unsold_total_text = f"💰 Łączna wartość: {unsold_total:.2f} PLN"
        sold_count_text = f"Sprzedane karty: {sold_count}"
        sold_total_text = f"Wartość sprzedanych: {sold_total:.2f} PLN"
        for attr, widget in widgets:
            if "sold" in attr:
                text = sold_count_text if "count" in attr else sold_total_text
            else:
                text = unsold_count_text if "count" in attr else unsold_total_text
            try:
                widget.configure(text=text)
            except tk.TclError:
                pass

        # Refresh the daily additions chart to reflect newly added cards
        daily = dict(sorted(csv_utils.get_daily_additions().items()))
        if Figure and FigureCanvasTkAgg and daily:
            try:
                if getattr(self, "daily_additions_chart", None):
                    fig = self.daily_additions_chart.figure
                    ax = fig.axes[0] if fig.axes else fig.add_subplot(111)
                    ax.clear()
                    ax.set_facecolor(BG_COLOR)
                    dates = list(daily.keys())
                    counts = list(daily.values())
                    colors = [
                        "#4a90e2",
                        "#50b848",
                        "#f39c12",
                        "#e74c3c",
                        "#9b59b6",
                        "#1abc9c",
                        "#7f8c8d",
                    ]
                    ax.bar(range(len(dates)), counts, color=colors[: len(dates)])
                    ax.set_ylabel("Dodane", color="#BBBBBB")
                    ax.set_title("Ostatnie 7 dni", color="#BBBBBB")
                    ax.set_xticks(range(len(dates)))
                    ax.set_xticklabels(dates, rotation=45, ha="right", color="#BBBBBB")
                    ax.tick_params(axis="x", labelsize=8, colors="#BBBBBB")
                    ax.tick_params(axis="y", colors="#BBBBBB")
                    for spine in ax.spines.values():
                        spine.set_color("#BBBBBB")
                    fig.tight_layout()
                    self.daily_additions_chart.draw()
                elif hasattr(self, "inventory_count_label"):
                    parent = getattr(self.inventory_count_label, "master", None)
                    if parent:
                        fig = Figure(figsize=(6, 3), facecolor=BG_COLOR)
                        ax = fig.add_subplot(111)
                        ax.set_facecolor(BG_COLOR)
                        dates = list(daily.keys())
                        counts = list(daily.values())
                        colors = [
                            "#4a90e2",
                            "#50b848",
                            "#f39c12",
                            "#e74c3c",
                            "#9b59b6",
                            "#1abc9c",
                            "#7f8c8d",
                        ]
                        ax.bar(range(len(dates)), counts, color=colors[: len(dates)])
                        ax.set_ylabel("Dodane", color="#BBBBBB")
                        ax.set_title("Ostatnie 7 dni", color="#BBBBBB")
                        ax.set_xticks(range(len(dates)))
                        ax.set_xticklabels(
                            dates, rotation=45, ha="right", color="#BBBBBB"
                        )
                        ax.tick_params(axis="x", labelsize=8, colors="#BBBBBB")
                        ax.tick_params(axis="y", colors="#BBBBBB")
                        for spine in ax.spines.values():
                            spine.set_color("#BBBBBB")
                        fig.tight_layout()
                        canvas = FigureCanvasTkAgg(fig, master=parent)
                        canvas.draw()
                        widget = canvas.get_tk_widget()
                        widget.pack(anchor="w", pady=(20, 5))
                        if hasattr(widget, "bind"):
                            widget.bind(
                                "<Button-1>",
                                lambda _e: self.open_statistics_window(),
                            )
                        self.daily_additions_chart = canvas
            except Exception:
                logger.exception("Failed to update daily additions chart")

    def placeholder_btn(self, text: str, master=None):
        if master is None:
            master = self.start_frame
        return self.create_button(
            master,
            text=text,
            command=lambda: messagebox.showinfo("Info", "Funkcja niezaimplementowana."),
        )

    def show_location_frame(self):
        """Display inputs for the starting scan location inside the main window."""
        # Hide any other active frames similar to other views
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
            self.magazyn_frame = None
            labels = getattr(self, "mag_card_image_labels", [])
            for i in range(len(labels)):
                labels[i] = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()

        self.root.minsize(1200, 800)
        frame = ctk.CTkFrame(self.root)
        frame.pack(expand=True, fill="both", padx=10, pady=10)
        frame.grid_anchor("center")
        self.location_frame = frame

        start_row = 0
        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = load_rgba_image(logo_path)
            if logo_img:
                logo_img.thumbnail((200, 80))
                self.location_logo_photo = _create_image(logo_img)
                ctk.CTkLabel(
                    frame,
                    image=self.location_logo_photo,
                    text="",
                ).pack(pady=(0, 10))

        # show last used location to inform the user where scanning previously ended
        last_idx = storage.load_last_location()
        try:
            last_code = storage.generate_location(last_idx)
        except Exception:
            last_code = ""
        if last_code:
            ctk.CTkLabel(frame, text=storage.location_from_code(last_code)).pack(
                pady=(0, 10)
            )

        # prefill inputs with the next free location
        try:
            next_code = self.next_free_location()
            match = re.match(r"K(\d+)R(\d+)P(\d+)", next_code)
            if match:
                self.start_box_var.set(str(int(match.group(1))))
                self.start_col_var.set(str(int(match.group(2))))
                self.start_pos_var.set(str(int(match.group(3))))
        except Exception:
            pass

        form = tk.Frame(frame, bg=self.root.cget("background"))
        form.pack(pady=5)
        for idx, label in enumerate(["Karton", "Kolumna", "Pozycja"]):
            ctk.CTkLabel(form, text=label).grid(row=0, column=idx, padx=5, pady=2)
        ctk.CTkEntry(form, textvariable=self.start_box_var, width=120).grid(
            row=1, column=0, padx=5
        )
        ctk.CTkEntry(form, textvariable=self.start_col_var, width=120).grid(
            row=1, column=1, padx=5
        )
        ctk.CTkEntry(form, textvariable=self.start_pos_var, width=120).grid(
            row=1, column=2, padx=5
        )

        folder_frame = tk.Frame(frame, bg=self.root.cget("background"))
        folder_frame.pack(pady=5)
        ctk.CTkLabel(folder_frame, text="Folder").grid(row=0, column=0, padx=5, pady=2)
        ctk.CTkEntry(folder_frame, textvariable=self.scan_folder_var, width=300).grid(
            row=0, column=1, padx=5
        )
        self.create_button(
            folder_frame,
            text="Wybierz",
            command=self.select_scan_folder,
            fg_color=FETCH_BUTTON_COLOR,
        ).grid(row=0, column=2, padx=5)

        button_frame = ctk.CTkFrame(frame)
        button_frame.pack(pady=5)
        self.create_button(
            button_frame,
            text="Dalej",
            command=self.start_browse_scans,
            fg_color=NAV_BUTTON_COLOR,
        ).grid(row=0, column=0, padx=5, pady=5)
        self.create_button(
            button_frame,
            text="Powrót",
            command=self.back_to_welcome,
            fg_color=NAV_BUTTON_COLOR,
        ).grid(row=0, column=1, padx=5, pady=5)

    def select_scan_folder(self):
        """Open a dialog to choose the folder with scans."""
        folder = filedialog.askdirectory()
        if folder:
            self.scan_folder_var.set(folder)

    def create_button(self, master=None, **kwargs):
        if master is None:
            master = self.root
        fg_color = kwargs.pop("fg_color", ACCENT_COLOR)
        width = kwargs.pop("width", 140)
        height = kwargs.pop("height", 60)
        font = kwargs.pop("font", ("Segoe UI", 20, "bold"))
        return ctk.CTkButton(
            master,
            fg_color=fg_color,
            hover_color=HOVER_COLOR,
            corner_radius=10,
            width=width,
            height=height,
            font=font,
            **kwargs,
        )

    def open_shoper_window(self):
        if not self.shoper_client:
            messagebox.showerror("Błąd", "Brak konfiguracji Shoper API")
            return
        # Quick connection test to provide clearer error messages
        try:
            # use a known endpoint to verify the connection
            resp = self.shoper_client.get_inventory()
            if not resp:
                raise RuntimeError("404")
        except (requests.RequestException, RuntimeError) as exc:
            msg = str(exc)
            if "404" in msg:
                messagebox.showerror(
                    "Błąd",
                    "Nie znaleziono endpointu Shoper API ('products'). Czy adres zawiera '/webapi/rest'?",
                )
            else:
                messagebox.showerror(
                    "Błąd", f"Połączenie z Shoper API nie powiodło się: {msg}"
                )
            return
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        if getattr(self, "statistics_frame", None):
            self.statistics_frame.destroy()
            self.statistics_frame = None
        # Ensure the window has a reasonable minimum size
        self.root.minsize(1200, 800)

        self.shoper_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.shoper_frame.pack(expand=True, fill="both", padx=10, pady=10)
        self.shoper_frame.columnconfigure(0, weight=1)
        self.shoper_frame.rowconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = load_rgba_image(logo_path)
            if logo_img:
                logo_img.thumbnail((200, 80))
                self.shoper_logo_photo = _create_image(logo_img)
                ctk.CTkLabel(
                    self.shoper_frame,
                    image=self.shoper_logo_photo,
                    text="",
                ).grid(row=0, column=0, pady=(0, 10))

        self.shoper_tabs = ctk.CTkTabview(self.shoper_frame)
        self.shoper_tabs.grid(row=1, column=0, sticky="nsew", pady=5)
        self.shoper_tabs.add("Zamówienia")
        orders_tab = self.shoper_tabs.tab("Zamówienia")

        orders_tab.columnconfigure(0, weight=1)
        orders_tab.rowconfigure(0, weight=1)

        orders_output = tk.Text(
            orders_tab,
            height=10,
            bg=self.root.cget("background"),
            fg="white",
        )
        orders_output.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.orders_output = orders_output

        self.create_button(
            orders_tab,
            text="Zamówienia",
            command=self.show_orders,
            fg_color=FETCH_BUTTON_COLOR,
        ).grid(row=1, column=0, pady=5)

        self.create_button(
            orders_tab,
            text="Potwierdź zamówienie",
            command=self.confirm_order,
            fg_color=SAVE_BUTTON_COLOR,
        ).grid(row=2, column=0, pady=5)

        self.create_button(
            self.shoper_frame,
            text="Powrót",
            command=self.back_to_welcome,
            fg_color=NAV_BUTTON_COLOR,
        ).grid(row=2, column=0, pady=5)

    def push_product(self, widget):
        """Send the currently selected card to Shoper."""
        try:
            card = None
            if getattr(self, "output_data", None):
                try:
                    self.save_current_data()
                except Exception as exc:
                    logger.exception("Failed to save current data")
                if 0 <= getattr(self, "index", 0) < len(self.output_data):
                    card = self.output_data[self.index]
                else:
                    card = next((r for r in self.output_data if r), None)
            if not card:
                messagebox.showerror("Błąd", "Brak danych karty do wysłania")
                return

            payload = self._build_shoper_payload(card)
            data = self.shoper_client.add_product(payload)
            product_id = data.get("product_id") or data.get("id")
            try:
                attr_values = [
                    name
                    for name, var in self.type_vars.items()
                    if getattr(var, "get", lambda: False)()
                ]
                if product_id and attr_values:
                    cache = getattr(self, "_attribute_cache", {})
                    attr_id = cache.get("Typ")
                    if attr_id is None:
                        attrs = self.shoper_client.get_attributes()
                        for a in attrs.get("list", attrs):
                            name = a.get("name")
                            aid = a.get("attribute_id")
                            if name and aid is not None:
                                cache[name] = aid
                        attr_id = cache.get("Typ")
                        self._attribute_cache = cache
                    if attr_id is not None:
                        self.shoper_client.add_product_attribute(
                            product_id, attr_id, attr_values
                        )
            except Exception as exc:
                logger.exception("Failed to set product attributes")
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
            else:
                messagebox.showinfo(
                    "Wysłano",
                    json.dumps(data, indent=2, ensure_ascii=False),
                )
        except requests.RequestException as e:
            logger.exception("Failed to push product")
            messagebox.showerror("Błąd", str(e))

    def open_auctions_window(self):
        """Open a queue editor for Discord auctions and save to ``aukcje.csv``."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
            self.magazyn_frame = None
            labels = getattr(self, "mag_card_image_labels", [])
            for i in range(len(labels)):
                labels[i] = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        if getattr(self, "auction_frame", None):
            self.auction_frame.destroy()
        if getattr(self, "statistics_frame", None):
            self.statistics_frame.destroy()
            self.statistics_frame = None
        try:
            import bot
            if not getattr(bot, "_thread_started", False):
                threading.Thread(target=bot.run_bot, daemon=True).start()
                bot._thread_started = True
        except Exception as e:
            logger.exception("Failed to start bot")
            messagebox.showerror("Błąd", str(e))

        self.root.minsize(1200, 800)
        self.auction_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.auction_frame.pack(expand=True, fill="both", padx=10, pady=10)

        container = tk.Frame(
            self.auction_frame, bg=self.root.cget("background")
        )
        container.pack(expand=True, fill="both")

        refresh_tree = self._build_auction_widgets(container)
        try:
            self._load_auction_queue()
        except FileNotFoundError:
            messagebox.showerror(
                "Błąd", f"Nie znaleziono pliku {csv_utils.WAREHOUSE_CSV}"
            )
            self.auction_queue = []
        except ValueError as exc:
            messagebox.showerror("Błąd", str(exc))
            self.auction_queue = []
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            logger.exception("Failed to load auction queue")
            messagebox.showerror("Błąd", str(exc))
            self.auction_queue = []

        refresh_tree()
        self._update_auction_status()

    def open_statistics_window(self):
        """Display inventory statistics inside the main window."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        for attr in (
            "pricing_frame",
            "shoper_frame",
            "frame",
            "magazyn_frame",
            "location_frame",
            "auction_frame",
            "statistics_frame",
        ):
            if getattr(self, attr, None):
                getattr(self, attr).destroy()
                setattr(self, attr, None)

        start_var = tk.StringVar(
            value=(datetime.date.today() - datetime.timedelta(days=6)).isoformat()
        )
        end_var = tk.StringVar(value=datetime.date.today().isoformat())

        self.root.minsize(1200, 800)
        self.statistics_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.statistics_frame.pack(expand=True, fill="both", padx=10, pady=10)

        filter_frame = ctk.CTkFrame(self.statistics_frame, fg_color=BG_COLOR)
        filter_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(filter_frame, text="Od:", text_color=TEXT_COLOR).pack(
            side="left", padx=5
        )
        ctk.CTkEntry(filter_frame, textvariable=start_var, width=100).pack(
            side="left"
        )
        ctk.CTkLabel(filter_frame, text="Do:", text_color=TEXT_COLOR).pack(
            side="left", padx=5
        )
        ctk.CTkEntry(filter_frame, textvariable=end_var, width=100).pack(
            side="left"
        )

        summary_frame = ctk.CTkFrame(self.statistics_frame, fg_color=BG_COLOR)
        summary_frame.pack(fill="x", pady=5)
        self.stats_total_label = ctk.CTkLabel(
            summary_frame,
            text="",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 20, "bold"),
        )
        self.stats_total_label.pack(anchor="w")
        self.stats_count_label = ctk.CTkLabel(
            summary_frame,
            text="",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 20, "bold"),
        )
        self.stats_count_label.pack(anchor="w")
        self.stats_max_sale_label = ctk.CTkLabel(
            summary_frame,
            text="",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 20, "bold"),
        )
        self.stats_max_sale_label.pack(anchor="w")
        self.stats_max_order_label = ctk.CTkLabel(
            summary_frame,
            text="",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 20, "bold"),
        )
        self.stats_max_order_label.pack(anchor="w")

        chart_frame = tk.Frame(self.statistics_frame, bg=self.root.cget("background"))
        chart_frame.pack(expand=True, fill="both", pady=5)

        def _update():
            try:
                start = datetime.date.fromisoformat(start_var.get())
                end = datetime.date.fromisoformat(end_var.get())
            except ValueError:
                messagebox.showerror("Błąd", "Niepoprawny format daty (RRRR-MM-DD)")
                return
            data = stats_utils.get_statistics(start, end)
            cumulative = data.get("cumulative", {})
            count = cumulative.get("count", 0)
            total_value = cumulative.get("total_value", 0.0)
            daily = data.get("daily", {})
            max_order = data.get("max_order", 0)
            max_price = data.get("max_price", 0.0)

            self.stats_total_label.configure(
                text=f"Wartość kolekcji: {total_value:.2f} zł"
            )
            self.stats_count_label.configure(text=f"Liczba kart: {count}")
            self.stats_max_sale_label.configure(
                text=f"Najdroższa sprzedaż: {max_price:.2f} zł"
            )
            self.stats_max_order_label.configure(
                text=f"Największe zamówienie: {max_order}"
            )

            if Figure and FigureCanvasTkAgg and daily:
                dates = list(daily.keys())
                added_vals = [v.get("added", 0) for v in daily.values()]
                sold_vals = [v.get("sold", 0) for v in daily.values()]
                fig = Figure(figsize=(8, 4), facecolor=BG_COLOR)
                ax1 = fig.add_subplot(121)
                ax1.set_facecolor(BG_COLOR)
                ax1.bar(range(len(dates)), added_vals, color="#4a90e2")
                ax1.set_title("Dodane", color="#BBBBBB")
                ax1.set_xticks(range(len(dates)))
                ax1.set_xticklabels(
                    dates, rotation=45, ha="right", color="#BBBBBB", fontsize=8
                )
                ax1.tick_params(axis="y", colors="#BBBBBB")
                for spine in ax1.spines.values():
                    spine.set_color("#BBBBBB")
                ax2 = fig.add_subplot(122)
                ax2.set_facecolor(BG_COLOR)
                ax2.bar(range(len(dates)), sold_vals, color="#e74c3c")
                ax2.set_title("Sprzedane", color="#BBBBBB")
                ax2.set_xticks(range(len(dates)))
                ax2.set_xticklabels(
                    dates, rotation=45, ha="right", color="#BBBBBB", fontsize=8
                )
                ax2.tick_params(axis="y", colors="#BBBBBB")
                for spine in ax2.spines.values():
                    spine.set_color("#BBBBBB")
                fig.tight_layout()
                if getattr(self, "statistics_chart", None):
                    self.statistics_chart.get_tk_widget().destroy()
                canvas = FigureCanvasTkAgg(fig, master=chart_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(expand=True, fill="both")
                self.statistics_chart = canvas
            elif getattr(self, "statistics_chart", None):
                self.statistics_chart.get_tk_widget().destroy()
                self.statistics_chart = None

        ctk.CTkButton(
            filter_frame,
            text="Odśwież",
            command=_update,
            fg_color=FETCH_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        self.create_button(
            self.statistics_frame,
            text="Powrót",
            command=self.back_to_welcome,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(pady=5)
        _update()

    def _build_auction_widgets(self, container):
        """Create auction editor widgets and return a refresh callback."""
        left_panel = tk.Frame(container, bg=self.root.cget("background"))
        left_panel.pack(side="right", fill="y", padx=10, pady=10)

        self.auction_image_label = ctk.CTkLabel(left_panel, text="")
        self.auction_image_label.pack(pady=5)
        self.auction_photo = None

        tk.Label(left_panel, text="Cena:", bg=self.root.cget("background"), fg="white").pack(anchor="w")
        self.current_price_var = tk.StringVar()
        tk.Label(left_panel, textvariable=self.current_price_var, bg=self.root.cget("background"), fg="white").pack(anchor="w")

        tk.Label(left_panel, text="Prowadzi:", bg=self.root.cget("background"), fg="white").pack(anchor="w")
        self.leader_var = tk.StringVar()
        tk.Label(left_panel, textvariable=self.leader_var, bg=self.root.cget("background"), fg="white").pack(anchor="w")

        tk.Label(left_panel, text="Pozostały czas:", bg=self.root.cget("background"), fg="white").pack(anchor="w")
        self.remaining_time_var = tk.StringVar()
        tk.Label(left_panel, textvariable=self.remaining_time_var, bg=self.root.cget("background"), fg="white").pack(anchor="w")

        win = tk.Frame(container, bg=self.root.cget("background"))
        win.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        form = tk.Frame(win, bg=self.root.cget("background"))
        form.pack(pady=5)

        labels = ["Nazwa karty", "Numer", "Cena start", "Kwota przebicia", "Czas [s]"]
        vars = []
        for i, lbl in enumerate(labels):
            tk.Label(form, text=lbl, bg=self.root.cget("background"), fg="white").grid(row=0, column=i, padx=2)
            var = tk.StringVar()
            ctk.CTkEntry(form, textvariable=var, width=100).grid(row=1, column=i, padx=2)
            vars.append(var)
        style = ttk.Style(win)
        style.configure(
            "Auction.Treeview",
            background=BG_COLOR,
            fieldbackground=BG_COLOR,
            foreground=TEXT_COLOR,
        )
        style.map("Auction.Treeview", background=[("selected", HOVER_COLOR)])
        style.configure(
            "Auction.Treeview.Heading",
            background=ACCENT_COLOR,
            foreground=TEXT_COLOR,
        )
        style.map(
            "Auction.Treeview.Heading",
            background=[("active", HOVER_COLOR)]
        )

        tree = ttk.Treeview(
            win,
            columns=("name", "price", "warehouse_code"),
            show="headings",
            height=8,
            style="Auction.Treeview",
        )
        for col, txt in [
            ("name", "Karta"),
            ("price", "Cena"),
            ("warehouse_code", "Kod magazynu"),
        ]:
            tree.heading(col, text=txt)
        tree.pack(expand=True, fill="both", padx=10, pady=10)

        self.info_var = tk.StringVar()
        tk.Label(
            win,
            textvariable=self.info_var,
            bg=self.root.cget("background"),
            fg="white",
        ).pack(pady=2)

        status_frame = tk.Frame(win, bg=self.root.cget("background"))
        status_frame.pack(pady=2)

        tk.Label(
            status_frame,
            text="Aktualna cena:",
            bg=self.root.cget("background"),
            fg=CURRENT_PRICE_COLOR,
        ).grid(row=0, column=0, padx=2, sticky="e")
        tk.Label(
            status_frame,
            textvariable=self.current_price_var,
            bg=self.root.cget("background"),
            fg=CURRENT_PRICE_COLOR,
        ).grid(row=0, column=1, padx=2, sticky="w")

        tk.Label(
            status_frame,
            text="Pozostały czas:",
            bg=self.root.cget("background"),
            fg="white",
        ).grid(row=0, column=2, padx=2, sticky="e")
        tk.Label(
            status_frame,
            textvariable=self.remaining_time_var,
            bg=self.root.cget("background"),
            fg="white",
        ).grid(row=0, column=3, padx=2, sticky="w")

        tk.Label(
            status_frame,
            text="Prowadzi:",
            bg=self.root.cget("background"),
            fg="white",
        ).grid(row=0, column=4, padx=2, sticky="e")
        tk.Label(
            status_frame,
            textvariable=self.leader_var,
            bg=self.root.cget("background"),
            fg="white",
        ).grid(row=0, column=5, padx=2, sticky="w")

        def refresh_tree():
            for r in tree.get_children():
                tree.delete(r)
            for row in self.auction_queue:
                tree.insert(
                    "",
                    "end",
                    values=(
                        row.get("name") or row.get("nazwa_karty"),
                        row.get("price") or row.get("cena_początkowa"),
                        row.get("warehouse_code", ""),
                    ),
                )
            if self.auction_queue:
                nxt = self.auction_queue[0]
                nazwa = nxt.get('name') or nxt.get('nazwa_karty')
                numer = nxt.get('numer_karty')
                if numer:
                    self.info_var.set(f"Następna karta: {nazwa} ({numer})")
                else:
                    self.info_var.set(f"Następna karta: {nazwa}")
            else:
                self.info_var.set("Brak kart w kolejce")
            if not tree.selection():
                items = tree.get_children()
                if items:
                    tree.selection_set(items[0])
            show_selected()

        def find_scan(name: str, num: str) -> Optional[str]:
            name = name.strip().lower().replace(" ", "_")
            num = num.strip().lower().replace("/", "-")
            candidates = [
                f"{name}_{num}",
                f"{name}-{num}",
                f"{name} {num}",
                num,
            ]
            exts = [".jpg", ".png", ".jpeg"]
            base_dir = SCANS_DIR
            for root_dir, _d, files in os.walk(base_dir):
                lower = {f.lower(): f for f in files}
                for cand in candidates:
                    for ext in exts:
                        fname = cand + ext
                        if fname in lower:
                            return os.path.join(root_dir, lower[fname])
            return None

        def load_image(path: Optional[str]):
            if not path:
                return
            try:
                if urlparse(path).scheme in ("http", "https"):
                    resp = requests.get(path, timeout=5)
                    resp.raise_for_status()
                    img = load_rgba_image(io.BytesIO(resp.content))
                else:
                    if os.path.exists(path):
                        img = load_rgba_image(path)
                    else:
                        return
                if img is None:
                    return
                img.thumbnail((200, 280))
                photo = _create_image(img)
                self.auction_photo = photo
                self.auction_image_label.configure(image=photo)
            except (requests.RequestException, OSError, UnidentifiedImageError) as exc:
                logger.warning("Failed to load auction image %s: %s", path, exc)

        def show_selected(event=None):
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            if 0 <= idx < len(self.auction_queue):
                row = self.auction_queue[idx]
                path = row.get("images 1") or find_scan(
                    row.get("nazwa_karty", ""), row.get("numer_karty", "")
                )
                load_image(path)

        def add_row():
            name, num, start, step, czas = [v.get().strip() for v in vars]
            if not name or not num:
                messagebox.showerror("Błąd", "Podaj nazwę i numer karty")
                return
            row = {
                "nazwa_karty": name,
                "numer_karty": num,
                "opis": "",
                "cena_początkowa": start or "0",
                "kwota_przebicia": step or "1",
                "czas_trwania": czas or "60",
            }
            self.auction_queue.append(row)
            for v in vars:
                v.set("")
            refresh_tree()

        def remove_selected():
            sel = tree.selection()
            for item_id in reversed(sel):
                idx = tree.index(item_id)
                tree.delete(item_id)
                if 0 <= idx < len(self.auction_queue):
                    self.auction_queue.pop(idx)
            refresh_tree()

        def import_selected():
            rows = []
            treeview = getattr(self, "inventory_tree", None)
            if treeview and str(treeview.winfo_exists()) == "1":
                codes = [treeview.item(i, "values")[0] for i in treeview.selection()]
                if codes:
                    try:
                        rows = self.read_inventory_rows(codes, csv_utils.WAREHOUSE_CSV)
                    except (OSError, csv.Error, UnicodeDecodeError) as exc:
                        logger.exception("Failed to read inventory rows")
                        messagebox.showerror("Błąd", str(exc))
                        return
            if not rows:
                path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
                if not path:
                    return
                try:
                    rows = self.read_inventory_rows([], path)
                except (OSError, csv.Error, UnicodeDecodeError) as exc:
                    logger.exception("Failed to read inventory rows")
                    messagebox.showerror("Błąd", str(exc))
                    return
            self.auction_queue.extend(rows)
            refresh_tree()

        def save_queue():
            fieldnames = [
                "nazwa_karty",
                "numer_karty",
                "opis",
                "cena_początkowa",
                "kwota_przebicia",
                "czas_trwania",
            ]
            with open("aukcje.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in self.auction_queue:
                    writer.writerow(row)
            try:
                import bot

                bot.aukcje_kolejka.clear()
                for r in self.auction_queue:
                    aukcja = bot.Aukcja(
                        r.get("nazwa_karty"),
                        r.get("numer_karty"),
                        r.get("opis"),
                        r.get("cena_początkowa"),
                        r.get("kwota_przebicia"),
                        r.get("czas_trwania"),
                    )
                    bot.aukcje_kolejka.append(aukcja)
            except Exception:
                logger.exception("Failed to update bot auction queue")
            messagebox.showinfo("Aukcje", "Kolejka zapisana do aukcje.csv")

        btn_frame = tk.Frame(win, bg=self.root.cget("background"))
        btn_frame.pack(pady=5)
        self.create_button(
            btn_frame,
            text="Dodaj",
            command=add_row,
            fg_color=SAVE_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        self.create_button(
            btn_frame,
            text="Wczytaj zaznaczone",
            command=import_selected,
            fg_color=FETCH_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        self.create_button(
            btn_frame,
            text="Usuń zaznaczone",
            command=remove_selected,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        self.create_button(
            btn_frame,
            text="Zapisz",
            command=save_queue,
            fg_color=SAVE_BUTTON_COLOR,
        ).pack(side="left", padx=5)


        control_frame = tk.Frame(win, bg=self.root.cget("background"))
        control_frame.pack(pady=5)

        def start_auction():
            try:
                import bot
                asyncio.run_coroutine_threadsafe(
                    bot.start_next_auction(), bot.bot.loop
                )
            except Exception as e:
                logger.exception("Failed to start auction")
                messagebox.showerror("Błąd", str(e))

        def next_card():
            start_auction()

        pause_btn = self.create_button(
            control_frame, text="⏸ Pauza", fg_color=NAV_BUTTON_COLOR
        )
        pause_btn.pack(side="left", padx=5)

        def reload_queue():
            try:
                self._load_auction_queue()
                refresh_tree()
            except (OSError, csv.Error, UnicodeDecodeError, ValueError) as exc:
                logger.exception("Failed to reload auction queue")
                messagebox.showerror("Błąd", str(exc))

        def toggle_pause():
            try:
                import bot
                bot.paused = not bot.paused
                pause_btn.configure(text="▶ Wznów" if bot.paused else "⏸ Pauza")
            except (ImportError, AttributeError) as e:
                logger.exception("Failed to toggle pause")
                messagebox.showerror("Błąd", str(e))

        self.create_button(
            control_frame,
            text="Start aukcji",
            command=start_auction,
            fg_color=SAVE_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        self.create_button(
            control_frame,
            text="Następna karta",
            command=next_card,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        pause_btn.configure(command=toggle_pause)
        self.create_button(
            control_frame,
            text="Wczytaj ponownie",
            command=reload_queue,
            fg_color=FETCH_BUTTON_COLOR,
        ).pack(side="left", padx=5)
        self.create_button(
            control_frame,
            text="Powrót do menu",
            command=self.back_to_welcome,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(side="left", padx=5)

        tree.bind("<<TreeviewSelect>>", show_selected)

        return refresh_tree

    def _load_auction_queue(self):
        """Load auction queue from inventory CSV into ``self.auction_queue``."""
        path = getattr(
            csv_utils,
            "WAREHOUSE_CSV",
            getattr(csv_utils, "INVENTORY_CSV", "magazyn.csv"),
        )
        self.auction_queue = self.read_inventory_rows([], path)

    def read_inventory_rows(self, codes, path=None):
        """Return rows from ``path`` filtered by ``codes``."""
        if path is None:
            path = getattr(
                csv_utils,
                "WAREHOUSE_CSV",
                getattr(csv_utils, "INVENTORY_CSV", "magazyn.csv"),
            )
        with open(path, newline="", encoding="utf-8") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            rows = [
                {norm_header(k): v for k, v in r.items() if k is not None}
                for r in reader
            ]

        headers = [norm_header(h) for h in (reader.fieldnames or [])]
        if "nazwa_karty" not in headers:
            if "name" in headers:
                for row in rows:
                    if "nazwa_karty" not in row:
                        name_val = str(row.get("name", "")).strip()
                        parts = name_val.rsplit(" ", 1)
                        if len(parts) == 2 and re.search(r"\d", parts[1]):
                            row["nazwa_karty"], row["numer_karty"] = parts
                        else:
                            row["nazwa_karty"] = name_val
                            row["numer_karty"] = ""
                    row["cena_początkowa"] = row.get("price", row.get("cena_początkowa", "0"))
                    row.setdefault("kwota_przebicia", "1")
                    row.setdefault("czas_trwania", "60")
            else:
                raise ValueError("Nie rozpoznano formatu pliku CSV")
        for row in rows:
            row.setdefault("price", "0")
            row.setdefault("product_code", "")
            if "image" in row and "images 1" not in row:
                row["images 1"] = row.pop("image")
        if codes:
            wanted = {str(c) for c in codes}
            rows = [r for r in rows if str(r.get("product_code")) in wanted]
        return rows

    def lookup_inventory_entry(self, key):
        """Return first row from ``WAREHOUSE_CSV`` matching ``key``."""
        parts = key.split("|")
        if len(parts) < 3:
            return None
        name, number, set_name = parts[:3]

        try:
            with open(csv_utils.WAREHOUSE_CSV, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for raw in reader:
                    row = {norm_header(k): v for k, v in raw.items() if k is not None}
                    row_name = (row.get("nazwa") or row.get("nazwa_karty") or row.get("name") or "").strip()
                    row_number = (
                        row.get("numer")
                        or row.get("numer_karty")
                        or row.get("number")
                        or ""
                    ).strip()
                    row_set = row.get("set", "").strip()
                    if (
                        row_name == name and row_number == number and row_set == set_name
                    ):
                        return {
                            "nazwa": row_name,
                            "numer": row_number,
                            "set": row_set,
                        }
        except FileNotFoundError:
            return None

        return None

    def _update_auction_status(self):
        """Update status panel with info from ``aktualna_aukcja.json``."""
        path = os.path.join("templates", "aktualna_aukcja.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)

                self.info_var.set(
                    f"Aktualna: {data.get('nazwa')} ({data.get('numer')})"
                )

                remaining = ""
                if data.get("start_time"):
                    try:
                        start = datetime.datetime.fromisoformat(
                            data["start_time"].rstrip("Z")
                        )
                        end = start + datetime.timedelta(
                            seconds=int(data.get("czas", 0))
                        )
                        rem = int(
                            (end - datetime.datetime.utcnow()).total_seconds()
                        )
                        remaining = f"{max(rem, 0)}s"
                    except (ValueError, TypeError) as exc:
                        logger.warning("Failed to parse auction time: %s", exc)
                        remaining = ""

                winner = data.get("zwyciezca") or "Brak"
                self.current_price_var.set(str(data.get("ostateczna_cena", "")))
                self.remaining_time_var.set(remaining)
                self.leader_var.set(winner)
                img_path = data.get("obraz")
                if img_path:
                    try:
                        if urlparse(img_path).scheme in ("http", "https"):
                            resp = requests.get(img_path, timeout=5)
                            resp.raise_for_status()
                            img = load_rgba_image(io.BytesIO(resp.content))
                        else:
                            if os.path.exists(img_path):
                                img = load_rgba_image(img_path)
                            else:
                                img = None
                        if img is not None:
                            img.thumbnail((200, 280))
                            photo = _create_image(img)
                            self.auction_photo = photo
                            self.auction_image_label.configure(image=photo)
                    except (requests.RequestException, OSError, UnidentifiedImageError) as exc:
                        logger.warning("Failed to load current auction image: %s", exc)
            except Exception as exc:
                logger.exception("Failed to update auction status")
        if self.auction_frame and self.auction_frame.winfo_exists():
            self.auction_frame.after(1000, self._update_auction_status)

    def _build_shoper_payload(self, card: dict) -> dict:
        """Map internal card data to the structure expected by the API."""
        name_parts = [card.get("nazwa", "")]
        if card.get("numer"):
            name_parts.append(card["numer"])
        name = " ".join(part for part in name_parts if part)

        payload = {
            "product_code": card.get("product_code"),
            "active": card.get("active", 1),
            "name": name,
            "price": card.get("cena", 0),
            "vat": card.get("vat", "23%"),
            "unit": card.get("unit", "szt."),
            "category": card.get("category"),
            "producer": card.get("producer"),
            "other_price": card.get("other_price", ""),
            "pkwiu": card.get("pkwiu", ""),
            "weight": card.get("weight", 0.01),
            "priority": card.get("priority", 0),
            "short_description": card.get("short_description", ""),
            "description": card.get("description", ""),
            "stock": card.get("ilość", 1),
            "stock_warnlevel": card.get("stock_warnlevel", 0),
            "availability": card.get("availability", 1),
            "delivery": card.get("delivery"),
            "views": card.get("views", ""),
            "rank": card.get("rank", ""),
            "rank_votes": card.get("rank_votes", ""),
            "warehouse_code": card.get("warehouse_code", ""),
        }
        if card.get("image1"):
            payload["images"] = card["image1"]
        return payload

    def show_orders(self, widget=None):
        """Display new orders with storage location hints."""
        try:
            if widget is None:
                widget = getattr(self, "orders_output", None)
            if widget is None:
                return
            orders = self.shoper_client.list_orders({"filters[status]": "new"})
            orders_list = orders.get("list", orders)
            self.pending_orders = orders_list
            choose_nearest_locations(orders_list, self.output_data)
            widget.delete("1.0", tk.END)
            lines = []
            for order in orders_list:
                oid = order.get("order_id") or order.get("id")
                lines.append(f"Zamówienie #{oid}")
                for item in order.get("products", []):
                    code = (
                        item.get("warehouse_code")
                        or item.get("product_code")
                        or item.get("code", "")
                    )
                    locations = [
                        self.location_from_code(c.strip())
                        for c in str(code).split(";")
                        if c.strip()
                    ]
                    location = "; ".join(l for l in locations if l)
                    lines.append(
                        f" - {item.get('name')} x{item.get('quantity')} [{code}] {location}"
                    )
            widget.insert(tk.END, "\n".join(lines))
        except requests.RequestException as e:
            logger.exception("Failed to list orders")
            messagebox.showerror("Błąd", str(e))

    def complete_order(self, order: dict):
        """Mark warehouse codes from ``order`` as sold.

        After updating the CSV the inventory statistics are recalculated and
        the warehouse view is refreshed.
        """

        csv_path = getattr(csv_utils, "WAREHOUSE_CSV", "magazyn.csv")
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = list(reader)
                fieldnames = reader.fieldnames or []
        except FileNotFoundError:
            return

        if "sold" not in fieldnames:
            fieldnames.append("sold")

        codes_to_mark = {
            c.strip()
            for item in order.get("products", [])
            for c in str(
                item.get("warehouse_code")
                or item.get("product_code")
                or item.get("code", "")
            ).split(";")
            if c.strip()
        }

        if not codes_to_mark:
            return

        for r in rows:
            if r.get("warehouse_code") in codes_to_mark:
                r["sold"] = "1"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        if hasattr(self, "update_inventory_stats"):
            try:
                self.update_inventory_stats()
            except Exception:
                logger.exception("Failed to update inventory stats")

        if hasattr(self, "show_magazyn_view"):
            try:
                self.show_magazyn_view()
            except Exception:
                logger.exception("Failed to refresh magazyn window")

    def confirm_order(self):
        """Confirm the first pending order and mark codes as sold."""

        orders = getattr(self, "pending_orders", [])
        if not orders:
            return
        order = orders.pop(0)
        self.complete_order(order)

    @staticmethod
    def location_from_code(code: str) -> str:
        return storage.location_from_code(code)

    def build_home_box_preview(self, parent):
        """Create a minimal box preview showing only overall fill percentages."""

        container = ctk.CTkFrame(parent, fg_color=BG_COLOR)
        container.pack(expand=True, fill="both", padx=10, pady=10)

        self.mag_box_order = list(range(1, BOX_COUNT + 1)) + [SPECIAL_BOX_NUMBER]
        self.home_percent_labels = {}
        self.home_box_canvases = {}
        self.mag_labels = []

        base_dir = Path(__file__).resolve().parents[1]
        if not hasattr(self, "_box_photo"):
            img = Image.open(base_dir / "box.png").resize(
                (BOX_THUMB_SIZE, BOX_THUMB_SIZE), Image.LANCZOS
            ).convert("RGBA")
            self._box_photo = ImageTk.PhotoImage(img)
        if not hasattr(self, "_box100_photo"):
            img = Image.open(base_dir / "box100.png").resize(
                (BOX_THUMB_SIZE, BOX_THUMB_SIZE), Image.LANCZOS
            ).convert("RGBA")
            self._box100_photo = ImageTk.PhotoImage(img)

        for i, box_num in enumerate(self.mag_box_order):
            frame = ctk.CTkFrame(container, fg_color=BG_COLOR)
            lbl = ctk.CTkLabel(
                frame,
                text=f"K{box_num}",
                fg_color=BG_COLOR,
                text_color=TEXT_COLOR,
                font=("Segoe UI", 24, "bold"),
            )
            lbl.pack()
            self.mag_labels.append(lbl)

            try:
                canvas = tk.Canvas(
                    frame,
                    width=BOX_THUMB_SIZE,
                    height=BOX_THUMB_SIZE,
                    bg=BG_COLOR,
                    highlightthickness=0,
                )
            except TypeError:
                # Some test doubles do not accept ``bg`` in the constructor.
                canvas = tk.Canvas(
                    frame,
                    width=BOX_THUMB_SIZE,
                    height=BOX_THUMB_SIZE,
                    highlightthickness=0,
                )
                canvas.config(bg=BG_COLOR)
            img = self._box100_photo if box_num == SPECIAL_BOX_NUMBER else self._box_photo
            canvas.create_image(0, 0, anchor="nw", image=img)
            canvas.image = img
            canvas.pack()
            self.home_box_canvases[box_num] = canvas

            pct_label = ctk.CTkLabel(
                frame,
                text="0%",
                width=40,
                fg_color=BG_COLOR,
                text_color=_occupancy_color(0),
                font=("Segoe UI", 24, "bold"),
            )
            pct_label.pack(pady=(5, 0))
            self.home_percent_labels[box_num] = pct_label

            row, col_idx = divmod(i, WAREHOUSE_GRID_COLUMNS)
            if box_num == SPECIAL_BOX_NUMBER:
                row = 0
                col_idx = WAREHOUSE_GRID_COLUMNS
            frame.grid(row=row, column=col_idx, padx=5, pady=5)

    def build_box_preview(self, parent):
        """Create a scrollable grid of frames and progress bars for boxes."""

        container = ctk.CTkFrame(parent, fg_color=BG_COLOR)
        container.pack(expand=True, fill="both", padx=10, pady=10)

        self.mag_box_order = list(range(1, BOX_COUNT + 1)) + [SPECIAL_BOX_NUMBER]
        self.mag_progressbars = {}
        self.mag_percent_labels = {}
        self.mag_labels = []
        for i, box_num in enumerate(self.mag_box_order):
            frame = ctk.CTkFrame(container, fg_color=BG_COLOR)
            lbl = ctk.CTkLabel(
                frame,
                text=f"K{box_num}",
                fg_color=BG_COLOR,
                text_color=TEXT_COLOR,
                font=("Segoe UI", 24, "bold"),
            )
            lbl.pack(anchor="w")
            self.mag_labels.append(lbl)
            for col in range(
                1, storage.BOX_COLUMNS.get(box_num, STANDARD_BOX_COLUMNS) + 1
            ):
                row_frame = ctk.CTkFrame(frame, fg_color=BG_COLOR)
                row_frame.pack(fill="x", padx=2, pady=2)
                bar = ctk.CTkProgressBar(
                    row_frame,
                    orientation="horizontal",
                    fg_color=FREE_COLOR,
                    progress_color=OCCUPIED_COLOR,
                )
                bar.set(0)
                bar.pack(side="left", fill="x", expand=True)
                pct_label = ctk.CTkLabel(
                    row_frame,
                    text="0%",
                    width=40,
                    fg_color=BG_COLOR,
                    text_color=_occupancy_color(0),
                    font=("Segoe UI", 24, "bold"),
                )
                pct_label.pack(side="left", padx=(5, 0))
                self.mag_progressbars[(box_num, col)] = bar
                self.mag_percent_labels[(box_num, col)] = pct_label
            row, col_idx = divmod(i, WAREHOUSE_GRID_COLUMNS)
            if box_num == SPECIAL_BOX_NUMBER:
                row = 0
                col_idx = WAREHOUSE_GRID_COLUMNS
            frame.grid(row=row, column=col_idx, padx=5, pady=5)

        # Internal helpers used by the magazyn window; populated lazily.
        self.mag_card_images = []
        self.mag_card_rows = []
        self.mag_card_labels = []
        self.mag_sold_labels = []
        self.mag_card_image_labels: list[Optional[ctk.CTkLabel]] = []

    def reload_mag_cards(self) -> None:
        """(Re)load warehouse card data from CSV and prepare image placeholders."""
        csv_path = getattr(csv_utils, "WAREHOUSE_CSV", "magazyn.csv")
        thumb_size = CARD_THUMB_SIZE
        placeholder_img = Image.new("RGB", (thumb_size, thumb_size), "#111111")
        self.mag_placeholder_photo = _create_image(placeholder_img)

        # reset containers
        self.mag_card_rows = []
        self.mag_card_images = []
        self.mag_card_image_labels = []
        self.mag_card_frames = []
        self._image_threads = []
        self._mag_column_occ: dict[tuple[int, int], int] = {}

        if not os.path.exists(csv_path):
            self._mag_prev_thumb = 0
            self._mag_csv_mtime = None
            self._mag_column_occ = {}
            return

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
            column_occ: dict[tuple[int, int], int] = {}
            for row in reader:
                if not row.get("name"):
                    logger.warning("Skipping row with missing name: %s", row)
                    continue
                key = (
                    row.get("name"),
                    row.get("number"),
                    row.get("set"),
                    row.get("variant") or "common",
                    str(row.get("sold") or ""),
                )
                groups[key].append(row)

                if str(row.get("sold") or "").lower() in {"1", "true", "yes"}:
                    continue
                codes = str(row.get("warehouse_code") or "").split(";")
                for code in codes:
                    code = code.strip()
                    if not code:
                        continue
                    m = re.match(r"K(\d+)R(\d)P(\d+)", code)
                    if not m:
                        continue
                    box = int(m.group(1))
                    col = int(m.group(2))
                    column_occ[(box, col)] = column_occ.get((box, col), 0) + 1
            self._mag_column_occ = column_occ

            for rows in groups.values():
                combined = dict(rows[0])
                added_dates: list[datetime.date] = []
                for r in rows:
                    value = (r.get("added_at") or "").strip()
                    if not value:
                        continue
                    try:
                        added_dates.append(datetime.date.fromisoformat(value))
                    except ValueError:
                        logger.warning("Skipping invalid added_at: %s", value)
                if added_dates:
                    combined["added_at"] = max(added_dates).isoformat()
                combined["image"] = next(
                    (r.get("image") for r in rows if r.get("image")),
                    "",
                )
                combined["variant"] = combined.get("variant") or "common"
                codes = [
                    r.get("warehouse_code", "") for r in rows if r.get("warehouse_code")
                ]
                combined["warehouse_code"] = ";".join(dict.fromkeys(codes))
                combined["_count"] = len(rows)
                idx = len(self.mag_card_rows)
                self.mag_card_rows.append(combined)
                self.mag_card_images.append(self.mag_placeholder_photo)
                self.mag_card_image_labels.append(None)

                img_path = combined.get("image") or ""
                if urlparse(img_path).scheme in ("http", "https"):
                    def _worker(i=idx, url=img_path):
                        img = _load_image(url)
                        if img is None:
                            return

                        def _update(img=img) -> None:
                            img_resized = _resize_to_width(img, thumb_size)
                            photo = _create_image(img_resized)
                            self.mag_card_images[i] = photo
                            lbl = self.mag_card_image_labels[i]
                            exists_fn = getattr(lbl, "winfo_exists", None)
                            if not lbl or (exists_fn and not exists_fn()):
                                return
                            if hasattr(lbl, "configure"):
                                try:
                                    lbl.configure(image=photo)
                                except tk.TclError:
                                    return
                            else:  # simple dummy widgets in tests
                                lbl.image = photo
                            relayout = getattr(self, "_relayout_mag_cards", None)
                            if callable(relayout):
                                after2 = getattr(self.root, "after", None)
                                if callable(after2):
                                    after2(0, relayout)
                                else:
                                    relayout()

                        after = getattr(self.root, "after", None)
                        if callable(after):
                            after(0, _update)
                        else:
                            _update()

                    th = threading.Thread(target=_worker, daemon=True)
                    th.start()
                    self._image_threads.append(th)
                else:
                    def _worker(i=idx, path=img_path):
                        img = _load_image(path)
                        if img is None:
                            return

                        def _update(img=img) -> None:
                            img_resized = _resize_to_width(img, thumb_size)
                            photo = _create_image(img_resized)
                            self.mag_card_images[i] = photo
                            lbl = self.mag_card_image_labels[i]
                            exists_fn = getattr(lbl, "winfo_exists", None)
                            if not lbl or (exists_fn and not exists_fn()):
                                return
                            if hasattr(lbl, "configure"):
                                try:
                                    lbl.configure(image=photo)
                                except tk.TclError:
                                    return
                            else:  # simple dummy widgets in tests
                                lbl.image = photo
                            relayout = getattr(self, "_relayout_mag_cards", None)
                            if callable(relayout):
                                after2 = getattr(self.root, "after", None)
                                if callable(after2):
                                    after2(0, relayout)
                                else:
                                    relayout()

                        after = getattr(self.root, "after", None)
                        if callable(after):
                            after(0, _update)
                        else:
                            _update()

                    th = threading.Thread(target=_worker, daemon=True)
                    th.start()
                    self._image_threads.append(th)

        self._mag_prev_thumb = 0
        try:
            self._mag_csv_mtime = os.path.getmtime(csv_path)
        except OSError:
            self._mag_csv_mtime = None

    def show_magazyn_view(self):
        """Display storage occupancy inside the main window."""
        # Unbind previous resize handlers if they exist before rebuilding the
        # magazine view. This prevents ``_relayout_mag_cards`` from being
        # triggered after the associated widgets are destroyed.
        if getattr(self, "_mag_bind_id", None) or getattr(self, "_root_mag_bind_id", None):
            mag_frame = getattr(self, "mag_list_frame", None)
            if mag_frame is not None:
                unbind = getattr(mag_frame, "unbind", None)
                if callable(unbind) and getattr(self, "_mag_bind_id", None):
                    unbind("<Configure>", self._mag_bind_id)
            if getattr(self, "_root_mag_bind_id", None):
                root_unbind = getattr(self.root, "unbind", None)
                if callable(root_unbind):
                    root_unbind("<Configure>", self._root_mag_bind_id)
            self._mag_bind_id = None
            self._root_mag_bind_id = None

        self.root.title("Podgląd magazynu")
        current_root = self.root
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
            self.magazyn_frame = None
            labels = getattr(self, "mag_card_image_labels", [])
            for i in range(len(labels)):
                labels[i] = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None

        if all(hasattr(self.root, attr) for attr in ("winfo_screenwidth", "winfo_screenheight", "minsize")):
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            min_w = int(screen_w * 0.75)
            min_h = int(screen_h * 0.75)
            self.root.minsize(min_w, min_h)
        self.magazyn_frame = ctk.CTkFrame(self.root, fg_color=BG_COLOR)
        self.magazyn_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # Reset box preview containers; tests or callers may rebuild preview
        # manually using :func:`build_box_preview` when needed.
        self.mag_progressbars = {}
        self.mag_percent_labels = {}
        self.mag_labels = []
        self.mag_box_order = []

        control_frame = ctk.CTkFrame(self.magazyn_frame, fg_color=BG_COLOR)
        control_frame.pack(fill="x", padx=10, pady=(10, 0))

        def _safe_var(value=""):
            try:
                return tk.StringVar(value=value)
            except (tk.TclError, RuntimeError):
                class _Var:
                    def __init__(self, val):
                        self._val = val
                        self._callbacks: list[callable] = []

                    def get(self):
                        return self._val

                    def set(self, val):
                        self._val = val
                        for cb in list(self._callbacks):
                            cb()

                    def trace_add(self, mode, callback):
                        self._callbacks.append(lambda *a, **k: callback())

                return _Var(value)

        self.mag_search_var = _safe_var()
        search_entry = ctk.CTkEntry(
            control_frame,
            textvariable=self.mag_search_var,
            placeholder_text="Szukaj",
            width=250,
        )
        search_entry.pack(side="left", padx=5, pady=5)

        search_button = ctk.CTkButton(
            control_frame, text="Szukaj", fg_color=FETCH_BUTTON_COLOR
        )
        search_button.pack(side="left", padx=5, pady=5)

        self.mag_sort_var = _safe_var("added")
        sort_menu = ctk.CTkOptionMenu(
            control_frame,
            variable=self.mag_sort_var,
            values=["added", "price", "name", "quantity"],
        )
        sort_menu.pack(side="left", padx=5, pady=5)

        self.mag_sold_filter_var = _safe_var("unsold")
        sold_filter_menu = ctk.CTkOptionMenu(
            control_frame,
            variable=self.mag_sold_filter_var,
            values=["all", "sold", "unsold"],
        )
        sold_filter_menu.pack(side="left", padx=5, pady=5)

        list_frame = ctk.CTkScrollableFrame(self.magazyn_frame, fg_color=LIGHT_BG_COLOR)
        list_frame.pack(expand=True, fill="both", padx=10, pady=10)
        # store reference for resize handling
        self.mag_list_frame = list_frame

        # Populate warehouse card data from CSV
        try:
            CardEditorApp.reload_mag_cards(self)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to reload warehouse cards")

        def _relayout_mag_cards(event=None):
            """Recompute thumbnail size and update scroll region on resize."""
            if getattr(self, "_mag_layout_running", False):
                return
            self._mag_layout_running = True
            try:
                exists_fn = getattr(self.mag_list_frame, "winfo_exists", lambda: True)
                if not self.mag_list_frame or not exists_fn():
                    return
                global CARD_THUMB_SIZE
                width = 0
                canvas = getattr(self.mag_list_frame, "_parent_canvas", None)
                if canvas is not None:
                    width_fn = getattr(canvas, "winfo_width", None)
                    if callable(width_fn):
                        width = width_fn()
                if width <= 1:
                    width_fn = getattr(self.magazyn_frame, "winfo_width", lambda: 0)
                    width = width_fn()
                if width <= 1:
                    return
                max_thumb = MAX_CARD_THUMB_SIZE
                cols = max(1, width // (max_thumb + MAG_CARD_GAP * 2))
                thumb = max(
                    32,
                    min((width - MAG_CARD_GAP * 2 * cols) // cols, max_thumb),
                )
                if thumb != self._mag_prev_thumb:
                    self._mag_prev_thumb = thumb
                    CARD_THUMB_SIZE = thumb
                    placeholder = Image.new("RGB", (thumb, thumb), "#111111")
                    old_placeholder = getattr(self, "mag_placeholder_photo", None)
                    self.mag_placeholder_photo = _create_image(placeholder)
                    for i, img in enumerate(list(self.mag_card_images)):
                        photo = img
                        if photo is None or photo is old_placeholder:
                            photo = self.mag_placeholder_photo
                            self.mag_card_images[i] = photo
                        else:
                            if hasattr(photo, "configure") and hasattr(photo, "_light_image"):
                                try:
                                    w, h = photo._light_image.size
                                    new_h = max(1, int(h * thumb / w)) if w else thumb
                                    photo.configure(size=(thumb, new_h))
                                except Exception:
                                    pass
                        lbl = self.mag_card_image_labels[i]
                        if lbl is not None:
                            # Ensure the label widget still exists before updating.
                            exists_fn = getattr(lbl, "winfo_exists", None)
                            try:
                                exists = True if exists_fn is None else bool(exists_fn())
                            except Exception:
                                exists = False
                            if exists:
                                if hasattr(lbl, "configure"):
                                    lbl.configure(image=photo)
                                else:
                                    lbl.image = photo

                col_conf = getattr(self.mag_list_frame, "grid_columnconfigure", None)
                if callable(col_conf):
                    prev_cols = getattr(self, "_mag_prev_cols", 0)
                    total = max(prev_cols, cols)
                    for i in range(total):
                        weight = 1 if i < cols else 0
                        col_conf(i, weight=weight)
                    self._mag_prev_cols = cols
                for i, frame in enumerate(self.mag_card_frames):
                    if frame is None:
                        continue
                    exists_fn = getattr(frame, "winfo_exists", None)
                    try:
                        exists = True if exists_fn is None else bool(exists_fn())
                    except Exception:
                        exists = False
                    if not exists:
                        continue
                    r = i // cols
                    c = i % cols
                    grid = getattr(frame, "grid", None)
                    if callable(grid):
                        grid(
                            row=r,
                            column=c,
                            padx=MAG_CARD_GAP,
                            pady=MAG_CARD_GAP,
                            sticky="nsew",
                        )

                canvas = getattr(self.mag_list_frame, "_parent_canvas", None)
                if canvas is not None:
                    def _update_scroll_region():
                        yview_fn = getattr(canvas, "yview", None)
                        try:
                            yview = yview_fn() if callable(yview_fn) else None
                        except Exception:
                            yview = None
                        bbox = canvas.bbox("all") or (0, 0, 0, 0)
                        canvas.configure(scrollregion=bbox)
                        if yview:
                            moveto = getattr(canvas, "yview_moveto", None)
                            if callable(moveto):
                                try:
                                    moveto(yview[0])
                                except Exception:
                                    pass

                    after_idle = getattr(canvas, "after_idle", None)
                    if callable(after_idle):
                        after_idle(_update_scroll_region)
                    else:
                        _update_scroll_region()
            finally:
                self._mag_layout_running = False

        # Expose relayout function for worker threads
        self._relayout_mag_cards = _relayout_mag_cards

        def _update_mag_list(*_):
            query_raw = self.mag_search_var.get().strip()
            sort_key = self.mag_sort_var.get()
            status_filter = self.mag_sold_filter_var.get()

            normalized_query = normalize(query_raw, keep_spaces=True)
            tokens = [tok for tok in normalized_query.split() if tok]
            if "sold" in tokens or "unsold" in tokens:
                status_filter = "all"

            def _matches(row: dict) -> bool:
                is_sold = str(row.get("sold") or "").lower() in {"1", "true", "yes"}
                if status_filter == "sold" and not is_sold:
                    return False
                if status_filter == "unsold" and is_sold:
                    return False
                price_str = str(row.get("price", "")).replace(",", ".")
                fields = [
                    normalize(row.get("name", "")),
                    normalize(str(row.get("number", ""))),
                    normalize(row.get("set", "")),
                    normalize(row.get("warehouse_code", "")),
                    normalize(row.get("variant") or ""),
                    normalize(price_str),
                ]
                for token in tokens:
                    if token == "sold":
                        if not is_sold:
                            return False
                        continue
                    if token == "unsold":
                        if is_sold:
                            return False
                        continue
                    if not any(token in field for field in fields):
                        return False
                return True

            indices = [i for i, r in enumerate(self.mag_card_rows) if _matches(r)]
            if sort_key == "added":
                indices.sort(
                    key=lambda i: self.mag_card_rows[i].get("added_at") or "",
                    reverse=True,
                )
            elif sort_key == "name":
                indices.sort(key=lambda i: self.mag_card_rows[i].get("name", ""))
            elif sort_key == "price":
                def _price(i: int) -> float:
                    val = str(self.mag_card_rows[i].get("price", "0")).replace(",", ".")
                    try:
                        return float(val)
                    except ValueError:
                        return 0.0

                indices.sort(key=_price)
            elif sort_key == "quantity":
                def _quantity(i: int) -> int:
                    try:
                        return int(self.mag_card_rows[i].get("_count", 1))
                    except (TypeError, ValueError):
                        return 1

                indices.sort(key=_quantity, reverse=True)

            unbind = getattr(self.mag_list_frame, "unbind", None)
            if callable(unbind) and getattr(self, "_mag_bind_id", None):
                unbind("<Configure>", self._mag_bind_id)
                self._mag_bind_id = None
            root_unbind = getattr(current_root, "unbind", None)
            if callable(root_unbind) and getattr(self, "_root_mag_bind_id", None):
                root_unbind("<Configure>", self._root_mag_bind_id)
                self._root_mag_bind_id = None

            frames = getattr(self, "mag_card_frames", [])
            self.mag_card_frames = []
            for frame in frames:
                try:
                    frame.destroy()
                except Exception:
                    pass
            labels = getattr(self, "mag_card_image_labels", [])
            for i in range(len(labels)):
                labels[i] = None
            self.mag_card_labels = []
            self.mag_sold_labels = []
            displayed = set(indices)

            for idx in indices:
                row = self.mag_card_rows[idx]
                photo = self.mag_card_images[idx]
                frame = ctk.CTkFrame(list_frame, fg_color=BG_COLOR)
                col_conf = getattr(frame, "grid_columnconfigure", None)
                if callable(col_conf):
                    col_conf(0, weight=1)
                is_sold = str(row.get("sold") or "").lower() in {"1", "true", "yes"}
                text = row.get("name", "")
                color = TEXT_COLOR
                font = None
                if is_sold:
                    text = f"[SOLD] {text}"
                    color = SOLD_COLOR
                    if hasattr(ctk, "CTkFont"):
                        font = ctk.CTkFont(size=20, overstrike=True)
                    else:
                        font = ("TkDefaultFont", 20, "overstrike")

                img_label = ctk.CTkLabel(frame, image=photo, text="")
                grid = getattr(img_label, "grid", None)
                if callable(grid):
                    grid(row=0, column=0, sticky="n")
                self.mag_card_image_labels[idx] = img_label

                count = int(row.get("_count", 1))
                if count > 1:
                    badge = ctk.CTkLabel(
                        frame,
                        text=str(count),
                        fg_color="#FF0000",
                        text_color="white",
                        width=20,
                        height=20,
                        corner_radius=10,
                    )
                    place = getattr(badge, "place", None)
                    if callable(place):
                        place(in_=img_label, relx=1.0, rely=0.0, anchor="ne")
                        lift = getattr(badge, "lift", None)
                        if callable(lift):
                            lift()
                    else:
                        grid_badge = getattr(badge, "grid", None)
                        if callable(grid_badge):
                            grid_badge(row=0, column=0, sticky="ne")
                        else:
                            badge.pack()

                label_kwargs = {
                    "text": text,
                    "text_color": color,
                    "width": CARD_THUMB_SIZE,
                    "wraplength": CARD_THUMB_SIZE,
                    "justify": "center",
                }
                if font is not None:
                    label_kwargs["font"] = font
                label = ctk.CTkLabel(frame, **label_kwargs)
                grid = getattr(label, "grid", None)
                if callable(grid):
                    grid(row=1, column=0, sticky="new")

                self.mag_card_frames.append(frame)

                for widget in (img_label, label):
                    widget.bind("<Button-1>", lambda e, r=row: self.show_card_details(r))
                    widget.bind(
                        "<Double-Button-1>",
                        lambda e, r=row: self.show_card_details(r),
                    )

                if is_sold:
                    self.mag_sold_labels.append(label)
                else:
                    self.mag_card_labels.append(label)

            for i in range(len(self.mag_card_image_labels)):
                if i not in displayed:
                    self.mag_card_image_labels[i] = None
            canvas = getattr(list_frame, "_parent_canvas", None)
            if canvas is not None:
                def _update_scroll_region():
                    bbox = canvas.bbox("all") or (0, 0, 0, 0)
                    canvas.configure(scrollregion=bbox)

                canvas_after_idle = getattr(canvas, "after_idle", None)
                if callable(canvas_after_idle):
                    canvas_after_idle(_update_scroll_region)
                else:
                    _update_scroll_region()

            list_after_idle = getattr(list_frame, "after_idle", None)
            if callable(list_after_idle):
                list_after_idle(_relayout_mag_cards)
            else:
                _relayout_mag_cards()

            bind = getattr(self.mag_list_frame, "bind", None)
            if callable(bind):
                self._mag_bind_id = bind("<Configure>", _relayout_mag_cards)
            canvas_bind = getattr(canvas, "bind", None)
            if callable(canvas_bind):
                self._mag_canvas_bind_id = canvas_bind("<Configure>", _relayout_mag_cards)
            root_bind = getattr(current_root, "bind", None)
            if callable(root_bind):
                self._root_mag_bind_id = root_bind("<Configure>", _relayout_mag_cards)

        self._update_mag_list = _update_mag_list
        if hasattr(search_entry, "bind"):
            search_entry.bind("<Return>", lambda _e: _update_mag_list())
        if hasattr(search_button, "configure"):
            search_button.configure(command=_update_mag_list)
        else:
            search_button.command = _update_mag_list
        self.mag_sold_filter_var.trace_add("write", _update_mag_list)
        if hasattr(sort_menu, "configure"):
            sort_menu.configure(command=lambda _: _update_mag_list())
        else:
            sort_menu.command = lambda _: _update_mag_list()
        if hasattr(sold_filter_menu, "configure"):
            sold_filter_menu.configure(command=lambda _: _update_mag_list())
        else:
            sold_filter_menu.command = lambda _: _update_mag_list()
        _update_mag_list()

        btn_frame = ctk.CTkFrame(self.magazyn_frame, fg_color=BG_COLOR)
        btn_frame.pack(pady=5)

        def _close_mag_window():
            """Return to the previous screen and remove magazyn bindings."""
            mag_frame = getattr(self, "mag_list_frame", None)
            if mag_frame is not None:
                unbind = getattr(mag_frame, "unbind", None)
                if callable(unbind) and getattr(self, "_mag_bind_id", None):
                    unbind("<Configure>", self._mag_bind_id)
            if getattr(self, "_root_mag_bind_id", None):
                root_unbind = getattr(current_root, "unbind", None)
                if callable(root_unbind):
                    root_unbind("<Configure>", self._root_mag_bind_id)
            self._mag_bind_id = None
            self._root_mag_bind_id = None
            if hasattr(self, "back_to_welcome"):
                self.back_to_welcome()

        self.create_button(
            btn_frame,
            text="Odśwież",
            command=self.refresh_magazyn,
            fg_color=FETCH_BUTTON_COLOR,
        ).pack(side="left", padx=5)

        self.create_button(
            btn_frame,
            text="Powrót",
            command=_close_mag_window,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(side="left", padx=5)

        stats_frame = ctk.CTkFrame(self.magazyn_frame, fg_color=BG_COLOR)
        # Center statistics below the action buttons
        stats_frame.pack(pady=(0, 10), anchor="center")

        font = ("Segoe UI", 16, "bold")
        unsold_count, unsold_total, sold_count, sold_total = csv_utils.get_inventory_stats()
        if not getattr(self, "mag_card_rows", []):
            messagebox.showinfo("Magazyn", "Brak kart w magazynie")
        self.mag_inventory_count_label = ctk.CTkLabel(
            stats_frame,
            text=f"📊 Łączna liczba kart: {unsold_count}",
            text_color=TEXT_COLOR,
            font=font,
        )
        self.mag_inventory_count_label.pack()
        self.mag_inventory_value_label = ctk.CTkLabel(
            stats_frame,
            text=f"💰 Łączna wartość: {unsold_total:.2f} PLN",
            text_color="#FFD700",
            font=font,
        )
        self.mag_inventory_value_label.pack()
        self.mag_sold_count_label = ctk.CTkLabel(
            stats_frame,
            text=f"Sprzedane karty: {sold_count}",
            text_color=TEXT_COLOR,
            font=font,
        )
        self.mag_sold_count_label.pack()
        self.mag_sold_value_label = ctk.CTkLabel(
            stats_frame,
            text=f"Wartość sprzedanych: {sold_total:.2f} PLN",
            text_color=TEXT_COLOR,
            font=font,
        )
        self.mag_sold_value_label.pack()

        # legend for color coding in the storage view
        legend_frame = ctk.CTkFrame(self.magazyn_frame, fg_color=BG_COLOR)
        legend_frame.pack(pady=(0, 10))
        legend_items = [
            (FREE_COLOR, "≥30% free"),
            (OCCUPIED_COLOR, "Occupied capacity segment"),
            (SOLD_COLOR, "Sold item"),
        ]
        for color, desc in legend_items:
            swatch = ctk.CTkLabel(legend_frame, text="", width=15, height=15, fg_color=color)
            swatch.pack(side="left", padx=5)
            ctk.CTkLabel(
                legend_frame, text=desc, text_color=TEXT_COLOR
            ).pack(side="left", padx=(0, 10))
            try:
                Tooltip(swatch, desc)
            except Exception as exc:
                logger.exception("Failed to create tooltip")

        self.refresh_magazyn()
        # Ensure the statistics reflect the latest warehouse state
        if hasattr(self, "update_inventory_stats"):
            try:
                self.update_inventory_stats()
            except Exception as exc:
                logger.exception("Failed to update inventory stats")

    def open_magazyn_window(self):
        """Legacy wrapper for :meth:`show_magazyn_view`.

        Existing callers expecting ``open_magazyn_window`` can still invoke it,
        but it simply delegates to :meth:`show_magazyn_view` and renders the
        view inside the main application window.
        """
        self.show_magazyn_view()

    def compute_box_occupancy(self) -> dict[int, int]:
        """Return dictionary of used slots per storage box."""
        return storage.compute_box_occupancy()

    def repack_column(self, box: int, column: int):
        """Renumber codes in the given column so there are no gaps."""
        storage.repack_column(box, column)
        self.refresh_magazyn()

    def refresh_home_preview(self):
        """Refresh box preview on the welcome screen."""
        if not getattr(self, "home_percent_labels", None):
            return

        col_occ = storage.compute_column_occupancy()

        for box, lbl in self.home_percent_labels.items():
            columns = storage.BOX_COLUMNS.get(box, 4)
            total_capacity = storage.BOX_CAPACITY.get(
                box, columns * storage.BOX_COLUMN_CAPACITY
            )
            box_used = sum(col_occ.get(box, {}).values())
            value = box_used / total_capacity if total_capacity else 0
            lbl.configure(text=f"{value * 100:.0f}%", text_color=_occupancy_color(value))

            canvas = self.home_box_canvases.get(box)
            if canvas is not None:
                draw_box_usage(canvas, box, col_occ.get(box, {}))

    def refresh_magazyn(self):
        """Refresh storage view and update column usage bars."""
        csv_path = getattr(csv_utils, "WAREHOUSE_CSV", "magazyn.csv")
        try:
            current_mtime = os.path.getmtime(csv_path)
        except OSError:
            current_mtime = None
        if getattr(self, "_mag_csv_mtime", None) != current_mtime:
            reload_fn = getattr(self, "reload_mag_cards", None)
            if callable(reload_fn):
                reload_fn()
        update_fn = getattr(self, "_update_mag_list", None)
        if callable(update_fn):
            try:
                update_fn()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to update magazyn list")

        if not getattr(self, "mag_progressbars", None):
            return

        col_occ = getattr(self, "_mag_column_occ", {})

        for (box, col), bar in self.mag_progressbars.items():
            filled = col_occ.get((box, col), 0)
            columns = storage.BOX_COLUMNS.get(box, 4)
            total_capacity = storage.BOX_CAPACITY.get(
                box, columns * storage.BOX_COLUMN_CAPACITY
            )
            col_capacity = total_capacity / columns if columns else storage.BOX_COLUMN_CAPACITY
            value = filled / col_capacity if col_capacity else 0
            bar.set(value)
            lbl = self.mag_percent_labels.get((box, col))
            if lbl:
                lbl.configure(text=f"{value * 100:.0f}%", text_color=_occupancy_color(value))

        if hasattr(self, "update_inventory_stats"):
            try:
                self.update_inventory_stats()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Failed to update inventory stats")

    def show_card_details(self, row: dict):
        """Display details for a selected warehouse card."""

        top = ctk.CTkToplevel(self.root)
        if hasattr(top, "transient"):
            top.transient(self.root)
        if hasattr(top, "grab_set"):
            top.grab_set()
        if hasattr(top, "lift"):
            top.lift()
        if hasattr(top, "focus_force"):
            top.focus_force()

        def close_details():
            if hasattr(top, "grab_release"):
                top.grab_release()
            top.destroy()

        if hasattr(top, "protocol"):
            top.protocol("WM_DELETE_WINDOW", close_details)
        top.title(row.get("name", _("Karta")))
        if hasattr(top, "overrideredirect"):
            top.overrideredirect(True)
        # ensure enough space for side-by-side layout
        if hasattr(top, "geometry"):
            top.geometry("600x400")
            try:
                top.minsize(600, 400)
            except tk.TclError:
                pass

        container = ctk.CTkFrame(top)
        container.pack(expand=True, fill="both", padx=10, pady=10)

        left = ctk.CTkFrame(container)
        left.pack(side="left", padx=(0, 10), pady=10)

        right = ctk.CTkFrame(container)
        right.pack(side="left", fill="both", expand=True, pady=10)

        img_path = row.get("image") or ""
        img = _load_image(img_path)
        text = ""
        if img is None:
            logger.info("Missing image for %s", img_path)
            img = Image.new("RGB", (300, 300), "#111111")
            text = "Brak skanu"
        img.thumbnail((300, 300))
        photo = _create_image(img)
        img_lbl = ctk.CTkLabel(left, image=photo, text=text, compound="center", text_color="white")
        img_lbl.image = photo  # keep reference
        img_lbl.pack()

        fields = [
            ("name", "Name"),
            ("number", "Number"),
            ("set", "Set"),
            ("price", "Price"),
            ("warehouse_code", "Warehouse Code"),
        ]
        row_idx = 0
        selected_var = None
        selected_default = ""
        for key, label in fields:
            val = row.get(key, "")
            if key == "warehouse_code":
                codes = [c.strip() for c in str(val).split(";") if c.strip()]
                if codes:
                    selected_default = codes[0]
                    pattern = re.compile(r"K(\d+)R(\d+)P(\d+)")
                    parsed = []
                    for code in codes:
                        m = pattern.fullmatch(code)
                        if m:
                            parsed.append((code, m.group(1), m.group(2), m.group(3)))
                        else:  # pragma: no cover - unexpected format
                            parsed.append((code, "", "", ""))

                    if len(parsed) > 1:
                        ctk.CTkLabel(
                            right,
                            text=_("Kody magazynowe:"),
                            font=("Inter", 16),
                        ).grid(row=row_idx, column=0, sticky="w", pady=2)
                        row_idx += 1
                        try:
                            selected_var = tk.StringVar(value=selected_default)
                        except (tk.TclError, RuntimeError):
                            selected_var = SimpleNamespace(get=lambda: selected_default)

                        def update_labels(selected: str) -> None:
                            info = next((p for p in parsed if p[0] == selected), parsed[0])
                            karton_lbl.configure(text=f"Karton: {info[1]}")
                            kolumna_lbl.configure(text=f"Kolumna: {info[2]}")
                            pozycja_lbl.configure(text=f"Pozycja: {info[3]}")

                        ctk.CTkOptionMenu(
                            right,
                            values=[p[0] for p in parsed],
                            variable=selected_var,
                            command=update_labels,
                        ).grid(row=row_idx, column=0, sticky="w", pady=2)
                        row_idx += 1

                        karton_lbl = ctk.CTkLabel(
                            right,
                            text=f"Karton: {parsed[0][1]}",
                            font=("Inter", 16),
                        )
                        karton_lbl.grid(row=row_idx, column=0, sticky="w", pady=2)
                        row_idx += 1
                        kolumna_lbl = ctk.CTkLabel(
                            right,
                            text=f"Kolumna: {parsed[0][2]}",
                            font=("Inter", 16),
                        )
                        kolumna_lbl.grid(row=row_idx, column=0, sticky="w", pady=2)
                        row_idx += 1
                        pozycja_lbl = ctk.CTkLabel(
                            right,
                            text=f"Pozycja: {parsed[0][3]}",
                            font=("Inter", 16),
                        )
                        pozycja_lbl.grid(row=row_idx, column=0, sticky="w", pady=2)
                        row_idx += 1
                        continue

                    # single code
                    c = parsed[0]
                    ctk.CTkLabel(
                        right,
                        text=f"Karton: {c[1]}",
                        font=("Inter", 16),
                    ).grid(row=row_idx, column=0, sticky="w", pady=2)
                    row_idx += 1
                    ctk.CTkLabel(
                        right,
                        text=f"Kolumna: {c[2]}",
                        font=("Inter", 16),
                    ).grid(row=row_idx, column=0, sticky="w", pady=2)
                    row_idx += 1
                    ctk.CTkLabel(
                        right,
                        text=f"Pozycja: {c[3]}",
                        font=("Inter", 16),
                    ).grid(row=row_idx, column=0, sticky="w", pady=2)
                    row_idx += 1
                    continue

            ctk.CTkLabel(
                right,
                text=f"{label}: {val}",
                font=("Inter", 16),
            ).grid(row=row_idx, column=0, sticky="w", pady=2)
            row_idx += 1

        buttons_frame = ctk.CTkFrame(top)
        buttons_frame.pack(side="bottom", pady=10)

        ctk.CTkButton(
            buttons_frame,
            text="Sprzedano",
            command=lambda: self.mark_as_sold(
                row,
                top,
                selected_var.get() if selected_var is not None else selected_default,
            ),
            fg_color=SAVE_BUTTON_COLOR,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            buttons_frame,
            text="Zamknij",
            command=close_details,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(side="left", padx=5)

    def mark_as_sold(
        self,
        row: dict,
        window=None,
        warehouse_code: Optional[str] = None,
    ):
        """Mark the card as sold, update CSV and refresh views."""

        csv_path = getattr(csv_utils, "WAREHOUSE_CSV", "magazyn.csv")
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = list(reader)
                fieldnames = reader.fieldnames or []
        except FileNotFoundError:
            return

        if "sold" not in fieldnames:
            fieldnames.append("sold")

        codes = [
            c.strip()
            for c in str(row.get("warehouse_code", "")).split(";")
            if c.strip()
        ]
        target = warehouse_code or (codes[0] if codes else "")
        for r in rows:
            if r.get("warehouse_code") == target:
                r["sold"] = "1"
                break

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

        # Refresh the magazyn view in-place rather than reopening the window.
        if hasattr(self, "refresh_magazyn"):
            try:
                self.refresh_magazyn()
            except Exception:
                logger.exception("Failed to refresh magazyn view")
        elif hasattr(self, "show_magazyn_view"):
            # Fallback for environments where the magazyn view was not yet
            # initialised; rebuild it inside the main window.
            try:
                self.show_magazyn_view()
            except Exception:
                logger.exception("Failed to display magazyn view")

    def toggle_sold(self, row: dict, window=None):
        """Toggle the sold flag for a warehouse card and update CSV."""

        csv_path = getattr(csv_utils, "WAREHOUSE_CSV", "magazyn.csv")
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = list(reader)
                fieldnames = reader.fieldnames or []
        except FileNotFoundError:
            return

        if "sold" not in fieldnames:
            fieldnames.append("sold")

        target = str(row.get("warehouse_code", ""))
        for r in rows:
            if r.get("warehouse_code") == target:
                current = str(r.get("sold") or "").lower() in {"1", "true", "yes"}
                r["sold"] = "" if current else "1"
                row["sold"] = r["sold"]
                break

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

        # Refresh main view to reflect the change without recreating the root
        if hasattr(self, "refresh_magazyn"):
            try:
                self.refresh_magazyn()
            except Exception:
                logger.exception("Failed to refresh magazyn view")
        elif hasattr(self, "show_magazyn_view"):
            try:
                self.show_magazyn_view()
            except Exception:
                logger.exception("Failed to display magazyn view")

    def setup_pricing_ui(self):
        """UI for quick card price lookup."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
        # Set a sensible minimum size and allow resizing
        self.root.minsize(1200, 800)
        self.pricing_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.pricing_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.pricing_frame.columnconfigure(0, weight=1)
        self.pricing_frame.columnconfigure(1, weight=1)
        self.pricing_frame.rowconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = load_rgba_image(logo_path)
            if logo_img:
                logo_img.thumbnail((200, 80))
                self.pricing_logo_photo = _create_image(logo_img)
                ctk.CTkLabel(
                    self.pricing_frame,
                    image=self.pricing_logo_photo,
                    text="",
                ).grid(row=0, column=0, columnspan=2, pady=(0, 10))

        self.input_frame = tk.Frame(
            self.pricing_frame, bg=self.root.cget("background")
        )
        self.input_frame.grid(row=1, column=0, sticky="nsew")

        self.image_frame = tk.Frame(
            self.pricing_frame, bg=self.root.cget("background")
        )
        self.image_frame.grid(row=1, column=1, sticky="nsew")

        self.input_frame.columnconfigure(0, weight=1)
        self.input_frame.columnconfigure(1, weight=1)
        self.input_frame.rowconfigure(5, weight=1)

        tk.Label(
            self.input_frame, text="Nazwa", bg=self.root.cget("background")
        ).grid(row=0, column=0, sticky="e")
        self.price_name_entry = ctk.CTkEntry(
            self.input_frame, width=200, placeholder_text="Nazwa karty"
        )
        self.price_name_entry.grid(row=0, column=1, sticky="ew")

        tk.Label(
            self.input_frame, text="Numer", bg=self.root.cget("background")
        ).grid(row=1, column=0, sticky="e")
        self.price_number_entry = ctk.CTkEntry(
            self.input_frame, width=200, placeholder_text="Numer"
        )
        self.price_number_entry.grid(row=1, column=1, sticky="ew")

        tk.Label(
            self.input_frame, text="Set", bg=self.root.cget("background")
        ).grid(row=2, column=0, sticky="e")
        self.price_set_entry = ctk.CTkEntry(
            self.input_frame, width=200, placeholder_text="Set"
        )
        self.price_set_entry.grid(row=2, column=1, sticky="ew")

        self.price_reverse_var = tk.BooleanVar()
        ctk.CTkCheckBox(
            self.input_frame,
            text="Reverse",
            variable=self.price_reverse_var,
        ).grid(row=3, column=0, columnspan=2, pady=5)

        self.price_reverse_var.trace_add("write", lambda *a: self.on_reverse_toggle())

        btn_frame = tk.Frame(
            self.input_frame, bg=self.root.cget("background")
        )
        btn_frame.grid(row=4, column=0, columnspan=2, pady=5, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.create_button(
            btn_frame,
            text="Wyszukaj",
            command=self.run_pricing_search,
            width=120,
            fg_color=FETCH_BUTTON_COLOR,
        ).grid(row=0, column=0, padx=5)

        self.create_button(
            btn_frame,
            text="Wyczyść",
            command=self.clear_price_pool,
            width=120,
            fg_color=NAV_BUTTON_COLOR,
        ).grid(row=0, column=1, padx=5)

        self.result_frame = tk.Frame(
            self.image_frame, bg=self.root.cget("background")
        )
        self.result_frame.pack(expand=True, fill="both", pady=10)

        self.pool_frame = tk.Frame(
            self.pricing_frame, bg=self.root.cget("background")
        )
        self.pool_frame.grid(row=2, column=0, columnspan=2, pady=5)
        self.pool_total_label = tk.Label(
            self.pool_frame,
            text="Suma puli: 0.00",
            bg=self.root.cget("background"),
            fg=TEXT_COLOR,
        )
        self.pool_total_label.pack(side="left")
        self.create_button(
            self.pool_frame,
            text="Powrót",
            command=self.back_to_welcome,
            width=120,
            fg_color=NAV_BUTTON_COLOR,
        ).pack(side="left", padx=5)

    def run_pricing_search(self):
        """Fetch and display pricing information."""
        name = self.price_name_entry.get()
        number = self.price_number_entry.get()
        set_name = self.price_set_entry.get()
        is_reverse = self.price_reverse_var.get()

        info = self.lookup_card_info(name, number, set_name)
        for w in self.result_frame.winfo_children():
            w.destroy()
        self.price_labels = []
        self.result_image_label = None
        self.set_logo_label = None
        self.add_pool_button = None
        if not info:
            messagebox.showinfo("Brak wyników", "Nie znaleziono karty.")
            return
        self.current_price_info = info

        if info.get("image_url"):
            try:
                res = requests.get(info["image_url"], timeout=10)
                if res.status_code == 200:
                    img = load_rgba_image(io.BytesIO(res.content))
                    if img:
                        img.thumbnail((240, 340))
                        self.pricing_photo = _create_image(img)
                        self.result_image_label = ctk.CTkLabel(
                            self.result_frame,
                            image=self.pricing_photo,
                            text="",
                        )
                        self.result_image_label.pack(pady=5)
            except (requests.RequestException, OSError, UnidentifiedImageError) as e:
                logger.warning("Loading image failed: %s", e)

        if info.get("set_logo_url"):
            try:
                res = requests.get(info["set_logo_url"], timeout=10)
                if res.status_code == 200:
                    img = load_rgba_image(io.BytesIO(res.content))
                    if img:
                        img.thumbnail((180, 60))
                        self.set_logo_photo = _create_image(img)
                        self.set_logo_label = ctk.CTkLabel(
                            self.result_frame,
                            image=self.set_logo_photo,
                            text="",
                        )
                        self.set_logo_label.pack(pady=5)
            except (requests.RequestException, OSError, UnidentifiedImageError) as e:
                logger.warning("Loading set logo failed: %s", e)
        self.display_price_info(info, is_reverse)

    def display_price_info(self, info, is_reverse):
        """Show pricing data with optional reverse multiplier."""
        price_pln = self.apply_variant_multiplier(
            info["price_pln"], is_reverse=is_reverse
        )
        price_80 = round(price_pln * 0.8, 2)
        if not getattr(self, "price_labels", None):
            eur = tk.Label(
                self.result_frame,
                text=f"Cena EUR: {info['price_eur']}",
                fg="blue",
                bg=self.root.cget("background"),
            )
            rate = tk.Label(
                self.result_frame,
                text=f"Kurs EUR→PLN: {info['eur_pln_rate']}",
                fg="gray",
                bg=self.root.cget("background"),
            )
            pln = tk.Label(
                self.result_frame,
                text=f"Cena PLN: {price_pln}",
                fg="green",
                bg=self.root.cget("background"),
            )
            pln80 = tk.Label(
                self.result_frame,
                text=f"80% ceny PLN: {price_80}",
                fg="red",
                bg=self.root.cget("background"),
            )
            for lbl in (eur, rate, pln, pln80):
                lbl.pack()
            self.add_pool_button = self.create_button(
                self.result_frame,
                text="Dodaj do puli",
                command=self.add_to_price_pool,
                fg_color=SAVE_BUTTON_COLOR,
            )
            self.add_pool_button.pack(pady=5)
            self.price_labels = [eur, rate, pln, pln80]
        else:
            eur, rate, pln, pln80 = self.price_labels
            eur.config(text=f"Cena EUR: {info['price_eur']}")
            rate.config(text=f"Kurs EUR→PLN: {info['eur_pln_rate']}")
            pln.config(text=f"Cena PLN: {price_pln}")
            pln80.config(text=f"80% ceny PLN: {price_80}")

    def on_reverse_toggle(self, *args):
        if getattr(self, "current_price_info", None):
            self.display_price_info(
                self.current_price_info, self.price_reverse_var.get()
            )

    def add_to_price_pool(self):
        if not getattr(self, "current_price_info", None):
            return
        price = self.apply_variant_multiplier(
            self.current_price_info["price_pln"],
            is_reverse=self.price_reverse_var.get(),
        )
        try:
            self.price_pool_total += float(price)
        except (TypeError, ValueError):
            return
        if self.pool_total_label:
            self.pool_total_label.config(
                text=f"Suma puli: {self.price_pool_total:.2f}"
            )

    def clear_price_pool(self):
        self.price_pool_total = 0.0
        if self.pool_total_label:
            self.pool_total_label.config(text="Suma puli: 0.00")

    def back_to_welcome(self):
        if getattr(self, "in_scan", False):
            if not messagebox.askyesno(
                "Potwierdzenie", "Czy na pewno chcesz przerwać?"
            ):
                return
        self.in_scan = False
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
            self.magazyn_frame = None
            labels = getattr(self, "mag_card_image_labels", [])
            for i in range(len(labels)):
                labels[i] = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        if getattr(self, "auction_frame", None):
            self.auction_frame.destroy()
            self.auction_frame = None
        if getattr(self, "statistics_frame", None):
            self.statistics_frame.destroy()
            self.statistics_frame = None
        self.setup_welcome_screen()

    def setup_editor_ui(self):
        # Provide a minimum size and allow the editor to expand
        self.root.minsize(1200, 800)
        self.frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.frame.pack(expand=True, fill="both", padx=10, pady=10)
        # Allow widgets inside the frame to expand properly
        for i in range(6):
            self.frame.columnconfigure(i, weight=1)
        self.frame.rowconfigure(2, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        logo_img = load_rgba_image(logo_path) if os.path.exists(logo_path) else None
        if logo_img:
            logo_img.thumbnail((200, 80))
            self.logo_photo = _create_image(logo_img)
        else:
            self.logo_photo = None
        self.logo_label = ctk.CTkLabel(
            self.frame,
            image=self.logo_photo,
            text="",
        )
        self.logo_label.grid(row=0, column=0, columnspan=6, pady=(0, 10))

        # label for the upcoming warehouse code
        self.location_label = ctk.CTkLabel(self.frame, text="", text_color=TEXT_COLOR)
        self.location_label.grid(row=1, column=0, columnspan=6, pady=(0, 10))


        # Bottom frame for action buttons
        self.button_frame = tk.Frame(
            self.frame, bg=self.root.cget("background")
        )
        # Do not stretch the button frame so that buttons remain centered
        self.button_frame.grid(row=15, column=0, columnspan=6, pady=10)

        self.end_button = self.create_button(
            self.button_frame,
            text="Zakończ i zapisz",
            command=self.export_csv,
            fg_color=SAVE_BUTTON_COLOR,
        )
        self.end_button.pack(side="left", padx=5)

        self.back_button = self.create_button(
            self.button_frame,
            text="Powrót",
            command=self.back_to_welcome,
            fg_color=NAV_BUTTON_COLOR,
        )
        self.back_button.pack(side="left", padx=5)

        # Navigation buttons to move between loaded scans
        self.prev_button = self.create_button(
            self.button_frame,
            text="\u23ee Poprzednia",
            command=self.previous_card,
            fg_color=NAV_BUTTON_COLOR,
        )
        self.prev_button.pack(side="left", padx=5)

        self.next_button = self.create_button(
            self.button_frame,
            text="Nast\u0119pna \u23ed",
            command=self.next_card,
            fg_color=NAV_BUTTON_COLOR,
        )
        self.next_button.pack(side="left", padx=5)

        self.cheat_button = self.create_button(
            self.button_frame,
            text="\U0001F9FE \u015aci\u0105ga",
            command=self.toggle_cheatsheet,
            fg_color=NAV_BUTTON_COLOR,
        )
        self.cheat_button.pack(side="left", padx=5)

        # Keep a constant label size so the window does not resize when
        # scans of different dimensions are displayed
        self.image_label = ctk.CTkLabel(self.frame, width=400, height=560)
        self.image_label.grid(row=2, column=0, rowspan=12, sticky="nsew")
        self.image_label.grid_propagate(False)
        # Progress indicator below the card image
        self.progress_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.progress_frame.grid(row=14, column=0, pady=5, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.pack(fill="x")
        # optional textual progress display
        self.progress_label = ctk.CTkLabel(self.progress_frame, textvariable=self.progress_var)
        self.progress_label.pack()

        # Container for card information fields
        self.info_frame = ctk.CTkFrame(self.frame)
        self.info_frame.grid(
            row=2, column=1, columnspan=4, rowspan=12, padx=10, sticky="nsew"
        )
        ctk.CTkLabel(self.info_frame, text="Informacje o karcie").grid(row=0, column=0, columnspan=8, pady=(0,5))
        start_row = 1
        for i in range(8):
            self.info_frame.columnconfigure(i, weight=1)

        self.entries = {}

        grid_opts = {"padx": 5, "pady": 2}

        tk.Label(
            self.info_frame, text="Język", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row, column=0, sticky="w", **grid_opts
        )
        self.lang_var = tk.StringVar(value="ENG")
        self.entries["język"] = self.lang_var
        lang_dropdown = ctk.CTkComboBox(
            self.info_frame, values=["ENG", "JP"], variable=self.lang_var, width=200
        )
        lang_dropdown.grid(row=start_row, column=1, sticky="ew", **grid_opts)
        lang_dropdown.bind("<<ComboboxSelected>>", self.update_set_options)

        tk.Label(
            self.info_frame, text="Nazwa", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 1, column=0, sticky="w", **grid_opts
        )
        self.entries["nazwa"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Nazwa"
        )
        self.entries["nazwa"].grid(row=start_row + 1, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Numer", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 2, column=0, sticky="w", **grid_opts
        )
        self.entries["numer"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Numer"
        )
        self.entries["numer"].grid(row=start_row + 2, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Era", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(row=start_row + 3, column=0, sticky="w", **grid_opts)
        self.era_var = tk.StringVar()
        self.era_dropdown = ctk.CTkComboBox(
            self.info_frame,
            values=list(tcg_sets_eng_by_era.keys()),
            variable=self.era_var,
            width=200,
        )
        self.era_dropdown.grid(row=start_row + 3, column=1, sticky="ew", **grid_opts)
        self.era_dropdown.bind("<<ComboboxSelected>>", self.update_set_options)
        self.entries["era"] = self.era_var

        tk.Label(
            self.info_frame, text="Set", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 4, column=0, sticky="w", **grid_opts
        )
        self.set_var = tk.StringVar()
        self.set_dropdown = ctk.CTkComboBox(
            self.info_frame, variable=self.set_var, width=20
        )
        self.set_dropdown.grid(row=start_row + 4, column=1, sticky="ew", **grid_opts)
        self.set_dropdown.bind("<KeyRelease>", self.filter_sets)
        self.set_dropdown.bind("<Tab>", self.autocomplete_set)
        self.entries["set"] = self.set_var

        tk.Label(
            self.info_frame, text="Typ", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 5, column=0, sticky="w", **grid_opts
        )
        self.type_vars = {}
        self.type_frame = ctk.CTkFrame(self.info_frame)
        self.type_frame.grid(row=start_row + 5, column=1, columnspan=7, sticky="w", **grid_opts)
        types = ["Common", "Holo", "Reverse"]
        for t in types:
            var = tk.BooleanVar()
            self.type_vars[t] = var
            ctk.CTkCheckBox(
                self.type_frame,
                text=t,
                variable=var,
            ).pack(side="left", padx=2)

        tk.Label(
            self.info_frame, text="Stan", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 6, column=0, sticky="w", **grid_opts
        )
        self.stan_var = tk.StringVar(value="NM")
        self.entries["stan"] = self.stan_var
        stan_dropdown = ctk.CTkComboBox(
            self.info_frame,
            variable=self.stan_var,
            values=["NM", "LP", "PL", "MP", "HP", "DMG"],
            width=20,
        )
        stan_dropdown.grid(row=start_row + 6, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Cena", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 7, column=0, sticky="w", **grid_opts
        )
        self.entries["cena"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Cena"
        )
        self.entries["cena"].grid(row=start_row + 7, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="PSA 10", bg=FIELD_BG_COLOR, fg=TEXT_COLOR
        ).grid(
            row=start_row + 8, column=0, sticky="w", **grid_opts
        )
        self.entries["psa10_price"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="PSA 10"
        )
        self.entries["psa10_price"].grid(
            row=start_row + 8, column=1, sticky="ew", **grid_opts
        )

        self.api_button = self.create_button(
            self.info_frame,
            text="Pobierz cenę",
            command=self.fetch_card_data,
            fg_color=FETCH_BUTTON_COLOR,
            width=120,
        )
        self.api_button.grid(row=start_row + 8, column=0, columnspan=1, sticky="ew", **grid_opts)

        self.cardmarket_button = self.create_button(
            self.info_frame,
            text="Cardmarket",
            command=self.open_cardmarket_search,
            fg_color=FETCH_BUTTON_COLOR,
        )
        self.cardmarket_button.grid(
            row=start_row + 8, column=4, columnspan=2, sticky="ew", **grid_opts
        )

        self.save_button = self.create_button(
            self.info_frame,
            text="Zapisz i dalej",
            command=self.save_and_next,
            fg_color=SAVE_BUTTON_COLOR,
            width=120,
        )
        self.save_button.grid(row=start_row + 9, column=0, columnspan=1, sticky="ew", **grid_opts)

        self.eur_entry = ctk.CTkEntry(
            self.info_frame, width=120, placeholder_text="Kwota w EUR"
        )
        self.eur_entry.grid(
            row=start_row + 10, column=0, columnspan=2, sticky="ew", **grid_opts
        )

        self.convert_button = self.create_button(
            self.info_frame,
            text="Przelicz",
            command=self.convert_eur_to_pln,
            fg_color=FETCH_BUTTON_COLOR,
        )
        self.convert_button.grid(
            row=start_row + 10, column=2, columnspan=2, sticky="ew", **grid_opts
        )

        self.pln_result_label = ctk.CTkLabel(self.info_frame, text="PLN: -")
        self.pln_result_label.grid(
            row=start_row + 11, column=0, columnspan=4, sticky="ew", **grid_opts
        )

        self.eur_entry.bind("<Return>", self.convert_eur_to_pln)

        for entry in self.entries.values():
            if isinstance(entry, (tk.Entry, ctk.CTkEntry)):
                entry.bind("<Return>", lambda e: self.save_and_next())

        self.root.bind("<Return>", lambda e: self.save_and_next())
        self.update_set_options()

        self.log_widget = tk.Text(
            self.frame,
            height=4,
            state="disabled",
            bg=self.root.cget("background"),
            fg="white",
        )
        self.log_widget.grid(row=16, column=0, columnspan=6, sticky="ew")

    def update_set_options(self, event=None):
        lang = self.lang_var.get().strip().upper()
        era = self.era_var.get().strip()
        if lang == "JP":
            self.sets_file = "tcg_sets_jp.json"
            sets_by_era = tcg_sets_jp_by_era
        else:
            self.sets_file = "tcg_sets.json"
            sets_by_era = tcg_sets_eng_by_era

        if era and era in sets_by_era:
            values = [item["name"] for item in sets_by_era[era]]
        else:
            values = [item["name"] for sets in sets_by_era.values() for item in sets]

        self.set_dropdown.configure(values=values)
        if getattr(self, "cheat_frame", None) is not None:
            self.create_cheat_frame()

    def filter_sets(self, event=None):
        typed = self.set_var.get().strip().lower()
        lang = self.lang_var.get().strip().upper()
        era = self.era_var.get().strip()
        if lang == "JP":
            sets_by_era = tcg_sets_jp_by_era
            name_list_all = tcg_sets_jp
            code_map_all = tcg_sets_jp_code_map
            abbr_map_all = tcg_sets_jp_abbr_name_map
        else:
            sets_by_era = tcg_sets_eng_by_era
            name_list_all = tcg_sets_eng
            code_map_all = tcg_sets_eng_code_map
            abbr_map_all = tcg_sets_eng_abbr_name_map

        if era and era in sets_by_era:
            name_list = [item["name"] for item in sets_by_era[era]]
            code_map = {item["code"]: item["name"] for item in sets_by_era[era]}
            abbr_map = {
                item["abbr"]: item["name"]
                for item in sets_by_era[era]
                if "abbr" in item
            }
        else:
            name_list = name_list_all
            code_map = code_map_all
            abbr_map = abbr_map_all

        search_map = {n.lower(): n for n in name_list}
        search_map.update({c.lower(): n for c, n in code_map.items()})
        search_map.update({a.lower(): n for a, n in abbr_map.items()})

        if typed:
            matches = [search_map[k] for k in search_map if typed in k]
            if not matches:
                close = difflib.get_close_matches(typed, search_map.keys(), n=10, cutoff=0.6)
                matches = [search_map[k] for k in close]
            filtered = []
            seen = set()
            for name in matches:
                if name not in seen:
                    filtered.append(name)
                    seen.add(name)
        else:
            filtered = name_list
        self.set_dropdown.configure(values=filtered)

    def autocomplete_set(self, event=None):
        typed = self.set_var.get().strip().lower()
        lang = self.lang_var.get().strip().upper()
        era = self.era_var.get().strip()
        if lang == "JP":
            sets_by_era = tcg_sets_jp_by_era
            code_map_all = tcg_sets_jp_code_map
            abbr_map_all = tcg_sets_jp_abbr_name_map
            name_list_all = tcg_sets_jp
        else:
            sets_by_era = tcg_sets_eng_by_era
            code_map_all = tcg_sets_eng_code_map
            abbr_map_all = tcg_sets_eng_abbr_name_map
            name_list_all = tcg_sets_eng

        if era and era in sets_by_era:
            name_list = [item["name"] for item in sets_by_era[era]]
            code_map = {item["code"]: item["name"] for item in sets_by_era[era]}
            abbr_map = {
                item.get("abbr"): item["name"]
                for item in sets_by_era[era]
                if "abbr" in item
            }
        else:
            name_list = name_list_all
            code_map = code_map_all
            abbr_map = abbr_map_all

        name = None
        if typed in code_map:
            name = code_map[typed]
        elif typed in abbr_map:
            name = abbr_map[typed]
        else:
            search_map = {n.lower(): n for n in name_list}
            search_map.update({c.lower(): n for c, n in code_map.items()})
            search_map.update({a.lower(): n for a, n in abbr_map.items()})
            close = difflib.get_close_matches(typed, search_map.keys(), n=1, cutoff=0.6)
            if close:
                name = search_map[close[0]]
        if name:
            self.set_var.set(name)
        event.widget.tk_focusNext().focus()
        return "break"

    def convert_eur_to_pln(self, event=None):
        eur_text = self.eur_entry.get().strip()
        try:
            eur = float(eur_text)
        except ValueError:
            self.pln_result_label.configure(text="Błąd")
            return "break"
        rate = self.get_exchange_rate()
        pln = eur * rate * PRICE_MULTIPLIER
        self.pln_result_label.configure(text=f"PLN: {pln:.2f}")
        return "break"

    def create_cheat_frame(self, show_headers: bool = True):
        """Create or refresh the cheatsheet frame with set logos."""
        if self.cheat_frame is not None:
            self.cheat_frame.destroy()
        self.cheat_frame = ctk.CTkScrollableFrame(
            self.frame,
            fg_color=self.root.cget("background"),
            width=240,
        )
        self.cheat_frame.grid(row=2, column=5, rowspan=12, sticky="nsew")

        lang = self.lang_var.get().strip().upper()
        sets_by_era = (
            tcg_sets_jp_by_era if lang == "JP" else tcg_sets_eng_by_era
        )

        row = 0
        for era, sets in sets_by_era.items():
            if show_headers:
                ctk.CTkLabel(
                    self.cheat_frame,
                    text=era,
                    font=("Segoe UI", 12, "bold"),
                ).grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=4)
                row += 1
            for item in sets:
                name = item["name"]
                code = item["code"]
                img = self.set_logos.get(code)
                if img:
                    ctk.CTkLabel(
                        self.cheat_frame,
                        image=img,
                        text="",
                    ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
                else:
                    ctk.CTkLabel(
                        self.cheat_frame,
                        text="",
                        width=2,
                    ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
                ctk.CTkLabel(
                    self.cheat_frame,
                    text=f"{name} ({code})",
                ).grid(row=row, column=1, sticky="w", padx=5, pady=2)
                row += 1

    def toggle_cheatsheet(self):
        """Show or hide the cheatsheet with set logos."""
        if self.cheat_frame is None:
            self.create_cheat_frame()
            return
        if self.cheat_frame.winfo_ismapped():
            self.cheat_frame.grid_remove()
        else:
            self.cheat_frame.grid()

    def start_browse_scans(self):
        """Wrapper for 'Dalej' button that closes the location frame."""
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        self.browse_scans()

    def browse_scans(self):
        """Ask for a folder and load scans starting from the entered location."""
        try:
            box = int(self.start_box_var.get())
            column = int(self.start_col_var.get())
            pos = int(self.start_pos_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Błąd", "Podaj poprawne wartości liczbowe")
            return

        if box not in {*range(1, BOX_COUNT + 1), SPECIAL_BOX_NUMBER}:
            messagebox.showerror(
                "Błąd", f"Box musi być w zakresie 1-{BOX_COUNT} lub {SPECIAL_BOX_NUMBER}"
            )
            return

        if box == SPECIAL_BOX_NUMBER:
            if column != 1 or not (1 <= pos <= SPECIAL_BOX_CAPACITY):
                messagebox.showerror(
                    "Błąd",
                    f"Dla boxu {SPECIAL_BOX_NUMBER} kolumna musi być 1, pozycja 1-{SPECIAL_BOX_CAPACITY}",
                )
                return
            self.starting_idx = BOX_COUNT * BOX_CAPACITY + (pos - 1)
        else:
            if not (1 <= column <= GRID_COLUMNS and 1 <= pos <= BOX_COLUMN_CAPACITY):
                messagebox.showerror(
                    "Błąd",
                    f"Podaj poprawne wartości (kolumna 1-{GRID_COLUMNS}, pozycja 1-{BOX_COLUMN_CAPACITY})",
                )
                return
            self.starting_idx = (
                (box - 1) * BOX_CAPACITY + (column - 1) * BOX_COLUMN_CAPACITY + (pos - 1)
            )
        folder = self.scan_folder_var.get().strip()
        if not folder:
            folder = filedialog.askdirectory()
            if not folder:
                return
            self.scan_folder_var.set(folder)
        csv_path = getattr(self, "session_csv_path", None)
        if not csv_path:
            try:
                csv_path = filedialog.asksaveasfilename(
                    defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
                )
            except tk.TclError:  # no display
                csv_path = os.path.join(folder, "session.csv")
            if not csv_path:
                return
            self.session_csv_path = csv_path
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=csv_utils.STORE_FIELDNAMES, delimiter=";"
                )
                writer.writeheader()
        self.in_scan = True
        CardEditorApp.load_images(self, folder)

    def load_images(self, folder):
        self.in_scan = True
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "frame", None) is None:
            self.setup_editor_ui()
        self.folder_path = folder
        self.folder_name = os.path.basename(folder)
        self.cards = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith((".jpg", ".png"))
        ]
        self.cards.sort()
        self.index = 0
        self.output_data = [None] * len(self.cards)
        self.card_counts = defaultdict(int)
        self.failed_cards = []
        total = len(self.cards)
        self.progress_var.set(f"0/{total} (0%)")
        self.log(f"Loaded {len(self.cards)} cards")
        self.show_card()

    def show_card(self):
        progress_cb = getattr(self, "_update_card_progress", None)
        if progress_cb:
            progress_cb(0, show=True)
        if self.index >= len(self.cards):
            if getattr(self, "failed_cards", None):
                msg = "Failed to load images:\n" + "\n".join(self.failed_cards)
                print(msg, file=sys.stderr)
                try:
                    messagebox.showerror("Errors", msg)
                except tk.TclError:
                    pass
            messagebox.showinfo("Koniec", "Wszystkie karty zostały zapisane.")
            self.export_csv()
            return

        total = len(self.cards) or 1
        percent = int((self.index + 1) / total * 100)
        self.progress_var.set(f"{self.index + 1}/{len(self.cards)} ({percent}%)")

        image_path = self.cards[self.index]
        filename = os.path.basename(image_path)
        self.current_image_path = image_path
        self.current_fingerprint = None
        self.current_location = ""
        cache_key = self.file_to_key.get(filename)
        if not cache_key:
            cache_key = self._guess_key_from_filename(image_path)
        inv_entry = self.lookup_inventory_entry(cache_key) if cache_key else None
        image = load_rgba_image(image_path)
        if image is None:
            print(f"Failed to load image {image_path}", file=sys.stderr)
            if getattr(self, "failed_cards", None) is not None:
                self.failed_cards.append(image_path)
            self.index += 1
            self.show_card()
            return
        image.thumbnail((400, 560))
        self.current_card_image = image.copy()
        img = _create_image(image)
        self.image_objects.append(img)
        self.image_objects = self.image_objects[-2:]
        self.current_card_photo = img
        self.image_label.configure(image=img)
        if hasattr(self, "location_label"):
            try:
                self.location_label.configure(text=self.next_free_location())
            except storage.NoFreeLocationError:
                try:
                    messagebox.showerror("Błąd", "Brak wolnych miejsc w magazynie")
                except tk.TclError:
                    pass
                self.location_label.configure(text="")

        for key, entry in list(self.entries.items()):
            if hasattr(entry, "winfo_exists"):
                try:
                    if not entry.winfo_exists():
                        self.entries.pop(key, None)
                        continue
                except tk.TclError:
                    self.entries.pop(key, None)
                    continue
            try:
                tk_entry_cls = getattr(tk, "Entry", None)
                ctk_entry_cls = getattr(ctk, "CTkEntry", None)
                entry_types = tuple(
                    t for t in (tk_entry_cls, ctk_entry_cls) if isinstance(t, type)
                )
                if entry_types and isinstance(entry, entry_types):
                    entry.delete(0, tk.END)
                elif isinstance(tk.StringVar, type) and isinstance(entry, tk.StringVar):
                    if key == "język":
                        entry.set("ENG")
                    elif key == "stan":
                        entry.set("NM")
                    else:
                        entry.set("")
                else:
                    bool_var_cls = getattr(tk, "BooleanVar", None)
                    if isinstance(bool_var_cls, type) and isinstance(entry, bool_var_cls):
                        entry.set(False)
            except tk.TclError:
                self.entries.pop(key, None)

        for var in self.type_vars.values():
            var.set(False)

        skip_analysis = False
        self.selected_candidate_meta = None
        if cache_key and cache_key in self.card_cache:
            cached = self.card_cache[cache_key]
            for field, value in cached.get("entries", {}).items():
                entry = self.entries.get(field)
                if isinstance(entry, (tk.Entry, ctk.CTkEntry)):
                    if field == "numer":
                        value = sanitize_number(str(value))
                    entry.insert(0, value)
                elif isinstance(entry, tk.StringVar):
                    entry.set(value)
            for name, val in cached.get("types", {}).items():
                if name in self.type_vars:
                    self.type_vars[name].set(val)
            self.update_set_options()

        elif inv_entry:
            self.entries["nazwa"].insert(0, inv_entry.get("nazwa", ""))
            self.entries["numer"].insert(
                0, sanitize_number(str(inv_entry.get("numer", "")))
            )
            self.entries["set"].set(inv_entry.get("set", ""))
            self.entries["era"].set(inv_entry.get("era", ""))
            self.update_set_options()
            skip_analysis = True
            logger.info(
                "Skipping analysis for %s: inventory entry found for key %s",
                filename,
                cache_key,
            )

        folder = os.path.basename(os.path.dirname(image_path))
        progress_cb = getattr(self, "_update_card_progress", None)

        fp_match = None
        if (
            not skip_analysis
            and getattr(self, "hash_db", None)
            and getattr(self, "auto_lookup", False)
        ):
            try:
                with Image.open(image_path) as img_fp:
                    try:
                        fp = compute_fingerprint(img_fp, use_orb=True)
                    except TypeError:
                        fp = compute_fingerprint(img_fp)
                self.current_fingerprint = fp
                lookup = getattr(self, "_lookup_fp_candidate", None)
                if lookup:
                    fp_match = lookup(fp)
                else:
                    fp_match = getattr(self.hash_db, "best_match", lambda *a, **k: None)(
                        fp, max_distance=HASH_MATCH_THRESHOLD
                    )
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                logger.warning("Fingerprint lookup failed for %s: %s", image_path, exc)
                fp_match = None
            if fp_match:
                meta = fp_match.meta
                self.selected_candidate_meta = meta
                csv_row = None
                code = meta.get("warehouse_code")
                if code:
                    csv_row = csv_utils.get_row_by_code(code)
                    self.current_location = code
                    if hasattr(self, "location_label"):
                        self.location_label.configure(text=code)
                if csv_row:
                    name = csv_row.get("name", "")
                    number = sanitize_number(str(csv_row.get("number", "")))
                    set_name = csv_row.get("set", "")
                else:
                    name = meta.get("nazwa", meta.get("name", ""))
                    number = sanitize_number(
                        str(meta.get("numer", meta.get("number", "")))
                    )
                    set_name = meta.get("set", meta.get("set_name", ""))
                variant = (
                    csv_row.get("variant")
                    if csv_row
                    else meta.get("wariant") or meta.get("variant")
                )
                duplicates = csv_utils.find_duplicates(
                    name, number, set_name, variant
                )
                if duplicates:
                    codes = ", ".join(
                        [d.get("warehouse_code", "") for d in duplicates if d.get("warehouse_code")]
                    )
                    msg = _(
                        "Card already exists in magazyn: {codes}. Add anyway?"
                    ).format(codes=codes)
                    if not messagebox.askyesno(_("Duplicate"), msg):
                        logger.info(
                            "Skipping duplicate card %s #%s in set %s", name, number, set_name
                        )
                        fp_match = None
                        skip_analysis = False
                    else:
                        self.current_location = self.next_free_location()
                        if hasattr(self, "location_label"):
                            self.location_label.configure(text=self.current_location)
                        logger.info(
                            "Assigned storage location %s to duplicate card", self.current_location
                        )
                if fp_match:
                    self.entries["nazwa"].delete(0, tk.END)
                    self.entries["numer"].delete(0, tk.END)
                    self.entries["nazwa"].insert(0, name)
                    self.entries["numer"].insert(0, number)
                    self.entries["set"].set("")
                    self.entries["set"].set(set_name)
                    era_name = get_set_era(set_name)
                    self.entries["era"].set(era_name)
                    cena = getattr(
                        self, "get_price_from_db", lambda *a, **k: None
                    )(name, number, set_name)
                    if cena is None:
                        cena = getattr(
                            self, "fetch_card_price", lambda *a, **k: None
                        )(name, number, set_name)
                    if cena is not None:
                        self.entries["cena"].delete(0, tk.END)
                        self.entries["cena"].insert(0, str(cena))
                        is_rev = getattr(self, "price_reverse_var", None)
                        price = self.apply_variant_multiplier(
                            cena, is_reverse=is_rev.get() if is_rev else False
                        )
                        try:
                            self.price_pool_total += float(price)
                        except (TypeError, ValueError):
                            pass
                        if getattr(self, "pool_total_label", None):
                            self.pool_total_label.config(
                                text=f"Suma puli: {self.price_pool_total:.2f}"
                            )
                    if isinstance(meta.get("typ"), str):
                        for name in meta["typ"].split(","):
                            name = name.strip()
                            if name in self.type_vars:
                                self.type_vars[name].set(True)
                    self.update_set_options()
                    skip_analysis = True
                    logger.info(
                        "Skipping analysis for %s: fingerprint match with distance %s",
                        filename,
                        fp_match.distance,
                    )
                    if progress_cb:
                        progress_cb(1.0)

        if not skip_analysis:
            if progress_cb:
                progress_cb(0, show=True)
            thread = threading.Thread(
                target=self._analyze_and_fill,
                args=(image_path, self.index),
                daemon=True,
            )
            self.current_analysis_thread = thread
            for btn_name in ("save_button", "next_button"):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    try:
                        btn.configure(state=tk.NORMAL)
                    except Exception:
                        pass
            thread.start()

        if getattr(self, "current_analysis_thread", None) is None:
            for btn_name in ("save_button", "next_button"):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    try:
                        btn.configure(state=tk.NORMAL)
                    except Exception:
                        pass

        # focus the name entry so the user can start typing immediately
        self.entries["nazwa"].focus_set()

    def _guess_key_from_filename(self, path: str):
        base = os.path.splitext(os.path.basename(path))[0]
        parts = re.split(r"[|_-]", base)
        if len(parts) >= 3:
            name = parts[0]
            number = parts[1]
            set_name = "_".join(parts[2:])
            return f"{name}|{number}|{set_name}|"
        return None

    def _update_card_progress(self, value: float, show: bool = False):
        """Update the progress bar for analyzing a single card."""
        if not hasattr(self, "progress_bar"):
            return
        try:
            self.progress_bar.set(value)
            if show and hasattr(self, "progress_frame"):
                self.progress_frame.grid()
        except tk.TclError:
            pass

    def _show_candidates_dialog(self, candidates: list[Candidate]) -> Optional[Candidate]:
        """Present a dialog allowing the user to choose from *candidates*."""

        if not candidates:
            return None

        selection: dict[str, Optional[Candidate]] = {"candidate": None}
        event = threading.Event()

        def _ask_user():
            dialog = ctk.CTkToplevel(self.root)
            dialog.title(_("Possible duplicates"))

            radio_var = tk.IntVar(value=-1)

            frame = ctk.CTkScrollableFrame(dialog)
            frame.pack(fill="both", expand=True, padx=10, pady=10)

            for idx, cand in enumerate(candidates):
                code = cand.meta.get("warehouse_code", "")
                ctk.CTkRadioButton(
                    frame,
                    text=f"{code} (d={cand.distance})",
                    variable=radio_var,
                    value=idx,
                ).pack(anchor="w")

            def _select():
                sel = radio_var.get()
                if sel >= 0:
                    selection["candidate"] = candidates[sel]
                dialog.destroy()

            def _cancel():
                dialog.destroy()

            btn_frame = ctk.CTkFrame(dialog)
            btn_frame.pack(fill="x", padx=10, pady=5)
            ctk.CTkButton(
                btn_frame, text=_("Select"), command=_select, fg_color=SAVE_BUTTON_COLOR
            ).pack(side="left", expand=True)
            ctk.CTkButton(
                btn_frame, text=_("Skip"), command=_cancel, fg_color=NAV_BUTTON_COLOR
            ).pack(side="right", expand=True)

            dialog.transient(self.root)
            dialog.grab_set()
            self.root.wait_window(dialog)
            event.set()

        if threading.current_thread() is threading.main_thread():
            _ask_user()
        else:
            self.root.after(0, _ask_user)
            event.wait()

        return selection["candidate"]

    def _lookup_fp_candidate(self, fp) -> Optional[Candidate]:
        """Return candidate chosen by the user for the fingerprint ``fp``."""

        if not getattr(self, "hash_db", None):
            return None
        try:
            best = self.hash_db.best_match(fp, max_distance=HASH_MATCH_THRESHOLD)
            if not best:
                return None
            candidates = self.hash_db.candidates(
                fp, limit=5, max_distance=HASH_MATCH_THRESHOLD
            )
        except Exception as exc:
            logger.warning("Fingerprint lookup failed: %s", exc)
            return None
        candidates = [c for c in candidates if c.distance <= HASH_MATCH_THRESHOLD]
        if not candidates:
            return None
        return self._show_candidates_dialog(candidates)

    def update_set_area_preview(self, rect, image):
        """Overlay ``rect`` on ``image`` and display it on ``image_label``."""
        if not rect or image is None:
            return
        try:
            # determine dimensions of the image used for analysis
            with Image.open(getattr(self, "current_image_path", "")) as im:
                orig_w, orig_h = im.size
        except (OSError, UnidentifiedImageError):
            orig_w, orig_h = image.size

        orientation = getattr(self, "_analysis_orientation", 0)
        if orientation == 90:
            base_w, base_h = orig_h, orig_w
        else:
            base_w, base_h = orig_w, orig_h

        disp_w, disp_h = image.size
        scale_x = disp_w / base_w if base_w else 1
        scale_y = disp_h / base_h if base_h else 1
        scaled_rect = (
            int(rect[0] * scale_x),
            int(rect[1] * scale_y),
            int(rect[2] * scale_x),
            int(rect[3] * scale_y),
        )

        if getattr(self, "_preview_source_image", None) is not image:
            self._preview_source_image = image
            self._preview_base_image = image.copy()
        preview = self._preview_base_image.copy()
        draw = ImageDraw.Draw(preview)
        draw.rectangle(scaled_rect, outline="red", width=3)

        img = _create_image(preview)
        self.current_card_photo = img
        self.image_label.configure(image=img)

    def _analyze_and_fill(self, path, idx):
        lang_var = getattr(self, "lang_var", None)
        translate = False
        if lang_var is not None:
            try:
                translate = lang_var.get() == "JP"
            except tk.TclError:
                translate = False
        update_progress = getattr(self, "_update_card_progress", None)
        if update_progress:
            self.root.after(0, lambda: update_progress(0, show=True))
        fp_match = None
        if getattr(self, "hash_db", None) and getattr(self, "auto_lookup", False):
            try:
                with Image.open(path) as img:
                    try:
                        fp = compute_fingerprint(img, use_orb=True)
                    except TypeError:
                        fp = compute_fingerprint(img)
                self.current_fingerprint = fp
                lookup = getattr(self, "_lookup_fp_candidate", None)
                if lookup:
                    fp_match = lookup(fp)
                    if fp_match:
                        self.selected_candidate_meta = fp_match.meta
                else:
                    fp_match = getattr(self.hash_db, "best_match", lambda *a, **k: None)(
                        fp, max_distance=HASH_MATCH_THRESHOLD
                    )
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                logger.warning("Fingerprint lookup failed for %s: %s", path, exc)
                fp_match = None
        if update_progress:
            self.root.after(0, lambda: update_progress(0.5))

        if fp_match:
            meta = fp_match.meta
            csv_row = None
            code = meta.get("warehouse_code")
            if code:
                csv_row = csv_utils.get_row_by_code(code)
            if csv_row:
                result = {
                    "name": csv_row.get("name", ""),
                    "number": sanitize_number(str(csv_row.get("number", ""))),
                    "total": meta.get("total", ""),
                    "set": csv_row.get("set", ""),
                    "set_code": meta.get("set_code", ""),
                    "orientation": 0,
                    "set_format": meta.get("set_format", ""),
                    "variant": csv_row.get("variant"),
                    "price": csv_row.get("price"),
                    "era": get_set_era(csv_row.get("set", "")),
                    "warehouse_code": code,
                }
            else:
                result = {
                    "name": meta.get("nazwa", meta.get("name", "")),
                    "number": meta.get("numer", meta.get("number", "")),
                    "total": meta.get("total", ""),
                    "set": meta.get("set", meta.get("set_name", "")),
                    "set_code": meta.get("set_code", ""),
                    "orientation": 0,
                    "set_format": meta.get("set_format", ""),
                    "variant": meta.get("wariant") or meta.get("variant"),
                    "warehouse_code": code,
                }
        else:
            result = analyze_card_image(
                path,
                translate_name=translate,
                debug=True,
                preview_cb=getattr(self, "update_set_area_preview", None),
                preview_image=getattr(self, "current_card_image", None),
            )
        product_code = csv_utils.build_product_code(
            result.get("set", ""),
            result.get("number", ""),
            result.get("variant"),
        )
        result["product_code"] = product_code
        store_row = getattr(self, "store_data", {}).get(product_code)
        if store_row:
            result.update(store_row)
            cat = store_row.get("category", "")
            parts = [p.strip() for p in cat.split(">")]
            if len(parts) >= 2:
                result["era"] = parts[1]
        if update_progress:
            self.root.after(0, lambda: update_progress(1.0))

        self.root.after(0, lambda: self._apply_analysis_result(result, idx))

    def _apply_analysis_result(self, result, idx):
        if idx != self.index:
            return
        progress_cb = getattr(self, "_update_card_progress", None)
        if progress_cb:
            progress_cb(1.0)
        if result:
            name = result.get("name", "")
            number = result.get("number", "")
            total = result.get("total") or ""
            if not total and isinstance(number, str):
                m = re.match(r"(\d+)\s*/\s*(\d+)", number)
                if m:
                    number, total = m.group(1), m.group(2)
            set_name = result.get("set", "")
            era_name = result.get("era", "") or get_set_era(set_name)
            price = result.get("price")
            number = sanitize_number(str(number))
            self.entries["nazwa"].delete(0, tk.END)
            self.entries["nazwa"].insert(0, name)
            self.entries["numer"].delete(0, tk.END)
            self.entries["numer"].insert(0, number)
            self.entries["era"].set(era_name)
            if price is not None:
                price_entry = self.entries.get("cena")
                if price_entry is not None:
                    price_entry.delete(0, tk.END)
                    price_entry.insert(0, price)
            self.update_set_options()
            self.entries["set"].set(set_name)

            code = result.get("warehouse_code")
            if code:
                self.current_location = code
                if hasattr(self, "location_label"):
                    self.location_label.configure(text=code)

            variant = result.get("variant")
            duplicates = csv_utils.find_duplicates(
                name, number, set_name, variant
            )
            if duplicates:
                codes = ", ".join(
                    [d.get("warehouse_code", "") for d in duplicates if d.get("warehouse_code")]
                )
                msg = _("Card already exists in magazyn: {codes}. Add anyway?").format(
                    codes=codes
                )
                if not messagebox.askyesno(_("Duplicate"), msg):
                    logger.info(
                        "Skipping duplicate card %s #%s in set %s", name, number, set_name
                    )
                    if progress_cb:
                        progress_cb(1.0)
                    self.current_analysis_thread = None
                    return
                self.current_location = self.next_free_location()
                if hasattr(self, "location_label"):
                    self.location_label.configure(text=self.current_location)
                logger.info(
                    "Assigned storage location %s to duplicate card", self.current_location
                )
            rect = result.get("rect")
            self._analysis_orientation = result.get("orientation", 0)
            if rect and hasattr(self, "current_card_image"):
                try:
                    self.update_set_area_preview(rect, self.current_card_image)
                except Exception:
                    logger.exception("Failed to update set area preview")
        for btn_name in ("save_button", "next_button"):
            btn = getattr(self, btn_name, None)
            if btn is not None:
                try:
                    btn.configure(state=tk.NORMAL)
                except Exception:
                    pass
        self.current_analysis_thread = None
        return

    def generate_location(self, idx):
        return storage.generate_location(idx)

    def next_free_location(self):
        """Return the next unused warehouse_code."""
        return storage.next_free_location(self)

    def load_price_db(self):
        if not os.path.exists(PRICE_DB_PATH):
            return []
        with open(PRICE_DB_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def load_set_logos(self):
        """Load set logos from SET_LOGO_DIR into self.set_logos."""
        self.set_logos.clear()
        if not os.path.isdir(SET_LOGO_DIR):
            return
        for file in os.listdir(SET_LOGO_DIR):
            path = os.path.join(SET_LOGO_DIR, file)
            if not os.path.isfile(path):
                continue
            if not file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                continue
            code = os.path.splitext(file)[0]
            if ALLOWED_SET_CODES and code not in ALLOWED_SET_CODES:
                continue
            img = load_rgba_image(path)
            if not img:
                continue
            img.thumbnail((40, 40))
            self.set_logos[code] = _create_image(img)

    def show_loading_screen(self):
        """Display a temporary loading screen during startup."""
        self.root.minsize(1200, 800)
        self.loading_frame = ctk.CTkFrame(self.root, fg_color=BG_COLOR)
        self.loading_frame.pack(expand=True, fill="both")
        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            img = load_rgba_image(logo_path)
            if img:
                img.thumbnail((300, 150))
                self.loading_logo = _create_image(img)
                ctk.CTkLabel(
                    self.loading_frame,
                    image=self.loading_logo,
                    text="",
                ).pack(pady=10)

        gif_path = os.path.join(os.path.dirname(__file__), "simple_pokeball.gif")
        if os.path.exists(gif_path):
            from PIL import ImageSequence
            with Image.open(gif_path) as img:
                img.convert("RGBA")
                self.gif_frames = []
                self.gif_durations = []
                for frame in ImageSequence.Iterator(img):
                    self.gif_frames.append(
                        _create_image(frame.convert("RGBA"))
                    )
                    self.gif_durations.append(frame.info.get("duration", 100))

            self.gif_label = ctk.CTkLabel(
                self.loading_frame, text=""
            )
            self.gif_label.pack()
            self.animate_loading_gif(0)
        self.loading_label = ctk.CTkLabel(
            self.loading_frame,
            text="Ładowanie...",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 16),
        )
        self.loading_label.pack(pady=10)
        self.root.update()

    def animate_loading_gif(self, index=0):
        """Cycle through frames of the loading GIF."""
        if not hasattr(self, "gif_frames"):
            return
        frame = self.gif_frames[index]
        self.gif_label.configure(image=frame)
        next_index = (index + 1) % len(self.gif_frames)
        delay = 100
        if hasattr(self, "gif_durations"):
            try:
                delay = self.gif_durations[index]
            except IndexError:
                pass
        self.gif_label.after(delay, self.animate_loading_gif, next_index)

    def startup_tasks(self):
        """Run initial setup tasks on the main thread."""
        last_check = storage.load_last_sets_check()
        now = datetime.datetime.now()

        def continue_startup():
            self.load_set_logos()
            self.finish_startup()

        if not last_check or last_check.year != now.year or last_check.month != now.month:
            def run_updates():
                self.update_sets()
                storage.save_last_sets_check(now)
                self.root.after(0, continue_startup)

            self.root.after(0, run_updates)
        else:
            self.root.after(0, continue_startup)

    def finish_startup(self):
        """Finalize initialization after background tasks complete."""
        if self.loading_frame is not None:
            self.loading_frame.destroy()
        self.shoper_client = None
        self.ensure_shoper_client()
        # The warehouse CSV is now bundled with the application, so no
        # network download is required during startup.
        self.setup_welcome_screen()

    def ensure_shoper_client(self):
        """Initialize ``ShoperClient`` using stored configuration.

        If configuration is missing or authentication fails, a configuration
        dialog is shown to the user.
        """
        global SHOPER_API_URL, SHOPER_API_TOKEN
        url = os.getenv("SHOPER_API_URL", "").strip()
        token = os.getenv("SHOPER_API_TOKEN", "").strip()
        if not url or not token:
            self.open_config_dialog()
            return
        try:
            client = ShoperClient(url, token)
            try:
                # perform a simple request to verify credentials
                client.get("products", params={"page": 1, "per-page": 1})
            except RuntimeError as exc:
                messagebox.showerror("Błąd", f"Autoryzacja nieudana: {exc}")
                self.open_config_dialog()
                return
            self.shoper_client = client
            SHOPER_API_URL, SHOPER_API_TOKEN = url, token
        except requests.RequestException as exc:
            messagebox.showerror("Błąd", f"Nie można połączyć się z API Shoper: {exc}")
            self.open_config_dialog()

    def download_set_symbols(self, sets):
        """Download logos for the provided set definitions."""
        os.makedirs(SET_LOGO_DIR, exist_ok=True)
        total = len(sets)
        for idx, item in enumerate(sets, start=1):
            name = item.get("name")
            code = item.get("code")
            if self.loading_label is not None:
                self.loading_label.configure(
                    text=f"Pobieram {idx}/{total}: {name}"
                )
                self.root.update()
            if not code:
                continue
            symbol_url = f"https://images.pokemontcg.io/{code}/symbol.png"
            try:
                res = requests.get(symbol_url, timeout=10)
                if res.status_code == 404:
                    alt = re.sub(r"(^sv)0(\d$)", r"\1\2", code)
                    if alt != code:
                        alt_url = f"https://images.pokemontcg.io/{alt}/symbol.png"
                        res = requests.get(alt_url, timeout=10)
                        if res.status_code == 200:
                            symbol_url = alt_url
                if res.status_code == 200:
                    parsed_path = urlparse(symbol_url).path
                    ext = os.path.splitext(parsed_path)[1] or ".png"
                    safe = code.replace("/", "_")
                    path = os.path.join(SET_LOGO_DIR, f"{safe}{ext}")
                    with open(path, "wb") as fh:
                        fh.write(res.content)
                else:
                    if res.status_code == 404:
                        print(f"[WARN] Symbol not found for {name}: {symbol_url}")
                    else:
                        print(
                            f"[ERROR] Failed to download symbol for {name} from {symbol_url}: {res.status_code}"
                        )
            except requests.RequestException as exc:
                print(f"[ERROR] {name}: {exc}")

    def update_sets(self):
        """Check remote API for new sets and update local files."""
        try:
            self.loading_label.configure(text="Sprawdzanie nowych setów...")
            self.root.update()
            with open(self.sets_file, encoding="utf-8") as f:
                current_sets = json.load(f)
        except (OSError, json.JSONDecodeError):
            current_sets = {}

        timeout = getattr(self, "API_TIMEOUT", 30)
        remote: list[dict] = []
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    "https://api.pokemontcg.io/v2/sets", timeout=timeout
                )
                resp.raise_for_status()
                remote = resp.json().get("data", [])
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        if not remote and last_exc is not None:
            self.log(f"[WARN] Using offline sets. Reason: {last_exc}")

        added = 0
        new_items = []
        existing_codes = {
            s.get("code", "").strip().lower()
            for sets in current_sets.values()
            for s in sets
        }

        for item in remote:
            series = item.get("series") or "Other"
            code = item.get("id")
            name = item.get("name")
            abbr = item.get("ptcgoCode")
            if not code or not name:
                continue
            code_key = code.strip().lower()
            if code_key in existing_codes:
                continue
            group = current_sets.setdefault(series, [])
            entry = {"name": name, "code": code}
            if abbr:
                entry["abbr"] = abbr
            group.append(entry)
            existing_codes.add(code_key)
            added += 1
            new_items.append({"name": name, "code": code})

        if added:
            with open(self.sets_file, "w", encoding="utf-8") as f:
                json.dump(current_sets, f, indent=2, ensure_ascii=False)
            reload_sets()
            refresh_logo_cache()
            names = ", ".join(item["name"] for item in new_items)
            self.loading_label.configure(
                text=f"Pobieram symbole setów 0/{added}..."
            )
            self.root.update()
            self.download_set_symbols(new_items)
            print(f"[INFO] Dodano {added} setów: {names}")

    def log(self, message: str):
        if self.log_widget:
            self.log_widget.configure(state="normal")
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state="disabled")
        print(message)

    def get_price_from_db(self, name, number, set_name):
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()

        for row in self.price_db:
            if (
                normalize(row.get("name", "")) == name_input
                and row.get("number", "").strip().lower() == number_input
                and row.get("set", "").strip().lower() == set_input
            ):
                try:
                    return float(row.get("price", 0))
                except (TypeError, ValueError):
                    return None
        return None

    def fetch_card_price(self, name, number, set_name, is_reverse=False, is_holo=False):
        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)
        full_name = get_set_name(set_code)
        if hasattr(self, "set_var"):
            try:
                self.set_var.set(full_name)
            except tk.TclError:
                pass

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_api,
                    "number": number_input,
                    "set": set_code,
                }
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.warning("API error: %s", response.status_code)
                return None

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []
            candidates = []

            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    candidates.append(card)

            if candidates:
                best = candidates[0]
                price_eur = extract_cardmarket_price(best)
                if price_eur is not None:
                    eur_pln = self.get_exchange_rate()
                    price_pln = round(float(price_eur) * eur_pln * PRICE_MULTIPLIER, 2)
                    logger.info(
                        "Cena %s (%s, %s) = %s PLN",
                        best.get('name'),
                        number_input,
                        set_input,
                        price_pln,
                    )
                    return price_pln

            logger.debug("Nie znaleziono dokładnej karty. Zbliżone:")
            for card in cards:
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()
                if number_input == card_number and set_input in card_set:
                    logger.debug(
                        "%s | %s | %s",
                        card.get('name'),
                        card_number,
                        card.get('episode', {}).get('name'),
                    )

        except requests.Timeout:
            logger.warning("Request timed out")
        except requests.RequestException as e:
            logger.warning("Fetching price from TCGGO failed: %s", e)
        except ValueError as e:
            logger.warning("Invalid JSON from TCGGO: %s", e)
        return None

    def fetch_psa10_price(self, name, number, set_name):
        """Return PSA10 price for a card converted to PLN.

        The function queries the card API similarly to ``fetch_card_price`` and
        looks up the PSA10 graded price under the
        ``prices.cardmarket.graded.psa.psa10`` path. If the nested structure or
        the value is missing at any point, an empty string is returned. The
        price is converted using the current EUR→PLN exchange rate and the
        result is formatted as an integer when possible or a float string
        otherwise.
        """

        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)
        full_name = get_set_name(set_code)
        if hasattr(self, "set_var"):
            try:
                self.set_var.set(full_name)
            except tk.TclError:
                pass

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_api,
                    "number": number_input,
                    "set": set_code,
                }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                return ""

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []

            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    try:
                        graded = (
                            card.get("prices", {})
                            .get("cardmarket", {})
                            .get("graded")
                        )
                        psa10 = None
                        if isinstance(graded, list):
                            for entry in graded:
                                if (
                                    isinstance(entry, dict)
                                    and str(entry.get("company", "")).lower() == "psa"
                                    and str(entry.get("grade", ""))
                                    .replace(" ", "")
                                    .lower()
                                    in {"psa10", "10"}
                                ):
                                    psa10 = entry.get("price")
                                    break
                        elif isinstance(graded, dict):
                            psa10 = (
                                graded.get("psa", {})
                                .get("psa10")
                            )
                        if psa10 is None:
                            return ""
                        rate = self.get_exchange_rate()
                        price_pln = round(float(psa10) * rate, 2)
                        return (
                            str(int(price_pln))
                            if price_pln.is_integer()
                            else str(price_pln)
                        )
                    except (AttributeError, TypeError, ValueError):
                        return ""
            return ""
        except requests.Timeout:
            logger.warning("Request timed out")
        except requests.RequestException as e:
            logger.warning("Fetching PSA10 price failed: %s", e)
        except ValueError as e:
            logger.warning("Invalid JSON from TCGGO: %s", e)
        return ""

    def fetch_card_variants(self, name, number, set_name):
        """Return all matching cards from the API with prices."""
        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)
        full_name = get_set_name(set_code)
        if hasattr(self, "set_var"):
            try:
                self.set_var.set(full_name)
            except tk.TclError:
                pass

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_api,
                    "number": number_input,
                    "set": set_code,
                }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.warning("API error: %s", response.status_code)
                return []

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []

            results = []
            eur_pln = self.get_exchange_rate()
            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    price_eur = extract_cardmarket_price(card)
                    price_pln = 0
                    if price_eur is not None:
                        price_pln = round(
                            float(price_eur) * eur_pln * PRICE_MULTIPLIER, 2
                        )
                    results.append(
                        {
                            "name": card.get("name"),
                            "number": card_number,
                            "set": card.get("episode", {}).get("name", ""),
                            "price": price_pln,
                        }
                    )
            return results
        except requests.Timeout:
            logger.warning("Request timed out")
        except requests.RequestException as e:
            logger.warning("Fetching variants from TCGGO failed: %s", e)
        except ValueError as e:
            logger.warning("Invalid JSON from TCGGO: %s", e)
        return []

    def lookup_card_info(self, name, number, set_name, is_holo=False, is_reverse=False):
        """Return image URL and pricing information for the first matching card."""
        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)
        full_name = get_set_name(set_code)
        if hasattr(self, "set_var"):
            try:
                self.set_var.set(full_name)
            except tk.TclError:
                pass

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {"name": name_api, "number": number_input, "set": set_code}

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.warning("API error: %s", response.status_code)
                return None

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []

            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    price_eur = extract_cardmarket_price(card) or 0
                    base_rate = self.get_exchange_rate()
                    eur_pln = base_rate * PRICE_MULTIPLIER
                    price_pln = round(float(price_eur) * eur_pln, 2)
                    if is_holo or is_reverse:
                        price_pln = round(price_pln * HOLO_REVERSE_MULTIPLIER, 2)
                    set_info = card.get("episode") or card.get("set") or {}
                    images = (
                        set_info.get("images", {}) if isinstance(set_info, dict) else {}
                    )
                    set_logo = (
                        images.get("logo")
                        or images.get("logoUrl")
                        or images.get("logo_url")
                        or set_info.get("logo")
                    )
                    image_url = (
                        card.get("images", {}).get("large")
                        or card.get("image")
                        or card.get("imageUrl")
                        or card.get("image_url")
                    )
                    return {
                        "image_url": image_url,
                        "set_logo_url": set_logo,
                        "price_eur": round(float(price_eur), 2),
                        "eur_pln_rate": round(base_rate, 4),
                        "price_pln": price_pln,
                        "price_pln_80": round(price_pln * 0.8, 2),
                    }
        except requests.Timeout:
            logger.warning("Request timed out")
        except requests.RequestException as e:
            logger.warning("Lookup failed: %s", e)
        except ValueError as e:
            logger.warning("Invalid JSON from TCGGO: %s", e)
        return None

    # ZMIANA: Logika pobierania ceny nie szuka już setu, jeśli jest on znany.
    def fetch_card_data(self):
        name = self.entries["nazwa"].get()
        number_raw = self.entries["numer"].get()
        set_name = self.entries["set"].get()

        # INFO: Jeśli set nie jest znany, spróbuj go znaleźć przed szukaniem ceny.
        if not set_name:
            self.log("Set nie jest znany, próba dopasowania przed pobraniem ceny...")
            total = None
            if "/" in str(number_raw):
                num_part, total_part = str(number_raw).split("/", 1)
                number = sanitize_number(num_part)
                total = sanitize_number(total_part)
            else:
                number = sanitize_number(number_raw)

            api_sets = lookup_sets_from_api(name, number, total)
            if api_sets:
                selected_code, resolved_name = api_sets[0]
                if len(api_sets) > 1:
                    self.log(
                        f"Znaleziono {len(api_sets)} pasujących setów, "
                        f"wybieram: {resolved_name}."
                    )
                self.entries["set"].set(resolved_name)
                set_name = resolved_name  # Zaktualizuj zmienną lokalną
                if hasattr(self, "update_set_options"):
                    self.update_set_options()
            else:
                self.log("Nie udało się automatycznie dopasować setu.")

        is_reverse = self.type_vars["Reverse"].get()
        is_holo = self.type_vars["Holo"].get()

        number = sanitize_number(number_raw.split('/')[0])

        # Teraz pobierz cenę, mając już pewność co do setu (lub jego braku)
        cena = self.get_price_from_db(name, number, set_name)
        if cena is not None:
            cena = self.apply_variant_multiplier(
                cena, is_reverse=is_reverse, is_holo=is_holo
            )
            self.entries["cena"].delete(0, tk.END)
            self.entries["cena"].insert(0, str(cena))
            self.log(f"Price for {name} {number}: {cena} zł")
        else:
            fetched = self.fetch_card_price(name, number, set_name)
            if fetched is not None:
                fetched = self.apply_variant_multiplier(
                    fetched, is_reverse=is_reverse, is_holo=is_holo
                )
                self.entries["cena"].delete(0, tk.END)
                self.entries["cena"].insert(0, str(fetched))
                self.log(f"Price for {name} {number}: {fetched} zł")
            else:
                messagebox.showinfo(
                    "Brak wyników",
                    "Nie znaleziono ceny dla podanej karty w bazie danych.",
                )
                self.log(f"Card {name} {number} not found")

        psa10_price = self.fetch_psa10_price(name, number, set_name)
        if psa10_price:
            self.entries["psa10_price"].delete(0, tk.END)
            self.entries["psa10_price"].insert(0, psa10_price)
            self.log(f"PSA10 price for {name} {number}: {psa10_price} zł")
        else:
            self.log(f"PSA10 price for {name} {number} not found")

    def open_cardmarket_search(self):
        """Open a Cardmarket search for the current card in the default browser."""
        name = self.entries["nazwa"].get()
        number = sanitize_number(self.entries["numer"].get())
        search_terms = " ".join(t for t in [name, number] if t)
        params = urlencode({"searchString": search_terms})
        url = f"https://www.cardmarket.com/en/Pokemon/Products/Search?{params}"
        webbrowser.open(url)

    def get_exchange_rate(self):
        try:
            res = requests.get(
                "https://api.nbp.pl/api/exchangerates/rates/A/EUR/?format=json",
                timeout=10,
            )
            if res.status_code == 200:
                return res.json()["rates"][0]["mid"]
        except requests.Timeout:
            logger.warning("Exchange rate request timed out")
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning("Failed to fetch exchange rate: %s", exc)
        return 4.265

    def apply_variant_multiplier(self, price, is_reverse=False, is_holo=False):
        """Apply holo/reverse or special variant multiplier when needed."""
        if price is None:
            return None
        multiplier = 1
        if is_reverse or is_holo:
            multiplier *= HOLO_REVERSE_MULTIPLIER

        try:
            return round(float(price) * multiplier, 2)
        except (TypeError, ValueError):
            return price

    def save_current_data(self):
        """Store the data for the currently displayed card without changing
        the index."""
        data: dict[str, str] = {}
        for k, v in self.entries.items():
            try:
                if hasattr(v, "winfo_exists") and not v.winfo_exists():
                    continue
                data[k] = v.get()
            except tk.TclError:
                continue
        data.setdefault("psa10_price", "")
        data.setdefault("nazwa", "")
        data.setdefault("numer", "")
        data.setdefault("set", "")
        data.setdefault("era", "")
        name = data.get("nazwa")
        number = data.get("numer")
        set_name = data.get("set")
        if not data["psa10_price"]:
            data["psa10_price"] = self.fetch_psa10_price(name, number, set_name)
        types = {name: var.get() for name, var in self.type_vars.items()}
        data["typ"] = ",".join([name for name, selected in types.items() if selected])
        data["types"] = types
        existing_wc = ""
        if getattr(self, "output_data", None) and 0 <= self.index < len(self.output_data):
            current = self.output_data[self.index]
            if current and current.get("warehouse_code"):
                existing_wc = current["warehouse_code"]
        current_loc = getattr(self, "current_location", "")
        data["warehouse_code"] = existing_wc or current_loc or self.next_free_location()
        # remember last used location index for subsequent sessions
        idx = storage.location_to_index(data["warehouse_code"].split(";")[0].strip())
        storage.save_last_location(idx)
        fp = getattr(self, "current_fingerprint", None)
        if (
            fp is None
            and getattr(self, "current_image_path", None)
            and getattr(self, "hash_db", None)
        ):
            try:
                with Image.open(self.current_image_path) as img:
                    try:
                        fp = compute_fingerprint(img, use_orb=True)
                    except TypeError:
                        fp = compute_fingerprint(img)
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                logger.warning(
                    "Failed to compute fingerprint for %s: %s",
                    self.current_image_path,
                    exc,
                )
                fp = None
            self.current_fingerprint = fp
        if fp is not None and getattr(self, "hash_db", None):
            if self.selected_candidate_meta:
                meta = self.selected_candidate_meta
            else:
                meta = {
                    k: data.get(k, "")
                    for k in (
                        "nazwa",
                        "numer",
                        "set",
                        "era",
                        "język",
                        "stan",
                        "typ",
                        "warehouse_code",
                    )
                }
            card_id = f"{meta.get('set', '')} {meta.get('numer', '')}".strip()
            try:
                self.hash_db.add_card_from_fp(fp, meta, card_id=card_id)
            except Exception as exc:
                logger.exception("Failed to store fingerprint")
            self.selected_candidate_meta = None
        key = f"{data['nazwa']}|{data['numer']}|{data['set']}|{data.get('era', '')}"
        data["ilość"] = 1
        self.card_cache[key] = {
            "entries": {k: v for k, v in data.items()},
            "types": types,
        }

        front_path = self.cards[self.index]
        front_file = os.path.basename(front_path)
        self.file_to_key[front_file] = key

        data["image1"] = f"{BASE_IMAGE_URL}/{self.folder_name}/{front_file}"
        variant = (
            "Holo"
            if types.get("Holo")
            else "Reverse"
            if types.get("Reverse")
            else ""
        )
        data["product_code"] = csv_utils.build_product_code(set_name, number, variant)
        data["unit"] = "szt."
        data["category"] = f"Karty Pokémon > {data['era']} > {data['set']}"
        data["producer"] = "Pokémon"
        data["producer_code"] = data["numer"]
        data["currency"] = "PLN"
        data["active"] = 1
        data["vat"] = "23%"
        data["seo_title"] = f"{data['nazwa']} {data['numer']} {data['set']}"
        data["seo_description"] = ""
        data["seo_keywords"] = ""

        name = html.escape(data["nazwa"])
        number = html.escape(data["numer"])
        raw_set_name = data["set"]
        set_name = html.escape(raw_set_name)
        card_type = html.escape(data["typ"])
        condition = html.escape(data["stan"])
        psa10_price = html.escape(data.get("psa10_price", "") or "???")

        data["short_description"] = (
            f'<ul style="margin:0 0 0.7em 1.2em; padding:0; font-size:1.14em;">'
            f'<li><strong>{name}</strong></li>'
            f'<li style="margin-top:0.3em;">Zestaw: {set_name}</li>'
            f'<li style="margin-top:0.3em;">Numer karty: {number}</li>'
            f'<li style="margin-top:0.3em;">Stan: {condition}</li>'
            f'<li style="margin-top:0.3em;">Typ: {card_type}</li>'
            "</ul>"
        )

        psa10_date = html.escape(datetime.date.today().isoformat())
        slug = raw_set_name.replace(" ", "-")
        link_set = html.escape(f"https://kartoteka.shop/pl/c/{slug}")
        psa_icon_url = html.escape(PSA_ICON_URL)

        data["description"] = (
            f'<div style="font-size:1.10em;line-height:1.7;">'
            f'<h2 style="margin:0 0 0.4em 0;">{name} – Pokémon TCG</h2>'
            f'<p><strong>Zestaw:</strong> {set_name}<br>'
            f'<strong>Numer karty:</strong> {number}<br>'
            f'<strong>Typ:</strong> {card_type}<br>'
            f'<strong>Stan:</strong> {condition}</p>'
            f'<div style="display:flex;align-items:center;margin:0.5em 0;">'
            f'<img src="{psa_icon_url}" alt="PSA 10" style="height:24px;width:auto;margin-right:0.4em;"/>'
            f'<span>Wartość tej karty w ocenie PSA 10 ({psa10_date}): ok. {psa10_price} PLN</span>'
            f'</div>'
            '<p>Dlaczego warto kupić w Kartoteka.shop?</p>'
            '<ul>'
            '<li>Oryginalne karty Pokémon</li>'
            '<li>Bezpieczna wysyłka i solidne opakowanie</li>'
            '<li>Profesjonalna obsługa klienta</li>'
            '</ul>'
            f'<p>Jeśli szukasz więcej kart z tego setu – sprawdź '
            f'<a href="{link_set}">pozostałe oferty</a>.</p>'
            '</div>'
        )

        data["availability"] = 1
        data["delivery"] = "3 dni"

        price = data.get("cena", "").strip()
        if price:
            data["cena"] = price
        else:
            cena_local = self.get_price_from_db(
                data["nazwa"], data["numer"], data["set"]
            )
            is_reverse = self.type_vars["Reverse"].get()
            is_holo = self.type_vars["Holo"].get()
            if cena_local is not None:
                cena_local = self.apply_variant_multiplier(
                    cena_local, is_reverse=is_reverse, is_holo=is_holo
                )
                data["cena"] = str(cena_local)
            else:
                fetched = self.fetch_card_price(
                    data["nazwa"],
                    data["numer"],
                    data["set"],
                )
                if fetched is not None:
                    fetched = self.apply_variant_multiplier(
                        fetched, is_reverse=is_reverse, is_holo=is_holo
                    )
                    data["cena"] = str(fetched)
                else:
                    data["cena"] = ""

        self.output_data[self.index] = data
        if getattr(self, "session_csv_path", None):
            with open(self.session_csv_path, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=csv_utils.STORE_FIELDNAMES,
                    delimiter=";",
                )
                writer.writerow(csv_utils.format_store_row(data))
        if hasattr(self, "current_location"):
            self.current_location = ""

    def save_and_next(self):
        """Save the current card data and display the next scan."""
        if getattr(self, "current_analysis_thread", None):
            try:
                messagebox.showwarning("Info", "Trwa analiza karty, poczekaj.")
            except tk.TclError:
                pass
            return
        try:
            self.save_current_data()
        except storage.NoFreeLocationError:
            try:
                messagebox.showerror("Błąd", "Brak wolnych miejsc w magazynie")
            except tk.TclError:
                pass
            return
        if self.index < len(self.cards) - 1:
            self.index += 1
            self.show_card()
        else:
            try:
                messagebox.showinfo("Info", "To jest ostatnia karta.")
            except tk.TclError:
                pass

    def previous_card(self):
        """Save current data and display the previous scan."""
        if self.index <= 0:
            return
        self.save_current_data()
        self.index -= 1
        self.show_card()

    def next_card(self):
        """Save current data and move forward without increasing stock."""
        if self.index >= len(self.cards) - 1:
            return
        self.save_current_data()
        self.index += 1
        self.show_card()

    def remove_warehouse_code(self, code: str):
        """Remove a code and repack the affected column."""
        match = re.match(r"K(\d+)R(\d)P(\d+)", code or "")
        if not match:
            return
        box = int(match.group(1))
        column = int(match.group(2))
        for row in list(self.output_data):
            if not row:
                continue
            codes = [c.strip() for c in str(row.get("warehouse_code") or "").split(";") if c.strip()]
            if code in codes:
                codes.remove(code)
                if codes:
                    row["warehouse_code"] = ";".join(codes)
                else:
                    self.output_data.remove(row)
                break
        self.repack_column(box, column)
        if hasattr(self, "update_inventory_stats"):
            try:
                self.update_inventory_stats()
            except Exception as exc:
                logger.exception("Failed to update inventory stats")

    def load_csv_data(self):
        """Load a CSV file and merge duplicate rows."""
        csv_utils.load_csv_data(self)

    def export_csv(self):
        self.in_scan = False
        csv_utils.export_csv(self, csv_utils.STORE_EXPORT_CSV)

    def open_config_dialog(self):
        """Display a dialog for editing Shoper API configuration."""
        url_var = tk.StringVar(value=os.getenv("SHOPER_API_URL", ""))
        token_var = tk.StringVar(value=os.getenv("SHOPER_API_TOKEN", ""))

        top = ctk.CTkToplevel(self.root)
        top.title("Konfiguracja Shoper API")
        top.grab_set()

        ctk.CTkLabel(top, text="URL API:", text_color=TEXT_COLOR).grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="e"
        )
        url_entry = ctk.CTkEntry(top, textvariable=url_var, width=400)
        url_entry.grid(row=0, column=1, padx=10, pady=(10, 5))

        ctk.CTkLabel(top, text="Token API:", text_color=TEXT_COLOR).grid(
            row=1, column=0, padx=10, pady=5, sticky="e"
        )
        token_entry = ctk.CTkEntry(top, textvariable=token_var, width=400)
        token_entry.grid(row=1, column=1, padx=10, pady=5)

        def save():
            url = url_var.get().strip()
            token = token_var.get().strip()
            if not url or not token:
                messagebox.showerror("Błąd", "Podaj URL i token API")
                return
            set_key(ENV_FILE, "SHOPER_API_URL", url)
            set_key(ENV_FILE, "SHOPER_API_TOKEN", token)
            os.environ["SHOPER_API_URL"] = url
            os.environ["SHOPER_API_TOKEN"] = token
            try:
                client = ShoperClient(url, token)
                try:
                    client.get("products", params={"page": 1, "per-page": 1})
                except RuntimeError as exc:
                    messagebox.showerror("Błąd", f"Autoryzacja nieudana: {exc}")
                    return
                self.shoper_client = client
                global SHOPER_API_URL, SHOPER_API_TOKEN
                SHOPER_API_URL, SHOPER_API_TOKEN = url, token
                messagebox.showinfo("Sukces", "Zapisano konfigurację Shoper API")
                top.destroy()
            except requests.RequestException as exc:
                messagebox.showerror(
                    "Błąd", f"Nie można połączyć się z API Shoper: {exc}"
                )

        save_btn = ctk.CTkButton(
            top, text="Zapisz", command=save, fg_color=SAVE_BUTTON_COLOR
        )
        save_btn.grid(row=2, column=0, columnspan=2, pady=10)
        top.grid_columnconfigure(1, weight=1)
        self.root.wait_window(top)

    def send_csv_to_shoper(self, file_path: str):
        """Send a CSV file using the Shoper API or WebDAV fallback."""
        csv_utils.send_csv_to_shoper(self, file_path)

