import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from ttkbootstrap import Style

try:
    from ttkbootstrap.icons import Icon
except Exception:  # pragma: no cover - fall back when icons unavailable
    Icon = None
from PIL import Image, ImageTk
import os
import csv
import json
import requests
import re
from collections import defaultdict
from dotenv import load_dotenv

from shoper_client import ShoperClient
from tooltip import Tooltip
import webbrowser
from urllib.parse import urlencode
import io

load_dotenv()

BASE_IMAGE_URL = "https://sklep839679.shoparena.pl/upload/images"

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

SHOPER_API_URL = os.getenv("SHOPER_API_URL")
SHOPER_API_TOKEN = os.getenv("SHOPER_API_TOKEN")

PRICE_DB_PATH = "card_prices.csv"
PRICE_MULTIPLIER = 1.23
HOLO_REVERSE_MULTIPLIER = 3.5


def load_icon(name: str):
    """Safely load ttkbootstrap icon if available."""
    if Icon and hasattr(Icon, "load"):
        try:
            return Icon.load(name)
        except Exception:
            return None
    return None


# Wczytanie danych setów
with open("tcg_sets.json", encoding="utf-8") as f:
    tcg_sets_eng = list(json.load(f).keys())

with open("tcg_sets_jp.json", encoding="utf-8") as f:
    tcg_sets_jp = list(json.load(f).keys())


class CardEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("KARTOTEKA")
        # improve default font for all widgets
        self.root.option_add("*Font", ("Helvetica", 12))
        self.index = 0
        self.cards = []
        self.image_objects = []
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.card_cache = {}
        self.file_to_key = {}
        self.price_db = self.load_price_db()
        self.folder_name = ""
        self.folder_path = ""
        self.progress_var = tk.StringVar(value="0/0")
        self.start_frame = None
        self.shoper_frame = None
        self.log_widget = None
        try:
            self.shoper_client = ShoperClient(SHOPER_API_URL, SHOPER_API_TOKEN)
        except Exception as e:
            print(f"[WARNING] ShoperClient init failed: {e}")
            self.shoper_client = None

        self.setup_welcome_screen()

    def setup_welcome_screen(self):
        """Display a simple welcome screen before loading scans."""
        # Allow resizing but provide a sensible minimum size
        self.root.minsize(1000, 700)
        self.start_frame = tk.Frame(self.root, bg=self.root.cget("background"))
        self.start_frame.pack(expand=True, fill="both")

        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((140, 140))
            self.logo_photo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(
                self.start_frame,
                image=self.logo_photo,
                bg=self.start_frame.cget("bg"),
            )
            logo_label.pack(pady=(10, 10))

        greeting = tk.Label(
            self.start_frame,
            text="Witaj w aplikacji KARTOTEKA",
            font=("Helvetica", 16, "bold"),
        )
        greeting.pack(pady=5)

        desc = tk.Label(
            self.start_frame,
            text=("Aplikacja KARTOTEKA.SHOP pomaga przygotować skany do sprzedaży."),
            wraplength=1400,
            justify="center",
        )
        desc.pack(pady=5)

        author = tk.Label(
            self.start_frame,
            text="Twórca: BOGUCKI | Właściciel: kartoteka.shop",
            wraplength=1400,
            justify="center",
            font=("Helvetica", 8),
        )
        author.pack(side="bottom", pady=5)

        button_frame = tk.Frame(self.start_frame, bg=self.start_frame.cget("bg"))
        # Keep the buttons centered without stretching across the entire window
        button_frame.pack(pady=10)

        scan_btn = ttk.Button(
            button_frame,
            text="\U0001f50d Skanuj",
            command=self.load_images,
            bootstyle="primary",
        )
        scan_btn.pack(side="left", padx=5)

        ttk.Button(
            button_frame,
            text="\U0001f4b0 Wyceniaj",
            command=self.setup_pricing_ui,
            bootstyle="info",
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame,
            text="\U0001f5c3\ufe0f Shoper",
            command=self.open_shoper_window,
            bootstyle="secondary",
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame,
            text="\U0001f4c2 Import CSV",
            command=self.load_csv_data,
            bootstyle="warning",
        ).pack(side="left", padx=5)

        # Display store statistics when Shoper credentials are available
        stats_frame = tk.Frame(self.start_frame, bg=self.start_frame.cget("bg"))
        # Keep the dashboard centered within the window
        stats_frame.pack(pady=10, anchor="center")
        stats_frame.grid_anchor("center")
        for i in range(3):
            stats_frame.columnconfigure(i, weight=1)

        stats = self.load_store_stats()

        total = stats.get("total_orders")
        progress_ship = None
        if total:
            progress_ship = (total - stats.get("pending_shipments", 0)) / float(total)

        stats_map = [
            (
                "Nowe dzisiaj",
                stats.get("new_orders_today", 0),
                "🆕",
                "Liczba nowych zamówień dzisiaj",
                None,
            ),
            (
                "Oczekujące wysyłki",
                stats.get("pending_shipments", 0),
                "📦",
                "Zamówienia gotowe do wysyłki",
                progress_ship,
            ),
            (
                "Oczekujące płatności",
                stats.get("pending_payments", 0),
                "💸",
                "Zamówienia bez opłaty",
                None,
            ),
            (
                "Otwarte zwroty",
                stats.get("open_returns", 0),
                "↩️",
                "Zwroty w toku",
                None,
            ),
            (
                "Sprzedaż dzisiaj",
                stats.get("sales_today", 0),
                "💰",
                "Łączna dzisiejsza sprzedaż",
                None,
            ),
            (
                "Sprzedaż tydzień",
                stats.get("sales_week", 0),
                "📈",
                "Łączna sprzedaż z ostatniego tygodnia",
                None,
            ),
            (
                "Sprzedaż miesiąc",
                stats.get("sales_month", 0),
                "📊",
                "Łączna sprzedaż z miesiąca",
                None,
            ),
            (
                "Średnia wartość",
                stats.get("avg_order_value", 0),
                "💵",
                "Średnia wartość zamówienia",
                None,
            ),
            (
                "Aktywne karty",
                stats.get("active_cards", 0),
                "🃏",
                "Produkty aktywne w sklepie",
                None,
            ),
        ]

        colors = [
            "#FCE4EC",
            "#E3F2FD",
            "#E8F5E9",
            "#FFF3E0",
            "#F3E5F5",
            "#E0F7FA",
            "#F1F8E9",
            "#FFFDE7",
            "#EDE7F6",
        ]

        # Ensure rows expand evenly when the window is resized
        rows = (len(stats_map) + 2) // 3
        for r in range(rows):
            stats_frame.rowconfigure(r, weight=1)

        for i, (label, value, icon, info, prog) in enumerate(stats_map):
            row = i // 3
            col = i % 3
            card = self.create_stat_card(
                stats_frame,
                label,
                value,
                icon,
                colors[i % len(colors)],
                info,
                prog,
            )
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        ttk.Button(
            stats_frame,
            text="Pokaż szczegóły",
            command=self.open_shoper_window,
            bootstyle="secondary",
        ).grid(row=len(stats_map) // 3 + 1, column=0, columnspan=3, pady=5)

    def placeholder_btn(self, text: str, master=None):
        if master is None:
            master = self.start_frame
        return ttk.Button(
            master,
            text=text,
            command=lambda: messagebox.showinfo("Info", "Funkcja niezaimplementowana."),
            bootstyle="secondary",
        )

    def create_stat_card(self, parent, title, value, icon, color, info, progress=None):
        """Create a small dashboard card with optional tooltip and progress bar."""
        frame = tk.Frame(parent, width=160, height=80, bg=color, bd=1, relief="ridge")
        # Keep the card size constant regardless of its contents
        frame.pack_propagate(False)
        frame.grid_propagate(False)
        tk.Label(frame, text=icon, font=("Helvetica", 24), bg=color).pack()
        tk.Label(frame, text=title, font=("Helvetica", 12, "bold"), bg=color).pack()
        tk.Label(frame, text=value, font=("Helvetica", 24), bg=color).pack()
        if progress is not None:
            bar = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
            bar["maximum"] = 100
            bar["value"] = max(0, min(100, progress * 100))
            bar.pack(fill="x", padx=5, pady=(0, 5))
        for w in (frame,) + tuple(frame.winfo_children()):
            Tooltip(w, info)
        return frame

    def load_store_stats(self):
        """Retrieve various store statistics from Shoper."""
        if not self.shoper_client:
            return {}
        from datetime import date

        stats = {}
        try:
            today = date.today().isoformat()
            orders_today = self.shoper_client.get_orders(
                status="new",
                filters={"filters[add_date][from]": today},
            )
            stats["new_orders_today"] = len(orders_today.get("list", orders_today))

            pending_ship = self.shoper_client.get_orders(status="pending_shipment")
            stats["pending_shipments"] = len(pending_ship.get("list", pending_ship))

            # Attempt to retrieve total order count for progress calculations
            try:
                all_orders = self.shoper_client.get_orders()
                total = (
                    all_orders.get("records")
                    or all_orders.get("count")
                    or len(all_orders.get("list", all_orders))
                )
                stats["total_orders"] = total
                if total:
                    stats["shipment_progress"] = (
                        total - stats["pending_shipments"]
                    ) / float(total)
            except Exception:
                pass

            pending_pay = self.shoper_client.get_orders(status="pending_payment")
            stats["pending_payments"] = len(pending_pay.get("list", pending_pay))

            open_ret = self.shoper_client.get_orders(status="return")
            stats["open_returns"] = len(open_ret.get("list", open_ret))

            sales = self.shoper_client.get_sales_stats()
            stats["sales_today"] = sales.get("today", 0)
            stats["sales_week"] = sales.get("week", 0)
            stats["sales_month"] = sales.get("month", 0)
            stats["avg_order_value"] = sales.get("avg_order_value", 0)
            stats["active_cards"] = sales.get("active_products", 0)
        except Exception as exc:  # pragma: no cover - network failure
            print(f"[WARNING] store stats failed: {exc}")
        return stats

    def open_shoper_window(self):
        if not self.shoper_client:
            messagebox.showerror("Błąd", "Brak konfiguracji Shoper API")
            return
        # Quick connection test to provide clearer error messages
        try:
            # use a known endpoint to verify the connection
            self.shoper_client.get_inventory()
        except Exception as exc:
            msg = str(exc)
            if "404" in msg:
                messagebox.showerror(
                    "Błąd",
                    "Nie znaleziono endpointu Shoper API ('products'). Czy adres zawiera '/webapi/rest'?",
                )
            else:
                messagebox.showerror(
                    "Błąd", f"Połączenie z Shoper API nie powiodło się: {msg}"
                )
            return
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        # Ensure the window has a reasonable minimum size
        self.root.minsize(1000, 700)

        self.shoper_frame = tk.Frame(self.root)
        self.shoper_frame.pack(expand=True, fill="both", padx=10, pady=10)
        self.shoper_frame.columnconfigure(0, weight=1)
        self.shoper_frame.rowconfigure(2, weight=1)
        self.shoper_frame.rowconfigure(4, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.shoper_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                self.shoper_frame,
                image=self.shoper_logo_photo,
                bg=self.shoper_frame.cget("bg"),
            ).grid(row=0, column=0, pady=(0, 10))

        search_frame = tk.Frame(self.shoper_frame)
        search_frame.grid(row=1, column=0, sticky="ew", pady=5)
        search_frame.columnconfigure(1, weight=1)
        search_frame.columnconfigure(3, weight=1)

        tk.Label(search_frame, text="Szukaj").grid(row=0, column=0, sticky="e")
        self.shoper_search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.shoper_search_var).grid(
            row=0, column=1, sticky="ew"
        )
        tk.Label(search_frame, text="Numer").grid(row=0, column=2, sticky="e")
        self.shoper_number_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.shoper_number_var).grid(
            row=0, column=3, sticky="ew"
        )
        tk.Label(search_frame, text="Sortuj").grid(row=0, column=4, sticky="e")
        self.shoper_sort_var = tk.StringVar(value="")
        ttk.Combobox(
            search_frame,
            textvariable=self.shoper_sort_var,
            values=["", "name", "-name", "price", "-price"],
            width=10,
        ).grid(row=0, column=5, padx=5)
        ttk.Button(
            search_frame,
            text="Wyszukaj",
            command=lambda: self.search_products(output),
        ).grid(row=0, column=6, padx=5)

        output = tk.Text(self.shoper_frame)
        output.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        # Automatically display current products upon connecting
        self.fetch_inventory(output)

        btn_frame = tk.Frame(self.shoper_frame)
        btn_frame.grid(row=3, column=0, pady=5, sticky="ew")

        ttk.Button(
            btn_frame,
            text="Wyślij produkt",
            command=lambda: self.push_product(output),
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame,
            text="Inwentarz",
            command=lambda: self.fetch_inventory(output),
        ).pack(side="left", padx=5)

        orders_output = tk.Text(self.shoper_frame, height=10)
        orders_output.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)

        ttk.Button(
            btn_frame,
            text="Zamówienia",
            command=lambda: self.show_orders(orders_output),
        ).pack(side="left", padx=5)

        ttk.Button(
            self.shoper_frame,
            text="Powrót",
            command=self.back_to_welcome,
        ).grid(row=5, column=0, pady=5)

    def push_product(self, widget):
        try:
            sample = {"name": "Sample", "price": 0}
            data = self.shoper_client.add_product(sample)
            widget.delete("1.0", tk.END)
            widget.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def fetch_inventory(self, widget):
        try:
            data = self.shoper_client.get_inventory()
            widget.delete("1.0", tk.END)
            # Display a friendly list of product names if possible
            products = data.get("list", data)
            lines = []
            for prod in products:
                translations = prod.get("translations") or {}
                name = ""
                if isinstance(translations, dict):
                    first = next(iter(translations.values()), {})
                    name = first.get("name", "")
                lines.append(f"{prod.get('product_id')}: {name}")
            if lines:
                widget.insert(tk.END, "\n".join(lines))
            else:
                widget.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def search_products(self, widget):
        """Search products using the Shoper API."""
        try:
            filters = {}
            term = self.shoper_search_var.get().strip()
            number = self.shoper_number_var.get().strip()
            if term:
                filters["filters[name][like]"] = term
            if number:
                filters["filters[code][like]"] = number
            sort = self.shoper_sort_var.get().strip()
            data = self.shoper_client.search_products(filters=filters, sort=sort)
            widget.delete("1.0", tk.END)
            widget.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def show_orders(self, widget):
        """Display new orders with storage location hints."""
        try:
            orders = self.shoper_client.list_orders({"filters[status]": "new"})
            widget.delete("1.0", tk.END)
            lines = []
            for order in orders.get("list", orders):
                oid = order.get("order_id") or order.get("id")
                lines.append(f"Zamówienie #{oid}")
                for item in order.get("products", []):
                    code = item.get("product_code") or item.get("code", "")
                    location = self.location_from_code(code)
                    lines.append(
                        f" - {item.get('name')} x{item.get('quantity')} [{code}] {location}"
                    )
            widget.insert(tk.END, "\n".join(lines))
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    @staticmethod
    def location_from_code(code: str) -> str:
        match = re.match(r"K(\d+)R(\d)P(\d+)", code or "")
        if not match:
            return ""
        box, row, pos = match.groups()
        return f"Karton {int(box)} | Rząd {int(row)} | Poz {int(pos)}"

    def setup_pricing_ui(self):
        """UI for quick card price lookup."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
        # Set a sensible minimum size and allow resizing
        self.root.minsize(1000, 700)
        self.pricing_frame = tk.Frame(self.root)
        self.pricing_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.pricing_frame.columnconfigure(0, weight=1)
        self.pricing_frame.columnconfigure(1, weight=1)
        self.pricing_frame.rowconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.pricing_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                self.pricing_frame,
                image=self.pricing_logo_photo,
                bg=self.pricing_frame.cget("bg"),
            ).grid(row=0, column=0, columnspan=2, pady=(0, 10))

        self.input_frame = tk.Frame(self.pricing_frame)
        self.input_frame.grid(row=1, column=0, sticky="nsew")

        self.image_frame = tk.Frame(self.pricing_frame)
        self.image_frame.grid(row=1, column=1, sticky="nsew")

        self.input_frame.columnconfigure(0, weight=1)
        self.input_frame.columnconfigure(1, weight=1)
        self.input_frame.rowconfigure(5, weight=1)

        tk.Label(self.input_frame, text="Nazwa").grid(row=0, column=0, sticky="e")
        self.price_name_entry = ttk.Entry(self.input_frame, width=30)
        self.price_name_entry.grid(row=0, column=1, sticky="ew")

        tk.Label(self.input_frame, text="Numer").grid(row=1, column=0, sticky="e")
        self.price_number_entry = ttk.Entry(self.input_frame, width=30)
        self.price_number_entry.grid(row=1, column=1, sticky="ew")

        tk.Label(self.input_frame, text="Set").grid(row=2, column=0, sticky="e")
        self.price_set_entry = ttk.Entry(self.input_frame, width=30)
        self.price_set_entry.grid(row=2, column=1, sticky="ew")

        self.price_reverse_var = tk.BooleanVar()
        ttk.Checkbutton(
            self.input_frame,
            text="Reverse",
            variable=self.price_reverse_var,
            bootstyle="round-toggle",
        ).grid(row=3, column=0, columnspan=2, pady=5)

        self.price_reverse_var.trace_add("write", lambda *a: self.on_reverse_toggle())

        btn_frame = tk.Frame(self.input_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=5, sticky="w")

        ttk.Button(
            btn_frame,
            text="Wyszukaj",
            command=self.run_pricing_search,
            bootstyle="primary",
            width=12,
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame,
            text="Powrót",
            command=self.back_to_welcome,
            width=12,
        ).pack(side="left", padx=5)

        self.result_frame = tk.Frame(self.image_frame)
        self.result_frame.pack(expand=True, fill="both", pady=10)

    def run_pricing_search(self):
        """Fetch and display pricing information."""
        name = self.price_name_entry.get()
        number = self.price_number_entry.get()
        set_name = self.price_set_entry.get()
        is_reverse = self.price_reverse_var.get()

        info = self.lookup_card_info(name, number, set_name)
        for w in self.result_frame.winfo_children():
            w.destroy()
        self.price_labels = []
        self.result_image_label = None
        self.set_logo_label = None
        if not info:
            messagebox.showinfo("Brak wyników", "Nie znaleziono karty.")
            return
        self.current_price_info = info

        if info.get("image_url"):
            try:
                res = requests.get(info["image_url"], timeout=10)
                if res.status_code == 200:
                    img = Image.open(io.BytesIO(res.content))
                    img.thumbnail((240, 340))
                    self.pricing_photo = ImageTk.PhotoImage(img)
                    self.result_image_label = tk.Label(
                        self.result_frame, image=self.pricing_photo
                    )
                    self.result_image_label.pack(pady=5)
            except Exception as e:
                print(f"[ERROR] Loading image failed: {e}")

        if info.get("set_logo_url"):
            try:
                res = requests.get(info["set_logo_url"], timeout=10)
                if res.status_code == 200:
                    img = Image.open(io.BytesIO(res.content))
                    img.thumbnail((180, 60))
                    self.set_logo_photo = ImageTk.PhotoImage(img)
                    self.set_logo_label = tk.Label(
                        self.result_frame, image=self.set_logo_photo
                    )
                    self.set_logo_label.pack(pady=5)
            except Exception as e:
                print(f"[ERROR] Loading set logo failed: {e}")
        self.display_price_info(info, is_reverse)

    def display_price_info(self, info, is_reverse):
        """Show pricing data with optional reverse multiplier."""
        price_pln = self.apply_variant_multiplier(
            info["price_pln"], is_reverse=is_reverse
        )
        price_80 = round(price_pln * 0.8, 2)
        if not getattr(self, "price_labels", None):
            eur = tk.Label(
                self.result_frame, text=f"Cena EUR: {info['price_eur']}", fg="blue"
            )
            rate = tk.Label(
                self.result_frame,
                text=f"Kurs EUR→PLN: {info['eur_pln_rate']}",
                fg="gray",
            )
            pln = tk.Label(self.result_frame, text=f"Cena PLN: {price_pln}", fg="green")
            pln80 = tk.Label(
                self.result_frame, text=f"80% ceny PLN: {price_80}", fg="red"
            )
            for lbl in (eur, rate, pln, pln80):
                lbl.pack()
            self.price_labels = [eur, rate, pln, pln80]
        else:
            eur, rate, pln, pln80 = self.price_labels
            eur.config(text=f"Cena EUR: {info['price_eur']}")
            rate.config(text=f"Kurs EUR→PLN: {info['eur_pln_rate']}")
            pln.config(text=f"Cena PLN: {price_pln}")
            pln80.config(text=f"80% ceny PLN: {price_80}")

    def on_reverse_toggle(self, *args):
        if getattr(self, "current_price_info", None):
            self.display_price_info(
                self.current_price_info, self.price_reverse_var.get()
            )

    def back_to_welcome(self):
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        self.setup_welcome_screen()

    def setup_editor_ui(self):
        # Provide a minimum size and allow the editor to expand
        self.root.minsize(1000, 700)
        self.frame = tk.Frame(self.root)
        self.frame.pack(expand=True, fill="both", padx=10, pady=10)
        # Allow widgets inside the frame to expand properly
        for i in range(5):
            self.frame.columnconfigure(i, weight=1)
        self.frame.rowconfigure(2, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.logo_photo = ImageTk.PhotoImage(logo_img)
            self.logo_label = tk.Label(
                self.frame,
                image=self.logo_photo,
                bg=self.frame.cget("bg"),
            )
            self.logo_label.grid(row=0, column=0, columnspan=5, pady=(0, 10))

        # Load ttkbootstrap icons when available
        self.icon_load = load_icon("document-open")
        self.icon_export = load_icon("document-save")
        self.icon_api = load_icon("network-server")
        self.icon_save = load_icon("document-save")

        # Bottom frame for action buttons
        self.button_frame = tk.Frame(self.frame)
        # Do not stretch the button frame so that buttons remain centered
        self.button_frame.grid(row=15, column=0, columnspan=5, pady=10)

        self.load_button = ttk.Button(
            self.button_frame,
            text="Import",
            image=self.icon_load,
            compound="left",
            command=self.load_images,
            bootstyle="primary",
        )
        self.load_button.pack(side="left", padx=5)

        self.end_button = ttk.Button(
            self.button_frame,
            text="Zakończ i zapisz",
            image=self.icon_export,
            compound="left",
            command=self.export_csv,
            bootstyle="success",
        )
        self.end_button.pack(side="left", padx=5)

        self.back_button = ttk.Button(
            self.button_frame,
            text="Powrót",
            command=self.back_to_welcome,
            bootstyle="secondary",
        )
        self.back_button.pack(side="left", padx=5)

        self.image_label = tk.Label(self.frame)
        self.image_label.grid(row=2, column=0, rowspan=12, sticky="nsew")
        # Display only a textual progress indicator below the card image
        self.progress_label = ttk.Label(self.frame, textvariable=self.progress_var)
        self.progress_label.grid(row=14, column=0, pady=5, sticky="ew")

        # Container for card information fields
        self.info_frame = ttk.LabelFrame(self.frame, text="Informacje o karcie")
        self.info_frame.grid(
            row=2, column=1, columnspan=4, rowspan=12, padx=10, sticky="nsew"
        )
        for i in range(8):
            self.info_frame.columnconfigure(i, weight=1)

        self.entries = {}

        grid_opts = {"padx": 5, "pady": 2}

        tk.Label(self.info_frame, text="Język").grid(
            row=0, column=0, sticky="w", **grid_opts
        )
        self.lang_var = tk.StringVar(value="ENG")
        self.entries["język"] = self.lang_var
        lang_dropdown = ttk.Combobox(
            self.info_frame, textvariable=self.lang_var, values=["ENG", "JP"], width=20
        )
        lang_dropdown.grid(row=0, column=1, sticky="ew", **grid_opts)
        lang_dropdown.bind("<<ComboboxSelected>>", self.update_set_options)

        tk.Label(self.info_frame, text="Nazwa").grid(
            row=1, column=0, sticky="w", **grid_opts
        )
        self.entries["nazwa"] = ttk.Entry(self.info_frame, width=20)
        self.entries["nazwa"].grid(row=1, column=1, sticky="ew", **grid_opts)

        tk.Label(self.info_frame, text="Numer").grid(
            row=2, column=0, sticky="w", **grid_opts
        )
        self.entries["numer"] = ttk.Entry(self.info_frame, width=20)
        self.entries["numer"].grid(row=2, column=1, sticky="ew", **grid_opts)

        tk.Label(self.info_frame, text="Set").grid(
            row=3, column=0, sticky="w", **grid_opts
        )
        self.set_var = tk.StringVar()
        self.set_dropdown = ttk.Combobox(
            self.info_frame, textvariable=self.set_var, width=20
        )
        self.set_dropdown.grid(row=3, column=1, sticky="ew", **grid_opts)
        self.set_dropdown.bind("<KeyRelease>", self.filter_sets)
        self.set_dropdown.bind("<Tab>", self.autocomplete_set)
        self.entries["set"] = self.set_var

        tk.Label(self.info_frame, text="Typ").grid(
            row=4, column=0, sticky="w", **grid_opts
        )
        self.type_vars = {}
        self.type_frame = tk.Frame(self.info_frame)
        self.type_frame.grid(row=4, column=1, columnspan=7, sticky="w", **grid_opts)
        types = ["Common", "Holo", "Reverse"]
        for t in types:
            var = tk.BooleanVar()
            self.type_vars[t] = var
            tk.Checkbutton(
                self.type_frame,
                text=t,
                variable=var,
                width=8,
            ).pack(side="left", padx=2)

        tk.Label(self.info_frame, text="Rarity").grid(
            row=5, column=0, sticky="w", **grid_opts
        )
        self.rarity_vars = {}
        self.rarity_frame = tk.Frame(self.info_frame)
        self.rarity_frame.grid(row=5, column=1, columnspan=7, sticky="w", **grid_opts)
        rarities = ["RR", "AR", "SR", "SAR", "UR", "ACE", "PROMO"]
        for r in rarities:
            var = tk.BooleanVar()
            self.rarity_vars[r] = var
            tk.Checkbutton(
                self.rarity_frame,
                text=r,
                variable=var,
                width=8,
            ).pack(side="left", padx=2)

        tk.Label(self.info_frame, text="Suffix").grid(
            row=6, column=0, sticky="w", **grid_opts
        )
        self.suffix_var = tk.StringVar(value="")
        self.entries["suffix"] = self.suffix_var
        suffix_dropdown = ttk.Combobox(
            self.info_frame,
            textvariable=self.suffix_var,
            values=["", "EX", "GX", "V", "VMAX", "VSTAR", "Shiny", "Promo"],
            width=20,
        )
        suffix_dropdown.grid(row=6, column=1, sticky="ew", **grid_opts)

        tk.Label(self.info_frame, text="Stan").grid(
            row=7, column=0, sticky="w", **grid_opts
        )
        self.stan_var = tk.StringVar(value="NM")
        self.entries["stan"] = self.stan_var
        stan_dropdown = ttk.Combobox(
            self.info_frame,
            textvariable=self.stan_var,
            values=["NM", "LP", "PL", "MP", "HP", "DMG"],
            width=20,
        )
        stan_dropdown.grid(row=7, column=1, sticky="ew", **grid_opts)

        tk.Label(self.info_frame, text="Cena").grid(
            row=8, column=0, sticky="w", **grid_opts
        )
        self.entries["cena"] = ttk.Entry(self.info_frame, width=20)
        self.entries["cena"].grid(row=8, column=1, sticky="ew", **grid_opts)

        self.api_button = ttk.Button(
            self.info_frame,
            text="Pobierz cenę z bazy",
            image=self.icon_api,
            compound="left",
            command=self.fetch_card_data,
            bootstyle="info",
        )
        self.api_button.grid(row=9, column=0, columnspan=2, sticky="ew", **grid_opts)

        self.variants_button = ttk.Button(
            self.info_frame,
            text="Inne warianty",
            command=self.show_variants,
            bootstyle="secondary",
        )
        self.variants_button.grid(
            row=9, column=2, columnspan=2, sticky="ew", **grid_opts
        )

        self.cardmarket_button = ttk.Button(
            self.info_frame,
            text="Cardmarket",
            command=self.open_cardmarket_search,
            bootstyle="secondary",
        )
        self.cardmarket_button.grid(
            row=9, column=4, columnspan=2, sticky="ew", **grid_opts
        )

        self.save_button = ttk.Button(
            self.info_frame,
            text="Zapisz i dalej",
            image=self.icon_save,
            compound="left",
            command=self.save_and_next,
            bootstyle="primary",
        )
        self.save_button.grid(row=10, column=0, columnspan=2, sticky="ew", **grid_opts)

        for entry in self.entries.values():
            if isinstance(entry, (tk.Entry, ttk.Entry)):
                entry.bind("<Return>", lambda e: self.save_and_next())

        self.root.bind("<Return>", lambda e: self.save_and_next())
        self.update_set_options()

        self.log_widget = tk.Text(self.frame, height=4, state="disabled")
        self.log_widget.grid(row=16, column=0, columnspan=5, sticky="ew")

    def update_set_options(self, event=None):
        lang = self.lang_var.get().strip().upper()
        if lang == "JP":
            self.set_dropdown["values"] = sorted(tcg_sets_jp)
        else:
            self.set_dropdown["values"] = sorted(tcg_sets_eng)

    def filter_sets(self, event=None):
        typed = self.set_var.get().lower()
        lang = self.lang_var.get().strip().upper()
        all_sets = tcg_sets_jp if lang == "JP" else tcg_sets_eng
        if typed:
            filtered = [s for s in all_sets if typed in s.lower()]
        else:
            filtered = all_sets
        self.set_dropdown["values"] = sorted(filtered)

    def autocomplete_set(self, event=None):
        typed = self.set_var.get().lower()
        lang = self.lang_var.get().strip().upper()
        all_sets = tcg_sets_jp if lang == "JP" else tcg_sets_eng
        if typed:
            filtered = [s for s in all_sets if typed in s.lower()]
        else:
            filtered = all_sets
        if filtered:
            self.set_var.set(filtered[0])
        event.widget.tk_focusNext().focus()
        return "break"

    def load_images(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
            self.setup_editor_ui()
        self.folder_path = folder
        self.folder_name = os.path.basename(folder)
        self.cards = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith((".jpg", ".png"))
        ]
        self.cards.sort()
        self.index = 0
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.progress_var.set(f"0/{len(self.cards)}")
        self.log(f"Loaded {len(self.cards)} cards")
        self.show_card()

    def show_card(self):
        if self.index >= len(self.cards):
            messagebox.showinfo("Koniec", "Wszystkie karty zostały zapisane.")
            self.export_csv()
            return

        self.progress_var.set(f"{self.index + 1}/{len(self.cards)}")

        image_path = self.cards[self.index]
        cache_key = self.file_to_key.get(os.path.basename(image_path))
        if not cache_key:
            cache_key = self._guess_key_from_filename(image_path)
        image = Image.open(image_path)
        image.thumbnail((400, 560))
        img = ImageTk.PhotoImage(image)
        self.image_objects.append(img)
        self.image_objects = self.image_objects[-2:]
        self.image_label.configure(image=img)

        for key, entry in self.entries.items():
            if isinstance(entry, (tk.Entry, ttk.Entry)):
                entry.delete(0, tk.END)
            elif isinstance(entry, tk.StringVar):
                if key == "język":
                    entry.set("ENG")
                elif key == "stan":
                    entry.set("NM")
                else:
                    entry.set("")
            elif isinstance(entry, tk.BooleanVar):
                entry.set(False)

        for var in self.rarity_vars.values():
            var.set(False)

        for var in self.type_vars.values():
            var.set(False)

        if cache_key and cache_key in self.card_cache:
            cached = self.card_cache[cache_key]
            for field, value in cached.get("entries", {}).items():
                entry = self.entries.get(field)
                if isinstance(entry, (tk.Entry, ttk.Entry)):
                    entry.insert(0, value)
                elif isinstance(entry, tk.StringVar):
                    entry.set(value)
            for name, val in cached.get("types", {}).items():
                if name in self.type_vars:
                    self.type_vars[name].set(val)
            for name, val in cached.get("rarities", {}).items():
                if name in self.rarity_vars:
                    self.rarity_vars[name].set(val)
            self.update_set_options()

        # focus the name entry so the user can start typing immediately
        self.entries["nazwa"].focus_set()

    def _guess_key_from_filename(self, path: str):
        base = os.path.splitext(os.path.basename(path))[0]
        parts = re.split(r"[|_-]", base)
        if len(parts) >= 3:
            name = parts[0]
            number = parts[1]
            set_name = "_".join(parts[2:])
            return f"{name}|{number}|{set_name}"
        return None

    def generate_location(self, idx):
        pos = idx % 1000 + 1
        row = (idx // 1000) % 4 + 1
        box = (idx // 4000) + 1
        return f"K{box:02d}R{row}P{pos:04d}"

    def load_price_db(self):
        if not os.path.exists(PRICE_DB_PATH):
            return []
        with open(PRICE_DB_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def log(self, message: str):
        if self.log_widget:
            self.log_widget.configure(state="normal")
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state="disabled")
        print(message)

    def get_price_from_db(self, name, number, set_name):
        import unicodedata

        def normalize(text: str) -> str:
            if not text:
                return ""
            text = unicodedata.normalize("NFKD", text)
            text = text.lower()
            for suffix in [
                " ex",
                " gx",
                " v",
                " vmax",
                " vstar",
                " shiny",
                " promo",
            ]:
                text = text.replace(suffix, "")
            return text.replace("-", "").replace(" ", "").strip()

        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()

        for row in self.price_db:
            if (
                normalize(row.get("name", "")) == name_input
                and row.get("number", "").strip().lower() == number_input
                and row.get("set", "").strip().lower() == set_input
            ):
                try:
                    return float(row.get("price", 0))
                except (TypeError, ValueError):
                    return None
        return None

    def fetch_card_price(self, name, number, set_name, is_reverse=False, is_holo=False):
        import unicodedata

        def normalize(text):
            if not text:
                return ""
            text = unicodedata.normalize("NFKD", text)
            text = text.lower()
            for suffix in [" ex", " gx", " v", " vmax", " vstar", " shiny", " promo"]:
                text = text.replace(suffix, "")
            return text.replace("-", "").replace(" ", "").strip()

        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_input}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_input,
                    "number": number_input,
                    "set": set_input,
                }
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] API error: {response.status_code}")
                return None

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []
            candidates = []

            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    candidates.append(card)

            if candidates:
                best = candidates[0]
                price_eur = (
                    best.get("prices", {}).get("cardmarket", {}).get("30d_average", 0)
                )
                if price_eur:
                    eur_pln = self.get_exchange_rate()
                    price_pln = round(float(price_eur) * eur_pln * PRICE_MULTIPLIER, 2)
                    print(
                        f"[INFO] Cena {best.get('name')} ({number_input}, {set_input}) = {price_pln} PLN"
                    )
                    return price_pln

            print("\n[DEBUG] Nie znaleziono dokładnej karty. Zbliżone:")
            for card in cards:
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()
                if number_input == card_number and set_input in card_set:
                    print(
                        f"- {card.get('name')} | {card_number} | {card.get('episode', {}).get('name')}"
                    )

        except requests.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Fetching price from TCGGO failed: {e}")
        return None

    def fetch_card_variants(self, name, number, set_name):
        """Return all matching cards from the API with prices."""
        import unicodedata

        def normalize(text):
            if not text:
                return ""
            text = unicodedata.normalize("NFKD", text)
            text = text.lower()
            for suffix in [" ex", " gx", " v", " vmax", " vstar", " shiny", " promo"]:
                text = text.replace(suffix, "")
            return text.replace("-", "").replace(" ", "").strip()

        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_input}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_input,
                    "number": number_input,
                    "set": set_input,
                }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] API error: {response.status_code}")
                return []

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []

            results = []
            eur_pln = self.get_exchange_rate()
            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    price_eur = (
                        card.get("prices", {})
                        .get("cardmarket", {})
                        .get("30d_average", 0)
                    )
                    price_pln = 0
                    if price_eur:
                        price_pln = round(
                            float(price_eur) * eur_pln * PRICE_MULTIPLIER, 2
                        )
                    results.append(
                        {
                            "name": card.get("name"),
                            "number": card_number,
                            "set": card.get("episode", {}).get("name", ""),
                            "price": price_pln,
                        }
                    )
            return results
        except requests.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Fetching variants from TCGGO failed: {e}")
        return []

    def lookup_card_info(self, name, number, set_name, is_holo=False, is_reverse=False):
        """Return image URL and pricing information for the first matching card."""
        import unicodedata

        def normalize(text):
            if not text:
                return ""
            text = unicodedata.normalize("NFKD", text)
            text = text.lower()
            for suffix in [" ex", " gx", " v", " vmax", " vstar", " shiny", " promo"]:
                text = text.replace(suffix, "")
            return text.replace("-", "").replace(" ", "").strip()

        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_input}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {"name": name_input, "number": number_input, "set": set_input}

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] API error: {response.status_code}")
                return None

            cards = response.json()
            if isinstance(cards, dict):
                if "cards" in cards:
                    cards = cards["cards"]
                elif "data" in cards:
                    cards = cards["data"]
                else:
                    cards = []

            for card in cards:
                card_name = normalize(card.get("name", ""))
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()

                name_match = name_input in card_name
                number_match = number_input == card_number
                set_match = set_input in card_set or card_set.startswith(set_input)

                if name_match and number_match and set_match:
                    price_eur = (
                        card.get("prices", {})
                        .get("cardmarket", {})
                        .get("30d_average", 0)
                        or 0
                    )
                    base_rate = self.get_exchange_rate()
                    eur_pln = base_rate * PRICE_MULTIPLIER
                    price_pln = round(float(price_eur) * eur_pln, 2)
                    if is_holo or is_reverse:
                        price_pln = round(price_pln * HOLO_REVERSE_MULTIPLIER, 2)
                    set_info = card.get("episode") or card.get("set") or {}
                    images = (
                        set_info.get("images", {}) if isinstance(set_info, dict) else {}
                    )
                    set_logo = (
                        images.get("logo")
                        or images.get("logoUrl")
                        or images.get("logo_url")
                        or set_info.get("logo")
                    )
                    image_url = (
                        card.get("images", {}).get("large")
                        or card.get("image")
                        or card.get("imageUrl")
                        or card.get("image_url")
                    )
                    return {
                        "image_url": image_url,
                        "set_logo_url": set_logo,
                        "price_eur": round(float(price_eur), 2),
                        "eur_pln_rate": round(base_rate, 4),
                        "price_pln": price_pln,
                        "price_pln_80": round(price_pln * 0.8, 2),
                    }
        except requests.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Lookup failed: {e}")
        return None

    def fetch_card_data(self):
        name = self.entries["nazwa"].get()
        number = self.entries["numer"].get()
        set_name = self.entries["set"].get()

        is_reverse = self.type_vars["Reverse"].get()
        is_holo = self.type_vars["Holo"].get()

        cena = self.get_price_from_db(name, number, set_name)
        if cena is not None:
            cena = self.apply_variant_multiplier(
                cena, is_reverse=is_reverse, is_holo=is_holo
            )
            self.entries["cena"].delete(0, tk.END)
            self.entries["cena"].insert(0, str(cena))
            self.log(f"Price for {name} {number}: {cena} zł")
        else:
            fetched = self.fetch_card_price(name, number, set_name)
            if fetched is not None:
                fetched = self.apply_variant_multiplier(
                    fetched, is_reverse=is_reverse, is_holo=is_holo
                )
                self.entries["cena"].delete(0, tk.END)
                self.entries["cena"].insert(0, str(fetched))
                self.log(f"Price for {name} {number}: {fetched} zł")
            else:
                messagebox.showinfo(
                    "Brak wyników",
                    "Nie znaleziono ceny dla podanej karty w bazie danych.",
                )
                self.log(f"Card {name} {number} not found")

    def show_variants(self):
        """Display a list of matching cards from the API."""
        name = self.entries["nazwa"].get()
        number = self.entries["numer"].get()
        set_name = self.entries["set"].get()

        is_reverse = self.type_vars["Reverse"].get()
        is_holo = self.type_vars["Holo"].get()

        variants = self.fetch_card_variants(name, number, set_name)
        if not variants:
            messagebox.showinfo("Brak wyników", "Nie znaleziono dodatkowych wariantów.")
            self.open_cardmarket_search()
            return

        top = tk.Toplevel(self.root)
        top.title("Inne warianty")
        top.geometry("600x400")

        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((140, 140))
            top.logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(top, image=top.logo_photo, bg=top.cget("bg")).pack(pady=(10, 10))

        columns = ("name", "number", "set", "price")
        tree = ttk.Treeview(top, columns=columns, show="headings")
        tree.heading("name", text="Nazwa")
        tree.heading("number", text="Numer")
        tree.heading("set", text="Set")
        tree.heading("price", text="Cena (PLN)")

        for card in variants:
            price = self.apply_variant_multiplier(
                card["price"], is_reverse=is_reverse, is_holo=is_holo
            )
            tree.insert(
                "", "end", values=(card["name"], card["number"], card["set"], price)
            )

        tree.pack(expand=True, fill="both", padx=10, pady=10)

        def set_selected_price(event=None):
            selected = tree.selection()
            if not selected:
                return
            values = tree.item(selected[0], "values")
            self.entries["cena"].delete(0, tk.END)
            self.entries["cena"].insert(0, values[3])
            top.destroy()

        ttk.Button(top, text="Ustaw cenę", command=set_selected_price).pack(pady=5)
        tree.bind("<Double-1>", set_selected_price)

    def open_cardmarket_search(self):
        """Open a Cardmarket search for the current card in the default browser."""
        name = self.entries["nazwa"].get()
        number = self.entries["numer"].get()
        search_terms = " ".join(t for t in [name, number] if t)
        params = urlencode({"searchString": search_terms})
        url = f"https://www.cardmarket.com/en/Pokemon/Products/Search?{params}"
        webbrowser.open(url)

    def get_exchange_rate(self):
        try:
            res = requests.get(
                "https://api.nbp.pl/api/exchangerates/rates/A/EUR/?format=json",
                timeout=10,
            )
            if res.status_code == 200:
                return res.json()["rates"][0]["mid"]
        except requests.Timeout:
            print("[ERROR] Exchange rate request timed out")
        except Exception:
            pass
        return 4.265

    def apply_variant_multiplier(self, price, is_reverse=False, is_holo=False):
        """Apply holo/reverse multiplier when needed."""
        if price is None:
            return None
        if is_reverse or is_holo:
            try:
                return round(float(price) * HOLO_REVERSE_MULTIPLIER, 2)
            except (TypeError, ValueError):
                return price
        return price

    def save_and_next(self):
        data = {k: v.get() for k, v in self.entries.items()}
        data["typ"] = ",".join(
            [name for name, var in self.type_vars.items() if var.get()]
        )
        data["rarity"] = ",".join([k for k, v in self.rarity_vars.items() if v.get()])
        key = f"{data['nazwa']}|{data['numer']}|{data['set']}"
        self.card_counts[key] += 1
        data["ilość"] = self.card_counts[key]
        self.card_cache[key] = {
            "entries": {k: v for k, v in data.items()},
            "types": {name: var.get() for name, var in self.type_vars.items()},
            "rarities": {name: var.get() for name, var in self.rarity_vars.items()},
        }
        front_path = self.cards[self.index]
        front_file = os.path.basename(front_path)
        back_file = None
        product_idx = self.index

        def core(name: str) -> str:
            name_no_ext, _ = os.path.splitext(name)
            for suf in ["_front", "-front", " front", "_back", "-back", " back"]:
                if name_no_ext.lower().endswith(suf):
                    return name_no_ext[: -len(suf)]
            return name_no_ext

        def extract_number(name: str):
            name_no_ext, _ = os.path.splitext(name)
            m = re.search(r"(\d+)$", name_no_ext)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass
            return None

        if self.index + 1 < len(self.cards):
            next_file = os.path.basename(self.cards[self.index + 1])
            if core(front_file).lower() == core(next_file).lower():
                back_file = next_file
                self.index += 1
            else:
                curr_num = extract_number(front_file)
                next_num = extract_number(next_file)
                if (
                    curr_num is not None
                    and next_num is not None
                    and next_num == curr_num + 1
                ):
                    back_file = next_file
                    self.index += 1

        self.file_to_key[front_file] = key
        if back_file:
            self.file_to_key[back_file] = key

        images = [front_file]
        if back_file:
            images.append(back_file)
        data["images1"] = f"{BASE_IMAGE_URL}/{self.folder_name}/{front_file}"
        data["images2"] = (
            f"{BASE_IMAGE_URL}/{self.folder_name}/{back_file}" if back_file else ""
        )
        data["product_code"] = self.generate_location(product_idx)
        data["active"] = 1
        data["vat"] = 23
        data["unit"] = "szt"
        data["category"] = f"Karty Pokémon > {data['set']}"
        data["producer"] = "Pokémon"
        data["other_price"] = ""
        data["pkwiu"] = ""
        data["weight"] = 0.01
        data["priority"] = 0
        data["short_description"] = f"Stan: {data['stan']}, Język: {data['język']}"
        data["description"] = (
            f"{data['nazwa']} karta Pokémon z setu {data['set']}, nr {data['numer']}, stan {data['stan']}."
        )
        data["stock_warnlevel"] = 0
        data["availability"] = 1
        data["delivery"] = 1
        data["views"] = ""
        data["rank"] = ""
        data["rank_votes"] = ""

        # Automatyczne pobranie ceny z bazy
        cena_local = self.get_price_from_db(data["nazwa"], data["numer"], data["set"])
        is_reverse = self.type_vars["Reverse"].get()
        is_holo = self.type_vars["Holo"].get()
        if cena_local is not None:
            cena_local = self.apply_variant_multiplier(
                cena_local, is_reverse=is_reverse, is_holo=is_holo
            )
            data["cena"] = str(cena_local)
        else:
            fetched = self.fetch_card_price(
                data["nazwa"],
                data["numer"],
                data["set"],
            )
            if fetched is not None:
                fetched = self.apply_variant_multiplier(
                    fetched, is_reverse=is_reverse, is_holo=is_holo
                )
                data["cena"] = str(fetched)
            else:
                data["cena"] = ""

        self.output_data.append(data)
        self.index += 1
        self.show_card()

    def load_csv_data(self):
        """Load a CSV file and merge duplicate rows."""
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return

        with open(file_path, encoding="utf-8") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            rows = list(reader)

        combined = {}
        qty_field = None

        for row in rows:
            key = f"{row.get('nazwa', '').strip()}|{row.get('numer', '').strip()}|{row.get('set', '').strip()}"
            if qty_field is None:
                if "stock" in row:
                    qty_field = "stock"
                elif "ilość" in row:
                    qty_field = "ilość"
            qty = 1
            if qty_field:
                try:
                    qty = int(row.get(qty_field, 0))
                except ValueError:
                    qty = 1

            if key in combined:
                combined[key]["qty"] += qty
            else:
                new_row = row.copy()
                new_row["qty"] = qty
                combined[key] = new_row

        fieldnames = reader.fieldnames or []
        if qty_field is None:
            qty_field = "ilość"
            if qty_field not in fieldnames:
                fieldnames.append(qty_field)

        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
        )
        if not save_path:
            return

        with open(save_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for row in combined.values():
                row_out = row.copy()
                row_out[qty_field] = row_out.pop("qty")
                if qty_field != "stock":
                    row_out.pop("stock", None)
                if qty_field != "ilość":
                    row_out.pop("ilość", None)
                writer.writerow({k: row_out.get(k, "") for k in fieldnames})

        messagebox.showinfo("Sukces", "Plik CSV został scalony i zapisany.")

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
        )
        if not file_path:
            return

        combined = {}
        for row in self.output_data:
            key = f"{row['nazwa']}|{row['numer']}|{row['set']}"
            if key in combined:
                combined[key]["stock"] += 1
            else:
                combined[key] = row.copy()
                combined[key]["stock"] = 1

        fieldnames = [
            "product_code",
            "active",
            "name",
            "price",
            "vat",
            "unit",
            "category",
            "producer",
            "other_price",
            "pkwiu",
            "weight",
            "priority",
            "short_description",
            "description",
            "stock",
            "stock_warnlevel",
            "availability",
            "delivery",
            "views",
            "rank",
            "rank_votes",
            "images1",
            "images2",
        ]

        with open(file_path, mode="w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for row in combined.values():
                suffix = row.get("suffix", "").strip()
                name_parts = [row["nazwa"]]
                if suffix:
                    name_parts.append(suffix)
                name_parts.append(row["numer"])
                formatted_name = " ".join(name_parts)

                writer.writerow(
                    {
                        "product_code": row["product_code"],
                        "active": row["active"],
                        "name": formatted_name,
                        "price": row["cena"],
                        "vat": row["vat"],
                        "unit": row["unit"],
                        "category": row["category"],
                        "producer": row["producer"],
                        "other_price": row["other_price"],
                        "pkwiu": row["pkwiu"],
                        "weight": row["weight"],
                        "priority": row["priority"],
                        "short_description": row["short_description"],
                        "description": row["description"],
                        "stock": row["stock"],
                        "stock_warnlevel": row["stock_warnlevel"],
                        "availability": row["availability"],
                        "delivery": row["delivery"],
                        "views": row["views"],
                        "rank": row["rank"],
                        "rank_votes": row["rank_votes"],
                        "images1": row.get("images1", ""),
                        "images2": row.get("images2", ""),
                    }
                )
        messagebox.showinfo("Sukces", "Plik CSV został zapisany.")
        self.back_to_welcome()


if __name__ == "__main__":
    style = Style("darkly")
    style.configure(".", font=("Helvetica", 12))
    app = CardEditorApp(style.master)
    style.master.mainloop()
