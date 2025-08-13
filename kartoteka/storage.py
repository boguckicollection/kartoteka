import csv
import re
from datetime import datetime
from . import csv_utils

LAST_PRODUCT_CODE_FILE = "last_product_code.txt"
LAST_SETS_CHECK_FILE = "last_sets_check.txt"


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
    pos = idx % 1000 + 1
    column = (idx // 1000) % 4 + 1
    box = (idx // 4000) + 1
    return f"K{box:02d}R{column}P{pos:04d}"


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
            idx = (box - 1) * 4000 + (column - 1) * 1000 + (pos - 1)
            used.add(idx)

    idx = getattr(app, "starting_idx", 0)
    while idx in used:
        idx += 1
    return generate_location(idx)


def compute_column_occupancy():
    occ = {b: {c: 0 for c in range(1, 5)} for b in range(1, 9)}
    try:
        with open(csv_utils.INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                codes = str(row.get("warehouse_code") or "").split(";")
                for code in codes:
                    code = code.strip()
                    if not code:
                        continue
                    m = re.match(r"K(\d+)R(\d)P(\d+)", code)
                    if not m:
                        continue
                    box = int(m.group(1))
                    c = int(m.group(2))
                    if box in occ and c in occ[box]:
                        occ[box][c] += 1
    except FileNotFoundError:
        pass
    return occ


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

