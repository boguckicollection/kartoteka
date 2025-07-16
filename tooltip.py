import customtkinter as ctk

class Tooltip:
    """Display a tooltip for a given widget."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        self.tipwindow = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        ctk.CTkLabel(tw, text=self.text).pack()
        tw.wm_geometry("+%d+%d" % (x, y))

    def hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None
