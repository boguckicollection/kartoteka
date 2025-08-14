import builtins
from pathlib import Path
import os
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
from kartoteka import csv_utils  # noqa: E402


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_get_inventory_stats_cached(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    _write_csv(
        csv_path,
        "name;number;set;warehouse_code;price;image\n" "A;1;S1;K1;10;img\n",
    )

    first = csv_utils.get_inventory_stats(str(csv_path))

    called = False
    orig_open = builtins.open

    def counting_open(*args, **kwargs):
        nonlocal called
        called = True
        return orig_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)

    second = csv_utils.get_inventory_stats(str(csv_path))
    assert second == first
    assert not called


def test_get_inventory_stats_recomputes_on_change(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    _write_csv(
        csv_path,
        "name;number;set;warehouse_code;price;image\n" "A;1;S1;K1;10;img\n",
    )

    first = csv_utils.get_inventory_stats(str(csv_path))

    mtime = os.path.getmtime(csv_path)
    _write_csv(
        csv_path,
        "name;number;set;warehouse_code;price;image\n" "A;1;S1;K1;10;img\n" "B;2;S2;K2;5;img2\n",
    )
    os.utime(csv_path, (mtime + 1, mtime + 1))

    second = csv_utils.get_inventory_stats(str(csv_path))
    assert second != first
    assert second == (2, pytest.approx(15.0), 0, pytest.approx(0.0))


def test_get_inventory_stats_force(tmp_path, monkeypatch):
    csv_path = tmp_path / "magazyn.csv"
    _write_csv(
        csv_path,
        "name;number;set;warehouse_code;price;image\n" "A;1;S1;K1;10;img\n",
    )

    csv_utils.get_inventory_stats(str(csv_path))

    called = False
    orig_open = builtins.open

    def counting_open(*args, **kwargs):
        nonlocal called
        called = True
        return orig_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)

    csv_utils.get_inventory_stats(str(csv_path), force=True)
    assert called
