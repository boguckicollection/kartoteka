import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import (
    DummyCTkButton,
    DummyCTkEntry,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkOptionMenu,
    DummyCTkScrollableFrame,
    DummyCanvas,
)


def _load_app(csv_path, stats, frame_cls=DummyCTkFrame):
    import types
    fake_tk = types.ModuleType("tkinter")
    def _raise(*a, **k):
        raise Exception
    fake_tk.StringVar = _raise
    fake_tk.TclError = Exception
    fake_tk.Canvas = object
    fake_tk.__path__ = []
    sys.modules["tkinter"] = fake_tk
    sys.modules["tkinter.filedialog"] = SimpleNamespace(
        askdirectory=lambda *a, **k: None,
        askopenfilename=lambda *a, **k: None,
        asksaveasfilename=lambda *a, **k: None,
    )
    sys.modules["tkinter.messagebox"] = SimpleNamespace(
        showinfo=lambda *a, **k: None,
        showerror=lambda *a, **k: None,
        showwarning=lambda *a, **k: None,
        askyesno=lambda *a, **k: None,
    )
    sys.modules["tkinter.simpledialog"] = SimpleNamespace(
        askstring=lambda *a, **k: None,
        askinteger=lambda *a, **k: None,
    )
    sys.modules["tkinter.ttk"] = SimpleNamespace()

    sys.modules.setdefault(
        "imagehash",
        SimpleNamespace(
            ImageHash=object,
            phash=lambda *a, **k: object(),
            dhash=lambda *a, **k: object(),
            average_hash=lambda *a, **k: object(),
        ),
    )
    for mod in ["openai", "pytesseract", "numpy"]:
        sys.modules.setdefault(mod, SimpleNamespace())
    sys.modules.setdefault("requests", SimpleNamespace(RequestException=Exception))
    sys.modules.setdefault("pydantic", SimpleNamespace(BaseModel=object))
    sys.modules.setdefault("dotenv", SimpleNamespace(load_dotenv=lambda *a, **k: None, set_key=lambda *a, **k: None))

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=frame_cls,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)
    ui.ImageTk.PhotoImage = lambda *a, **k: photo_mock
    ui.tk.Canvas = DummyCanvas
    ui.csv_utils.WAREHOUSE_CSV = str(csv_path)
    ui.csv_utils.get_inventory_stats = lambda: stats

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
    return app, ui


def test_magazyn_displays_all_cards(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    header = "name;number;era;set;warehouse_code;price;image;variant\n"
    rows = [
        f"Card{i:02d};{i};E;S;K{i};1;img{i}.png;common\n" for i in range(25)
    ]
    csv_path.write_text(header + "".join(rows), encoding="utf-8")

    app, _ = _load_app(csv_path, (25, 25.0, 0, 0))

    assert len(app.mag_card_labels) == 25
    assert not hasattr(app, "mag_prev_button")
    assert not hasattr(app, "mag_next_button")


def test_magazyn_adaptive_grid(tmp_path):
    class RecordingFrame(DummyCTkFrame):
        def grid(self, **kwargs):
            self.grid_kwargs = kwargs
            return self

    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;era;set;warehouse_code;price;image;variant\n"
        "A;1;E;S;K1;1;foo1.png;common\n"
        "B;2;E;S;K2;1;foo2.png;common\n"
        "C;3;E;S;K3;1;foo3.png;common\n",
        encoding="utf-8",
    )

    app, _ = _load_app(csv_path, (3, 3.0, 0, 0), frame_cls=RecordingFrame)

    frames = app.mag_card_frames
    app.mag_list_frame.winfo_width = lambda: 600
    app._relayout_mag_cards()
    assert frames[0].grid_kwargs["row"] == 0
    assert frames[0].grid_kwargs["column"] == 0
    assert frames[1].grid_kwargs["row"] == 0
    assert frames[1].grid_kwargs["column"] == 1

    app.mag_list_frame.winfo_width = lambda: 200
    app._relayout_mag_cards()
    assert frames[1].grid_kwargs["row"] == 1
    assert frames[1].grid_kwargs["column"] == 0

