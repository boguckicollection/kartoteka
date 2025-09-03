import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import date

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))

from kartoteka import csv_utils


def test_get_daily_additions_returns_last_days(tmp_path, monkeypatch):
    path = tmp_path / "magazyn.csv"
    monkeypatch.setattr(csv_utils, "WAREHOUSE_CSV", str(path))

    class DummyDate(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 5)

    monkeypatch.setattr(csv_utils, "date", DummyDate)

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_utils.WAREHOUSE_FIELDNAMES, delimiter=";")
        writer.writeheader()
        blank = {fn: "" for fn in csv_utils.WAREHOUSE_FIELDNAMES}
        row = blank.copy(); row["added_at"] = "2024-01-04"; writer.writerow(row)
        row = blank.copy(); row["added_at"] = "2024-01-05"; writer.writerow(row)
        row = blank.copy(); row["added_at"] = "2024-01-01"; writer.writerow(row)

    result = csv_utils.get_daily_additions(days=3)
    assert list(result.keys()) == ["2024-01-03", "2024-01-04", "2024-01-05"]
    assert result["2024-01-04"] == 1
    assert result["2024-01-05"] == 1
    assert result["2024-01-03"] == 0
