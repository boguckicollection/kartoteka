import pytest

from kartoteka.csv_utils import _sanitize_number


@pytest.mark.parametrize(
    "value,expected",
    [
        ("001", "1"),
        ("0000", "0"),
        ("", "0"),
    ],
)
def test_sanitize_number_basic(value, expected):
    assert _sanitize_number(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (" 001", "1"),
        ("001 ", "1"),
        (" 0000 ", "0"),
    ],
)
def test_sanitize_number_with_spaces(value, expected):
    assert _sanitize_number(value) == expected
