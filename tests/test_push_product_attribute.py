import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())
sys.path.append(str(Path(__file__).resolve().parents[1]))
import kartoteka.ui as ui
importlib.reload(ui)

class DummyVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

class DummyText:
    def delete(self, *a, **k):
        pass
    def insert(self, *a, **k):
        pass


def test_push_product_posts_attribute(monkeypatch):
    fake_client = SimpleNamespace(
        add_product=lambda data: {"product_id": 3},
        get_attributes=lambda: {"list": [{"attribute_id": 2, "name": "Typ"}]},
        add_product_attribute=MagicMock(),
    )

    dummy = SimpleNamespace(
        output_data=[{"foo": "bar", "card_type": "R"}],
        index=0,
        save_current_data=lambda: None,
        _build_shoper_payload=lambda card: {"name": "x"},
        shoper_client=fake_client,
        type_vars={"Reverse": DummyVar(True)},
        entries={},
    )

    monkeypatch.setattr(ui.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(ui.tk, "Text", DummyText, raising=False)
    monkeypatch.setattr(ui.tk, "END", "end", raising=False)

    widget = DummyText()
    ui.CardEditorApp.push_product(dummy, widget)

    fake_client.add_product_attribute.assert_called_once_with(3, 2, ["Reverse"])
