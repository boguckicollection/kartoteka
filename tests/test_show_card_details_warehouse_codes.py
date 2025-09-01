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


labels: list = []
option_menus: list = []
buttons: list = []


class CapturingLabel(DummyCTkLabel):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        labels.append(self)


class CapturingOptionMenu(DummyCTkOptionMenu):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        option_menus.append(self)


class CapturingButton(DummyCTkButton):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        buttons.append(k)


def setup_ctk():
    top = SimpleNamespace(
        title=lambda t: None,
        geometry=lambda *a, **k: None,
        minsize=lambda *a, **k: None,
    )
    sys.modules["customtkinter"] = SimpleNamespace(
        CTkToplevel=lambda master: top,
        CTkFrame=DummyCTkFrame,
        CTkLabel=CapturingLabel,
        CTkButton=CapturingButton,
        CTkOptionMenu=CapturingOptionMenu,
    )
    return top


def reload_ui(monkeypatch):
    import importlib
    import kartoteka.ui as ui
    importlib.reload(ui)
    monkeypatch.setattr(ui, "_load_image", lambda path: Image.new("RGB", (1, 1)))
    monkeypatch.setattr(ui, "_create_image", lambda img: SimpleNamespace())
    return ui


def test_show_card_details_displays_single_code_fields(monkeypatch):
    global labels, option_menus, buttons
    labels, option_menus, buttons = [], [], []
    setup_ctk()
    ui = reload_ui(monkeypatch)

    app = SimpleNamespace(root=None, mark_as_sold=lambda *a, **k: None)
    ui.CardEditorApp.show_card_details(app, {"warehouse_code": "K1R2P3"})

    texts = [lbl.text for lbl in labels]
    assert "Karton: 1" in texts
    assert "Kolumna: 2" in texts
    assert "Pozycja: 3" in texts


def test_show_card_details_updates_labels_for_multiple_codes(monkeypatch):
    global labels, option_menus, buttons
    labels, option_menus, buttons = [], [], []
    setup_ctk()
    ui = reload_ui(monkeypatch)

    captured = []
    app = SimpleNamespace(root=None, mark_as_sold=lambda r, w=None, c=None: captured.append(c))

    class DummyVar:
        def __init__(self, value=""):
            self._v = value

        def get(self):
            return self._v

        def set(self, v):
            self._v = v

    monkeypatch.setattr(ui.tk, "StringVar", DummyVar)
    ui.CardEditorApp.show_card_details(app, {"warehouse_code": "K1R1P1;K2R2P2"})

    texts = [lbl.text for lbl in labels]
    # initial labels correspond to the first code
    assert "Kody magazynowe:" in texts
    assert "Karton: 1" in texts
    assert "Kolumna: 1" in texts
    assert "Pozycja: 1" in texts
    # option menu should expose raw codes for backend usage
    assert option_menus[0].values == ["K1R1P1", "K2R2P2"]

    option_menus[0].set("K2R2P2")
    texts = [lbl.text for lbl in labels]
    assert "Karton: 2" in texts
    assert "Kolumna: 2" in texts
    assert "Pozycja: 2" in texts

    sprzedano_btn = next(b for b in buttons if b.get("text") == "Sprzedano")
    sprzedano_btn["command"]()
    assert captured == ["K2R2P2"]
