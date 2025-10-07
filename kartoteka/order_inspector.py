"""Utility for inspecting Shoper order status information.

The module exposes a ``main`` function used by ``inspect_shoper_orders.py`` so
operators can quickly query the API without the GUI defaults and check which
status identifiers the backend is returning.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Iterable, Mapping, MutableMapping, Optional

from shoper_client import ShoperClient


def _extract_status_type(order: Mapping[str, Any]) -> Optional[str]:
    """Return the numeric status type exposed by the Shoper API."""

    status_type: Any = order.get("status_type")
    if isinstance(status_type, Mapping):
        status_type = status_type.get("type") or status_type.get("id")
    if not status_type:
        status = order.get("status")
        if isinstance(status, Mapping):
            status_type = status.get("type") or status.get("id")
    if status_type is None:
        return None
    return str(status_type)


def _normalise_filters(raw_filters: Iterable[str]) -> MutableMapping[str, Any]:
    """Convert KEY=VALUE pairs from the CLI into a mapping."""

    filters: MutableMapping[str, Any] = {}
    for item in raw_filters:
        key, _, value = item.partition("=")
        if not key:
            continue
        key = key.strip()
        value = value.strip()
        if not value:
            continue
        filters.setdefault(key, []).append(value)
    for key, values in list(filters.items()):
        if len(values) == 1:
            filters[key] = values[0]
        else:
            filters[key] = values
    return filters


def _format_order_summary(order: Mapping[str, Any]) -> str:
    """Return a human readable summary line for console output."""

    status = order.get("status")
    if isinstance(status, Mapping):
        status_name = status.get("name") or status.get("status")
    else:
        status_name = order.get("status_name") or status

    status_type = _extract_status_type(order) or "?"
    order_id = order.get("order_id") or order.get("id") or "?"

    return f"#{order_id}: status={status_name!r} (type={status_type})"


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Entry point for the ``inspect_shoper_orders`` CLI script."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--per-page",
        type=int,
        default=5,
        help="Number of orders to fetch in one request (default: 5)",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number to request (default: 1)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Dump the raw JSON response instead of formatted summaries",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Additional query filters, e.g. --filter filters[status.type]=2. "
            "Repeat the option to provide multiple values."
        ),
    )
    args = parser.parse_args(argv)

    filters = _normalise_filters(args.filter)

    client = ShoperClient()
    response = client.list_orders(
        filters=filters or None, page=args.page, per_page=args.per_page
    )

    orders = response.get("list", [])
    if args.raw:
        json.dump(response, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if not orders:
        print("Brak zamówień w odpowiedzi API.")
        return 0

    print("Znaleziono", len(orders), "zamówień:")
    for order in orders:
        print(" -", _format_order_summary(order))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
