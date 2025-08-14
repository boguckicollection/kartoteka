class _Widget:
    def pack(self, *a, **k):
        return self

    def grid(self, *a, **k):
        return self

    def destroy(self):
        pass

    def configure(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    def winfo_exists(self):
        return True


class DummyCTkFrame(_Widget):
    def __init__(self, master=None, fg_color=None, **kwargs):
        self.master = master
        self.fg_color = fg_color


class DummyCTkLabel(_Widget):
    def __init__(
        self,
        master=None,
        text="",
        image=None,
        fg_color=None,
        text_color=None,
        compound=None,
        font=None,
        **kwargs,
    ):
        self.master = master
        self.text = text
        self.image = image
        self.fg_color = fg_color
        self.text_color = text_color
        self.compound = compound
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
