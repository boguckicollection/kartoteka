import csv
import os
import re
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Tuple

try:  # pragma: no cover - allow running as a script
    from . import csv_utils
except Exception:  # pragma: no cover
    import csv_utils  # type: ignore


def _parse_date(value: str) -> date | None:
    """Return ``date`` extracted from ISO string ``value``.

    Empty or malformed values return ``None`` instead of raising an error.
    """
    if not value:
        return None
    value = value.split("T", 1)[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _load_rows(path: str) -> List[dict]:
    """Load rows from ``path`` as dictionaries."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


def get_statistics(start: date, end: date, path: str | None = None) -> Dict:
    """Return aggregated warehouse statistics between ``start`` and ``end``.

    Parameters
    ----------
    start, end:
        Inclusive date range to analyse.
    path:
        Optional path to the warehouse CSV.  Defaults to
        :data:`csv_utils.WAREHOUSE_CSV`.
    """

    if path is None:
        path = csv_utils.WAREHOUSE_CSV

    rows = _load_rows(path)

    filtered: List[dict] = []
    for row in rows:
        added = _parse_date(str(row.get("added_at") or ""))
        if added is None:
            logging.warning("Missing added_at value, using today's date")
            added = date.today()
            row["added_at"] = added.isoformat()
        if start <= added <= end:
            filtered.append(row)

    cumulative_count = 0
    cumulative_value = 0.0
    sold_count = 0
    unsold_count = 0

    daily: Dict[str, Dict[str, int]] = {}
    sets_by_count: Dict[str, int] = defaultdict(int)
    sets_by_value: Dict[str, float] = defaultdict(float)
    boxes_by_count: Dict[int, int] = defaultdict(int)
    boxes_by_value: Dict[int, float] = defaultdict(float)
    max_price = 0.0

    for row in filtered:
        price_raw = str(row.get("price") or "0").replace(",", ".")
        try:
            price = float(price_raw)
        except ValueError:
            price = 0.0
        cumulative_count += 1
        cumulative_value += price

        sold = str(row.get("sold") or "").lower() in {"1", "true", "yes"}
        if sold:
            sold_count += 1
            if price > max_price:
                max_price = price
        else:
            unsold_count += 1

        added = _parse_date(str(row.get("added_at") or ""))
        if added is not None:
            key = added.isoformat()
            stats = daily.setdefault(key, {"added": 0, "sold": 0})
            stats["added"] += 1
            if sold:
                stats["sold"] += 1

        set_name = row.get("set") or ""
        sets_by_count[set_name] += 1
        sets_by_value[set_name] += price

        codes = str(row.get("warehouse_code") or "").split(";")
        box = None
        for code in codes:
            m = re.match(r"K(\d+)", code.strip())
            if m:
                box = int(m.group(1))
                break
        if box is not None:
            boxes_by_count[box] += 1
            boxes_by_value[box] += price

    # ensure every day in the range is present
    cur = start
    while cur <= end:
        daily.setdefault(cur.isoformat(), {"added": 0, "sold": 0})
        cur += timedelta(days=1)

    def _sort_items(d: Dict) -> List[Tuple]:
        return sorted(d.items(), key=lambda x: (-x[1], x[0]))[:5]

    avg_price = cumulative_value / cumulative_count if cumulative_count else 0.0
    sold_ratio = sold_count / cumulative_count if cumulative_count else 0.0
    unsold_ratio = unsold_count / cumulative_count if cumulative_count else 0.0
    max_order = max((stats.get("sold", 0) for stats in daily.values()), default=0)

    return {
        "cumulative": {"count": cumulative_count, "total_value": cumulative_value},
        "daily": dict(sorted(daily.items())),
        "top_sets_by_count": _sort_items(sets_by_count),
        "top_sets_by_value": _sort_items(sets_by_value),
        "top_boxes_by_count": _sort_items(boxes_by_count),
        "top_boxes_by_value": _sort_items(boxes_by_value),
        "average_price": avg_price,
        "sold_ratio": sold_ratio,
        "unsold_ratio": unsold_ratio,
        "max_price": max_price,
        "max_order": max_order,
    }


def export_statistics_csv(data: Dict, path: str) -> None:
    """Write ``data`` returned from :func:`get_statistics` to ``path``."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["metric", "value"])
        cumulative = data.get("cumulative", {})
        writer.writerow(["count", cumulative.get("count", 0)])
        writer.writerow(["total_value", cumulative.get("total_value", 0.0)])
        writer.writerow(["average_price", data.get("average_price", 0.0)])
        writer.writerow(["sold_ratio", data.get("sold_ratio", 0.0)])
        writer.writerow(["unsold_ratio", data.get("unsold_ratio", 0.0)])
