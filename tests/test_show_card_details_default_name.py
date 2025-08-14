from types import SimpleNamespace

from PIL import Image
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.ui as ui
from tests.ctk_mocks import DummyCTkFrame, DummyCTkLabel, DummyCTkButton


def test_show_card_details_uses_localized_fallback(monkeypatch):
    top = SimpleNamespace(
        title=lambda t: setattr(top, "title_value", t),
        geometry=lambda *a, **k: None,
        minsize=lambda *a, **k: None,
    )
    monkeypatch.setattr(ui.ctk, "CTkToplevel", lambda master: top)
    monkeypatch.setattr(ui.ctk, "CTkFrame", DummyCTkFrame)
    monkeypatch.setattr(ui.ctk, "CTkLabel", DummyCTkLabel)
    monkeypatch.setattr(ui.ctk, "CTkButton", DummyCTkButton)
    monkeypatch.setattr(ui, "_load_image", lambda path: Image.new("RGB", (1, 1)))
    monkeypatch.setattr(ui, "_create_image", lambda img: SimpleNamespace())
    app = SimpleNamespace(root=None, mark_as_sold=lambda *a, **k: None)
    ui.CardEditorApp.show_card_details(app, {})
    assert top.title_value == "Karta"
