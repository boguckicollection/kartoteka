import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)


def make_dummy(tmp_path, sets_file):
    return SimpleNamespace(
        sets_file=str(sets_file),
        loading_label=SimpleNamespace(configure=lambda *a, **k: None),
        root=SimpleNamespace(update=lambda *a, **k: None),
        download_set_symbols=MagicMock(),
    )


def test_update_set_options_sets_file_jp():
    dummy = SimpleNamespace(
        lang_var=SimpleNamespace(get=lambda: "JP"),
        set_dropdown=MagicMock(),
        cheat_frame=None,
        sets_file="tcg_sets.json",
    )
    ui.CardEditorApp.update_set_options(dummy)
    assert dummy.sets_file == "tcg_sets_jp.json"
    dummy.set_dropdown.configure.assert_called_with(values=ui.tcg_sets_jp)


def test_update_set_options_sets_file_eng():
    dummy = SimpleNamespace(
        lang_var=SimpleNamespace(get=lambda: "ENG"),
        set_dropdown=MagicMock(),
        cheat_frame=None,
        sets_file="tcg_sets_jp.json",
    )
    ui.CardEditorApp.update_set_options(dummy)
    assert dummy.sets_file == "tcg_sets.json"
    dummy.set_dropdown.configure.assert_called_with(values=ui.tcg_sets_eng)


def run_update_sets(tmp_path, filename):
    sets_file = tmp_path / filename
    sets_file.write_text("{}", encoding="utf-8")
    dummy = make_dummy(tmp_path, sets_file)

    resp = SimpleNamespace(
        status_code=200,
        json=lambda: {"data": [{"series": "X", "id": "CODE", "name": "Name"}]},
        raise_for_status=lambda: None,
    )
    with patch("requests.get", return_value=resp), patch.object(ui, "reload_sets") as reload_mock:
        ui.CardEditorApp.update_sets(dummy)
        reload_mock.assert_called_once()

    data = json.loads(sets_file.read_text(encoding="utf-8"))
    # expect inserted under "X" with code and name
    assert "X" in data
    assert {"name": "Name", "code": "CODE"} in data["X"]
    dummy.download_set_symbols.assert_called_once_with([{"name": "Name", "code": "CODE"}])



def test_update_sets_eng(tmp_path):
    run_update_sets(tmp_path, "tcg_sets.json")



def test_update_sets_jp(tmp_path):
    run_update_sets(tmp_path, "tcg_sets_jp.json")

