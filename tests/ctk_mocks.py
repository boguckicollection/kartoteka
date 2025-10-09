class _Widget:
    def pack(self, *a, **k):
        self.pack_calls = getattr(self, "pack_calls", [])
        self.pack_calls.append((a, k))
        self.pack_params = k
        return self

    def grid(self, *a, **k):
        self.grid_calls = getattr(self, "grid_calls", [])
        self.grid_calls.append((a, k))
        self.grid_params = k
        return self

    def destroy(self):
        pass

    def configure(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    def winfo_exists(self):
        return True

    def grid_columnconfigure(self, index, weight=0):
        if not hasattr(self, "_grid_columns"):
            self._grid_columns = {}
        self._grid_columns[index] = {"weight": weight}
        return self


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


class DummyCTkCheckBox(_Widget):
    def __init__(self, master=None, text="", variable=None, text_color=None, **kwargs):
        self.master = master
        self.text = text
        self.variable = variable
        self.text_color = text_color
        self.kwargs = kwargs
        if variable is not None and hasattr(variable, "get"):
            try:
                variable.set(variable.get())
            except Exception:
                pass


class DummyCTkScrollableFrame(_Widget):
    def __init__(self, master=None, fg_color=None, **kwargs):
        self.master = master
        self.fg_color = fg_color


class DummyCTkEntry(_Widget):
    def __init__(self, master=None, textvariable=None, placeholder_text=None, **kwargs):
        self.master = master
        self.textvariable = textvariable
        self.placeholder_text = placeholder_text


class DummyCTkOptionMenu(_Widget):
    def __init__(self, master=None, variable=None, values=(), command=None, **kwargs):
        self.master = master
        self.variable = variable
        self.values = list(values)
        self.command = command

    def set(self, value):
        if self.variable is not None:
            self.variable.set(value)
        if callable(self.command):
            self.command(value)


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


class DummyCanvas(_Widget):
    def __init__(self, master=None, width=0, height=0, highlightthickness=0):
        self.master = master
        self.width_val = width
        self.height_val = height
        self.bg = None
        self.items = {}
        self._next_id = 1

    def config(self, **kwargs):
        if "bg" in kwargs:
            self.bg = kwargs["bg"]

    def create_image(self, *a, **k):
        pass

    def create_rectangle(self, x1, y1, x2, y2, fill="", outline=None, width=1):
        rid = self._next_id
        self._next_id += 1
        self.items[rid] = {"coords": (x1, y1, x2, y2), "fill": fill}
        return rid

    def create_text(self, *a, **k):
        pass

    def delete(self, rid):
        self.items.pop(rid, None)

    def itemconfigure(self, rid, **kwargs):
        item = self.items.get(rid)
        if not item:
            return
        if "fill" in kwargs:
            item["fill"] = kwargs["fill"]

    def coords(self, rid, x1, y1, x2, y2):
        item = self.items.get(rid)
        if item:
            item["coords"] = (x1, y1, x2, y2)

    def width(self):
        return self.width_val

    def height(self):
        return self.height_val
