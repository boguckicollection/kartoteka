import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock
import tkinter as tk

import kartoteka.ui as ui
importlib.reload(ui)


def make_dummy():
    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()
    dummy = SimpleNamespace(
        entries={"nazwa": name_entry, "numer": num_entry, "set": set_var},
        root=SimpleNamespace(),
        index=0,
        stop_scan_animation=lambda: None,
        update_set_options=lambda: None,
        update_set_area_preview=lambda *a, **k: None,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)
    return dummy, name_entry, num_entry, set_var


def test_apply_analysis_result_updates_fields():
    dummy, name_entry, num_entry, set_var = make_dummy()
    dummy._apply_analysis_result({"name": "Pikachu", "number": "037/159", "set": "Set X"}, 0)
    name_entry.insert.assert_called_with(0, "Pikachu")
    num_entry.insert.assert_called_with(0, "37")
    set_var.set.assert_called_with("Set X")
