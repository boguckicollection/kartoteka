import importlib
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


def _extract_label(widget):
    """Return the innermost label regardless of wrapping structure."""
    seen = set()
    current = widget
    while id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, dict) and "label" in current:
            current = current["label"]
            continue
        if hasattr(current, "label"):
            current = current.label
            continue
        break
    return current


def test_sold_cards_styled(tmp_path):
    csv_path = tmp_path / "magazyn.csv"
    csv_path.write_text(
        "name;number;set;warehouse_code;price;image;sold\n"
        "A;1;S1;K1R1P1;1;foo.png;\n"
        "B;2;S2;K1R1P2;1;foo.png;1\n",
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
    importlib.reload(ui)

    photo_mock = SimpleNamespace(width=lambda: 150, height=lambda: 150)

    with patch.object(ui.ImageTk, "PhotoImage", return_value=photo_mock), \
         patch.object(ui.tk, "Canvas", DummyCanvas), \
         patch.object(ui.csv_utils, "WAREHOUSE_CSV", str(csv_path)):
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
        app.mag_sold_filter_var.set("all")
        app._update_mag_list()

    assert len(app.mag_card_labels) == 1
    assert len(app.mag_sold_labels) == 1
    sold_label = _extract_label(app.mag_sold_labels[0])
    assert sold_label.text.startswith("[SOLD]")
    assert sold_label.text_color == ui.SOLD_COLOR
    font = sold_label.font
    assert getattr(font, "overstrike", False) or (
        isinstance(font, tuple) and "overstrike" in font
    )
