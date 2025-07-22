from kartoteka import CardEditorApp
import customtkinter as ctk
import tkinter as tk
import os

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    ico_path = os.path.join(os.path.dirname(__file__), "logo-_1_.ico")
    if os.path.exists(ico_path):
        try:
            root.iconbitmap(ico_path)
        except Exception:
            pass
    icon_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(icon_path):
        root.iconphoto(True, tk.PhotoImage(file=icon_path))
    app = CardEditorApp(root)
    root.mainloop()
