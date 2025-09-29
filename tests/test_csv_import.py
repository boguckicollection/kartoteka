import csv
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
from kartoteka.ui import CardEditorApp


def run_load_csv(tmp_path, csv_content):
    in_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.csv"
    in_path.write_text(csv_content, encoding="utf-8")

    dummy = SimpleNamespace(product_code_map={})

    with patch("tkinter.filedialog.askopenfilename", return_value=str(in_path)), \
         patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_path)), \
         patch("tkinter.messagebox.showinfo"), \
         patch("tkinter.messagebox.askyesno", return_value=False):
        CardEditorApp.load_csv_data(dummy)

    with open(out_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        return rows, dummy, reader.fieldnames


def test_old_csv_location_pattern(tmp_path):
    rows, dummy, _ = run_load_csv(
        tmp_path,
        "product_code;nazwa;numer;set;stock\n"
        "K1R1P1;Pikachu;1;Base;1\n"
        "K1R1P1;Pikachu;1;Base;1\n",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["warehouse_code"] == "K1R1P1"
    assert row["product_code"] == "PKM-BAS-1C"
    assert dummy.product_code_map == {}


def test_image_header_replaced(tmp_path):
    rows, _, fieldnames = run_load_csv(
        tmp_path,
        "product_code;nazwa;numer;set;stock;image1\n"
        "1;Bulbasaur;1;Base;1;img.png\n",
    )
    assert "images 1" in fieldnames
    row = rows[0]
    assert row["images 1"] == "img.png"
