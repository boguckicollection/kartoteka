import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import customtkinter as ctk
import tkinter.ttk as ttk
from PIL import Image, ImageTk, ImageFilter, ImageOps
import imagehash
import os
import csv
import json
import requests
import openai
import base64
import mimetypes
import re
import asyncio
import datetime
import time
from collections import defaultdict
from dotenv import load_dotenv
import unicodedata
from itertools import combinations
import html
import difflib
import sys
from typing import Iterable, Optional
from pydantic import BaseModel
import pytesseract

from shoper_client import ShoperClient
from ftp_client import FTPClient
from . import csv_utils, storage
import threading
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
import io
import webbrowser
import logging

load_dotenv()

logger = logging.getLogger(__name__)

BASE_IMAGE_URL = os.getenv("BASE_IMAGE_URL", "https://sklep839679.shoparena.pl/upload/images")
SCANS_DIR = os.getenv("SCANS_DIR", "scans")

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

SHOPER_API_URL = os.getenv("SHOPER_API_URL", "").strip()
SHOPER_API_TOKEN = os.getenv("SHOPER_API_TOKEN", "").strip()
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASSWORD = os.getenv("FTP_PASSWORD")
SHOPER_DELIVERY_ID = int(os.getenv("SHOPER_DELIVERY_ID", "1"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

PRICE_DB_PATH = "card_prices.csv"
PRICE_MULTIPLIER = 1.23
HOLO_REVERSE_MULTIPLIER = 3.5
SET_LOGO_DIR = "set_logos"
HASH_DIFF_THRESHOLD = 20  # hash difference threshold for accepting matches
HASH_SIZE = (32, 32)

# minimum similarity ratio for fuzzy set code matching
SET_CODE_MATCH_CUTOFF = 0.8
try:
    SET_CODE_MATCH_CUTOFF = float(
        os.getenv("SET_CODE_MATCH_CUTOFF", SET_CODE_MATCH_CUTOFF)
    )
except ValueError:
    pass

_LOGO_HASHES: dict[str, tuple[imagehash.ImageHash, imagehash.ImageHash, imagehash.ImageHash]] = {}


def _preprocess_symbol(im: Image.Image) -> Image.Image:
    """Normalize symbol/logo image before hashing."""
    im = ImageOps.fit(im.convert("L"), HASH_SIZE, method=Image.Resampling.LANCZOS)
    im = im.filter(ImageFilter.MedianFilter(3))
    im = ImageOps.autocontrast(im)
    return im.convert("1")


def load_logo_hashes() -> None:
    """Populate the global `_LOGO_HASHES` cache with preprocessed hashes."""
    _LOGO_HASHES.clear()
    if not os.path.isdir(SET_LOGO_DIR):
        return
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
                im = _preprocess_symbol(im)
                _LOGO_HASHES[code] = (
                    imagehash.phash(im),
                    imagehash.dhash(im),
                    imagehash.average_hash(im),
                )
        except Exception:
            continue

DEFAULT_LOGO_LIMIT = 20
try:
    DEFAULT_LOGO_LIMIT = int(os.getenv("SET_LOGO_LIMIT", DEFAULT_LOGO_LIMIT))
except ValueError:
    pass

# custom theme colors in grayscale
BG_COLOR = "#2E2E2E"
ACCENT_COLOR = "#666666"
HOVER_COLOR = "#525252"
TEXT_COLOR = "#FFFFFF"
BORDER_COLOR = "#444444"



def normalize(text: str, keep_spaces: bool = False) -> str:
    """Normalize text for comparisons and API queries."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
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
    tcg_sets_eng = [
        item["name"] for sets in tcg_sets_eng_by_era.values() for item in sets
    ]

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
    tcg_sets_jp = [
        item["name"] for sets in tcg_sets_jp_by_era.values() for item in sets
    ]


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


def refresh_logo_cache() -> None:
    """Regenerate ``ALLOWED_SET_CODES`` and reload logo hashes."""
    global ALLOWED_SET_CODES
    ALLOWED_SET_CODES = {
        item["code"]
        for era, sets in tcg_sets_eng_by_era.items()
        if era in ALLOWED_ERAS
        for item in sets
    }
    load_logo_hashes()


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
    print(
        f"Nie znaleziono nazwy dla setu '{code}'. Weryfikacja ręczna wymagana."
    )
    return code


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
        print("[ERROR] Request timed out")
        return []
    except Exception as e:  # pragma: no cover - network/JSON errors
        print(f"[ERROR] Fetching sets from TCGGO failed: {e}")
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


def prompt_set_selection(options):
    """Prompt the user to choose a set by its logo.

    Parameters
    ----------
    options:
        List of ``(set_code, set_name)`` tuples. Only the first four are
        displayed.

    Returns
    -------
    str
        The selected ``set_code`` or the first option when no selection is
        made or the dialog cannot be displayed.
    """

    if not options:
        return ""

    options = options[:4]
    selected = {"code": options[0][0]}

    try:
        root = tk._default_root or tk.Tk()
        top = ctk.CTkToplevel(root, fg_color=BG_COLOR)
    except Exception:
        return selected["code"]

    top.title("Wybierz set")
    images: list[ImageTk.PhotoImage | None] = []

    def choose(code: str):
        selected["code"] = code
        try:
            top.destroy()
        except Exception:
            pass

    for i, (code, name) in enumerate(options):
        img = None
        path = os.path.join(SET_LOGO_DIR, f"{code}.png")
        if os.path.exists(path):
            try:
                logo_img = Image.open(path)
                logo_img.thumbnail((40, 40))
                img = ImageTk.PhotoImage(logo_img)
            except Exception:
                img = None
        btn = ctk.CTkButton(
            top,
            image=img,
            text="",
            fg_color=ACCENT_COLOR,
            text_color=TEXT_COLOR,
            hover_color=HOVER_COLOR,
            command=lambda c=code: choose(c),
        )
        btn.grid(row=0, column=i, padx=5, pady=5)
        ctk.CTkLabel(top, text=name, text_color=TEXT_COLOR).grid(
            row=1, column=i, padx=5, pady=2
        )
        images.append(img)
        top.grid_columnconfigure(i, weight=1, minsize=100)

    # keep references to prevent garbage collection
    top.images = images

    try:
        top.update_idletasks()
        w = top.winfo_width()
        h = top.winfo_height()
        min_width = len(options) * 120
        w = max(w, min_width)
        x = int(top.winfo_screenwidth() / 2 - w / 2)
        y = int(top.winfo_screenheight() / 2 - h / 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.focus_force()
        top.grab_set()
        top.wait_window()
    except Exception:
        pass

    return selected["code"]


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
    """Return the best available Cardmarket price for a card.

    The function checks multiple possible fields in the ``cardmarket`` price
    section and returns the first non-zero value.  If none of the fields are
    present or they evaluate to zero, ``None`` is returned.
    """

    cardmarket = card.get("prices", {}).get("cardmarket", {}) or {}
    for field in ["30d_average", "trendPrice", "trend_price", "lowest_near_mint"]:
        price = cardmarket.get(field)
        try:
            value = float(price)
        except (TypeError, ValueError):
            continue
        if value:
            print(f"[DEBUG] Using Cardmarket field '{field}' with value {value}")
            return value
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
            max_completion_tokens=50,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
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
        except Exception:
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

    if not _LOGO_HASHES:
        load_logo_hashes()
    if not _LOGO_HASHES:
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
    except Exception:
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
    scan_path: str, rect: tuple[int, int, int, int]
) -> list[str]:
    """Extract potential set codes from the scan using OCR.

    Parameters
    ----------
    scan_path:
        Path to the card scan image.
    rect:
        Bounding box ``(left, upper, right, lower)`` containing the expected
        location of the set code.

    Returns
    -------
    list[str]
        List of unique set code strings recognized from the image. When no codes
        are recognized the list is empty.
    """

    try:
        with Image.open(scan_path) as im:
            crop = im.crop(rect)
        crop = crop.convert("L").resize((crop.width * 3, crop.height * 3))
        raw = pytesseract.image_to_string(
            crop,
            config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ/-",
        )
    except Exception:
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


# ZMIANA: Funkcja prosi OpenAI o wszystkie dane naraz, w tym o zestaw
def extract_card_info_openai(path: str) -> tuple[str, str, str, str, str]:
    """Recognize card name, number, and set using OpenAI Vision.

    Returns a tuple ``(name, number, total, set_name, set_code)``.  The
    ``set_name`` value is normalised to the canonical display name whenever a
    matching ``set_code`` can be resolved.
    """
    try:
        parsed = urlparse(path)
        if parsed.scheme in ("http", "https"):
            try:
                r = requests.get(path, timeout=10)
                r.raise_for_status()
                mime = r.headers.get("Content-Type") or mimetypes.guess_type(path)[0] or "image/jpeg"
                encoded = base64.b64encode(r.content).decode("utf-8")
            except Exception as e:
                print(f"[ERROR] extract_card_info_openai failed to fetch image: {e}")
                return "", "", "", "", ""
        else:
            mime = mimetypes.guess_type(path)[0] or "image/jpeg"
            try:
                with open(path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
            except OSError as e:
                print(f"[ERROR] extract_card_info_openai failed to read image: {e}")
                return "", "", "", "", ""
        data_url = f"data:{mime};base64,{encoded}"

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "", "", "", "", ""
        client = openai.OpenAI(api_key=api_key)

        PROMPT = (
            "You must return a JSON object with the Pokémon card's English name, "
            "card number in the form NNN/NNN, and English set name. The response "
            "must strictly match {\"name\":\"\", \"number\":\"\", \"set_name\":\"\"}."
        )

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
        if not raw:
            logger.error(
                "extract_card_info_openai got empty response from OpenAI: %r", resp
            )
            return "", "", "", "", ""
        content = raw

        data_dict = json.loads(content)
        data = CardInfo(**data_dict)

        raw_number = data.number or ""
        number, total = "", ""
        if isinstance(raw_number, str):
            m = re.search(r"(\d+)(?:\s*/\s*(\d+))?", raw_number)
            if m:
                number, total = m.group(1), m.group(2) or ""
            else:
                number = re.sub(r"\D+", "", raw_number)

        name = data.name or ""
        set_name = data.set_name or ""
        set_code = ""
        if set_name:
            set_code = get_set_code(set_name)
            mapped = get_set_name(set_code)
            if mapped:
                set_name = mapped
        return name, number, total, set_name, set_code
    except Exception as e:
        print(f"[ERROR] extract_card_info_openai failed: {e}")
        return "", "", "", "", ""

# ZMIANA: Całkowicie nowa, hierarchiczna logika analizy obrazu
def analyze_card_image(path: str, translate_name: bool = False, debug: bool = False):
    """Return card details recognized from an image using a prioritized workflow."""
    parsed = urlparse(path)
    local_path = path if parsed.scheme not in ("http", "https") else None
    orientation = 0
    rects: list[tuple[int, int, int, int]] = []
    rect: Optional[tuple[int, int, int, int]] = None
    rotated_path = None
    if local_path and os.path.exists(local_path):
        try:
            with Image.open(local_path) as im:
                w, h = im.size
                orientation = 90 if w > h else 0
                if orientation == 90:
                    im = im.rotate(90, expand=True)
                    rotated_path = local_path + ".rot.jpg"
                    im.save(rotated_path)
                    local_path = rotated_path
                    path = rotated_path
                    w, h = im.size
                rects = get_symbol_rects(w, h)
                if rects:
                    rect = rects[0]
        except Exception:
            rects = []
            rect = None

    name = number = total = set_name = ""
    set_code = ""

    try:
        # --- PRIORITY 1: OpenAI Vision ---
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            print("[INFO] Step 1: Analyzing with OpenAI Vision...")
            try:
                name, number, total, set_name, set_code = extract_card_info_openai(path)

                if translate_name and name and not name.isascii():
                    name = translate_to_english(name)

                if name and number and set_name:
                    print(f"[SUCCESS] OpenAI found all data: {name}, {number}, {set_name}")
                    result = {
                        "name": name,
                        "number": number,
                        "total": total,
                        "set": set_name,
                        "set_code": set_code,
                        "orientation": orientation,
                    }
                    if debug and rect:
                        result["rect"] = rect
                    return result

                print("[INFO] OpenAI returned partial data. Proceeding to fallback methods.")

            except Exception as e:
                print(f"[ERROR] OpenAI analysis failed: {e}")
                name = number = total = set_name = ""
                set_code = ""
        else:
            print("[WARN] No OpenAI API key. Skipping to local analysis.")

        # --- PRIORITY 2: TCGGO API Lookup (if name and number are known) ---
        if name and number:
            print("[INFO] Step 2: Looking up sets via TCGGO API...")
            try:
                api_sets = lookup_sets_from_api(name, number, total or None)
                if len(api_sets) == 1:
                    set_code, api_set_name = api_sets[0]
                    print(f"[SUCCESS] TCGGO API found a single match: {api_set_name}")
                    result = {
                        "name": name,
                        "number": number,
                        "total": total,
                        "set": api_set_name,
                        "set_code": set_code,
                        "orientation": orientation,
                    }
                    if debug and rect:
                        result["rect"] = rect
                    return result

                if len(api_sets) > 1:
                    print("[INFO] TCGGO API found multiple matches. Prompting user...")
                    selected_code = prompt_set_selection(api_sets)
                    name_lookup = get_set_name(selected_code)
                    selected_name = (
                        name_lookup
                        if name_lookup != selected_code
                        else next((n for c, n in api_sets if c == selected_code), selected_code)
                    )
                    print(f"[SUCCESS] User selected: {selected_name}")
                    result = {
                        "name": name,
                        "number": number,
                        "total": total,
                        "set": selected_name,
                        "set_code": selected_code,
                        "orientation": orientation,
                    }
                    if debug and rect:
                        result["rect"] = rect
                    return result

            except Exception as e:
                print(f"[ERROR] TCGGO API lookup failed: {e}")

        # --- PRIORITY 3: Local Analysis (Hash/OCR as last resort) ---
        if local_path:
            print("[INFO] Step 3: Performing local analysis (hash/OCR)...")
            try:
                if not rects:
                    rects = [(0, 0, 0, 0)]

                for candidate in rects:
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
                            result = {
                                "name": name,
                                "number": number,
                                "total": total,
                                "set": set_name,
                                "set_code": set_code,
                                "orientation": orientation,
                            }
                            if debug and rect:
                                result["rect"] = rect
                            return result

                print("[INFO] Hash analysis did not yield a confident result. Trying OCR...")

                rect = rect or rects[0]
                ocr_codes = extract_set_code_ocr(local_path, rect)
                for code in ocr_codes:
                    name_lookup = get_set_name(code)
                    if name_lookup and name_lookup != code:
                        set_code = code
                        set_name = name_lookup
                        print(f"[SUCCESS] OCR recognized set code: {name_lookup}")
                        result = {
                            "name": name,
                            "number": number,
                            "total": total,
                            "set": set_name,
                            "set_code": set_code,
                            "orientation": orientation,
                        }
                        if debug and rect:
                            result["rect"] = rect
                        return result
                    else:
                        print(f"[WARN] OCR produced unknown set code: {code}")

                print("[INFO] OCR analysis did not find a valid set code.")
            except Exception as e:
                print(f"[ERROR] Local analysis failed: {e}")

        # If all methods fail, return any partial data we might have
        print("[FAIL] All analysis methods failed to find a definitive set.")
        result = {
            "name": name,
            "number": number,
            "total": total,
            "set": set_name,
            "set_code": set_code,
            "orientation": orientation,
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
    API_TIMEOUT = 10

    def __init__(self, root):
        self.root = root
        self.root.title("KARTOTEKA")
        # improve default font for all widgets
        self.root.configure(bg=BG_COLOR, fg_color=BG_COLOR)
        self.root.option_add("*Font", ("Segoe UI", 16))
        self.root.option_add("*Foreground", TEXT_COLOR)
        self.index = 0
        self.cards = []
        self.image_objects = []
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.card_cache = {}
        self.file_to_key = {}
        self.product_code_map = {}
        self.next_product_code = 1
        self.price_db = self.load_price_db()
        self.folder_name = ""
        self.folder_path = ""
        self.sets_file = "tcg_sets.json"
        self.progress_var = tk.StringVar(value="0/0")
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
        self.mag_canvases = []
        self.mag_box_photo = None
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
        self.show_loading_screen()
        threading.Thread(target=self.startup_tasks, daemon=True).start()

    def setup_welcome_screen(self):
        """Display a simple welcome screen before loading scans."""
        # Allow resizing but provide a sensible minimum size
        self.root.minsize(1000, 700)
        self.start_frame = ctk.CTkFrame(
            self.root, fg_color=BG_COLOR, corner_radius=10
        )
        self.start_frame.pack(expand=True, fill="both")

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((140, 140))
            self.logo_photo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(
                self.start_frame,
                image=self.logo_photo,
                bg=self.root.cget("background"),
            )
            logo_label.pack(pady=(10, 10))

        greeting = ctk.CTkLabel(
            self.start_frame,
            text="Witaj w aplikacji KARTOTEKA",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
        )
        greeting.pack(pady=5)

        desc = ctk.CTkLabel(
            self.start_frame,
            text=(
                "Aplikacja KARTOTEKA.SHOP pomaga przygotować skany do sprzedaży."
            ),
            wraplength=1400,
            justify="center",
            text_color=TEXT_COLOR,
        )
        desc.pack(pady=5)

        author = ctk.CTkLabel(
            self.start_frame,
            text="Twórca: BOGUCKI | Właściciel: kartoteka.shop",
            wraplength=1400,
            justify="center",
            font=("Inter", 10),
            text_color="#CCCCCC",
        )
        author.pack(side="bottom", pady=5)

        button_frame = tk.Frame(
            self.start_frame, bg=self.root.cget("background")
        )
        # Keep the buttons centered without stretching across the entire window
        button_frame.pack(pady=10)

        scan_btn = self.create_button(
            button_frame,
            text="\U0001f50d Skanuj",
            command=self.show_location_frame,
            fg_color="#6A6A6A",
        )
        scan_btn.pack(side="left", padx=10, pady=5)
        self.create_button(
            button_frame,
            text="\U0001f4b0 Wyceniaj",
            command=self.setup_pricing_ui,
            fg_color="#636363",
        ).pack(side="left", padx=10, pady=5)
        self.create_button(
            button_frame,
            text="\U0001f5c3\ufe0f Shoper",
            command=self.open_shoper_window,
            fg_color="#5C5C5C",
        ).pack(side="left", padx=10, pady=5)
        self.create_button(
            button_frame,
            text="\U0001f4e6 Magazyn",
            command=self.open_magazyn_window,
            fg_color="#555555",
        ).pack(side="left", padx=10, pady=5)
        self.create_button(
            button_frame,
            text="\U0001f528 Licytacje",
            command=self.open_auctions_window,
            fg_color="#4E4E4E",
        ).pack(side="left", padx=10, pady=5)
        self.create_button(
            button_frame,
            text="\U0001f4f7 FTP Obrazy",
            command=self.upload_images_dialog,
            fg_color="#474747",
        ).pack(side="left", padx=10, pady=5)

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
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()

        self.root.minsize(1000, 700)
        frame = ctk.CTkFrame(self.root)
        frame.pack(expand=True, fill="both", padx=10, pady=10)
        frame.grid_anchor("center")
        self.location_frame = frame

        start_row = 0
        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.location_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                frame,
                image=self.location_logo_photo,
                bg=self.root.cget("background"),
            ).pack(pady=(0, 10))

        form = tk.Frame(frame, bg=self.root.cget("background"))
        form.pack(pady=5)
        for idx, label in enumerate(["Karton", "Kolumna", "Pozycja"]):
            ctk.CTkLabel(form, text=label).grid(row=0, column=idx, padx=5, pady=2)
        ctk.CTkEntry(form, textvariable=self.start_box_var, width=60).grid(row=1, column=0, padx=5)
        ctk.CTkEntry(form, textvariable=self.start_col_var, width=60).grid(row=1, column=1, padx=5)
        ctk.CTkEntry(form, textvariable=self.start_pos_var, width=60).grid(row=1, column=2, padx=5)

        folder_frame = tk.Frame(frame, bg=self.root.cget("background"))
        folder_frame.pack(pady=5)
        ctk.CTkLabel(folder_frame, text="Folder").grid(row=0, column=0, padx=5, pady=2)
        ctk.CTkEntry(folder_frame, textvariable=self.scan_folder_var, width=200).grid(row=0, column=1, padx=5)
        self.create_button(folder_frame, text="Wybierz", command=self.select_scan_folder).grid(row=0, column=2, padx=5)

        self.create_button(frame, text="Dalej", command=self.start_browse_scans).pack(pady=5)

    def select_scan_folder(self):
        """Open a dialog to choose the folder with scans."""
        folder = filedialog.askdirectory()
        if folder:
            self.scan_folder_var.set(folder)

    def create_button(self, master=None, **kwargs):
        if master is None:
            master = self.root
        fg_color = kwargs.pop("fg_color", ACCENT_COLOR)
        width = kwargs.pop("width", 180)
        height = kwargs.pop("height", 50)
        font = kwargs.pop("font", ("Segoe UI", 16, "bold"))
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

    def _on_shoper_tab_changed(self):
        if (
            self.shoper_tabs.get() == "Stan magazynowy"
            and getattr(self, "inventory_tree", None)
        ):
            self.load_inventory_csv(self.inventory_tree)

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
        except Exception as exc:
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
        # Ensure the window has a reasonable minimum size
        self.root.minsize(1000, 700)

        self.shoper_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.shoper_frame.pack(expand=True, fill="both", padx=10, pady=10)
        self.shoper_frame.columnconfigure(0, weight=1)
        self.shoper_frame.rowconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.shoper_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                self.shoper_frame,
                image=self.shoper_logo_photo,
                bg=self.root.cget("background"),
            ).grid(row=0, column=0, pady=(0, 10))

        self.shoper_tabs = ctk.CTkTabview(
            self.shoper_frame, command=self._on_shoper_tab_changed
        )
        self.shoper_tabs.grid(row=1, column=0, sticky="nsew", pady=5)
        self.shoper_tabs.add("Wyślij produkt")
        self.shoper_tabs.add("Stan magazynowy")
        self.shoper_tabs.add("Zamówienia")
        upload_tab = self.shoper_tabs.tab("Wyślij produkt")
        inventory_tab = self.shoper_tabs.tab("Stan magazynowy")
        orders_tab = self.shoper_tabs.tab("Zamówienia")

        inventory_tab.columnconfigure(0, weight=1)
        inventory_tab.rowconfigure(1, weight=1)
        orders_tab.columnconfigure(0, weight=1)
        orders_tab.rowconfigure(0, weight=1)
        upload_tab.columnconfigure(0, weight=1)
        upload_tab.rowconfigure(0, weight=1)

        search_frame = tk.Frame(
            inventory_tab, bg=self.root.cget("background")
        )
        search_frame.grid(row=0, column=0, sticky="ew", pady=5)
        search_frame.columnconfigure(1, weight=1)
        search_frame.columnconfigure(3, weight=1)
        search_frame.columnconfigure(5, weight=1)
        search_frame.columnconfigure(7, weight=1)

        tk.Label(
            search_frame, text="Szukaj", bg=self.root.cget("background")
        ).grid(row=0, column=0, sticky="e")
        self.shoper_search_var = tk.StringVar()
        ctk.CTkEntry(search_frame, textvariable=self.shoper_search_var, placeholder_text="Nazwa produktu").grid(
            row=0, column=1, sticky="ew"
        )
        tk.Label(
            search_frame, text="Numer", bg=self.root.cget("background")
        ).grid(row=0, column=2, sticky="e")
        self.shoper_number_var = tk.StringVar()
        ctk.CTkEntry(search_frame, textvariable=self.shoper_number_var, placeholder_text="Kod").grid(
            row=0, column=3, sticky="ew"
        )
        tk.Label(
            search_frame, text="Set", bg=self.root.cget("background")
        ).grid(row=0, column=4, sticky="e")
        self.shoper_set_var = tk.StringVar()
        ctk.CTkEntry(search_frame, textvariable=self.shoper_set_var, placeholder_text="Set").grid(
            row=0, column=5, sticky="ew"
        )
        tk.Label(
            search_frame, text="Kategoria", bg=self.root.cget("background")
        ).grid(row=0, column=6, sticky="e")
        self.shoper_category_var = tk.StringVar()
        ctk.CTkEntry(
            search_frame,
            textvariable=self.shoper_category_var,
            placeholder_text="Kategoria",
        ).grid(row=0, column=7, sticky="ew")
        tk.Label(
            search_frame, text="Sortuj", bg=self.root.cget("background")
        ).grid(row=0, column=8, sticky="e")
        self.shoper_sort_var = tk.StringVar(value="")
        ctk.CTkComboBox(
            search_frame,
            variable=self.shoper_sort_var,
            values=["", "name", "-name", "price", "-price"],
            width=10,
        ).grid(row=0, column=9, padx=5)
        self.create_button(
            search_frame,
            text="Wyszukaj",
            command=lambda: self.search_products(output),
        ).grid(row=0, column=10, padx=5)

        columns = ("code", "name", "stock", "warehouse")
        output = ttk.Treeview(inventory_tab, columns=columns, show="headings")
        output.heading("code", text="Kod")
        output.heading("name", text="Nazwa")
        output.heading("stock", text="Ilość")
        output.heading("warehouse", text="Magazyn")
        output.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        # Automatically display current products from local CSV
        self.load_inventory_csv(output)
        self.inventory_tree = output

        self.create_button(
            inventory_tab,
            text="Odśwież",
            command=lambda: self.load_inventory_csv(output),
        ).grid(row=2, column=0, pady=5)

        upload_output = tk.Text(
            upload_tab,
            height=10,
            bg=self.root.cget("background"),
            fg="white",
        )
        upload_output.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.create_button(
            upload_tab,
            text="Wyślij produkt",
            command=lambda: self.push_product(upload_output),
        ).grid(row=1, column=0, pady=5)

        orders_output = tk.Text(
            orders_tab,
            height=10,
            bg=self.root.cget("background"),
            fg="white",
        )
        orders_output.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.create_button(
            orders_tab,
            text="Zamówienia",
            command=lambda: self.show_orders(orders_output),
        ).grid(row=1, column=0, pady=5)

        self.create_button(
            self.shoper_frame,
            text="Powrót",
            command=self.back_to_welcome,
        ).grid(row=2, column=0, pady=5)

    def push_product(self, widget):
        """Send the currently selected card to Shoper."""
        try:
            card = None
            if getattr(self, "output_data", None):
                try:
                    self.save_current_data()
                except Exception:
                    pass
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
            except Exception:
                pass
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
            else:
                messagebox.showinfo(
                    "Wysłano",
                    json.dumps(data, indent=2, ensure_ascii=False),
                )
        except Exception as e:
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
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        if getattr(self, "auction_frame", None):
            self.auction_frame.destroy()

        try:
            import bot
            if not getattr(bot, "_thread_started", False):
                threading.Thread(target=bot.run_bot, daemon=True).start()
                bot._thread_started = True
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

        self.root.minsize(1000, 700)
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
        except Exception as exc:
            messagebox.showerror("Błąd", str(exc))
            self.auction_queue = []

        refresh_tree()
        self._update_auction_status()

    def _build_auction_widgets(self, container):
        """Create auction editor widgets and return a refresh callback."""
        left_panel = tk.Frame(container, bg=self.root.cget("background"))
        left_panel.pack(side="right", fill="y", padx=10, pady=10)

        self.auction_image_label = tk.Label(left_panel, bg=self.root.cget("background"))
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
            fg="white",
        ).grid(row=0, column=0, padx=2, sticky="e")
        tk.Label(
            status_frame,
            textvariable=self.current_price_var,
            bg=self.root.cget("background"),
            fg="white",
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
                    img = Image.open(io.BytesIO(resp.content))
                else:
                    if os.path.exists(path):
                        img = Image.open(path)
                    else:
                        return
                img.thumbnail((200, 280))
                if hasattr(ctk, "CTkImage"):
                    photo = ctk.CTkImage(light_image=img, size=img.size)
                else:
                    photo = ImageTk.PhotoImage(img)
                self.auction_photo = photo
                self.auction_image_label.configure(image=photo)
            except Exception:
                pass

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
                    except Exception as exc:
                        messagebox.showerror("Błąd", str(exc))
                        return
            if not rows:
                path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
                if not path:
                    return
                try:
                    rows = self.read_inventory_rows([], path)
                except Exception as exc:
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
                pass
            messagebox.showinfo("Aukcje", "Kolejka zapisana do aukcje.csv")

        btn_frame = tk.Frame(win, bg=self.root.cget("background"))
        btn_frame.pack(pady=5)
        self.create_button(btn_frame, text="Dodaj", command=add_row).pack(
            side="left", padx=5
        )
        self.create_button(
            btn_frame, text="Wczytaj zaznaczone", command=import_selected
        ).pack(side="left", padx=5)
        self.create_button(
            btn_frame, text="Usuń zaznaczone", command=remove_selected
        ).pack(side="left", padx=5)
        self.create_button(btn_frame, text="Zapisz", command=save_queue).pack(
            side="left", padx=5
        )


        control_frame = tk.Frame(win, bg=self.root.cget("background"))
        control_frame.pack(pady=5)

        def start_auction():
            try:
                import bot
                asyncio.run_coroutine_threadsafe(
                    bot.start_next_auction(), bot.bot.loop
                )
            except Exception as e:
                messagebox.showerror("Błąd", str(e))

        def next_card():
            start_auction()

        pause_btn = self.create_button(control_frame, text="⏸ Pauza")
        pause_btn.pack(side="left", padx=5)

        def reload_queue():
            try:
                self._load_auction_queue()
                refresh_tree()
            except Exception as exc:
                messagebox.showerror("Błąd", str(exc))

        def toggle_pause():
            try:
                import bot
                bot.paused = not bot.paused
                pause_btn.configure(text="▶ Wznów" if bot.paused else "⏸ Pauza")
            except Exception as e:
                messagebox.showerror("Błąd", str(e))

        self.create_button(
            control_frame, text="Start aukcji", command=start_auction
        ).pack(side="left", padx=5)
        self.create_button(
            control_frame, text="Następna karta", command=next_card
        ).pack(side="left", padx=5)
        pause_btn.configure(command=toggle_pause)
        self.create_button(
            control_frame, text="Wczytaj ponownie", command=reload_queue
        ).pack(side="left", padx=5)
        self.create_button(
            control_frame, text="Powrót do menu", command=self.back_to_welcome
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
        try:
            name, number, set_name = key.split("|", 2)
        except ValueError:
            return None

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
                    except Exception:
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
                            img = Image.open(io.BytesIO(resp.content))
                        else:
                            if os.path.exists(img_path):
                                img = Image.open(img_path)
                            else:
                                img = None
                        if img is not None:
                            img.thumbnail((200, 280))
                            if hasattr(ctk, "CTkImage"):
                                photo = ctk.CTkImage(light_image=img, size=img.size)
                            else:
                                photo = ImageTk.PhotoImage(img)
                            self.auction_photo = photo
                            self.auction_image_label.configure(image=photo)
                    except Exception:
                        pass
            except Exception:
                pass
        if self.auction_frame and self.auction_frame.winfo_exists():
            self.auction_frame.after(1000, self._update_auction_status)

    # backward compatibility
    def fetch_inventory(self, widget):
        """Deprecated: use load_products_from_shoper."""
        return self.load_products_from_shoper(widget)

    def open_product_details(self, event=None):
        tree = event.widget if event else self.inventory_tree
        selected = tree.selection()
        if not selected:
            return
        item_id = selected[0]
        product = getattr(self, "inventory_products", {}).get(item_id)
        if not product:
            return
        top = tk.Toplevel(self.root)
        top.title(f"Produkt {product.get('product_id')}")
        top.configure(bg=self.root.cget("background"))
        text = tk.Text(top, bg=self.root.cget("background"), fg="white")
        text.pack(expand=True, fill="both", padx=10, pady=10)
        text.insert("1.0", json.dumps(product, indent=2, ensure_ascii=False))
        self.create_button(top, text="Zamknij", command=top.destroy).pack(pady=5)

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

    def load_products_from_shoper(self, widget):
        try:
            all_products = []
            page = 1
            per_page = 50
            while True:
                data = self.shoper_client.get_inventory(page=page, per_page=per_page)
                products = data.get("list", data)
                if not products:
                    break
                all_products.extend(products)
                if len(products) < per_page:
                    break
                page += 1

            if isinstance(widget, ttk.Treeview):
                widget.delete(*widget.get_children())
                self.inventory_products = {}
                for prod in all_products:
                    translations = prod.get("translations") or {}
                    name = ""
                    if isinstance(translations, dict):
                        first = next(iter(translations.values()), {})
                        name = first.get("name", "")
                    item_id = widget.insert(
                        "",
                        "end",
                        values=(
                            prod.get("product_id"),
                            name,
                            prod.get("code", ""),
                            prod.get("price", ""),
                        ),
                    )
                    self.inventory_products[item_id] = prod
            else:
                widget.delete("1.0", tk.END)
                lines = []
                for prod in all_products:
                    translations = prod.get("translations") or {}
                    name = ""
                    if isinstance(translations, dict):
                        first = next(iter(translations.values()), {})
                        name = first.get("name", "")
                    lines.append(f"{prod.get('product_id')}: {name}")
                if lines:
                    widget.insert(tk.END, "\n".join(lines))
                else:
                    widget.insert(
                        tk.END,
                        json.dumps(all_products, indent=2, ensure_ascii=False),
                    )
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def load_inventory_csv(self, widget):
        """Load local inventory data from the CSV file."""
        try:
            path = csv_utils.WAREHOUSE_CSV
            if isinstance(widget, ttk.Treeview):
                style = ttk.Style(widget)
                style.configure(
                    "Inventory.Treeview",
                    background=BG_COLOR,
                    fieldbackground=BG_COLOR,
                    foreground=TEXT_COLOR,
                )
                style.map(
                    "Inventory.Treeview", background=[("selected", HOVER_COLOR)]
                )
                style.configure(
                    "Inventory.Treeview.Heading",
                    background=ACCENT_COLOR,
                    foreground=TEXT_COLOR,
                )
                style.map(
                    "Inventory.Treeview.Heading",
                    background=[("active", HOVER_COLOR)],
                )
                widget.configure(style="Inventory.Treeview")
                widget.delete(*widget.get_children())
                with open(path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        widget.insert(
                            "",
                            "end",
                            values=(
                                row.get("product_code"),
                                row.get("name"),
                                row.get("stock"),
                                row.get("warehouse_code"),
                            ),
                        )
            else:
                with open(path, newline="", encoding="utf-8") as f:
                    data = f.read()
                widget.delete("1.0", tk.END)
                widget.insert(tk.END, data)
        except FileNotFoundError:
            messagebox.showerror("Błąd", f"Nie znaleziono pliku {path}")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def search_products(self, widget):
        """Search products using the Shoper API."""
        try:
            filters = {}
            term = self.shoper_search_var.get().strip()
            number = self.shoper_number_var.get().strip()
            set_name = self.shoper_set_var.get().strip()
            category = self.shoper_category_var.get().strip()
            if term:
                filters["filters[name][like]"] = term
            if number:
                filters["filters[code][like]"] = number
            if set_name:
                filters["filters[set][like]"] = set_name
            if category:
                filters["filters[category]"] = category
            sort = self.shoper_sort_var.get().strip()
            data = self.shoper_client.search_products(filters=filters, sort=sort)
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
            else:
                top = tk.Toplevel(self.root)
                top.title("Wyniki")
                top.configure(bg=self.root.cget("background"))
                text = tk.Text(top, bg=self.root.cget("background"), fg="white")
                text.pack(expand=True, fill="both", padx=10, pady=10)
                text.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
                self.create_button(top, text="Zamknij", command=top.destroy).pack(pady=5)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def show_orders(self, widget):
        """Display new orders with storage location hints."""
        try:
            orders = self.shoper_client.list_orders({"filters[status]": "new"})
            orders_list = orders.get("list", orders)
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
                    locations = [self.location_from_code(c.strip()) for c in str(code).split(";") if c.strip()]
                    location = "; ".join(l for l in locations if l)
                    lines.append(
                        f" - {item.get('name')} x{item.get('quantity')} [{code}] {location}"
                    )
            widget.insert(tk.END, "\n".join(lines))
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
    @staticmethod
    def location_from_code(code: str) -> str:
        return storage.location_from_code(code)

    def open_magazyn_window(self):
        """Display storage occupancy inside the main window."""
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
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None

        self.root.minsize(1000, 700)
        self.magazyn_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.magazyn_frame.pack(expand=True, fill="both", padx=10, pady=10)

        img_path = os.path.join(os.path.dirname(__file__), "box.png")
        if os.path.exists(img_path):
            img = Image.open(img_path)
            img.thumbnail((150, 150))
        else:
            img = Image.new("RGB", (150, 150), "#111111")
        self.mag_box_photo = ImageTk.PhotoImage(img)

        container = tk.Frame(
            self.magazyn_frame, bg=self.root.cget("background")
        )
        container.pack(padx=10, pady=10)

        # Order boxes so that the grid layout is:
        # row0 -> K1 K2 K5 K6
        # row1 -> K3 K4 K7 K8
        self.mag_box_order = [1, 2, 5, 6, 3, 4, 7, 8]
        self.mag_canvases = []
        self.mag_labels = []
        for i, box_num in enumerate(self.mag_box_order):
            frame = tk.Frame(container, bg=self.root.cget("background"))
            lbl = tk.Label(frame, text=f"K{box_num}", bg=self.root.cget("background"))
            lbl.pack()
            canvas = tk.Canvas(
                frame,
                width=self.mag_box_photo.width(),
                height=self.mag_box_photo.height(),
                bg="#111111",
                highlightthickness=0,
            )
            canvas.create_image(0, 0, image=self.mag_box_photo, anchor="nw")
            canvas.pack()
            frame.grid(row=i // 4, column=i % 4, padx=5, pady=5)
            self.mag_canvases.append(canvas)
            self.mag_labels.append(lbl)

        btn_frame = tk.Frame(
            self.magazyn_frame, bg=self.root.cget("background")
        )
        btn_frame.pack(pady=5)

        self.create_button(
            btn_frame, text="Odśwież", command=self.refresh_magazyn
        ).pack(side="left", padx=5)

        self.create_button(
            btn_frame, text="Powrót", command=self.back_to_welcome
        ).pack(side="left", padx=5)

        self.refresh_magazyn()

    def compute_column_occupancy(self):
        """Return dictionary of used slots per box column."""
        return storage.compute_column_occupancy()

    def repack_column(self, box: int, column: int):
        """Renumber codes in the given column so there are no gaps."""
        storage.repack_column(box, column)
        self.refresh_magazyn()

    def refresh_magazyn(self):
        """Refresh storage view and color code capacity usage.

        A column's background turns orange when 30% or more of its
        capacity is still free.  Individual 100-card segments become
        green as soon as they are occupied.
        """
        occ = self.compute_column_occupancy()
        if not self.mag_canvases:
            return
        for idx, canvas in enumerate(self.mag_canvases):
            box = (
                self.mag_box_order[idx]
                if hasattr(self, "mag_box_order")
                else idx + 1
            )
            canvas.delete("stats")
            col_w = self.mag_box_photo.width() / 4
            canvas.create_image(0, 0, image=self.mag_box_photo, anchor="nw")
            for c in range(1, 5):
                filled = occ.get(box, {}).get(c, 0)
                free_percent = (1000 - filled) / 10
                x1 = (c - 1) * col_w
                x_mid = x1 + col_w / 2
                if free_percent >= 30:
                    canvas.create_rectangle(
                        x1,
                        0,
                        x1 + col_w,
                        self.mag_box_photo.height(),
                        fill="#ffcc80",
                        width=0,
                        tags="stats",
                    )
                # Draw 100-card sections
                filled_sections = filled // 100
                seg_h = self.mag_box_photo.height() / 10
                for i in range(10):
                    y1 = self.mag_box_photo.height() - seg_h * (i + 1)
                    y2 = self.mag_box_photo.height() - seg_h * i
                    color = "#c8f7c8" if i < filled_sections else ""
                    canvas.create_rectangle(
                        x1,
                        y1,
                        x1 + col_w,
                        y2,
                        fill=color,
                        outline="black",
                        width=1,
                        tags="stats",
                    )
                canvas.create_text(
                    x_mid,
                    self.mag_box_photo.height() / 2,
                    text=f"C{c}: {free_percent:.0f}%",
                    tags="stats",
                )

    def setup_pricing_ui(self):
        """UI for quick card price lookup."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
        # Set a sensible minimum size and allow resizing
        self.root.minsize(1000, 700)
        self.pricing_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.pricing_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.pricing_frame.columnconfigure(0, weight=1)
        self.pricing_frame.columnconfigure(1, weight=1)
        self.pricing_frame.rowconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.pricing_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                self.pricing_frame,
                image=self.pricing_logo_photo,
                bg=self.root.cget("background"),
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
        ).grid(row=0, column=0, padx=5)

        self.create_button(
            btn_frame,
            text="Powrót",
            command=self.back_to_welcome,
            width=120,
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
            text="Wyczyść",
            command=self.clear_price_pool,
            width=120,
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
                    img = Image.open(io.BytesIO(res.content))
                    img.thumbnail((240, 340))
                    self.pricing_photo = ImageTk.PhotoImage(img)
                    self.result_image_label = tk.Label(
                        self.result_frame,
                        image=self.pricing_photo,
                        bg=self.root.cget("background"),
                    )
                    self.result_image_label.pack(pady=5)
            except Exception as e:
                print(f"[ERROR] Loading image failed: {e}")

        if info.get("set_logo_url"):
            try:
                res = requests.get(info["set_logo_url"], timeout=10)
                if res.status_code == 200:
                    img = Image.open(io.BytesIO(res.content))
                    img.thumbnail((180, 60))
                    self.set_logo_photo = ImageTk.PhotoImage(img)
                    self.set_logo_label = tk.Label(
                        self.result_frame,
                        image=self.set_logo_photo,
                        bg=self.root.cget("background"),
                    )
                    self.set_logo_label.pack(pady=5)
            except Exception as e:
                print(f"[ERROR] Loading set logo failed: {e}")
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
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        if getattr(self, "auction_frame", None):
            self.auction_frame.destroy()
            self.auction_frame = None
        self.setup_welcome_screen()

    def setup_editor_ui(self):
        # Provide a minimum size and allow the editor to expand
        self.root.minsize(1000, 700)
        self.frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.frame.pack(expand=True, fill="both", padx=10, pady=10)
        # Allow widgets inside the frame to expand properly
        for i in range(6):
            self.frame.columnconfigure(i, weight=1)
        self.frame.rowconfigure(2, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
        self.logo_photo = ImageTk.PhotoImage(logo_img)
        self.logo_label = tk.Label(
            self.frame,
            image=self.logo_photo,
            bg=self.root.cget("background"),
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

        self.load_button = self.create_button(
            self.button_frame,
            text="Import",
            command=self.browse_scans,
        )
        self.load_button.pack(side="left", padx=5)

        self.end_button = self.create_button(
            self.button_frame,
            text="Zakończ i zapisz",
            command=self.export_csv,
        )
        self.end_button.pack(side="left", padx=5)

        self.back_button = self.create_button(
            self.button_frame,
            text="Powrót",
            command=self.back_to_welcome,
        )
        self.back_button.pack(side="left", padx=5)

        # Navigation buttons to move between loaded scans
        self.prev_button = self.create_button(
            self.button_frame,
            text="\u23ee Poprzednia",
            command=self.previous_card,
        )
        self.prev_button.pack(side="left", padx=5)

        self.next_button = self.create_button(
            self.button_frame,
            text="Nast\u0119pna \u23ed",
            command=self.next_card,
        )
        self.next_button.pack(side="left", padx=5)

        self.cheat_button = self.create_button(
            self.button_frame,
            text="\U0001F9FE \u015aci\u0105ga",
            command=self.toggle_cheatsheet,
        )
        self.cheat_button.pack(side="left", padx=5)

        # Keep a constant label size so the window does not resize when
        # scans of different dimensions are displayed
        self.image_label = ctk.CTkLabel(self.frame, width=400, height=560)
        self.image_label.grid(row=2, column=0, rowspan=12, sticky="nsew")
        self.image_label.grid_propagate(False)
        # Display only a textual progress indicator below the card image
        self.progress_label = ctk.CTkLabel(self.frame, textvariable=self.progress_var)
        self.progress_label.grid(row=14, column=0, pady=5, sticky="ew")

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
            self.info_frame, text="Język", bg=self.root.cget("background")
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
            self.info_frame, text="Nazwa", bg=self.root.cget("background")
        ).grid(
            row=start_row + 1, column=0, sticky="w", **grid_opts
        )
        self.entries["nazwa"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Nazwa"
        )
        self.entries["nazwa"].grid(row=start_row + 1, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Numer", bg=self.root.cget("background")
        ).grid(
            row=start_row + 2, column=0, sticky="w", **grid_opts
        )
        self.entries["numer"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Numer"
        )
        self.entries["numer"].grid(row=start_row + 2, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Set", bg=self.root.cget("background")
        ).grid(
            row=start_row + 3, column=0, sticky="w", **grid_opts
        )
        self.set_var = tk.StringVar()
        self.set_dropdown = ctk.CTkComboBox(
            self.info_frame, variable=self.set_var, width=20
        )
        self.set_dropdown.grid(row=start_row + 3, column=1, sticky="ew", **grid_opts)
        self.set_dropdown.bind("<KeyRelease>", self.filter_sets)
        self.set_dropdown.bind("<Tab>", self.autocomplete_set)
        self.entries["set"] = self.set_var

        tk.Label(
            self.info_frame, text="Typ", bg=self.root.cget("background")
        ).grid(
            row=start_row + 4, column=0, sticky="w", **grid_opts
        )
        self.type_vars = {}
        self.type_frame = ctk.CTkFrame(self.info_frame)
        self.type_frame.grid(row=start_row + 4, column=1, columnspan=7, sticky="w", **grid_opts)
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
            self.info_frame, text="Stan", bg=self.root.cget("background")
        ).grid(
            row=start_row + 5, column=0, sticky="w", **grid_opts
        )
        self.stan_var = tk.StringVar(value="NM")
        self.entries["stan"] = self.stan_var
        stan_dropdown = ctk.CTkComboBox(
            self.info_frame,
            variable=self.stan_var,
            values=["NM", "LP", "PL", "MP", "HP", "DMG"],
            width=20,
        )
        stan_dropdown.grid(row=start_row + 5, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Cena", bg=self.root.cget("background")
        ).grid(
            row=start_row + 6, column=0, sticky="w", **grid_opts
        )
        self.entries["cena"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Cena"
        )
        self.entries["cena"].grid(row=start_row + 6, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="PSA 10", bg=self.root.cget("background")
        ).grid(
            row=start_row + 7, column=0, sticky="w", **grid_opts
        )
        self.entries["psa10_price"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="PSA 10"
        )
        self.entries["psa10_price"].grid(
            row=start_row + 7, column=1, sticky="ew", **grid_opts
        )

        self.api_button = self.create_button(
            self.info_frame,
            text="Pobierz cenę z bazy",
            command=self.fetch_card_data,
        )
        self.api_button.grid(row=start_row + 8, column=0, columnspan=2, sticky="ew", **grid_opts)

        self.variants_button = self.create_button(
            self.info_frame,
            text="Inne warianty",
            command=self.show_variants,
        )
        self.variants_button.grid(
            row=start_row + 8, column=2, columnspan=2, sticky="ew", **grid_opts
        )

        self.cardmarket_button = self.create_button(
            self.info_frame,
            text="Cardmarket",
            command=self.open_cardmarket_search,
        )
        self.cardmarket_button.grid(
            row=start_row + 8, column=4, columnspan=2, sticky="ew", **grid_opts
        )

        self.save_button = self.create_button(
            self.info_frame,
            text="Zapisz i dalej",
            command=self.save_and_next,
        )
        self.save_button.grid(row=start_row + 9, column=0, columnspan=2, sticky="ew", **grid_opts)

        self.eur_entry = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Kwota w EUR"
        )
        self.eur_entry.grid(
            row=start_row + 10, column=0, columnspan=4, sticky="ew", **grid_opts
        )

        self.convert_button = self.create_button(
            self.info_frame,
            text="Przelicz",
            command=self.convert_eur_to_pln,
        )
        self.convert_button.grid(
            row=start_row + 10, column=4, columnspan=2, sticky="ew", **grid_opts
        )

        self.pln_result_label = ctk.CTkLabel(self.info_frame, text="PLN: -")
        self.pln_result_label.grid(
            row=start_row + 11, column=0, columnspan=6, sticky="ew", **grid_opts
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
        if lang == "JP":
            self.sets_file = "tcg_sets_jp.json"
            self.set_dropdown.configure(values=tcg_sets_jp)
        else:
            self.sets_file = "tcg_sets.json"
            self.set_dropdown.configure(values=tcg_sets_eng)
        if getattr(self, "cheat_frame", None) is not None:
            self.create_cheat_frame()

    def filter_sets(self, event=None):
        typed = self.set_var.get().lower()
        lang = self.lang_var.get().strip().upper()
        all_sets = tcg_sets_jp if lang == "JP" else tcg_sets_eng
        if typed:
            filtered = [s for s in all_sets if typed in s.lower()]
        else:
            filtered = all_sets
        self.set_dropdown.configure(values=filtered)

    def autocomplete_set(self, event=None):
        typed = self.set_var.get().lower()
        lang = self.lang_var.get().strip().upper()
        all_sets = tcg_sets_jp if lang == "JP" else tcg_sets_eng
        if typed:
            filtered = [s for s in all_sets if typed in s.lower()]
        else:
            filtered = all_sets
        if filtered:
            self.set_var.set(filtered[0])
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
                    tk.Label(
                        self.cheat_frame,
                        image=img,
                        bg=self.root.cget("background"),
                    ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
                else:
                    tk.Label(
                        self.cheat_frame,
                        text="",
                        width=2,
                        bg=self.root.cget("background"),
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
            messagebox.showerror(
                "Błąd", "Podaj poprawne wartości (kolumna 1-4, pozycja 1-1000)"
            )
            return
        if column < 1 or column > 4 or pos < 1 or pos > 1000:
            messagebox.showerror(
                "Błąd", "Podaj poprawne wartości (kolumna 1-4, pozycja 1-1000)"
            )
            return
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
        self.starting_idx = (box - 1) * 4000 + (column - 1) * 1000 + (pos - 1)
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
        self.progress_var.set(f"0/{len(self.cards)}")
        self.log(f"Loaded {len(self.cards)} cards")
        self.show_card()

    def show_card(self):
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

        self.progress_var.set(f"{self.index + 1}/{len(self.cards)}")

        image_path = self.cards[self.index]
        self.current_image_path = image_path
        cache_key = self.file_to_key.get(os.path.basename(image_path))
        if not cache_key:
            cache_key = self._guess_key_from_filename(image_path)
        inv_entry = self.lookup_inventory_entry(cache_key) if cache_key else None
        try:
            image = Image.open(image_path)
        except Exception as e:
            print(f"Failed to load image {image_path}: {e}", file=sys.stderr)
            if getattr(self, "failed_cards", None) is not None:
                self.failed_cards.append(image_path)
            self.index += 1
            self.show_card()
            return
        image.thumbnail((400, 560))
        self.current_card_image = image.copy()
        if hasattr(ctk, "CTkImage"):
            img = ctk.CTkImage(light_image=image, size=image.size)
        else:
            img = ImageTk.PhotoImage(image)
        self.image_objects.append(img)
        self.image_objects = self.image_objects[-2:]
        self.current_card_photo = img
        self.image_label.configure(image=img)
        if hasattr(self, "location_label"):
            self.location_label.configure(text=self.next_free_location())

        for key, entry in self.entries.items():
            if isinstance(entry, (tk.Entry, ctk.CTkEntry)):
                entry.delete(0, tk.END)
            elif isinstance(entry, tk.StringVar):
                if key == "język":
                    entry.set("ENG")
                elif key == "stan":
                    entry.set("NM")
                else:
                    entry.set("")
            elif isinstance(entry, tk.BooleanVar):
                entry.set(False)

        for var in self.type_vars.values():
            var.set(False)

        skip_analysis = False
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
            self.update_set_options()
            skip_analysis = True

        folder = os.path.basename(os.path.dirname(image_path))
        if not skip_analysis:
            self.start_scan_animation()
            threading.Thread(
                target=self._analyze_and_fill,
                args=(image_path, self.index),
                daemon=True,
            ).start()
        else:
            if hasattr(self, "prompt_set_selection"):
                try:
                    with Image.open(image_path) as im:
                        rects = get_symbol_rects(*im.size)
                    matches = []
                    for r in rects:
                        matches = identify_set_by_hash(image_path, r)
                        if matches:
                            break
                except Exception:
                    matches = []
                options = [(c, n) for c, n, _ in matches]
                if options:
                    try:
                        self.prompt_set_selection(options)
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
            return f"{name}|{number}|{set_name}"
        return None

    def start_scan_animation(self, index=0):
        """Show the scanning GIF on top of the image label."""
        path = os.path.join(os.path.dirname(__file__), "scan.gif")
        w = self.image_label.winfo_width() or 400
        h = self.image_label.winfo_height() or 560
        if os.path.exists(path) and hasattr(self, "current_card_image"):
            from PIL import ImageSequence

            img = Image.open(path)
            frames = []
            durations = []
            base = (
                self.current_card_image.convert("RGBA")
                .resize((w, h))
                .filter(ImageFilter.GaussianBlur(radius=2))
            )
            for frame in ImageSequence.Iterator(img):
                overlay = frame.convert("RGBA").resize((w, h))
                composed = Image.alpha_composite(base, overlay)
                if hasattr(ctk, "CTkImage"):
                    frames.append(ctk.CTkImage(light_image=composed, size=(w, h)))
                else:
                    frames.append(ImageTk.PhotoImage(composed))
                durations.append(frame.info.get("duration", 100))
            self.scan_gif_frames = frames
            self.scan_gif_durations = durations
            self.scan_gif_size = (w, h)
        else:
            self.scan_gif_frames = []
        if not self.scan_gif_frames:
            return
        self.scan_animation_running = True
        self._animate_scan_gif(index)

    def _animate_scan_gif(self, index=0):
        if not getattr(self, "scan_animation_running", False):
            return
        frame = self.scan_gif_frames[index]
        self.image_label.configure(image=frame)
        next_index = (index + 1) % len(self.scan_gif_frames)
        delay = self.scan_gif_durations[index] if hasattr(self, "scan_gif_durations") else 100
        self.scan_after_id = self.image_label.after(delay, self._animate_scan_gif, next_index)

    def stop_scan_animation(self):
        """Hide the scanning GIF."""
        self.scan_animation_running = False
        if hasattr(self, "scan_after_id"):
            try:
                self.image_label.after_cancel(self.scan_after_id)
            except Exception:
                pass
        if hasattr(self, "current_card_photo"):
            self.image_label.configure(image=self.current_card_photo)

    def _analyze_and_fill(self, path, idx):
        lang_var = getattr(self, "lang_var", None)
        translate = False
        if lang_var is not None:
            try:
                translate = lang_var.get() == "JP"
            except Exception:
                translate = False
        result = analyze_card_image(path, translate_name=translate)
        self.root.after(0, lambda: self._apply_analysis_result(result, idx))

    def _apply_analysis_result(self, result, idx):
        if idx != self.index:
            return
        self.stop_scan_animation()
        if result:
            name = result.get("name", "")
            number = result.get("number", "")
            total = result.get("total") or ""
            if not total and isinstance(number, str):
                m = re.match(r"(\d+)\s*/\s*(\d+)", number)
                if m:
                    number, total = m.group(1), m.group(2)
            set_name = result.get("set", "")
            number = sanitize_number(str(number))
            self.entries["nazwa"].delete(0, tk.END)
            self.entries["nazwa"].insert(0, name)
            self.entries["numer"].delete(0, tk.END)
            self.entries["numer"].insert(0, number)
            self.entries["set"].set(set_name)
            self.update_set_options()
        return

    def prompt_set_selection(self, options: list[tuple[str, str]]):
        """Display a dialog with candidate set logos for manual selection.

        Parameters
        ----------
        options:
            List of ``(set_code, set_name)`` tuples. Only the first four are
            shown.

        Returns
        -------
        str
            Selected ``set_code`` or the first option when no choice is made.
        """

        if not options:
            return ""

        options = options[:4]

        # Load logos if they haven't been loaded yet
        if not getattr(self, "set_logos", None):
            try:
                self.load_set_logos()
            except Exception:
                pass

        selected = {"code": options[0][0]}

        def apply_selection(code: str):
            selected["code"] = code
            name = get_set_name(code) or code
            if hasattr(self, "set_var"):
                try:
                    self.set_var.set(name)
                except Exception:
                    pass
            if "set" in getattr(self, "entries", {}):
                entry = self.entries["set"]
                try:
                    entry.set(name)
                except Exception:
                    try:
                        entry.delete(0, tk.END)
                        entry.insert(0, name)
                    except Exception:
                        pass
            if hasattr(self, "update_set_options"):
                try:
                    self.update_set_options()
                except Exception:
                    pass

        # In headless environments, avoid creating GUI windows
        try:
            top = ctk.CTkToplevel(self.root, fg_color=BG_COLOR)
        except Exception:
            apply_selection(options[0][0])
            return selected["code"]

        top.title("Wybierz set")
        images = []

        for i, (code, name) in enumerate(options):
            img = self.set_logos.get(code)
            if img is None:
                path = os.path.join(SET_LOGO_DIR, f"{code}.png")
                if os.path.exists(path):
                    try:
                        logo_img = Image.open(path)
                        logo_img.thumbnail((40, 40))
                        img = ImageTk.PhotoImage(logo_img)
                        self.set_logos[code] = img
                    except Exception:
                        img = None
            if img is not None:
                btn = ctk.CTkButton(
                    top,
                    image=img,
                    text="",
                    fg_color=ACCENT_COLOR,
                    text_color=TEXT_COLOR,
                    hover_color=HOVER_COLOR,
                    command=lambda c=code: (apply_selection(c), top.destroy()),
                )
                btn.grid(row=0, column=i, padx=5, pady=5)
                ctk.CTkLabel(top, text=name, text_color=TEXT_COLOR).grid(
                    row=1, column=i, padx=5, pady=2
                )
            else:
                btn = ctk.CTkButton(
                    top,
                    text=name,
                    fg_color=ACCENT_COLOR,
                    text_color=TEXT_COLOR,
                    hover_color=HOVER_COLOR,
                    command=lambda c=code: (apply_selection(c), top.destroy()),
                )
                btn.grid(row=0, column=i, padx=5, pady=5)
            images.append(img)
            top.grid_columnconfigure(i, weight=1, minsize=100)

        # keep references to prevent garbage collection
        top.images = images
        try:
            top.update_idletasks()
            w = top.winfo_width()
            h = top.winfo_height()
            min_width = len(options) * 120
            w = max(w, min_width)
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = int(screen_w / 2 - w / 2)
            y = int(screen_h / 2 - h / 2)
            top.geometry(f"{w}x{h}+{x}+{y}")
            top.transient(self.root)
            top.grab_set()
            top.wait_window()
        except Exception:
            pass

        return selected["code"]

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
            try:
                img = Image.open(path)
                img.thumbnail((40, 40))
                self.set_logos[code] = ImageTk.PhotoImage(img)
            except Exception:
                continue

    def show_loading_screen(self):
        """Display a temporary loading screen during startup."""
        self.root.minsize(1000, 700)
        self.loading_frame = ctk.CTkFrame(self.root, fg_color=BG_COLOR)
        self.loading_frame.pack(expand=True, fill="both")
        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            img.thumbnail((300, 150))
            self.loading_logo = ImageTk.PhotoImage(img)
            tk.Label(
                self.loading_frame,
                image=self.loading_logo,
                bg=self.loading_frame.cget("fg_color"),
            ).pack(pady=10)

        gif_path = os.path.join(os.path.dirname(__file__), "simple_pokeball.gif")
        if os.path.exists(gif_path):
            from PIL import ImageSequence

            img = Image.open(gif_path)
            self.gif_frames = []
            self.gif_durations = []
            for frame in ImageSequence.Iterator(img):
                self.gif_frames.append(ImageTk.PhotoImage(frame.copy()))
                self.gif_durations.append(frame.info.get("duration", 100))

            self.gif_label = tk.Label(
                self.loading_frame, bg=self.loading_frame.cget("fg_color")
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
        """Run initial setup tasks in the background."""
        self.update_sets()
        self.root.after(0, self.load_set_logos)
        self.root.after(1, self.finish_startup)

    def finish_startup(self):
        """Finalize initialization after background tasks complete."""
        if self.loading_frame is not None:
            self.loading_frame.destroy()
        try:
            if not SHOPER_API_URL or not SHOPER_API_TOKEN:
                raise ValueError("Brak konfiguracji Shoper API")
            self.shoper_client = ShoperClient(SHOPER_API_URL, SHOPER_API_TOKEN)
        except Exception as e:
            print(f"[ERROR] ShoperClient init failed: {e}")
            self.shoper_client = None
        if not self.shoper_client:
            messagebox.showerror(
                "Błąd", "Nie można połączyć się z API Shoper. Sprawdź dane w pliku .env."
            )
        self.setup_welcome_screen()

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
        except Exception:
            current_sets = {}

        timeout = getattr(self, "API_TIMEOUT", 10)
        for attempt in range(3):
            try:
                resp = requests.get(
                    "https://api.pokemontcg.io/v2/sets", timeout=timeout
                )
                resp.raise_for_status()
                remote = resp.json().get("data", [])
                break
            except Exception as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                self.log(
                    "Nie udało się odświeżyć listy setów. Użyte zostaną dane offline."
                )
                print(f"[WARN] Unable to fetch sets: {exc}")
                return

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
            except Exception:
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
                print(f"[ERROR] API error: {response.status_code}")
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
                    print(
                        f"[INFO] Cena {best.get('name')} ({number_input}, {set_input}) = {price_pln} PLN"
                    )
                    return price_pln

            print("\n[DEBUG] Nie znaleziono dokładnej karty. Zbliżone:")
            for card in cards:
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()
                if number_input == card_number and set_input in card_set:
                    print(
                        f"- {card.get('name')} | {card_number} | {card.get('episode', {}).get('name')}"
                    )

        except requests.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Fetching price from TCGGO failed: {e}")
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
            except Exception:
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
                    psa10 = (
                        card.get("prices", {})
                        .get("cardmarket", {})
                        .get("graded", {})
                        .get("psa", {})
                        .get("psa10")
                    )
                    try:
                        if psa10 is None:
                            return ""
                        rate = self.get_exchange_rate()
                        price_pln = round(float(psa10) * rate, 2)
                        return (
                            str(int(price_pln))
                            if price_pln.is_integer()
                            else str(price_pln)
                        )
                    except (TypeError, ValueError):
                        return ""
            return ""
        except requests.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Fetching PSA10 price failed: {e}")
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
            except Exception:
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
                print(f"[ERROR] API error: {response.status_code}")
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
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Fetching variants from TCGGO failed: {e}")
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
            except Exception:
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
                print(f"[ERROR] API error: {response.status_code}")
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
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Lookup failed: {e}")
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
                if len(api_sets) > 1:
                    self.log(f"Znaleziono {len(api_sets)} pasujących setów, proszę wybrać.")
                    selected_code = self.prompt_set_selection(api_sets)
                else:
                    selected_code = api_sets[0][0]
                
                resolved_name = get_set_name(selected_code) or next((n for c, n in api_sets if c == selected_code), "")
                self.entries["set"].set(resolved_name)
                set_name = resolved_name # Zaktualizuj zmienną lokalną
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

    def show_variants(self):
        """Display a list of matching cards from the API."""
        name = self.entries["nazwa"].get()
        number = sanitize_number(self.entries["numer"].get())
        set_name = self.entries["set"].get()

        is_reverse = self.type_vars["Reverse"].get()
        is_holo = self.type_vars["Holo"].get()

        variants = self.fetch_card_variants(name, number, set_name)
        if not variants:
            messagebox.showinfo("Brak wyników", "Nie znaleziono dodatkowych wariantów.")
            self.open_cardmarket_search()
            return

        top = ctk.CTkToplevel(self.root)
        top.title("Inne warianty")
        top.geometry("600x400")

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((140, 140))
            top.logo_image = ctk.CTkImage(light_image=logo_img, size=logo_img.size)
            ctk.CTkLabel(top, image=top.logo_image, text="").pack(pady=(10, 10))

        columns = ("name", "number", "set", "price")
        tree = ttk.Treeview(top, columns=columns, show="headings")
        tree.heading("name", text="Nazwa")
        tree.heading("number", text="Numer")
        tree.heading("set", text="Set")
        tree.heading("price", text="Cena (PLN)")

        for card in variants:
            price = self.apply_variant_multiplier(
                card["price"], is_reverse=is_reverse, is_holo=is_holo
            )
            tree.insert(
                "", "end", values=(card["name"], card["number"], card["set"], price)
            )

        tree.pack(expand=True, fill="both", padx=10, pady=10)

        def set_selected_price(event=None):
            selected = tree.selection()
            if not selected:
                return
            values = tree.item(selected[0], "values")
            self.entries["cena"].delete(0, tk.END)
            self.entries["cena"].insert(0, values[3])
            top.destroy()

        self.create_button(top, text="Ustaw cenę", command=set_selected_price).pack(pady=5)
        tree.bind("<Double-1>", set_selected_price)

    def open_cardmarket_search(self):
        """Open a Cardmarket search for the current card inside the app."""
        name = self.entries["nazwa"].get()
        number = sanitize_number(self.entries["numer"].get())
        search_terms = " ".join(t for t in [name, number] if t)
        params = urlencode({"searchString": search_terms})
        url = f"https://www.cardmarket.com/en/Pokemon/Products/Search?{params}"

        try:
            from tkinterweb import HtmlFrame, utilities
        except ModuleNotFoundError:
            messagebox.showwarning(
                "Brak modułu",
                "Moduł 'tkinterweb' nie jest zainstalowany.\n"
                "Aby korzystać z wbudowanej przeglądarki, zainstaluj go poleceniem:\n"
                "pip install tkinterweb",
            )
            return

        top = ctk.CTkToplevel(self.root)
        top.title("Cardmarket Search")
        top.geometry("800x600")

        browser = HtmlFrame(top, messages_enabled=False)
        browser.pack(fill="both", expand=True)
        try:
            utilities.HEADERS["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            )
            browser.load_website(url)
        except HTTPError as e:
            messagebox.showerror(
                "Błąd", f"Nie udało się wczytać Cardmarket ({e.code})."
            )
            top.destroy()
            webbrowser.open(url)
            return

        self.create_button(top, text="Close", command=top.destroy).pack(pady=5)

    def get_exchange_rate(self):
        try:
            res = requests.get(
                "https://api.nbp.pl/api/exchangerates/rates/A/EUR/?format=json",
                timeout=10,
            )
            if res.status_code == 200:
                return res.json()["rates"][0]["mid"]
        except requests.Timeout:
            print("[ERROR] Exchange rate request timed out")
        except Exception:
            pass
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
        data = {k: v.get() for k, v in self.entries.items()}
        data.setdefault("psa10_price", "")
        data["typ"] = ",".join(
            [name for name, var in self.type_vars.items() if var.get()]
        )
        key = f"{data['nazwa']}|{data['numer']}|{data['set']}"
        data["ilość"] = 1
        self.card_cache[key] = {
            "entries": {k: v for k, v in data.items()},
            "types": {name: var.get() for name, var in self.type_vars.items()},
        }

        front_path = self.cards[self.index]
        front_file = os.path.basename(front_path)
        self.file_to_key[front_file] = key

        data["image1"] = f"{BASE_IMAGE_URL}/{self.folder_name}/{front_file}"
        data["product_code"] = self.next_product_code
        self.next_product_code += 1
        data["unit"] = "szt."
        data["category"] = f"Karty Pokémon > {data['set']}"
        data["producer"] = "Pokémon"
        data["producer_code"] = data["numer"]
        data["currency"] = "PLN"
        data["seo_title"] = ""
        data["seo_description"] = ""
        data["seo_keywords"] = ""

        name = html.escape(data["nazwa"])
        number = html.escape(data["numer"])
        set_name = html.escape(data["set"])
        card_type = html.escape(data["typ"])
        condition = html.escape(data["stan"])

        data["short_description"] = (
            f"<p><strong>{name}</strong></p>"
            "<!-- <ul> -->"
            f'<ul style="margin:0 0 0.7em 1.2em;">'
            f'<li>Zestaw: {set_name}</li>'
            f'<li>Numer karty: {number}</li>'
            f'<li>Typ: {card_type}</li>'
            f'<li>Stan: {condition}</li>'
            "</ul>"
        )

        desc_template = (
            '<div style="font-size:1.10em;line-height:1.7;">'
            '<p>{name} – Pokémon TCG</p>'
            '<p>Karta pochodzi z zestawu {set} i ma numer {number}. '
            'Typ karty: {type}. Stan: {condition}.</p>'
            '<p>Każda karta jest dokładnie sprawdzana przed wysyłką i odpowiednio '
            'zabezpieczana – trafia do Ciebie w idealnym stanie, gotowa do gry lub kolekcji.</p>'
            '<p>Zdjęcia przedstawiają rzeczywisty produkt lub jego odpowiednik. Jeśli szukasz więcej kart z tego setu – sprawdź pozostałe oferty.</p>'
            '</div>'
        )
        data["description"] = desc_template.format(
            name=name,
            set=set_name,
            number=number,
            condition=condition,
            type=card_type,
        )

        data["availability"] = 1
        data["delivery"] = SHOPER_DELIVERY_ID

        cena_local = self.get_price_from_db(data["nazwa"], data["numer"], data["set"])
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

    def save_and_next(self):
        """Save the current card data and display the next scan."""
        self.save_current_data()
        self.index += 1
        self.show_card()

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

    def load_csv_data(self):
        """Load a CSV file and merge duplicate rows."""
        csv_utils.load_csv_data(self)

    def export_csv(self):
        self.in_scan = False
        csv_utils.export_csv(self)

    def upload_images_dialog(self):
        """Upload images from a selected directory via FTP."""
        directory = filedialog.askdirectory()
        if not directory:
            return
        host = simpledialog.askstring("FTP", "Serwer", initialvalue=FTP_HOST or "")
        user = simpledialog.askstring("FTP", "Użytkownik", initialvalue=FTP_USER or "")
        password = simpledialog.askstring("FTP", "Hasło", show="*", initialvalue=FTP_PASSWORD or "")
        if not host or not user or not password:
            messagebox.showerror("Błąd", "Nie podano pełnych danych logowania")
            return
        try:
            with FTPClient(host, user, password) as ftp:
                ftp.upload_directory(directory)
            messagebox.showinfo("Sukces", "Obrazy zostały wysłane na serwer FTP")
        except Exception as exc:
            messagebox.showerror("Błąd", f"Nie udało się wysłać obrazów: {exc}")

    def send_csv_to_shoper(self, file_path: str):
        """Send a CSV file using the Shoper API or FTP fallback."""
        csv_utils.send_csv_to_shoper(self, file_path)

