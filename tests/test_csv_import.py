import csv
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import main


def run_load_csv(tmp_path, csv_content):
    in_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.csv"
    in_path.write_text(csv_content, encoding="utf-8")

    dummy = SimpleNamespace(product_code_map={}, next_product_code=1)

    with patch("tkinter.filedialog.askopenfilename", return_value=str(in_path)), \
         patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_path)), \
         patch("tkinter.messagebox.showinfo"), \
         patch("tkinter.messagebox.askyesno", return_value=False):
        main.CardEditorApp.load_csv_data(dummy)

    with open(out_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";")), dummy


def test_old_csv_location_pattern(tmp_path):
    rows, dummy = run_load_csv(
        tmp_path,
        "product_code;nazwa;numer;set;stock\n"
        "K1R1P1;Pikachu;1;Base;1\n"
        "K1R1P1;Pikachu;1;Base;1\n",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["warehouse_code"] == "K1R1P1"
    assert row["product_code"] == "1"
    assert dummy.product_code_map == {"Pikachu|1|Base": 1}
    assert dummy.next_product_code == 2
