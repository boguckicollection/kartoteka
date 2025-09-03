from datetime import date
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils, stats_utils  # noqa: E402


def test_get_statistics_aggregates_correctly(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant;sold;added_at\n"
        "A;1;Set1;K1R1P0001;10;;common;;2025-09-01\n"
        "B;2;Set1;K1R1P0002;5;;common;1;2025-09-01\n"
        "C;3;Set2;K2R1P0001;8;;common;;2025-09-02\n"
        "D;4;Set3;K2R1P0002;7;;common;1;2025-09-02\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(csv_path))
    stats = stats_utils.get_statistics(date(2025, 9, 1), date(2025, 9, 2))
    assert stats["cumulative"]["count"] == 4
    assert abs(stats["cumulative"]["total_value"] - 30) < 1e-6
    assert stats["daily"]["2025-09-01"] == {"added": 2, "sold": 1}
    assert stats["daily"]["2025-09-02"] == {"added": 2, "sold": 1}
    assert stats["top_sets_by_count"][0] == ("Set1", 2)
    assert stats["top_sets_by_value"][0][0] == "Set1"
    assert stats["top_boxes_by_count"][0] == (1, 2)
    assert abs(stats["average_price"] - 7.5) < 1e-6
    assert abs(stats["sold_ratio"] - 0.5) < 1e-6
    assert abs(stats["unsold_ratio"] - 0.5) < 1e-6
