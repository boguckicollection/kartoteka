from types import SimpleNamespace
from pathlib import Path
from PIL import Image
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import kartoteka.ui as ui
from tests.ctk_mocks import DummyCTkFrame, DummyCTkLabel, DummyCTkButton


def test_show_card_details_splits_warehouse_codes(monkeypatch):
    top = SimpleNamespace(
        title=lambda t: None,
        geometry=lambda *a, **k: None,
        minsize=lambda *a, **k: None,
    )
    monkeypatch.setattr(ui.ctk, "CTkToplevel", lambda master: top)
    monkeypatch.setattr(ui.ctk, "CTkFrame", DummyCTkFrame)
    labels = []

    class CapturingLabel(DummyCTkLabel):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            labels.append(self)

    monkeypatch.setattr(ui.ctk, "CTkLabel", CapturingLabel)
    monkeypatch.setattr(ui.ctk, "CTkButton", DummyCTkButton)
    monkeypatch.setattr(ui, "_load_image", lambda path: Image.new("RGB", (1, 1)))
    monkeypatch.setattr(ui, "_create_image", lambda img: SimpleNamespace())

    app = SimpleNamespace(root=None, mark_as_sold=lambda *a, **k: None)
    ui.CardEditorApp.show_card_details(app, {"warehouse_code": "K1;K2"})

    texts = [lbl.text for lbl in labels]
    assert "Kody magazynowe:" in texts
    assert "K1" in texts
    assert "K2" in texts
