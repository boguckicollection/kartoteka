import csv
import re
from datetime import datetime
from . import csv_utils

LAST_PRODUCT_CODE_FILE = "last_product_code.txt"
LAST_SETS_CHECK_FILE = "last_sets_check.txt"

# Total card capacity per storage box.  Standard boxes hold 4000 cards in
# four columns, while the special box ``100`` is a single 500-card column.
BOX_COUNT = 10  # number of standard boxes
BOX_CAPACITY: dict[int, int] = {**{b: 4000 for b in range(1, BOX_COUNT + 1)}, 100: 500}

# Number of columns per storage box.  All regular boxes (1-10) have four
# columns, while the overflow box ``100`` only one.  The mapping is kept
# explicit so the column layout can be adjusted independently of
# :data:`BOX_CAPACITY`.
BOX_COLUMNS: dict[int, int] = {**{b: 4 for b in range(1, BOX_COUNT + 1)}, 100: 1}

# Default per-column capacity for standard boxes.  Used as a fallback when
# handling boxes outside of :data:`BOX_CAPACITY`.
BOX_COLUMN_CAPACITY = 1000


def load_last_product_code() -> int:
    try:
        with open(LAST_PRODUCT_CODE_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_last_product_code(value: int) -> None:
    with open(LAST_PRODUCT_CODE_FILE, "w", encoding="utf-8") as f:
        f.write(str(int(value)))


def load_last_sets_check() -> datetime | None:
    try:
        with open(LAST_SETS_CHECK_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if not text:
                return None
            return datetime.fromisoformat(text)
    except (FileNotFoundError, ValueError):
        return None


def save_last_sets_check(value: datetime | None = None) -> None:
    if value is None:
        value = datetime.now()
    with open(LAST_SETS_CHECK_FILE, "w", encoding="utf-8") as f:
        f.write(value.isoformat())


def location_from_code(code: str) -> str:
    match = re.match(r"K(\d+)R(\d)P(\d+)", code or "")
    if not match:
        return ""
    box, column, pos = match.groups()
    return f"Karton {int(box)} | Kolumna {int(column)} | Poz {int(pos)}"


def generate_location(idx):
    """Return a warehouse code for a sequential slot index.

    The first 40 000 indices map to boxes 1-10 (four 1000-card columns each).
    Subsequent indices map to the special box 100 which has a single
    500-card column.
    """

    if idx < BOX_COUNT * 4000:
        pos = idx % 1000 + 1
        column = (idx // 1000) % 4 + 1
        box = (idx // 4000) + 1
        return f"K{box:02d}R{column}P{pos:04d}"

    idx -= BOX_COUNT * 4000
    if idx < 500:
        # box 100, only one column
        pos = idx + 1
        return f"K100R1P{pos:04d}"

    raise ValueError("Index out of range for known storage boxes")


def next_free_location(app):
    used = set()
    pattern = re.compile(r"K(\d+)R(\d)P(\d+)")
    for row in getattr(app, "output_data", []):
        if not row:
            continue
        for code in str(row.get("warehouse_code") or "").split(";"):
            match = pattern.match(code.strip())
            if not match:
                continue
            box = int(match.group(1))
            column = int(match.group(2))
            pos = int(match.group(3))
            if box == 100:
                idx = BOX_COUNT * 4000 + (pos - 1)
            else:
                idx = (box - 1) * 4000 + (column - 1) * 1000 + (pos - 1)
            used.add(idx)

    idx = getattr(app, "starting_idx", 0)
    while idx in used:
        idx += 1
    return generate_location(idx)


def compute_column_occupancy() -> dict[int, dict[int, int]]:
    """Return count of used slots per column in each storage box.

    The returned mapping is a nested dictionary where the first key is the
    box number and the second key the column number.  Cards marked as sold are
    ignored.  Missing boxes or columns are represented with zero counts.
    """

    occ: dict[int, dict[int, int]] = {
        box: {col: 0 for col in range(1, BOX_COLUMNS.get(box, 4) + 1)}
        for box in BOX_COLUMNS
    }
    try:
        with open(csv_utils.INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
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
                    occ.setdefault(box, {})
                    occ[box][col] = occ[box].get(col, 0) + 1
    except FileNotFoundError:
        pass

    for box, cols in BOX_COLUMNS.items():
        box_occ = occ.setdefault(box, {})
        for col in range(1, cols + 1):
            box_occ.setdefault(col, 0)
    return occ


def compute_box_occupancy() -> dict[int, int]:
    """Return count of used slots per storage box.

    This helper aggregates the per-column data from
    :func:`compute_column_occupancy` into totals for each box.
    """

    col_occ = compute_column_occupancy()
    return {box: sum(cols.values()) for box, cols in col_occ.items()}


def repack_column(box: int, column: int):
    path = csv_utils.INVENTORY_CSV
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except FileNotFoundError:
        return

    pattern = re.compile(r"K(\d+)R(\d)P(\d+)")
    entries = []
    for row in rows:
        codes = [
            c.strip()
            for c in str(row.get("warehouse_code") or "").split(";")
            if c.strip()
        ]
        for idx, code in enumerate(codes):
            m = pattern.fullmatch(code)
            if m and int(m.group(1)) == box and int(m.group(2)) == column:
                pos = int(m.group(3))
                entries.append((pos, row, idx, codes))

    entries.sort(key=lambda x: x[0])
    for new_pos, (_, row, idx, codes) in enumerate(entries, start=1):
        codes[idx] = f"K{box:02d}R{column}P{new_pos:04d}"
        row["warehouse_code"] = ";".join(codes)

    if entries:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

