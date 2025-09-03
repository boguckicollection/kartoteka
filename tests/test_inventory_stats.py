import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def test_get_inventory_stats(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image\n"
        "A;1;S1;K1;10.5;img1\n" "B;2;S2;K2;5,25;img2\n",
        encoding="utf-8",
    )
    count_unsold, total_unsold, count_sold, total_sold = csv_utils.get_inventory_stats(
        str(csv_path)
    )
    assert count_unsold == 2
    assert total_unsold == pytest.approx(15.75)
    assert count_sold == 0
    assert total_sold == pytest.approx(0)


def test_inventory_stats_excludes_sold(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n"
        "A;1;S1;K1;10;img1;\n" "B;2;S2;K2;5;img2;1\n",
        encoding="utf-8",
    )
    count_unsold, total_unsold, count_sold, total_sold = csv_utils.get_inventory_stats(
        str(csv_path)
    )
    assert count_unsold == 1
    assert total_unsold == pytest.approx(10)
    assert count_sold == 1
    assert total_sold == pytest.approx(5)
