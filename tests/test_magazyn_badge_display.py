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


def test_badge_display_for_duplicates_only(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant\n"
        "A;1;S;K1R1P1;1;foo1.png;common\n"
        "A;1;S;K1R1P2;1;foo2.png;common\n"
        "B;2;S;K1R1P3;1;foo3.png;common\n",
        encoding="utf-8",
    )

    created_labels = []

    class RecordingDummyCTkLabel(DummyCTkLabel):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.kwargs = k
            created_labels.append(self)

        def place(self, **kwargs):
            self.place_kwargs = kwargs
            return self

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=RecordingDummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)

    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)), \
         patch.object(ui.csv_utils, "get_inventory_stats", return_value=(3, 3.0, 0, 0)):
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

    badges = [lbl for lbl in created_labels if lbl.kwargs.get("width") == 20]
    assert len(badges) == 1
    badge = badges[0]
    assert badge.text == "2"
    assert badge.fg_color == "#FF0000"
    assert badge.text_color == "white"
    assert badge.kwargs.get("height") == 20
    assert badge.kwargs.get("corner_radius") == 10
    assert badge.place_kwargs.get("relx") == 1.0
    assert badge.place_kwargs.get("rely") == 0.0
    assert badge.place_kwargs.get("anchor") == "ne"
    assert "in_" in badge.place_kwargs
