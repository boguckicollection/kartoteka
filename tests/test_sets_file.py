import importlib
import json
import sys
import datetime
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
        era_var=SimpleNamespace(get=lambda: ""),
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
        era_var=SimpleNamespace(get=lambda: ""),
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
        json=lambda: {
            "data": [
                {
                    "series": "X",
                    "id": "CODE",
                    "name": "Name",
                    "ptcgoCode": "PTCGO",
                }
            ]
        },
        raise_for_status=lambda: None,
    )
    with patch("requests.get", return_value=resp), patch.object(ui, "reload_sets") as reload_mock:
        ui.CardEditorApp.update_sets(dummy)
        reload_mock.assert_called_once()

    data = json.loads(sets_file.read_text(encoding="utf-8"))
    # expect inserted under "X" with code, name and abbr
    assert "X" in data
    assert {"name": "Name", "code": "CODE", "abbr": "PTCGO"} in data["X"]
    dummy.download_set_symbols.assert_called_once_with([{"name": "Name", "code": "CODE"}])



def test_update_sets_eng(tmp_path):
    run_update_sets(tmp_path, "tcg_sets.json")



def test_update_sets_jp(tmp_path):
    run_update_sets(tmp_path, "tcg_sets_jp.json")


def test_startup_tasks_skips_when_same_month():
    now = datetime.datetime.now()
    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func, *args: func(*args)),
        load_set_logos=lambda: None,
        finish_startup=lambda: None,
        update_sets=MagicMock(),
    )
    with patch.object(ui.storage, "load_last_sets_check", return_value=now), patch.object(
        ui.storage, "save_last_sets_check"
    ) as save_mock:
        ui.CardEditorApp.startup_tasks(dummy)
        dummy.update_sets.assert_not_called()
        save_mock.assert_not_called()


def test_startup_tasks_runs_when_old_month():
    now = datetime.datetime.now()
    prev_month = now.replace(day=1) - datetime.timedelta(days=1)
    dummy = SimpleNamespace(
        root=SimpleNamespace(after=lambda delay, func, *args: func(*args)),
        load_set_logos=lambda: None,
        finish_startup=lambda: None,
        update_sets=MagicMock(),
    )
    with patch.object(
        ui.storage, "load_last_sets_check", return_value=prev_month
    ), patch.object(ui.storage, "save_last_sets_check") as save_mock:
        ui.CardEditorApp.startup_tasks(dummy)
        dummy.update_sets.assert_called_once()
        save_mock.assert_called_once()

