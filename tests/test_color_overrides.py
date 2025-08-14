import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


def test_color_env_override(monkeypatch):
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    monkeypatch.setitem(sys.modules, "customtkinter", SimpleNamespace())
    import kartoteka.ui as ui
    monkeypatch.setenv("SOLD_COLOR", "#123456")
    importlib.reload(ui)
    assert ui.SOLD_COLOR == "#123456"
    monkeypatch.delenv("SOLD_COLOR", raising=False)
    importlib.reload(ui)
    assert ui.SOLD_COLOR == "#888888"
