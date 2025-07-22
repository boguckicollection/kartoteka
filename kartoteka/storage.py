import re


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

    idx = 0
    while idx in used:
        idx += 1
    return generate_location(idx)


def compute_column_occupancy(app):
    occ = {b: {c: 0 for c in range(1, 5)} for b in range(1, 9)}
    for row in getattr(app, "output_data", []):
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
    return occ


def repack_column(app, box: int, column: int):
    pattern = re.compile(r"K(\d+)R(\d)P(\d+)")
    entries = []
    for row in getattr(app, "output_data", []):
        if not row:
            continue
        codes = [c.strip() for c in str(row.get("warehouse_code") or "").split(";") if c.strip()]
        for idx, code in enumerate(codes):
            m = pattern.fullmatch(code)
            if m and int(m.group(1)) == box and int(m.group(2)) == column:
                pos = int(m.group(3))
                entries.append((pos, row, idx, codes))

    entries.sort(key=lambda x: x[0])
    for new_pos, (_, row, idx, codes) in enumerate(entries, start=1):
        codes[idx] = f"K{box:02d}R{column}P{new_pos:04d}"
        row["warehouse_code"] = ";".join(codes)

    if entries and hasattr(app, "refresh_magazyn"):
        app.refresh_magazyn()

