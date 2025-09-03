from pathlib import Path
import importlib

from kartoteka import csv_utils as _csv_utils


def test_local_warehouse_csv_exists():
    csv_utils = importlib.reload(_csv_utils)
    path = Path(csv_utils.WAREHOUSE_CSV)
    assert path.exists()
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == ";".join(csv_utils.WAREHOUSE_FIELDNAMES)
    assert csv_utils.WAREHOUSE_FIELDNAMES == [
        "name",
        "number",
        "set",
        "warehouse_code",
        "price",
        "image",
        "variant",
        "sold",
        "added_at",
    ]


def test_download_function_removed():
    assert not hasattr(_csv_utils, "download_warehouse_csv")
