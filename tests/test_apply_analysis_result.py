import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, call
import tkinter as tk

import kartoteka.ui as ui
importlib.reload(ui)


def make_dummy():
    name_entry = MagicMock()
    num_entry = MagicMock()
    set_var = MagicMock()
    era_var = MagicMock()
    card_type_var = SimpleNamespace(get=lambda: "C", set=MagicMock())
    name_entry.delete = MagicMock()
    name_entry.insert = MagicMock()
    num_entry.delete = MagicMock()
    num_entry.insert = MagicMock()
    set_var.set = MagicMock()
    dummy = SimpleNamespace(
        entries={
            "nazwa": name_entry,
            "numer": num_entry,
            "set": set_var,
            "era": era_var,
            "card_type": card_type_var,
        },
        root=SimpleNamespace(),
        index=0,
        update_set_options=lambda: None,
        update_set_area_preview=lambda *a, **k: None,
        card_type_var=card_type_var,
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)
    dummy._get_card_type_code = ui.CardEditorApp._get_card_type_code.__get__(dummy, ui.CardEditorApp)
    dummy._set_card_type_code = ui.CardEditorApp._set_card_type_code.__get__(dummy, ui.CardEditorApp)
    dummy._set_card_type_from_mapping = ui.CardEditorApp._set_card_type_from_mapping.__get__(dummy, ui.CardEditorApp)
    return dummy, name_entry, num_entry, set_var


def test_apply_analysis_result_updates_fields():
    dummy, name_entry, num_entry, set_var = make_dummy()
    dummy._apply_analysis_result({"name": "Pikachu", "number": "037/159", "set": "Set X", "era": ""}, 0)
    name_entry.insert.assert_called_with(0, "Pikachu")
    num_entry.insert.assert_called_with(0, "37")
    set_var.set.assert_called_with("Set X")


def make_dummy_with_progress():
    dummy, name_entry, num_entry, set_var = make_dummy()
    dummy._update_card_progress = MagicMock()
    dummy.next_free_location = MagicMock(return_value="K1R1P1")
    dummy.location_label = SimpleNamespace(configure=MagicMock())
    dummy.current_analysis_thread = "t"
    dummy._get_card_type_code = ui.CardEditorApp._get_card_type_code.__get__(dummy, ui.CardEditorApp)
    dummy._set_card_type_code = ui.CardEditorApp._set_card_type_code.__get__(dummy, ui.CardEditorApp)
    dummy._set_card_type_from_mapping = ui.CardEditorApp._set_card_type_from_mapping.__get__(dummy, ui.CardEditorApp)
    return dummy, name_entry, num_entry, set_var


def test_apply_analysis_result_duplicate_cancel(monkeypatch):
    dummy, _, _, _ = make_dummy_with_progress()
    find_mock = MagicMock(return_value=[{"warehouse_code": "K1"}])
    ask_mock = MagicMock(return_value=False)
    monkeypatch.setattr(ui.csv_utils, "find_duplicates", find_mock)
    monkeypatch.setattr(ui.messagebox, "askyesno", ask_mock)

    dummy._apply_analysis_result(
        {"name": "Pika", "number": "001", "set": "Set X", "era": ""}, 0
    )

    find_mock.assert_called_once_with("Pika", "1", "Set X", "C")
    ask_mock.assert_called_once()
    assert dummy._update_card_progress.call_args_list == [
        call(0, hide=True),
        call(1.0, hide=True),
    ]
    dummy.next_free_location.assert_not_called()
    assert dummy.current_analysis_thread is None


def test_apply_analysis_result_duplicate_confirm(monkeypatch):
    dummy, _, _, _ = make_dummy_with_progress()
    find_mock = MagicMock(return_value=[{"warehouse_code": "K1"}])
    ask_mock = MagicMock(return_value=True)
    monkeypatch.setattr(ui.csv_utils, "find_duplicates", find_mock)
    monkeypatch.setattr(ui.messagebox, "askyesno", ask_mock)

    dummy._apply_analysis_result(
        {"name": "Pika", "number": "001", "set": "Set X", "era": ""}, 0
    )

    find_mock.assert_called_once_with("Pika", "1", "Set X", "C")
    ask_mock.assert_called_once()
    dummy._update_card_progress.assert_called_once_with(0, hide=True)
    dummy.next_free_location.assert_called_once()
    dummy.location_label.configure.assert_called_once_with(text="K1R1P1")
    assert dummy.current_location == "K1R1P1"
