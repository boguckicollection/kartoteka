import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

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
    def __init__(
        self,
        master=None,
        text="",
        fg_color=None,
        text_color=None,
        font=None,
        **kwargs,
    ):
        self.master = master
        self.text = text
        self.fg_color = fg_color
        self.text_color = text_color
        self.font = font
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


class DummyCTkEntry(_Widget):
    def __init__(self, master=None, textvariable=None, **kwargs):
        self.master = master
        self.textvariable = textvariable


class DummyCTkOptionMenu(_Widget):
    def __init__(self, master=None, variable=None, values=(), command=None, **kwargs):
        self.master = master
        self.variable = variable
        self.values = list(values)
        self.command = command


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


class DummyCTkProgressBar(_Widget):
    def __init__(
        self,
        master=None,
        orientation="horizontal",
        fg_color=None,
        progress_color=None,
        **kwargs,
    ):
        self.master = master
        self.orientation = orientation
        self.value = 0
        self.fg_color = fg_color
        self.progress_color = progress_color

    def set(self, value):
        self.value = value

    def get(self):
        return self.value

def test_magazyn_label_colors():
    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
        CTkProgressBar=DummyCTkProgressBar,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)

    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), patch.object(
        ui.messagebox, "showinfo", lambda *a, **k: None
    ):
        dummy_root = SimpleNamespace(
            minsize=lambda *a, **k: None,
            title=lambda *a, **k: None,
        )
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
        )

        ui.CardEditorApp.show_magazyn_view(app)
        ui.CardEditorApp.build_box_preview(app, app.magazyn_frame)

    label = app.mag_labels[0]
    assert label.fg_color == ui.BG_COLOR
    assert label.text_color == ui.TEXT_COLOR
    assert label.font == ("Segoe UI", 24, "bold")

    key = (app.mag_box_order[0], 1)
    bar = app.mag_progressbars[key]
    assert bar.fg_color == ui.FREE_COLOR
    assert bar.progress_color == ui.OCCUPIED_COLOR
    pct = app.mag_percent_labels[key]
    assert pct.font == ("Segoe UI", 24, "bold")
    assert pct.text_color == ui._occupancy_color(0)
