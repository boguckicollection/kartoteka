from kartoteka import csv_utils

def test_ensure_function_removed():
    assert not hasattr(csv_utils, "ensure_warehouse_csv")
