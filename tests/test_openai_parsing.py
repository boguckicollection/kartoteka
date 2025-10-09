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


def test_parse_chat_completion_structure(monkeypatch, tmp_path):
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
    resp = {"choices": [{"message": {"content": json.dumps(payload)}}]}

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


def test_parse_code_relaxed_validation(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("STRICT_SET_VALIDATION", "0")
    importlib.reload(ui)

    img = tmp_path / "x.jpg"
    img.write_bytes(b"data")

    payload = {
        "name": "Pikachu",
        "number": "037/198",
        "set_name": f"{SV01_NAME} EN",
        "era_name": "SV EN",
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
        str(img)
    )
    assert (name, number, total) == ("Pikachu", "037", "198")
    assert set_code == SV01_CODE
    assert set_name == SV01_NAME
    assert era_name == ui.get_set_era(SV01_CODE)
    assert set_format == "text"
    assert calls and "response_format" in calls[0]
    props = calls[0]["response_format"]["json_schema"]["schema"]["properties"]["set_name"]
    assert "enum" not in props


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
        if len(calls) < 3:
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
    assert len(calls) == 3
    assert "response_format" in calls[0]
    assert "response_format" in calls[1]
    assert "response_format" not in calls[2]


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
        if len(calls) < 3:
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
    assert len(calls) == 3
    assert "response_format" in calls[0]
    assert "response_format" in calls[1]
    assert "response_format" not in calls[2]


def test_parse_code_fallback_enums(monkeypatch, tmp_path):
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
        if len(calls) == 1:
            raise ui.openai.OpenAIError("bad enum")
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
    first_props = calls[0]["response_format"]["json_schema"]["schema"]["properties"]
    assert "enum" in first_props["set_name"]
    assert "response_format" in calls[1]
    second_props = calls[1]["response_format"]["json_schema"]["schema"]["properties"]
    assert "enum" not in second_props["set_name"]


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


def test_parse_alt_output_attr(monkeypatch, tmp_path):
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
    resp = SimpleNamespace(
        output=[SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])]
    )

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


def test_parse_alt_output_dict(monkeypatch, tmp_path):
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
    resp = {
        "output": [
            {
                "content": [{"text": {"value": json.dumps(payload)}}]
            }
        ]
    }

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
