import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import csv
from PIL import Image

# Dummy widgets to simulate customtkinter components
class _Widget:
    def pack(self, *a, **k):
        return self

    def grid(self, *a, **k):
        return self

    def destroy(self):
        pass


class DummyCTkFrame(_Widget):
    def __init__(self, master=None, fg_color=None, **kwargs):
        self.master = master
        self.fg_color = fg_color


class DummyCTkLabel(_Widget):
    def __init__(self, master=None, text="", image=None, fg_color=None, text_color=None, compound=None, anchor=None, **kwargs):
        self.master = master
        self.text = text
        self.image = image
        self.fg_color = fg_color
        self.text_color = text_color
        self.compound = compound
        self.anchor = anchor
        self._bindings = {}

    def bind(self, event, callback):
        self._bindings[event] = callback
        return self


class DummyCTkButton(_Widget):
    def __init__(self, master=None, **kwargs):
        self.master = master
        self.kwargs = kwargs


class DummyCTkScrollableFrame(_Widget):
    def __init__(self, master=None, fg_color=None, **kwargs):
        self.master = master
        self.fg_color = fg_color


class DummyCanvas(_Widget):
    def __init__(self, master=None, width=0, height=0, highlightthickness=0):
        self.master = master
        self.width_val = width
        self.height_val = height
        self.bg = None

    def config(self, **kwargs):
        if "bg" in kwargs:
            self.bg = kwargs["bg"]

    def create_image(self, *a, **k):
        pass

    def create_rectangle(self, *a, **k):
        pass

    def create_text(self, *a, **k):
        pass

    def delete(self, *a, **k):
        pass

    def width(self):
        return self.width_val

    def height(self):
        return self.height_val


def test_show_card_details_receives_row(tmp_path):
    # Prepare CSV and image
    img_path = tmp_path / "card.png"
    Image.new("RGB", (10, 10), "white").save(img_path)
    csv_path = tmp_path / "magazyn.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "number", "set", "warehouse_code", "price", "image"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Test Card",
                "number": "001",
                "set": "Base",
                "warehouse_code": "K1R1P1",
                "price": "9.99",
                "image": str(img_path),
            }
        )

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)

    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)):
        dummy_root = SimpleNamespace(minsize=lambda *a, **k: None)
        captured = {}

        def fake_show(row):
            captured["row"] = row

        app = SimpleNamespace(
            root=dummy_root,
            start_frame=None,
            pricing_frame=None,
            shoper_frame=None,
            frame=None,
            magazyn_frame=None,
            location_frame=None,
            create_button=lambda master, **kwargs: DummyCTkButton(master, **kwargs),
            refresh_magazyn=lambda: None,
            back_to_welcome=lambda: None,
            show_card_details=fake_show,
        )

        ui.CardEditorApp.open_magazyn_window(app)
        label = app.mag_card_labels[0]
        label._bindings["<Button-1>"](None)

    assert captured["row"]["name"] == "Test Card"
    assert captured["row"]["warehouse_code"] == "K1R1P1"
