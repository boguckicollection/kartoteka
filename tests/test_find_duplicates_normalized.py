import sys
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.csv_utils as csv_utils


def test_find_duplicates_normalized(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant\n"
        "Pokémon;1;Éxample Set;K1;1;foo.png;HólO\n",
        encoding="utf-8",
    )

    with patch.object(csv_utils, "WAREHOUSE_CSV", str(csv_path)):
        matches = csv_utils.find_duplicates("POKEMON", "1", "example set", variant="holo")

    assert {m["warehouse_code"] for m in matches} == {"K1"}


def test_find_duplicates_variant_wildcard(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant\n"
        "Poke;1;Set;K1;1;foo.png;holo\n"
        "Poke;1;Set;K2;1;bar.png;reverse\n",
        encoding="utf-8",
    )

    with patch.object(csv_utils, "WAREHOUSE_CSV", str(csv_path)):
        matches = csv_utils.find_duplicates("Poke", "1", "Set", variant=None)

    assert {m["warehouse_code"] for m in matches} == {"K1", "K2"}
