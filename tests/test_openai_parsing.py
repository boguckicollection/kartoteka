import importlib
import sys
from pathlib import Path
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import tkinter as tk

sys.modules["customtkinter"] = SimpleNamespace(
    CTkEntry=tk.Entry,
    CTkImage=MagicMock(),
    CTkButton=MagicMock,
    CTkToplevel=MagicMock,
)
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)

SV01_CODE = "sv01"
SV01_NAME = ui.get_set_name(SV01_CODE)


def test_parse_code_fence(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    img = tmp_path / "x.jpg"
    img.write_bytes(b"data")

    payload = {
        "name": "Pikachu",
        "number": "037/198",
        "set_name": SV01_CODE,
        "era_name": ui.get_set_era(SV01_CODE),
        "set_format": "text",
    }
    resp = SimpleNamespace(output_text=f"```json\n{json.dumps(payload)}\n```")

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=lambda *a, **k: resp)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(str(img))
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"
