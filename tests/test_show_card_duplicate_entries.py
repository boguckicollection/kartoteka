from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.ui as ui
from tests.ctk_mocks import DummyCTkEntry


def test_show_card_warns_on_magazyn_duplicate(tmp_path, monkeypatch):
    img = tmp_path / "card.jpg"
    img.write_bytes(b"data")

    class DummyImage:
        size = (100, 100)

        def thumbnail(self, *a, **k):
            pass

        def copy(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def convert(self, *a, **k):
            return self

    class DummyEntry:
        def __init__(self):
            self.value = ""

        def delete(self, start, end=None):
            self.value = ""

        def insert(self, index, text):
            self.value = self.value[:index] + text + self.value[index:]

        def get(self):
            return self.value

        def focus_set(self):
            pass

    name_entry = DummyEntry()
    num_entry = DummyEntry()
    set_var = SimpleNamespace(set=lambda *a, **k: None)

    card_type_var = SimpleNamespace(set=lambda *a, **k: None, get=lambda: "C")
    dummy = SimpleNamespace(
        cards=[str(img)],
        index=0,
        image_objects=[],
        image_label=MagicMock(),
        progress_var=SimpleNamespace(set=lambda *a, **k: None),
        entries={
            "nazwa": name_entry,
            "numer": num_entry,
            "set": set_var,
            "era": SimpleNamespace(set=lambda *a, **k: None),
            "card_type": card_type_var,
        },
        type_vars={},
        card_cache={},
        file_to_key={},
        _guess_key_from_filename=lambda *a, **k: None,
        lookup_inventory_entry=lambda *a, **k: None,
        update_set_options=lambda *a, **k: None,
        root=SimpleNamespace(after=lambda delay, func: func()),
        auto_lookup=True,
        hash_db=SimpleNamespace(
            best_match=lambda fp, max_distance=None: SimpleNamespace(
                meta={"nazwa": "Pika", "numer": "001", "set": "Set X"},
                distance=0,
            )
        ),
        card_type_var=card_type_var,
    )
    dummy._analyze_and_fill = lambda *a, **k: None
    dummy._apply_analysis_result = lambda *a, **k: None

    monkeypatch.setattr(ui, "compute_fingerprint", lambda img: "fp")
    monkeypatch.setattr(ui, "analyze_card_image", lambda *a, **k: {})
    monkeypatch.setattr(ui, "_create_image", lambda img: SimpleNamespace())
    monkeypatch.setattr(ui, "load_rgba_image", lambda path: DummyImage())
    monkeypatch.setattr(ui.ctk, "CTkEntry", DummyCTkEntry, raising=False)

    dup_rows = [{"warehouse_code": "K1"}]
    find_mock = MagicMock(return_value=dup_rows)
    monkeypatch.setattr(ui.csv_utils, "find_duplicates", find_mock)
    ask_mock = MagicMock(return_value=False)
    monkeypatch.setattr(ui.messagebox, "askyesno", ask_mock)

    with patch.object(ui.Image, "open", return_value=DummyImage()):
        ui.CardEditorApp.show_card(dummy)

    find_mock.assert_called_once_with("Pika", "1", "Set X", "C")
    assert ask_mock.called
    assert name_entry.get() == ""
    assert num_entry.get() == ""
