from kartoteka import CardEditorApp
import customtkinter as ctk
import tkinter as tk
import sys
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    try:
        if sys.platform.startswith("win"):
            root.iconbitmap("logo-_1_.ico")
        else:
            root.iconphoto(True, tk.PhotoImage(file="logo.png"))
    except Exception as exc:
        logging.exception("Failed to load application icon: %s", exc)
    app = CardEditorApp(root)
    root.mainloop()
