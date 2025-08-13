from types import SimpleNamespace


def test_compute_column_occupancy_box100(tmp_path, monkeypatch):
    from kartoteka import csv_utils, storage

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text("name;warehouse_code\nA;K100R1P0001\n", encoding="utf-8")
    monkeypatch.setattr(csv_utils, "INVENTORY_CSV", str(csv_path))
    occ = storage.compute_column_occupancy()
    assert occ[100][1] == 1


def test_generate_and_next_free_location_box100():
    from kartoteka import storage

    idx = 8 * 4000
    assert storage.generate_location(idx) == "K100R1P0001"

    app = SimpleNamespace(output_data=[{"warehouse_code": "K100R1P0001"}], starting_idx=idx)
    assert storage.next_free_location(app) == "K100R1P0002"
