import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import (  # noqa: E402
    DummyCTkButton,
    DummyCTkEntry,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkOptionMenu,
    DummyCTkScrollableFrame,
    DummyCanvas,
)


def test_group_duplicates(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;variant\n"
        "A;1;S;K1R1P1;1;foo1.png;common\n"
        "A;1;S;K1R1P2;1;foo2.png;common\n",
        encoding="utf-8",
    )

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkFrame=DummyCTkFrame,
        CTkLabel=DummyCTkLabel,
        CTkButton=DummyCTkButton,
        CTkScrollableFrame=DummyCTkScrollableFrame,
        CTkEntry=DummyCTkEntry,
        CTkOptionMenu=DummyCTkOptionMenu,
    )
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    import kartoteka.ui as ui
    import importlib
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)

    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
        patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)), \
        patch.object(ui.messagebox, "showinfo", lambda *a, **k: None):
        duplicates = ui.csv_utils.find_duplicates("A", "1", "S", None)
        assert {row["warehouse_code"] for row in duplicates} == {"K1R1P1", "K1R1P2"}

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

    assert len(app.mag_card_rows) == 1
    row = app.mag_card_rows[0]
    assert row["_count"] == 2
    assert row["warehouse_code"] == "K1R1P1;K1R1P2"
    assert row["image"] == "foo1.png"
