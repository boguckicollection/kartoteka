import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import csv
import io
from PIL import Image
import requests


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

    def bind(self, event, callback):
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


class DummyCTkCheckBox(_Widget):
    def __init__(self, master=None, text="", variable=None, text_color=None, **kwargs):
        self.master = master
        self.text = text
        self.variable = variable
        self.text_color = text_color
        self.kwargs = kwargs


class DummyCTkOptionMenu(_Widget):
    def __init__(self, master=None, variable=None, values=(), command=None, **kwargs):
        self.master = master
        self.variable = variable
        self.values = list(values)
        self.command = command


class DummyCTkToplevel(_Widget):
    def __init__(self, master=None):
        self.master = master
        self.children = []

    def title(self, *a, **k):
        return self


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


def _setup_module(tmp_path):
    """Import ``ui`` module with dummy customtkinter widgets."""

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkCheckBox=DummyCTkCheckBox,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkToplevel=DummyCTkToplevel,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)
    return ui


def _write_csv(path, image_url):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "number", "set", "warehouse_code", "price", "image"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Remote Card",
                "number": "001",
                "set": "Base",
                "warehouse_code": "K1R1P1",
                "price": "9.99",
                "image": image_url,
            }
        )


def test_show_magazyn_view_remote_thumbnail(tmp_path):
    ui = _setup_module(tmp_path)

    url = "https://example.com/card.png"
    csv_path = tmp_path / "magazyn.csv"
    _write_csv(csv_path, url)

    img_bytes = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(img_bytes, format="PNG")
    img_bytes = img_bytes.getvalue()

    placeholder_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)
    photo_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)

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
        show_card_details=lambda *a, **k: None,
    )

    resp = SimpleNamespace(content=img_bytes, raise_for_status=lambda: None)

    calls = iter([placeholder_mock, photo_mock])

    def _photo_side_effect(*a, **k):
        try:
            return next(calls)
        except StopIteration:
            return photo_mock

    with patch.object(ui.ImageTk, "PhotoImage", side_effect=_photo_side_effect), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.requests, "get", return_value=resp) as mock_get, \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)), \
         patch.object(ui.messagebox, "showinfo", lambda *a, **k: None):
        ui.CardEditorApp.show_magazyn_view(app)
        for t in app._image_threads:
            t.join()

    assert mock_get.called
    assert app.mag_card_images[0] is photo_mock


def test_show_magazyn_view_local_thumbnail(tmp_path):
    ui = _setup_module(tmp_path)

    img_path = tmp_path / "card.png"
    Image.new("RGB", (10, 10), "white").save(img_path, format="PNG")
    csv_path = tmp_path / "magazyn.csv"
    _write_csv(csv_path, str(img_path))

    placeholder_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)
    photo_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)

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
        show_card_details=lambda *a, **k: None,
    )

    calls = iter([placeholder_mock, photo_mock])

    def _photo_side_effect(*a, **k):
        try:
            return next(calls)
        except StopIteration:
            return photo_mock

    with patch.object(ui.ImageTk, "PhotoImage", side_effect=_photo_side_effect), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)), \
         patch.object(ui.messagebox, "showinfo", lambda *a, **k: None):
        ui.CardEditorApp.show_magazyn_view(app)
        assert app._image_threads  # ensures a thread was spawned
        for t in app._image_threads:
            t.join()

    assert app.mag_card_images[0] is photo_mock


def test_show_card_details_remote_uses_cache(tmp_path):
    ui = _setup_module(tmp_path)

    url = "https://example.com/card.png"
    csv_path = tmp_path / "magazyn.csv"
    _write_csv(csv_path, url)

    img_bytes = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(img_bytes, format="PNG")
    img_bytes = img_bytes.getvalue()

    photo_mock = SimpleNamespace(width=lambda: 64, height=lambda: 64)

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

    resp = SimpleNamespace(content=img_bytes, raise_for_status=lambda: None)

    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.requests, "get", return_value=resp) as mock_get, \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)):
        # first load thumbnails
        ui.CardEditorApp.show_magazyn_view(app)
        for t in app._image_threads:
            t.join()
        # then show details which should reuse cache and not trigger new request
        ui.CardEditorApp.show_card_details(app, app.mag_card_rows[0])

    # only one HTTP request despite two image loads
    assert mock_get.call_count == 1


def test_load_image_ssl_error_retry(tmp_path):
    ui = _setup_module(tmp_path)

    url = "https://example.com/card.png"
    img_bytes = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(img_bytes, format="PNG")
    img_bytes = img_bytes.getvalue()
    resp = SimpleNamespace(content=img_bytes, raise_for_status=lambda: None)

    DummySSLError = type("DummySSLError", (Exception,), {})
    side_effects = [DummySSLError("bad ssl"), resp]

    def _side_effect(*args, **kwargs):
        result = side_effects.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch.object(ui.requests, "get", side_effect=_side_effect) as mock_get, \
         patch.object(ui.requests.exceptions, "SSLError", DummySSLError):
        img = ui._load_image(url)

    assert img is not None
    assert mock_get.call_count == 2
    first_kwargs = mock_get.call_args_list[0][1]
    assert first_kwargs["verify"] is True
    assert first_kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
    assert mock_get.call_args_list[1][1]["verify"] is False
    assert mock_get.call_args_list[1][1]["headers"]["User-Agent"] == "Mozilla/5.0"


def test_load_image_connection_error_retry_cached(tmp_path):
    url = "https://example.com/card.png"
    img_bytes = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(img_bytes, format="PNG")
    img_bytes = img_bytes.getvalue()

    def _run_with_error(error_factory):
        ui = _setup_module(tmp_path)
        resp = SimpleNamespace(content=img_bytes, raise_for_status=lambda: None)
        side_effects = [error_factory(ui), resp]

        def _side_effect(*args, **kwargs):
            result = side_effects.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.object(ui.requests, "get", side_effect=_side_effect) as mock_get:
            first_img = ui._load_image(url)
            cached_img = ui._load_image(url)

        assert first_img is not None
        assert cached_img is not None
        assert mock_get.call_count == 2
        first_kwargs = mock_get.call_args_list[0][1]
        second_kwargs = mock_get.call_args_list[1][1]
        assert first_kwargs["verify"] is True
        assert first_kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        assert second_kwargs["verify"] is False
        assert second_kwargs["headers"]["User-Agent"] == "Mozilla/5.0"

    disconnect_message = "Remote end closed connection without response"
    error_factories = [
        lambda module: module.requests.exceptions.ConnectionError(
            module.urllib3.exceptions.ProtocolError(
                "Connection aborted.",
                module.RemoteDisconnected(disconnect_message),
            )
        ),
        lambda module: module.urllib3.exceptions.ProtocolError(
            "Connection aborted.",
            module.RemoteDisconnected(disconnect_message),
        ),
    ]

    for factory in error_factories:
        _run_with_error(factory)
