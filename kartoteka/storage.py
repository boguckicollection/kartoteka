import csv
import re
from datetime import datetime
from . import csv_utils
from .storage_config import (
    BOX_CAPACITY,
    BOX_COLUMNS,
    BOX_COLUMN_CAPACITY,
    BOX_COUNT,
    STANDARD_BOX_COLUMNS,
)

LAST_SETS_CHECK_FILE = "last_sets_check.txt"
LAST_LOCATION_FILE = "last_location.txt"

# Constants are provided by :mod:`kartoteka.storage_config` to keep the storage
# layout in one place.  The mappings above describe the capacity and column
# counts for each storage box.  ``BOX_OFFSETS`` below holds the sequential start
# index for each configured box and is derived from :data:`BOX_CAPACITY`.

# Build ordered list of boxes and compute their starting offsets.  Regular boxes
# (``1``..``BOX_COUNT``) are followed by any additional boxes defined in
# :data:`BOX_CAPACITY` such as the special overflow box.
_box_order = list(range(1, BOX_COUNT + 1)) + [
    b for b in sorted(BOX_CAPACITY) if b > BOX_COUNT
]
BOX_OFFSETS: dict[int, int] = {}
_offset = 0
for b in _box_order:
    BOX_OFFSETS[b] = _offset
    _offset += BOX_CAPACITY[b]
del _box_order, _offset


class NoFreeLocationError(Exception):
    """Raised when all storage locations are occupied."""


def max_capacity() -> int:
    """Return total number of available storage slots.

    The calculation sums :data:`BOX_CAPACITY` for all configured boxes.
    Boxes missing in :data:`BOX_CAPACITY` fall back to the default
    :data:`BOX_COLUMN_CAPACITY` multiplied by their number of columns.
    """

    total = 0
    for box, cols in BOX_COLUMNS.items():
        total += BOX_CAPACITY.get(box, cols * BOX_COLUMN_CAPACITY)
    return total


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


def load_last_location() -> int:
    """Return index of last used warehouse slot.

    Falls back to ``0`` when the file does not exist or contains
    invalid data.
    """

    try:
        with open(LAST_LOCATION_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def save_last_location(idx: int) -> None:
    """Persist ``idx`` as the last used warehouse slot."""

    with open(LAST_LOCATION_FILE, "w", encoding="utf-8") as f:
        f.write(str(idx))


def location_to_index(code: str) -> int:
    """Convert ``warehouse_code`` to its sequential index."""

    match = re.match(r"K(\d+)R(\d)P(\d+)", code or "")
    if not match:
        return 0
    box, column, pos = map(int, match.groups())
    offset = BOX_OFFSETS.get(box)
    if offset is None:
        return 0
    return offset + (column - 1) * BOX_COLUMN_CAPACITY + (pos - 1)


def location_from_code(code: str) -> str:
    match = re.match(r"K(\d+)R(\d)P(\d+)", code or "")
    if not match:
        return ""
    box, column, pos = match.groups()
    return f"Karton {int(box)} | Kolumna {int(column)} | Poz {int(pos)}"


def generate_location(idx):
    """Return a warehouse code for a sequential slot index.
    
    Uses :data:`BOX_OFFSETS` so that the mapping stays in sync with
    :func:`location_to_index`.
    """

    total = max_capacity()
    if idx < 0 or idx >= total:
        raise ValueError("Index out of range for known storage boxes")

    # Determine which box ``idx`` falls into by subtracting capacities in order.
    for box in BOX_OFFSETS:
        cap = BOX_CAPACITY[box]
        if idx < cap:
            pos = idx % BOX_COLUMN_CAPACITY + 1
            column = idx // BOX_COLUMN_CAPACITY + 1
            return f"K{box:02d}R{column}P{pos:04d}"
        idx -= cap

    # Should not reach here because of the range check above
    raise ValueError("Index out of range for known storage boxes")


def next_free_location(app):
    used = set()
    pattern = re.compile(r"K(\d+)R(\d)P(\d+)")
    output_data = getattr(app, "output_data", [])
    for row in output_data:
        if not row:
            continue
        for code in str(row.get("warehouse_code") or "").split(";"):
            match = pattern.match(code.strip())
            if not match:
                continue
            box = int(match.group(1))
            column = int(match.group(2))
            pos = int(match.group(3))
            offset = BOX_OFFSETS.get(box)
            if offset is None:
                continue
            idx = offset + (column - 1) * BOX_COLUMN_CAPACITY + (pos - 1)
            used.add(idx)

    last_idx = load_last_location() if not output_data else 0
    base_idx = getattr(app, "starting_idx", 0)
    next_idx = max(used | {last_idx, base_idx - 1}) + 1
    if next_idx >= max_capacity():
        raise NoFreeLocationError("no free storage locations available")
    return generate_location(next_idx)


def compute_column_occupancy() -> dict[int, dict[int, int]]:
    """Return count of used slots per column in each storage box.

    The returned mapping is a nested dictionary where the first key is the
    box number and the second key the column number.  Cards marked as sold are
    ignored.  Missing boxes or columns are represented with zero counts.
    """

    occ: dict[int, dict[int, int]] = {
        box: {
            col: 0
            for col in range(1, BOX_COLUMNS.get(box, STANDARD_BOX_COLUMNS) + 1)
        }
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

