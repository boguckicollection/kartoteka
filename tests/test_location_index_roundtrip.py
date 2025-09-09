from kartoteka import storage


def test_location_index_roundtrip():
    """Ensure converting index -> code -> index is lossless."""

    total = storage.max_capacity()
    for idx in range(total):
        code = storage.generate_location(idx)
        assert storage.location_to_index(code) == idx
