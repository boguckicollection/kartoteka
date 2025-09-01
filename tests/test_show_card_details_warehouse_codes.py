from types import SimpleNamespace
from pathlib import Path
from PIL import Image
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from tests.ctk_mocks import (
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkButton,
    DummyCTkOptionMenu,
)


def test_show_card_details_splits_warehouse_codes(monkeypatch):
    top = SimpleNamespace(
        title=lambda t: None,
        geometry=lambda *a, **k: None,
        minsize=lambda *a, **k: None,
    )
    labels = []
    option_menus = []

    class CapturingLabel(DummyCTkLabel):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            labels.append(self)

    class CapturingOptionMenu(DummyCTkOptionMenu):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            option_menus.append(self)

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkToplevel=lambda master: top,
        CTkFrame=DummyCTkFrame,
        CTkLabel=CapturingLabel,
        CTkButton=DummyCTkButton,
        CTkOptionMenu=CapturingOptionMenu,
    )

    import importlib
    import kartoteka.ui as ui
    importlib.reload(ui)

    monkeypatch.setattr(ui, "_load_image", lambda path: Image.new("RGB", (1, 1)))
    monkeypatch.setattr(ui, "_create_image", lambda img: SimpleNamespace())

    app = SimpleNamespace(root=None, mark_as_sold=lambda *a, **k: None)
    ui.CardEditorApp.show_card_details(app, {"warehouse_code": "K1;K2"})

    texts = [lbl.text for lbl in labels]
    assert "Kody magazynowe:" in texts
    assert option_menus[0].values == ["K1", "K2"]
