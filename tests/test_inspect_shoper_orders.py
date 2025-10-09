from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.order_inspector as inspector


def test_extract_status_type_plain_number():
    order = {"status_type": 2}
    assert inspector._extract_status_type(order) == "2"


def test_extract_status_type_nested_mapping():
    order = {"status_type": {"type": 3}}
    assert inspector._extract_status_type(order) == "3"


def test_extract_status_type_fallback_to_status_object():
    order = {"status": {"type": 4}}
    assert inspector._extract_status_type(order) == "4"


def test_extract_status_type_missing():
    assert inspector._extract_status_type({}) is None


def test_normalise_filters_splits_pairs():
    filters = inspector._normalise_filters([
        "filters[status.type]=2",
        "filters[status.type]=3",
        "with=products",
    ])
    assert filters["filters[status.type]"] == ["2", "3"]
    assert filters["with"] == "products"


def test_format_order_summary_handles_strings():
    order = {"order_id": 10, "status_name": "open", "status_type": 2}
    assert inspector._format_order_summary(order) == "#10: status='open' (type=2)"


def test_format_order_summary_handles_status_mapping():
    order = {
        "order_id": 11,
        "status": {"name": "W realizacji", "type": 2},
    }
    assert (
        inspector._format_order_summary(order)
        == "#11: status='W realizacji' (type=2)"
    )
