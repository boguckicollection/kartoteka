import csv
import os
import re
from datetime import date, timedelta
from typing import Any, Mapping, Optional, Tuple
from tkinter import filedialog, messagebox, TclError
import unicodedata

import logging

from webdav_client import WebDAVClient
INVENTORY_CSV = os.getenv(
    "INVENTORY_CSV", os.getenv("WAREHOUSE_CSV", "magazyn.csv")
)
WAREHOUSE_CSV = os.getenv("WAREHOUSE_CSV", INVENTORY_CSV)
STORE_EXPORT_CSV = os.getenv("STORE_EXPORT_CSV", "store_export.csv")

# Track last modification time and cached statistics for the warehouse CSV
WAREHOUSE_CSV_MTIME: Optional[float] = None
_inventory_stats_cache: Optional[Tuple[int, float, int, float]] = None
_inventory_stats_path: Optional[str] = None

# column order for exported CSV files
STORE_FIELDNAMES = [
    "product_code",
    "name",
    "producer_code",
    "category",
    "producer",
    "short_description",
    "description",
    "price",
    "currency",
    "availability",
    "unit",
    "delivery",
    "stock",
    "active",
    "seo_title",
    "vat",
    "images 1",
]

# include a ``sold`` flag so individual cards can be marked as sold and track
# when cards were added to the warehouse
WAREHOUSE_FIELDNAMES = [
    "name",
    "number",
    "set",
    "warehouse_code",
    "price",
    "image",
    "variant",
    "sold",
    "added_at",
]


logger = logging.getLogger(__name__)


