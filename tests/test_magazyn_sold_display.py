import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent))
from ctk_mocks import (  # noqa: E402
    DummyCTkButton,
    DummyCTkFrame,
    DummyCTkLabel,
    DummyCTkScrollableFrame,
    DummyCanvas,
)


def test_sold_cards_styled(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n" "A;1;S1;K1R1P1;1;;\n" "B;2;S2;K1R1P2;1;;1\n",
        encoding="utf-8",
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

        ui.CardEditorApp.open_magazyn_window(app)

    assert len(app.mag_card_labels) == 1
    assert len(app.mag_sold_labels) == 1
    assert app.mag_sold_labels[0].text.startswith("[SOLD]")
    assert app.mag_sold_labels[0].text_color == "#888888"
    font = app.mag_sold_labels[0].font
    assert getattr(font, "overstrike", False) or (
        isinstance(font, tuple) and "overstrike" in font
    )
