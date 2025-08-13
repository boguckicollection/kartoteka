import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def test_get_inventory_stats(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image\n" "A;1;S1;K1;10.5;img1\n" "B;2;S2;K2;5,25;img2\n",
        encoding="utf-8",
    )
    count, total = csv_utils.get_inventory_stats(str(csv_path))
    assert count == 2
    assert total == pytest.approx(15.75)
