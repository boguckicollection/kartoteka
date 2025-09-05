from types import SimpleNamespace
import sys
from pathlib import Path

import tkinter as tk

sys.modules["customtkinter"] = SimpleNamespace(
    CTkEntry=tk.Entry,
    CTkImage=SimpleNamespace(),
    CTkButton=SimpleNamespace,
    CTkToplevel=SimpleNamespace,
)
sys.path.append(str(Path(__file__).resolve().parents[1]))
from hash_db import Candidate
import kartoteka.ui as ui


def test_lookup_fp_candidate_threshold(monkeypatch):
    good = Candidate(meta={"warehouse_code": "OK"}, distance=ui.HASH_MATCH_THRESHOLD)
    bad = Candidate(meta={"warehouse_code": "BAD"}, distance=ui.HASH_MATCH_THRESHOLD + 1)

    fp = object()
    calls: list[list[Candidate]] = []

    def fake_dialog(cands):
        calls.append(list(cands))
        return "chosen"

    # mixed candidates: dialog should receive only the valid one
    candidate_calls: list[int] = []

    def fake_candidates(fp, limit=5, max_distance=None):
        candidate_calls.append(1)
        return [good, bad]

    app = SimpleNamespace(
        hash_db=SimpleNamespace(
            best_match=lambda fp, max_distance=None: good,
            candidates=fake_candidates,
        ),
        _show_candidates_dialog=fake_dialog,
    )
    result = ui.CardEditorApp._lookup_fp_candidate(app, fp)
    assert result == "chosen"
    assert calls == [[good]]
    assert candidate_calls == [1]

    calls.clear()
    candidate_calls.clear()

    # only invalid candidate: dialog should not be invoked
    app = SimpleNamespace(
        hash_db=SimpleNamespace(
            best_match=lambda fp, max_distance=None: None,
            candidates=fake_candidates,
        ),
        _show_candidates_dialog=fake_dialog,
    )
    result = ui.CardEditorApp._lookup_fp_candidate(app, fp)
    assert result is None
    assert calls == []
    assert candidate_calls == []

