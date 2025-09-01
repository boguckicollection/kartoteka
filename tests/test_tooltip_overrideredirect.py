import sys
from types import SimpleNamespace


def test_tooltip_overrideredirect_called():
    called = {
        "flag": False
    }

    class DummyTop:
        def wm_overrideredirect(self, value):
            called["flag"] = value

        def wm_geometry(self, *a, **k):
            pass

    top = DummyTop()

    class DummyLabel:
        def __init__(self, master=None, text=""):
            pass

        def pack(self, *a, **k):
            return self

    def fake_toplevel(parent):
        return top

    sys.modules["customtkinter"] = SimpleNamespace(
        CTkToplevel=fake_toplevel,
        CTkLabel=DummyLabel,
    )

    import importlib
    import tooltip
    importlib.reload(tooltip)
    Tooltip = tooltip.Tooltip

    widget = SimpleNamespace(
        bind=lambda *a, **k: None,
        winfo_rootx=lambda: 0,
        winfo_rooty=lambda: 0,
        winfo_height=lambda: 0,
    )

    t = Tooltip(widget, "tip")
    t.show()

    assert called["flag"] is True