def get_warehouse_inventory():
    """Wczytuje całą zawartość pliku magazyn.csv."""
    try:
        with open(WAREHOUSE_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            return list(reader)
    except FileNotFoundError:
        logger.error(f"Plik magazynu {WAREHOUSE_CSV} nie został znaleziony.")
        return []
    except Exception as e:
        logger.error(f"Błąd odczytu pliku {WAREHOUSE_CSV}: {e}")
        return []

def _ensure_warehouse_csv_exists(path: str = WAREHOUSE_CSV) -> None:
    """Create an empty warehouse CSV with headers when missing."""

    if not path:
        return

    directory = os.path.dirname(path)
    try:
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        if os.path.exists(path):
            return
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(WAREHOUSE_FIELDNAMES)
    except OSError as exc:  # pragma: no cover - best effort logging
        logger.warning("Unable to initialise warehouse CSV at %s: %s", path, exc)


_ensure_warehouse_csv_exists()


def load_store_export(path: str = STORE_EXPORT_CSV) -> dict[str, dict[str, str]]:
    """Return mapping of ``product_code`` to rows from the store export CSV.

    Parameters
    ----------
    path:
        Optional path to the store export CSV.  Defaults to
        :data:`STORE_EXPORT_CSV`.

    Returns
    -------
    dict[str, dict[str, str]]
        Mapping where keys are product codes and values are the corresponding
        CSV rows.  Missing files result in an empty mapping.
    """

    data: dict[str, dict[str, str]] = {}
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                code = (row.get("product_code") or "").strip()
                if code:
                    data[code] = row
    except OSError:
        return {}
    return data


def _sanitize_number(value: str) -> str:
    """Return ``value`` without leading zeros.

    Parameters
    ----------
    value:
        Raw number string.

    Returns
    -------
    str
        Normalised number or ``"0"`` if the result is empty.
    """

    return value.strip().lstrip("0") or "0"


VARIANT_CODE_TO_NAME = {"C": "common", "H": "holo", "R": "reverse"}
VARIANT_SUFFIXES = {name: code for code, name in VARIANT_CODE_TO_NAME.items()}


def try_normalize_variant_code(value: Any) -> Optional[str]:
    """Return the variant code (``C``, ``H`` or ``R``) when recognised."""

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        normalized = unicodedata.normalize("NFKD", stripped)
        ascii_variant = "".join(ch for ch in normalized if not unicodedata.combining(ch)) or stripped
        upper = ascii_variant.upper()
        if upper in VARIANT_CODE_TO_NAME:
            return upper
        lower = ascii_variant.lower()
        if lower in VARIANT_SUFFIXES:
            return VARIANT_SUFFIXES[lower]
    return None


def normalize_variant_code(value: Any, *, default: str = "C") -> str:
    """Return a variant code, falling back to ``default`` when unknown."""

    return try_normalize_variant_code(value) or default


def variant_code_to_name(code: str, *, default: str = "common") -> str:
    """Return the textual name for ``code``."""

    return VARIANT_CODE_TO_NAME.get(code, default)


def infer_variant_code(data: Mapping[str, Any] | None) -> str:
    """Infer variant code from ``data`` supporting legacy structures."""

    if not data:
        return "C"
    for key in ("card_type", "variant", "typ"):
        code = try_normalize_variant_code(data.get(key))
        if code:
            return code
    types = data.get("types") if isinstance(data, Mapping) else None
    if isinstance(types, Mapping):
        if types.get("Holo") or types.get("holo"):
            return "H"
        if types.get("Reverse") or types.get("reverse"):
            return "R"
    return "C"


def build_product_code(
    set_name: str,
    number: str,
    variant: str | None = None,
    ball_suffix: str | None = None,
) -> str:
    """Return a product code based on set abbreviation and card number."""
    from .ui import get_set_abbr  # local import to avoid circular dependency

    abbr = get_set_abbr(set_name)
    if not abbr:
        sanitized = re.sub(r"[^A-Za-z0-9]", "", set_name).upper()
        abbr = sanitized[:3]
    num = _sanitize_number(str(number))
    variant_code = normalize_variant_code(variant)
    ball = (ball_suffix or "").strip().upper()
    if ball not in {"P", "M"}:
        ball = ""
    return f"PKM-{abbr}-{num}{variant_code}{ball}"


def infer_product_code(data: Mapping[str, Any] | None) -> str:
    """Return a product code derived from ``data`` when available."""

    if not data:
        return ""

    for key in ("product_code", "code", "producer_code"):
        value = str(data.get(key) or "").strip()
        if value:
            return value

    set_name = data.get("set") or data.get("set_name") or ""
    number = data.get("number") or data.get("numer") or ""
    variant = data.get("variant") or data.get("card_type")
    ball = data.get("ball") or data.get("ball_suffix")
    if not set_name or not number:
        return ""

    try:
        return build_product_code(set_name, number, variant, ball)
    except Exception:
        return ""


def decrement_store_stock(product_counts: Mapping[str, int]):
    """Zmniejsza stan magazynowy ('availability') w store_export.csv i prosi o potwierdzenie."""
    if not product_counts:
        return
    try:
        with open(STORE_EXPORT_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            fieldnames = reader.fieldnames
    except FileNotFoundError:
        logger.warning(f"Plik {STORE_EXPORT_CSV} nie został znaleziony.")
        return

    if not fieldnames or "product_code" not in fieldnames or "availability" not in fieldnames:
        logger.error(f"Plik {STORE_EXPORT_CSV} ma nieprawidłowe nagłówki.")
        return

    for row in rows:
        product_code = row.get("product_code")
        if product_code in product_counts:
            current_stock = int(row.get("availability", 0))
            sold_quantity = product_counts[product_code]
            row["availability"] = str(max(0, current_stock - sold_quantity))

    if messagebox.askyesno("Potwierdzenie zapisu", f"Czy na pewno chcesz zapisać zmiany stanów magazynowych w pliku {os.path.basename(STORE_EXPORT_CSV)}?"):
        try:
            with open(STORE_EXPORT_CSV, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"Plik {STORE_EXPORT_CSV} został zaktualizowany.")
        except OSError as e:
            logger.error(f"Błąd zapisu do pliku {STORE_EXPORT_CSV}: {e}")
    else:
        logger.info("Zapis do store_export.csv anulowany przez użytkownika.")


def mark_warehouse_codes_as_sold(codes, *, path: str | None = None) -> int:
    """Mark cards associated with ``codes`` as sold in the warehouse CSV.

    The helper understands grouped entries where multiple warehouse codes are
    stored in a single CSV row.  When such a row contains both sold and unsold
    codes the function keeps the unsold codes together and duplicates the row
    with the sold flag set for each sold code.  This mirrors how the magazyn
    view groups cards while ensuring sold entries are removed from future
    exports.

    Parameters
    ----------
    codes:
        Iterable with warehouse codes to mark as sold.  Empty or falsy entries
        are ignored.
    path:
        Optional explicit path to the CSV file.  When omitted the configured
        :data:`WAREHOUSE_CSV` is used.

    Returns
    -------
    int
        Number of codes that were successfully marked as sold.
    """

    codes_to_mark = [c.strip() for c in (codes or []) if str(c).strip()]
    if not codes_to_mark:
        return 0

    csv_path = path or WAREHOUSE_CSV
    if not csv_path:
        return 0

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            fieldnames = reader.fieldnames or WAREHOUSE_FIELDNAMES
    except FileNotFoundError:
        return 0

    sold_codes: set[str] = set()
    updated_rows: list[dict[str, str]] = []

    for row in rows:
        raw_codes = str(row.get("warehouse_code") or "")
        split_codes = [c.strip() for c in raw_codes.split(";") if c.strip()]
        matches = [c for c in split_codes if c in codes_to_mark]

        if not matches:
            updated_rows.append(row)
            continue

        remaining = [c for c in split_codes if c not in matches]
        if remaining:
            unsold_row = dict(row)
            unsold_row["warehouse_code"] = ";".join(remaining)
            # ensure unsold row does not inherit a sold flag
            if str(unsold_row.get("sold") or "").lower() in {"1", "true", "yes"}:
                unsold_row["sold"] = ""
            updated_rows.append(unsold_row)

        for code in matches:
            sold_row = dict(row)
            sold_row["warehouse_code"] = code
            sold_row["sold"] = "1"
            updated_rows.append(sold_row)
            sold_codes.add(code)

    if not sold_codes:
        return 0

    if "sold" not in fieldnames:
        fieldnames = list(fieldnames) + ["sold"]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(updated_rows)

    return len(sold_codes)


def find_duplicates(
    name: str, number: str, set_name: str, variant: str | None = None
):
    """Return rows from ``WAREHOUSE_CSV`` matching the given card details.

    Parameters
    ----------
    name, number, set_name:
        Card attributes to match against ``WAREHOUSE_CSV`` entries.
    variant:
        Optional card variant. When ``None`` or falsy any variant matches.

    Returns
    -------
    list[dict[str, str]]
        List of matching rows including warehouse codes.
    """

    from .ui import normalize  # local import to avoid circular dependency

    matches = []
    number = _sanitize_number(str(number))
    name_norm = normalize(name)
    set_norm = normalize(set_name)
    requested_code = try_normalize_variant_code(variant)

    if not os.path.exists(WAREHOUSE_CSV):
        return matches

    try:
        with open(WAREHOUSE_CSV, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                row_number = _sanitize_number(str(row.get("number", "")))
                row_name = normalize(row.get("name") or "")
                row_set = normalize(row.get("set") or "")
                row_variant_code = infer_variant_code(row)
                if (
                    row_name == name_norm
                    and row_number == number
                    and row_set == set_norm
                    and (requested_code is None or row_variant_code == requested_code)
                ):
                    matches.append(row)
    except OSError:
        pass

    return matches


def get_row_by_code(code: str, path: str = WAREHOUSE_CSV) -> Optional[dict[str, str]]:
    """Return the first row in ``path`` matching ``code``.

    Parameters
    ----------
    code:
        Warehouse code identifying a card.
    path:
        Optional path to the warehouse CSV. Defaults to :data:`WAREHOUSE_CSV`.

    Returns
    -------
    dict | None
        Matching row or ``None`` when the code is not found or the file is
        inaccessible.
    """

    code = (code or "").strip()
    if not code:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                codes = [c.strip() for c in str(row.get("warehouse_code") or "").split(";") if c.strip()]
                if code in codes:
                    return row
    except OSError:
        return None
    return None


def get_inventory_stats(path: str = WAREHOUSE_CSV, force: bool = False):
    """Return statistics for both unsold and sold items in the warehouse CSV.

    Parameters
    ----------
    path:
        Optional path to the warehouse CSV. Defaults to ``WAREHOUSE_CSV``.

    Returns
    -------
    tuple[int, float, int, float]
        ``(count_unsold, total_unsold, count_sold, total_sold)`` where each
        count is the number of rows and each total is the sum of the ``price``
        column for items in the respective category.
    """

    count_unsold = 0
    total_unsold = 0.0
    count_sold = 0
    total_sold = 0.0

    global WAREHOUSE_CSV_MTIME, _inventory_stats_cache, _inventory_stats_path

    # Determine current modification time if the file exists
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        current_mtime = None

    cache_valid = (
        not force
        and _inventory_stats_cache is not None
        and _inventory_stats_path == path
        and WAREHOUSE_CSV_MTIME == current_mtime
    )

    if cache_valid:
        return _inventory_stats_cache

    if not os.path.exists(path):
        _inventory_stats_cache = (
            count_unsold,
            total_unsold,
            count_sold,
            total_sold,
        )
        _inventory_stats_path = path
        WAREHOUSE_CSV_MTIME = current_mtime
        return _inventory_stats_cache

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            sold_flag = str(row.get("sold") or "").lower() in {"1", "true", "yes"}
            price_raw = str(row.get("price") or "0").replace(",", ".")
            try:
                price = float(price_raw)
            except ValueError:
                continue

            if sold_flag:
                count_sold += 1
                total_sold += price
            else:
                count_unsold += 1
                total_unsold += price

    _inventory_stats_cache = (
        count_unsold,
        total_unsold,
        count_sold,
        total_sold,
    )
    _inventory_stats_path = path
    WAREHOUSE_CSV_MTIME = current_mtime
    return _inventory_stats_cache


def get_daily_additions(days: int = 7) -> dict[str, int]:
    """Return counts of cards added per day for the last ``days`` days."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    counts = {
        (start + timedelta(days=i)).isoformat(): 0 for i in range(days)
    }
    if not os.path.exists(WAREHOUSE_CSV):
        return counts

    with open(WAREHOUSE_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            added_raw = (row.get("added_at") or "").split("T", 1)[0]
            try:
                added_date = date.fromisoformat(added_raw)
            except ValueError:
                continue
            if start <= added_date <= end:
                counts[added_date.isoformat()] += 1
    return counts


def format_store_row(row):
    """Return a row formatted for the store CSV."""
    formatted_name = row["nazwa"]

    return {
        "product_code": row["product_code"],
        "name": formatted_name,
        "producer_code": row.get("producer_code") or row.get("numer", ""),
        "category": row["category"],
        "producer": row["producer"],
        "short_description": row["short_description"],
        "description": row["description"],
        "price": row["cena"],
        "currency": row.get("currency", "PLN"),
        "availability": row.get("availability", 1),
        "unit": row.get("unit", "szt."),
        "delivery": "3 dni",
        "stock": row.get("stock", 1),
        "active": row.get("active", 1),
        "seo_title": row.get("seo_title", ""),
        "vat": row.get("vat", "23%"),
        "images 1": row.get("image1", row.get("images", "")),
    }


def format_warehouse_row(row):
    """Return a row formatted for the warehouse CSV."""
    variant_code = infer_variant_code(row)
    variant = variant_code_to_name(variant_code)
    return {
        "name": row.get("nazwa", ""),
        "number": row.get("numer", ""),
        "set": row.get("set", ""),
        "warehouse_code": row.get("warehouse_code", ""),
        "price": row.get("cena") or row.get("price", ""),
        "image": row.get("image1", row.get("images", "")),
        "variant": variant,
        "sold": row.get("sold", ""),
        "added_at": row.get("added_at") or date.today().isoformat(),
    }


def load_csv_data(app):
    """Load a CSV file and merge duplicate rows."""
    file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
    if not file_path:
        return

    with open(file_path, encoding="utf-8") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)

        def norm_header(name: str) -> str:
            normalized = name.strip().lower()
            if normalized == "images 1":
                return "image1"
            return normalized

        fieldnames = [norm_header(fn) for fn in reader.fieldnames or []]
        rows = []
        for raw_row in reader:
            row = {(norm_header(k) if k else k): v for k, v in raw_row.items()}
            if "warehouse_code" not in row and re.match(r"k\d+r\d+p\d+", str(row.get("product_code", "")).lower()):
                row["warehouse_code"] = row["product_code"]
                row["product_code"] = ""
                if "warehouse_code" not in fieldnames:
                    fieldnames.append("warehouse_code")
            rows.append(row)

    combined = {}
    qty_field = None
    qty_variants = {"stock", "ilość", "ilosc", "quantity", "qty"}

    for row in rows:
        img_val = row.get("image1") or row.get("images", "")
        row["image1"] = img_val
        row["images"] = img_val

        key = (
            f"{row.get('nazwa', '').strip()}|{row.get('numer', '').strip()}|{row.get('set', '').strip()}"
        )
        if qty_field is None:
            for variant in qty_variants:
                if variant in row:
                    qty_field = variant
                    break
        qty = 1
        if qty_field:
            try:
                qty = int(row.get(qty_field, 0))
            except ValueError:
                qty = 1

        warehouse = str(row.get("warehouse_code", "")).strip()

        if key in combined:
            combined[key]["qty"] += qty
            if warehouse:
                combined[key]["warehouses"].add(warehouse)
        else:
            new_row = row.copy()
            new_row["qty"] = qty
            new_row["warehouses"] = set()
            if warehouse:
                new_row["warehouses"].add(warehouse)
            combined[key] = new_row

    for row in combined.values():
        if not row.get("product_code"):
            number = row.get("numer") or row.get("number") or ""
            row["product_code"] = build_product_code(
                row.get("set", ""),
                number,
                infer_variant_code(row),
                ball_suffix=row.get("ball_type"),
            )

    if qty_field is None:
        qty_field = "ilość"
        if qty_field not in fieldnames:
            fieldnames.append(qty_field)

    if "image1" in fieldnames:
        fieldnames[fieldnames.index("image1")] = "images 1"

    save_path = filedialog.asksaveasfilename(
        defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
    )
    if not save_path:
        return

    with open(save_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in combined.values():
            row_out = row.copy()
            row_out[qty_field] = row_out.pop("qty")
            row_out["warehouse_code"] = ";".join(sorted(row_out.pop("warehouses", [])))
            row_out["images 1"] = row_out.get("image1", row_out.get("images", ""))
            if qty_field != "stock":
                row_out.pop("stock", None)
            if qty_field != "ilość":
                row_out.pop("ilość", None)
            writer.writerow({k: row_out.get(k, "") for k in fieldnames})

    messagebox.showinfo("Sukces", "Plik CSV został scalony i zapisany.")


def export_csv(app, path: str = STORE_EXPORT_CSV):
    """Export collected data to the store CSV file."""

    combined: dict[str, dict[str, str | int]] = {}

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                product_code = row.get("product_code")
                if not product_code:
                    continue
                try:
                    row["stock"] = int(row.get("stock") or 0)
                except ValueError:
                    row["stock"] = 0
                combined[product_code] = row

    for row in app.output_data:
        if row is None:
            continue
        product_code = str(row["product_code"])
        if product_code in combined:
            combined[product_code]["stock"] = int(combined[product_code]["stock"]) + 1
        else:
            row_copy = row.copy()
            row_copy["stock"] = 1
            combined[product_code] = format_store_row(row_copy)

    fieldnames = STORE_FIELDNAMES

    with open(path, mode="w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in combined.values():
            row_out = row.copy()
            row_out["stock"] = str(row_out.get("stock", 0))
            writer.writerow(row_out)
    append_warehouse_csv(app)
    messagebox.showinfo("Sukces", "Plik CSV został zapisany.")
    if messagebox.askyesno("Wysyłka", "Czy wysłać plik do Shoper?"):
        send_csv_to_shoper(app, path)
    app.back_to_welcome()


def append_warehouse_csv(app, path: str = WAREHOUSE_CSV):
    """Append all collected rows to the warehouse CSV."""
    fieldnames = WAREHOUSE_FIELDNAMES

    file_exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        if not file_exists:
            writer.writeheader()
        for row in app.output_data:
            if row is None:
                continue
            writer.writerow(format_warehouse_row(row))

    # Recompute and cache inventory statistics to include newly written rows
    get_inventory_stats(path, force=True)

    if hasattr(app, "update_inventory_stats"):
        try:
            app.update_inventory_stats(force=True)
        except TclError:
            pass


def send_csv_to_shoper(app, file_path: str):
    """Send a CSV file using the Shoper API or WebDAV fallback."""
    from tkinter import messagebox  # ensure patched instance is used
    try:
        if getattr(app, "shoper_client", None):
            result = app.shoper_client.import_csv(file_path)
            errors = result.get("errors") or []
            warnings = result.get("warnings") or []
            status = (result.get("status") or "").lower()
            if errors or warnings or status not in {"completed", "finished", "done", "success"}:
                issues = "\n".join(map(str, errors + warnings)) or f"Status: {status or 'nieznany'}"
                messagebox.showerror("Błąd", f"Import zakończony z problemami:\n{issues}")
            else:
                messagebox.showinfo("Sukces", f"Import zakończony: {status}")
        else:
            with WebDAVClient(
                getattr(app, "WEBDAV_URL", None),
                getattr(app, "WEBDAV_USER", None),
                getattr(app, "WEBDAV_PASSWORD", None),
            ) as client:
                client.upload_file(file_path)
            messagebox.showinfo("Sukces", "Plik CSV został wysłany.")
    except Exception as exc:  # pragma: no cover - network failure
        messagebox.showerror("Błąd", f"Nie udało się wysłać pliku: {exc}")

