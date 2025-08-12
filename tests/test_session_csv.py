import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
import kartoteka.csv_utils as csv_utils
import kartoteka.storage as storage


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def make_dummy():
    return SimpleNamespace(
        entries={
            "nazwa": DummyVar("Charizard"),
            "numer": DummyVar("4"),
            "set": DummyVar("Base"),
            "język": DummyVar("ENG"),
            "stan": DummyVar("NM"),
            "cena": DummyVar(""),
            "psa10_price": DummyVar("")
        },
        type_vars={"Reverse": DummyVar(False), "Holo": DummyVar(False)},
        card_cache={},
        cards=["/tmp/char.jpg"],
        index=0,
        folder_name="folder",
        file_to_key={},
        product_code_map={},
        next_product_code=1,
        next_free_location=lambda: "K1R1P1",
        generate_location=lambda idx: "K1R1P1",
        output_data=[None],
        get_price_from_db=lambda *a: None,
        fetch_card_price=lambda *a: None,
        fetch_psa10_price=lambda *a, **k: "",
    )


def test_session_csv_created(tmp_path):
    session_path = tmp_path / "session.csv"
    dummy = SimpleNamespace(
        start_box_var=DummyVar("1"),
        start_col_var=DummyVar("1"),
        start_pos_var=DummyVar("1"),
        scan_folder_var=DummyVar("folder"),
        load_images=lambda self, folder: None,
    )

    with patch.object(ui.CardEditorApp, "load_images", lambda self, folder: None), \
         patch("tkinter.filedialog.asksaveasfilename", return_value=str(session_path)):
        ui.CardEditorApp.browse_scans(dummy)

    assert dummy.session_csv_path == str(session_path)
    with open(session_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        assert reader.fieldnames == csv_utils.STORE_FIELDNAMES
        assert "stock" in reader.fieldnames


def test_save_current_appends_session(tmp_path):
    session_path = tmp_path / "session.csv"
    dummy = make_dummy()
    dummy.session_csv_path = str(session_path)
    with open(session_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_utils.STORE_FIELDNAMES, delimiter=";")
        writer.writeheader()

    ui.CardEditorApp.save_current_data(dummy)

    with open(session_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["name"]
        assert rows[0]["currency"] == "PLN"
        assert rows[0]["producer_code"] == "4"
        assert rows[0]["stock"] == "1"
        assert rows[0]["active"] == "1"
        assert rows[0]["vat"] == "23%"
        assert rows[0]["seo_title"] == "Charizard 4 Base"
        assert rows[0]["delivery"] == "3 dni"


def test_product_code_persists_between_sessions(tmp_path):
    session_path = tmp_path / "session.csv"
    last_code_file = tmp_path / "last_product_code.txt"

    with patch.object(storage, "LAST_PRODUCT_CODE_FILE", str(last_code_file)):
        dummy = make_dummy()
        dummy.session_csv_path = str(session_path)
        with open(session_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=csv_utils.STORE_FIELDNAMES, delimiter=";"
            )
            writer.writeheader()

        ui.CardEditorApp.save_current_data(dummy)

        root = SimpleNamespace(
            title=lambda *a, **k: None,
            configure=lambda *a, **k: None,
            option_add=lambda *a, **k: None,
        )

        with patch.object(ui.CardEditorApp, "load_price_db", lambda self: {}), \
             patch.object(ui.CardEditorApp, "show_loading_screen", lambda self: None), \
             patch.object(ui.threading, "Thread", lambda *a, **k: SimpleNamespace(start=lambda: None)), \
             patch("kartoteka.ui.tk.StringVar", lambda *a, **k: DummyVar(k.get("value", ""))):
            app = ui.CardEditorApp(root)

        assert app.next_product_code == 2

