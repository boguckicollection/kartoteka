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

    calls = []

    def create(*a, **k):
        calls.append(k)
        return resp

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img)
    )
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"
    assert calls and "response_format" in calls[0]
    enums = (
        calls[0]["response_format"]["json_schema"]["schema"]["properties"]["set_name"]["enum"]
    )
    assert enums == ui.OPENAI_SETS


def test_parse_code_fallback(monkeypatch, tmp_path):
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
    resp = SimpleNamespace(output_text=json.dumps(payload))

    calls = []

    def create(*a, **k):
        calls.append(k)
        if len(calls) == 1:
            raise TypeError("response_format not supported")
        return resp

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img)
    )
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_parse_code_fallback_openai_error(monkeypatch, tmp_path):
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
    resp = SimpleNamespace(output_text=json.dumps(payload))

    calls = []

    def create(*a, **k):
        calls.append(k)
        if len(calls) == 1:
            raise ui.openai.OpenAIError("unexpected keyword argument 'response_format'")
        return resp

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img)
    )
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_parse_truncated_json_repair(monkeypatch, tmp_path):
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
    truncated = json.dumps(payload)[:-1]
    resp = SimpleNamespace(output_text=truncated)

    def create(*a, **k):
        return resp

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img)
    )
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"


def test_retry_on_json_decode_error(monkeypatch, tmp_path):
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
    bad = SimpleNamespace(output_text="not json")
    good = SimpleNamespace(output_text=json.dumps(payload))

    calls = []

    def create(*a, **k):
        calls.append(k)
        return bad if len(calls) == 1 else good

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img)
    )
    assert (name, number, total, era_name) == (
        "Pikachu",
        "037",
        "198",
        ui.get_set_era(SV01_CODE),
    )
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert set_format == "text"
    assert len(calls) == 2


def test_parse_with_available_sets(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    importlib.reload(ui)

    img = tmp_path / "x.jpg"
    img.write_bytes(b"data")

    payload = {
        "name": "Pikachu",
        "number": "037/198",
        "set_name": SV01_NAME,
        "era_name": ui.get_set_era(SV01_CODE),
        "set_format": "text",
    }
    resp = SimpleNamespace(output_text=json.dumps(payload))

    calls = []

    def create(*a, **k):
        calls.append(k)
        return resp

    class DummyClient:
        def __init__(self, *a, **k):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(ui.openai, "OpenAI", DummyClient)
    name, number, total, era_name, set_name, set_code, set_format = ui.extract_card_info_openai(
        str(img), available_sets=[SV01_NAME]
    )
    assert set_name == SV01_NAME
    assert set_code == SV01_CODE
    enums = (
        calls[0]["response_format"]["json_schema"]["schema"]["properties"]["set_name"]["enum"]
    )
    assert enums == [SV01_NAME]
