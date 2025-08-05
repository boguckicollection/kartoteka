from types import SimpleNamespace
from unittest.mock import MagicMock
import kartoteka.ui as ui


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
        current_image_path="/tmp/img.jpg",
    )
    dummy._apply_analysis_result = ui.CardEditorApp._apply_analysis_result.__get__(dummy, ui.CardEditorApp)
    dummy.prompt_set_selection_api = MagicMock()
    dummy.prompt_set_selection = MagicMock()
    return dummy, name_entry, num_entry, set_var


def test_apply_analysis_result_single_set(monkeypatch):
    dummy, _n, _num, set_var = make_dummy()
    captured = {}

    def fake_lookup(name, number, total):
        captured["args"] = (name, number, total)
        return [("sv01", "Scarlet & Violet")]

    monkeypatch.setattr(ui, "lookup_sets_from_api", fake_lookup)

    dummy._apply_analysis_result({"name": "Pikachu", "number": "037/159", "set": ""}, 0)
    assert captured["args"] == ("Pikachu", "37", "159")
    set_var.set.assert_called_with("Scarlet & Violet")
    dummy.prompt_set_selection_api.assert_not_called()
    dummy.prompt_set_selection.assert_not_called()


def test_apply_analysis_result_multiple_sets(monkeypatch):
    dummy, _n, _num, _set = make_dummy()
    options = [("a", "Set A"), ("b", "Set B")]
    monkeypatch.setattr(ui, "lookup_sets_from_api", lambda n, num, total: options)

    dummy._apply_analysis_result({"name": "Pikachu", "number": "037", "total": "159", "set": ""}, 0)
    dummy.prompt_set_selection_api.assert_called_once_with(options)
    dummy.prompt_set_selection.assert_not_called()


def test_apply_analysis_result_fallback(monkeypatch):
    dummy, _n, _num, _set = make_dummy()
    monkeypatch.setattr(ui, "lookup_sets_from_api", lambda n, num, total: [])
    class DummyImage:
        size = (100, 100)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(ui.Image, "open", lambda path: DummyImage())
    monkeypatch.setattr(
        ui,
        "identify_set_by_hash",
        lambda path, rect: [("x", "Set X", 0)],
    )

    dummy._apply_analysis_result(
        {"name": "Pikachu", "number": "037", "total": "159", "set": ""}, 0
    )
    dummy.prompt_set_selection.assert_called_once_with([("x", "Set X")])
