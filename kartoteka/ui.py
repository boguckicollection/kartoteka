import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import customtkinter as ctk
import tkinter.ttk as ttk
from PIL import Image, ImageTk
import os
import csv
import json
import requests
import openai
import re
from collections import defaultdict
from dotenv import load_dotenv
import unicodedata
from itertools import combinations
import html
import subprocess
import sys

from shoper_client import ShoperClient
from ftp_client import FTPClient
from . import csv_utils, storage
import threading
import webbrowser
from urllib.parse import urlencode, urlparse
import io

load_dotenv()

BASE_IMAGE_URL = os.getenv("BASE_IMAGE_URL", "https://sklep839679.shoparena.pl/upload/images")

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

SHOPER_API_URL = os.getenv("SHOPER_API_URL")
SHOPER_API_TOKEN = os.getenv("SHOPER_API_TOKEN")
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASSWORD = os.getenv("FTP_PASSWORD")
SHOPER_DELIVERY_ID = int(os.getenv("SHOPER_DELIVERY_ID", "1"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

PRICE_DB_PATH = "card_prices.csv"
PRICE_MULTIPLIER = 1.23
HOLO_REVERSE_MULTIPLIER = 3.5
POKEBALL_MULTIPLIER = 5
MASTERBALL_MULTIPLIER = 10
SET_LOGO_DIR = "set_logos"

# custom theme colors in grayscale
BG_COLOR = "#2E2E2E"
ACCENT_COLOR = "#666666"
HOVER_COLOR = "#525252"
TEXT_COLOR = "#FFFFFF"
BORDER_COLOR = "#444444"



def normalize(text: str, keep_spaces: bool = False) -> str:
    """Normalize text for comparisons and API queries."""
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
    text = text.replace("-", "")
    if not keep_spaces:
        text = text.replace(" ", "")
    return text.strip()




# Wczytanie danych setów
def reload_sets():
    """Load set definitions from the JSON files."""
    global tcg_sets_eng_by_era, tcg_sets_eng_map, tcg_sets_eng
    global tcg_sets_jp_by_era, tcg_sets_jp_map, tcg_sets_jp

    try:
        with open("tcg_sets.json", encoding="utf-8") as f:
            tcg_sets_eng_by_era = json.load(f)
    except FileNotFoundError:
        tcg_sets_eng_by_era = {}
    tcg_sets_eng_map = {
        item["name"]: item["code"]
        for sets in tcg_sets_eng_by_era.values()
        for item in sets
    }
    tcg_sets_eng = [
        item["name"] for sets in tcg_sets_eng_by_era.values() for item in sets
    ]

    try:
        with open("tcg_sets_jp.json", encoding="utf-8") as f:
            tcg_sets_jp_by_era = json.load(f)
    except FileNotFoundError:
        tcg_sets_jp_by_era = {}
    tcg_sets_jp_map = {
        item["name"]: item["code"]
        for sets in tcg_sets_jp_by_era.values()
        for item in sets
    }
    tcg_sets_jp = [
        item["name"] for sets in tcg_sets_jp_by_era.values() for item in sets
    ]


reload_sets()




def get_set_code(name: str) -> str:
    """Return the API code for a set name if available."""
    if not name:
        return ""
    search = name.strip().lower()
    for mapping in (tcg_sets_eng_map, tcg_sets_jp_map):
        for key, code in mapping.items():
            if key.lower() == search:
                return code
    return name


def choose_nearest_locations(order_list, output_data):
    """Assign the nearest warehouse codes to order items.

    The function modifies the provided ``order_list`` in place, attaching a
    ``warehouse_code`` to each product when possible.  When multiple codes are
    available for the same ``product_code`` the combination with the smallest
    total Manhattan distance is chosen.
    """

    pattern = re.compile(r"K(\d+)R(\d)P(\d+)")
    available = defaultdict(list)

    # Collect available locations grouped by product_code
    for row in output_data:
        if not row:
            continue
        prod = str(row.get("product_code", ""))
        codes = str(row.get("warehouse_code") or "").split(";")
        for code in codes:
            code = code.strip()
            m = pattern.match(code)
            if not m:
                continue
            box, col, pos = map(int, m.groups())
            available[prod].append(((box, col, pos), code))

    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    def best_codes(options, qty):
        if qty <= 1:
            return [options[0][1]]

        best = None
        best_cost = None
        for combo in combinations(options, min(qty, len(options))):
            coords = [c[0] for c in combo]
            cost = 0
            for i in range(len(coords)):
                for j in range(i + 1, len(coords)):
                    cost += manhattan(coords[i], coords[j])
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = [c[1] for c in combo]
        return best or []

    for order in order_list:
        for item in order.get("products", []):
            prod = str(item.get("product_code") or item.get("code") or "")
            qty = int(item.get("quantity", 1))
            options = available.get(prod)
            if not options:
                continue
            options.sort(key=lambda x: x[1])
            chosen = best_codes(options, qty)
            # remove used ones
            remaining = [o for o in options if o[1] not in chosen]
            available[prod] = remaining
            if chosen:
                item["warehouse_code"] = ";".join(chosen)

    return order_list


def extract_cardmarket_price(card):
    """Return the best available Cardmarket price for a card.

    The function checks multiple possible fields in the ``cardmarket`` price
    section and returns the first non-zero value.  If none of the fields are
    present or they evaluate to zero, ``None`` is returned.
    """

    cardmarket = card.get("prices", {}).get("cardmarket", {}) or {}
    for field in ["30d_average", "trendPrice", "trend_price", "lowest_near_mint"]:
        price = cardmarket.get(field)
        try:
            value = float(price)
        except (TypeError, ValueError):
            continue
        if value:
            print(f"[DEBUG] Using Cardmarket field '{field}' with value {value}")
            return value
    return None


def analyze_card_image(path: str):
    """Return card details recognized from the image using OpenAI."""
    if not OPENAI_API_KEY:
        return {"name": "", "number": "", "set": "", "suffix": ""}

    parsed = urlparse(path)
    if parsed.scheme in ("http", "https"):
        url = path
    else:
        folder = os.path.basename(os.path.dirname(path))
        filename = os.path.basename(path)
        url = f"{BASE_IMAGE_URL}/{folder}/{filename}"

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract Pokemon card name, number, set and suffix (EX, GX, V, VMAX, VSTAR, Shiny, Promo) as JSON {\"name\":\"\",\"number\":\"\",\"set\":\"\",\"suffix\":\"\"}. Return empty suffix when not applicable."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": url},
                        },
                    ],
                }
            ],
            max_tokens=100,
        )
        content = resp.choices[0].message.content
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = None

        if data is None:
            # Remove Markdown code fences if present
            text = content.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                    text = "\n".join(lines[1:-1]).strip()
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"[ERROR] analyze_card_image failed to decode JSON: {content!r} - {e}")
                return {"name": "", "number": "", "set": "", "suffix": ""}

        number = data.get("number", "")
        if isinstance(number, str):
            m = re.match(r"\D*(\d+)", number)
            if m:
                data["number"] = str(int(m.group(1)))

        name = data.get("name", "")
        suffix = data.get("suffix", "").upper() if isinstance(data.get("suffix"), str) else ""
        if isinstance(name, str) and not suffix:
            parts = name.split()
            if parts and parts[-1].upper() in {"EX", "GX", "V", "VMAX", "VSTAR", "SHINY", "PROMO"}:
                suffix = parts[-1].upper()
                name = " ".join(parts[:-1])
        data["name"] = name
        data["suffix"] = suffix
        return data
    except Exception as e:
        print(f"[ERROR] analyze_card_image failed: {e}")
        return {"name": "", "number": "", "set": "", "suffix": ""}


class CardEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("KARTOTEKA")
        # improve default font for all widgets
        self.root.configure(bg=BG_COLOR, fg_color=BG_COLOR)
        self.root.option_add("*Font", ("Segoe UI", 12))
        self.root.option_add("*Foreground", TEXT_COLOR)
        self.index = 0
        self.cards = []
        self.image_objects = []
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.card_cache = {}
        self.file_to_key = {}
        self.product_code_map = {}
        self.next_product_code = 1
        self.price_db = self.load_price_db()
        self.folder_name = ""
        self.folder_path = ""
        self.progress_var = tk.StringVar(value="0/0")
        self.start_box_var = tk.StringVar(value="1")
        self.start_col_var = tk.StringVar(value="1")
        self.start_pos_var = tk.StringVar(value="1")
        self.scan_folder_var = tk.StringVar()
        self.starting_idx = 0
        self.start_frame = None
        self.shoper_frame = None
        self.pricing_frame = None
        self.magazyn_frame = None
        self.location_frame = None
        self.mag_canvases = []
        self.mag_box_photo = None
        self.log_widget = None
        self.cheat_frame = None
        self.set_logos = {}
        self.loading_frame = None
        self.loading_label = None
        self.show_loading_screen()
        threading.Thread(target=self.startup_tasks, daemon=True).start()

    def setup_welcome_screen(self):
        """Display a simple welcome screen before loading scans."""
        # Allow resizing but provide a sensible minimum size
        self.root.minsize(1000, 700)
        self.start_frame = ctk.CTkFrame(
            self.root, fg_color=BG_COLOR, corner_radius=10
        )
        self.start_frame.pack(expand=True, fill="both")

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((140, 140))
            self.logo_photo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(
                self.start_frame,
                image=self.logo_photo,
                bg=self.root.cget("background"),
            )
            logo_label.pack(pady=(10, 10))

        greeting = ctk.CTkLabel(
            self.start_frame,
            text="Witaj w aplikacji KARTOTEKA",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 24, "bold"),
        )
        greeting.pack(pady=5)

        desc = ctk.CTkLabel(
            self.start_frame,
            text=(
                "Aplikacja KARTOTEKA.SHOP pomaga przygotować skany do sprzedaży."
            ),
            wraplength=1400,
            justify="center",
            text_color=TEXT_COLOR,
        )
        desc.pack(pady=5)

        author = ctk.CTkLabel(
            self.start_frame,
            text="Twórca: BOGUCKI | Właściciel: kartoteka.shop",
            wraplength=1400,
            justify="center",
            font=("Inter", 10),
            text_color="#CCCCCC",
        )
        author.pack(side="bottom", pady=5)

        button_frame = tk.Frame(
            self.start_frame, bg=self.root.cget("background")
        )
        # Keep the buttons centered without stretching across the entire window
        button_frame.pack(pady=10)

        scan_btn = self.create_button(
            button_frame,
            text="\U0001f50d Skanuj",
            command=self.show_location_frame,
        )
        scan_btn.pack(side="left", padx=5)
        self.create_button(
            button_frame,
            text="\U0001f4b0 Wyceniaj",
            command=self.setup_pricing_ui,
        ).pack(side="left", padx=5)
        self.create_button(
            button_frame,
            text="\U0001f5c3\ufe0f Shoper",
            command=self.open_shoper_window,
        ).pack(side="left", padx=5)
        self.create_button(
            button_frame,
            text="\U0001f4e6 Magazyn",
            command=self.open_magazyn_window,
        ).pack(side="left", padx=5)
        self.create_button(
            button_frame,
            text="\U0001f528 Licytacje",
            command=self.open_auctions_window,
        ).pack(side="left", padx=5)
        self.create_button(
            button_frame,
            text="\U0001f4f7 FTP Obrazy",
            command=self.upload_images_dialog,
        ).pack(side="left", padx=5)



        # Display store statistics when Shoper credentials are available
        stats_frame = tk.Frame(
            self.start_frame, bg=self.root.cget("background")
        )
        # Keep the dashboard centered within the window
        stats_frame.pack(pady=10, anchor="center")
        stats_frame.grid_anchor("center")
        for i in range(3):
            stats_frame.columnconfigure(i, weight=1)

        stats = self.load_store_stats()

        total = stats.get("total_orders")
        try:
            total_num = int(total)
        except (TypeError, ValueError):
            total_num = None
        progress_ship = None
        if total_num:
            progress_ship = (total_num - stats.get("pending_shipments", 0)) / float(total_num)

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

        # Generate subtle variations of the background color so that the
        # white text on the dashboard cards remains readable while the
        # overall theme stays consistent.
        def lighten(color: str, factor: float) -> str:
            color = color.lstrip("#")
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            r = min(255, int(r + (255 - r) * factor))
            g = min(255, int(g + (255 - g) * factor))
            b = min(255, int(b + (255 - b) * factor))
            return f"#{r:02x}{g:02x}{b:02x}"

        colors = [lighten(BG_COLOR, 0.08 + 0.02 * i) for i in range(9)]

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

        self.create_button(
            stats_frame,
            text="Pokaż szczegóły",
            command=self.open_shoper_window,
        ).grid(row=len(stats_map) // 3 + 1, column=0, columnspan=3, pady=5)

    def placeholder_btn(self, text: str, master=None):
        if master is None:
            master = self.start_frame
        return self.create_button(
            master,
            text=text,
            command=lambda: messagebox.showinfo("Info", "Funkcja niezaimplementowana."),
        )

    def show_location_frame(self):
        """Display inputs for the starting scan location inside the main window."""
        # Hide any other active frames similar to other views
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
            self.magazyn_frame = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()

        self.root.minsize(1000, 700)
        frame = ctk.CTkFrame(self.root)
        frame.pack(expand=True, fill="both", padx=10, pady=10)
        frame.grid_anchor("center")
        # evenly distribute columns so the form stays centered
        for i in range(4):
            frame.columnconfigure(i, weight=1)
        self.location_frame = frame

        start_row = 0
        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.location_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                frame,
                image=self.location_logo_photo,
                bg=self.root.cget("background"),
            ).grid(row=start_row, column=0, columnspan=4, pady=(0, 10))
            start_row += 1

        for idx, label in enumerate(["Karton", "Kolumna", "Pozycja"]):
            ctk.CTkLabel(frame, text=label).grid(row=start_row, column=idx, padx=5, pady=2)
        ctk.CTkEntry(frame, textvariable=self.start_box_var, width=60).grid(row=start_row + 1, column=0)
        ctk.CTkEntry(frame, textvariable=self.start_col_var, width=60).grid(row=start_row + 1, column=1)
        ctk.CTkEntry(frame, textvariable=self.start_pos_var, width=60).grid(row=start_row + 1, column=2)

        ctk.CTkLabel(frame, text="Folder").grid(row=start_row + 2, column=0, padx=5, pady=2)
        ctk.CTkEntry(frame, textvariable=self.scan_folder_var, width=200).grid(row=start_row + 2, column=1, columnspan=2, sticky="ew")
        self.create_button(frame, text="Wybierz", command=self.select_scan_folder).grid(row=start_row + 2, column=3, padx=5)

        self.create_button(frame, text="Dalej", command=self.start_browse_scans).grid(row=start_row + 3, column=0, columnspan=4, pady=5)

    def select_scan_folder(self):
        """Open a dialog to choose the folder with scans."""
        folder = filedialog.askdirectory()
        if folder:
            self.scan_folder_var.set(folder)

    def create_button(self, master=None, **kwargs):
        if master is None:
            master = self.root
        return ctk.CTkButton(
            master,
            fg_color=ACCENT_COLOR,
            hover_color=HOVER_COLOR,
            corner_radius=10,
            **kwargs,
        )

    def create_stat_card(self, parent, title, value, icon, color, info, progress=None):
        """Create a dashboard card with optional progress bar."""
        frame = tk.Frame(parent, width=200, height=100, bg=color, bd=1, relief="ridge")
        # Keep the card size constant regardless of its contents
        frame.pack_propagate(False)
        frame.grid_propagate(False)
        tk.Label(frame, text=icon, font=("Helvetica", 24), bg=color).pack()
        tk.Label(frame, text=title, font=("Helvetica", 12, "bold"), bg=color).pack()
        tk.Label(frame, text=value, font=("Helvetica", 24), bg=color).pack()
        if progress is not None:
            bar = ctk.CTkProgressBar(frame)
            bar.set(max(0, min(1, progress)))
            bar.pack(fill="x", padx=5, pady=(0, 5))
        # Tooltip removed for cleaner display
        return frame

    def load_store_stats(self):
        """Retrieve various store statistics from Shoper.

        Numeric fields returned by the API are converted to integers when
        possible so they can be used safely in calculations.
        """
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
                try:
                    total = int(float(total))
                except (TypeError, ValueError):
                    total = 0
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
            for key, default in {
                "today": 0,
                "week": 0,
                "month": 0,
                "avg_order_value": 0,
                "active_products": 0,
            }.items():
                try:
                    value = int(float(sales.get(key, default)))
                except (TypeError, ValueError):
                    value = default
                stats_key = {
                    "today": "sales_today",
                    "week": "sales_week",
                    "month": "sales_month",
                    "avg_order_value": "avg_order_value",
                    "active_products": "active_cards",
                }[key]
                stats[stats_key] = value
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
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        # Ensure the window has a reasonable minimum size
        self.root.minsize(1000, 700)

        self.shoper_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.shoper_frame.pack(expand=True, fill="both", padx=10, pady=10)
        self.shoper_frame.columnconfigure(0, weight=1)
        self.shoper_frame.rowconfigure(2, weight=1)
        self.shoper_frame.rowconfigure(4, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.shoper_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                self.shoper_frame,
                image=self.shoper_logo_photo,
                bg=self.root.cget("background"),
            ).grid(row=0, column=0, pady=(0, 10))

        search_frame = tk.Frame(
            self.shoper_frame, bg=self.root.cget("background")
        )
        search_frame.grid(row=1, column=0, sticky="ew", pady=5)
        search_frame.columnconfigure(1, weight=1)
        search_frame.columnconfigure(3, weight=1)

        tk.Label(
            search_frame, text="Szukaj", bg=self.root.cget("background")
        ).grid(row=0, column=0, sticky="e")
        self.shoper_search_var = tk.StringVar()
        ctk.CTkEntry(search_frame, textvariable=self.shoper_search_var, placeholder_text="Nazwa produktu").grid(
            row=0, column=1, sticky="ew"
        )
        tk.Label(
            search_frame, text="Numer", bg=self.root.cget("background")
        ).grid(row=0, column=2, sticky="e")
        self.shoper_number_var = tk.StringVar()
        ctk.CTkEntry(search_frame, textvariable=self.shoper_number_var, placeholder_text="Kod").grid(
            row=0, column=3, sticky="ew"
        )
        tk.Label(
            search_frame, text="Sortuj", bg=self.root.cget("background")
        ).grid(row=0, column=4, sticky="e")
        self.shoper_sort_var = tk.StringVar(value="")
        ctk.CTkComboBox(
            search_frame,
            variable=self.shoper_sort_var,
            values=["", "name", "-name", "price", "-price"],
            width=10,
        ).grid(row=0, column=5, padx=5)
        self.create_button(
            search_frame,
            text="Wyszukaj",
            command=lambda: self.search_products(output),
        ).grid(row=0, column=6, padx=5)

        output = tk.Text(
            self.shoper_frame,
            bg=self.root.cget("background"),
            fg="white",
        )
        output.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        # Automatically display current products upon connecting
        self.fetch_inventory(output)

        btn_frame = tk.Frame(
            self.shoper_frame, bg=self.root.cget("background")
        )
        btn_frame.grid(row=3, column=0, pady=5, sticky="ew")

        self.create_button(
            btn_frame,
            text="Wyślij produkt",
            command=lambda: self.push_product(output),
        ).pack(side="left", padx=5)

        self.create_button(
            btn_frame,
            text="Inwentarz",
            command=lambda: self.fetch_inventory(output),
        ).pack(side="left", padx=5)

        orders_output = tk.Text(
            self.shoper_frame,
            height=10,
            bg=self.root.cget("background"),
            fg="white",
        )
        orders_output.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)

        self.create_button(
            btn_frame,
            text="Zamówienia",
            command=lambda: self.show_orders(orders_output),
        ).pack(side="left", padx=5)

        self.create_button(
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
            orders_list = orders.get("list", orders)
            choose_nearest_locations(orders_list, self.output_data)
            widget.delete("1.0", tk.END)
            lines = []
            for order in orders_list:
                oid = order.get("order_id") or order.get("id")
                lines.append(f"Zamówienie #{oid}")
                for item in order.get("products", []):
                    code = (
                        item.get("warehouse_code")
                        or item.get("product_code")
                        or item.get("code", "")
                    )
                    locations = [self.location_from_code(c.strip()) for c in str(code).split(";") if c.strip()]
                    location = "; ".join(l for l in locations if l)
                    lines.append(
                        f" - {item.get('name')} x{item.get('quantity')} [{code}] {location}"
                    )
            widget.insert(tk.END, "\n".join(lines))
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def open_auctions_window(self):
        """Display items from the 'Licytacja' category in a new window."""
        if not self.shoper_client:
            messagebox.showerror("Błąd", "Brak konfiguracji Shoper API")
            return
        win = tk.Toplevel(self.root)
        win.title("Licytacje")
        win.configure(bg=self.root.cget("background"))
        output = tk.Text(win, bg=self.root.cget("background"), fg="white")
        output.pack(expand=True, fill="both", padx=10, pady=10)
        self.create_button(win, text="Zamknij", command=win.destroy).pack(pady=5)
        self.fetch_auction_items(output)

    def fetch_auction_items(self, widget):
        """Fetch items in the 'Licytacja' category from Shoper."""
        try:
            data = self.shoper_client.search_products(
                filters={"filters[category]": "Licytacja"}
            )
            widget.delete("1.0", tk.END)
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

    @staticmethod
    def location_from_code(code: str) -> str:
        return storage.location_from_code(code)

    def open_magazyn_window(self):
        """Display storage occupancy inside the main window."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
            self.pricing_frame = None
        if getattr(self, "shoper_frame", None):
            self.shoper_frame.destroy()
            self.shoper_frame = None
        if getattr(self, "frame", None):
            self.frame.destroy()
            self.frame = None
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None

        self.root.minsize(1000, 700)
        self.magazyn_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.magazyn_frame.pack(expand=True, fill="both", padx=10, pady=10)

        img_path = os.path.join(os.path.dirname(__file__), "box.png")
        if os.path.exists(img_path):
            img = Image.open(img_path)
            img.thumbnail((150, 150))
        else:
            img = Image.new("RGB", (150, 150), "#111111")
        self.mag_box_photo = ImageTk.PhotoImage(img)

        container = tk.Frame(
            self.magazyn_frame, bg=self.root.cget("background")
        )
        container.pack(padx=10, pady=10)

        # Order boxes so that the grid layout is:
        # row0 -> K1 K2 K5 K6
        # row1 -> K3 K4 K7 K8
        self.mag_box_order = [1, 2, 5, 6, 3, 4, 7, 8]
        self.mag_canvases = []
        self.mag_labels = []
        for i, box_num in enumerate(self.mag_box_order):
            frame = tk.Frame(container, bg=self.root.cget("background"))
            lbl = tk.Label(frame, text=f"K{box_num}", bg=self.root.cget("background"))
            lbl.pack()
            canvas = tk.Canvas(
                frame,
                width=self.mag_box_photo.width(),
                height=self.mag_box_photo.height(),
                bg="#111111",
                highlightthickness=0,
            )
            canvas.create_image(0, 0, image=self.mag_box_photo, anchor="nw")
            canvas.pack()
            frame.grid(row=i // 4, column=i % 4, padx=5, pady=5)
            self.mag_canvases.append(canvas)
            self.mag_labels.append(lbl)

        btn_frame = tk.Frame(
            self.magazyn_frame, bg=self.root.cget("background")
        )
        btn_frame.pack(pady=5)

        self.create_button(
            btn_frame, text="Odśwież", command=self.refresh_magazyn
        ).pack(side="left", padx=5)

        self.create_button(
            btn_frame, text="Powrót", command=self.back_to_welcome
        ).pack(side="left", padx=5)

        self.refresh_magazyn()

    def compute_column_occupancy(self):
        """Return dictionary of used slots per box column."""
        return storage.compute_column_occupancy(self)

    def repack_column(self, box: int, column: int):
        """Renumber codes in the given column so there are no gaps."""
        storage.repack_column(self, box, column)

    def refresh_magazyn(self):
        """Refresh storage view and color code capacity usage.

        A column's background turns orange when 30% or more of its
        capacity is still free.  Individual 100-card segments become
        green as soon as they are occupied.
        """
        occ = self.compute_column_occupancy()
        if not self.mag_canvases:
            return
        for idx, canvas in enumerate(self.mag_canvases):
            box = (
                self.mag_box_order[idx]
                if hasattr(self, "mag_box_order")
                else idx + 1
            )
            canvas.delete("stats")
            col_w = self.mag_box_photo.width() / 4
            canvas.create_image(0, 0, image=self.mag_box_photo, anchor="nw")
            for c in range(1, 5):
                filled = occ.get(box, {}).get(c, 0)
                free_percent = (1000 - filled) / 10
                x1 = (c - 1) * col_w
                x_mid = x1 + col_w / 2
                if free_percent >= 30:
                    canvas.create_rectangle(
                        x1,
                        0,
                        x1 + col_w,
                        self.mag_box_photo.height(),
                        fill="#ffcc80",
                        width=0,
                        tags="stats",
                    )
                # Draw 100-card sections
                filled_sections = filled // 100
                seg_h = self.mag_box_photo.height() / 10
                for i in range(10):
                    y1 = self.mag_box_photo.height() - seg_h * (i + 1)
                    y2 = self.mag_box_photo.height() - seg_h * i
                    color = "#c8f7c8" if i < filled_sections else ""
                    canvas.create_rectangle(
                        x1,
                        y1,
                        x1 + col_w,
                        y2,
                        fill=color,
                        outline="black",
                        width=1,
                        tags="stats",
                    )
                canvas.create_text(
                    x_mid,
                    self.mag_box_photo.height() / 2,
                    text=f"C{c}: {free_percent:.0f}%",
                    tags="stats",
                )

    def setup_pricing_ui(self):
        """UI for quick card price lookup."""
        if self.start_frame is not None:
            self.start_frame.destroy()
            self.start_frame = None
        if getattr(self, "pricing_frame", None):
            self.pricing_frame.destroy()
        # Set a sensible minimum size and allow resizing
        self.root.minsize(1000, 700)
        self.pricing_frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.pricing_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.pricing_frame.columnconfigure(0, weight=1)
        self.pricing_frame.columnconfigure(1, weight=1)
        self.pricing_frame.rowconfigure(1, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
            self.pricing_logo_photo = ImageTk.PhotoImage(logo_img)
            tk.Label(
                self.pricing_frame,
                image=self.pricing_logo_photo,
                bg=self.root.cget("background"),
            ).grid(row=0, column=0, columnspan=2, pady=(0, 10))

        self.input_frame = tk.Frame(
            self.pricing_frame, bg=self.root.cget("background")
        )
        self.input_frame.grid(row=1, column=0, sticky="nsew")

        self.image_frame = tk.Frame(
            self.pricing_frame, bg=self.root.cget("background")
        )
        self.image_frame.grid(row=1, column=1, sticky="nsew")

        self.input_frame.columnconfigure(0, weight=1)
        self.input_frame.columnconfigure(1, weight=1)
        self.input_frame.rowconfigure(5, weight=1)

        tk.Label(
            self.input_frame, text="Nazwa", bg=self.root.cget("background")
        ).grid(row=0, column=0, sticky="e")
        self.price_name_entry = ctk.CTkEntry(
            self.input_frame, width=200, placeholder_text="Nazwa karty"
        )
        self.price_name_entry.grid(row=0, column=1, sticky="ew")

        tk.Label(
            self.input_frame, text="Numer", bg=self.root.cget("background")
        ).grid(row=1, column=0, sticky="e")
        self.price_number_entry = ctk.CTkEntry(
            self.input_frame, width=200, placeholder_text="Numer"
        )
        self.price_number_entry.grid(row=1, column=1, sticky="ew")

        tk.Label(
            self.input_frame, text="Set", bg=self.root.cget("background")
        ).grid(row=2, column=0, sticky="e")
        self.price_set_entry = ctk.CTkEntry(
            self.input_frame, width=200, placeholder_text="Set"
        )
        self.price_set_entry.grid(row=2, column=1, sticky="ew")

        self.price_reverse_var = tk.BooleanVar()
        ctk.CTkCheckBox(
            self.input_frame,
            text="Reverse",
            variable=self.price_reverse_var,
        ).grid(row=3, column=0, columnspan=2, pady=5)

        self.price_reverse_var.trace_add("write", lambda *a: self.on_reverse_toggle())

        btn_frame = tk.Frame(
            self.input_frame, bg=self.root.cget("background")
        )
        btn_frame.grid(row=4, column=0, columnspan=2, pady=5, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.create_button(
            btn_frame,
            text="Wyszukaj",
            command=self.run_pricing_search,
            width=120,
        ).grid(row=0, column=0, padx=5)

        self.create_button(
            btn_frame,
            text="Powrót",
            command=self.back_to_welcome,
            width=120,
        ).grid(row=0, column=1, padx=5)

        self.result_frame = tk.Frame(
            self.image_frame, bg=self.root.cget("background")
        )
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
        if getattr(self, "magazyn_frame", None):
            self.magazyn_frame.destroy()
            self.magazyn_frame = None
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        self.setup_welcome_screen()

    def setup_editor_ui(self):
        # Provide a minimum size and allow the editor to expand
        self.root.minsize(1000, 700)
        self.frame = tk.Frame(
            self.root, bg=self.root.cget("background")
        )
        self.frame.pack(expand=True, fill="both", padx=10, pady=10)
        # Allow widgets inside the frame to expand properly
        for i in range(6):
            self.frame.columnconfigure(i, weight=1)
        self.frame.rowconfigure(2, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((200, 80))
        self.logo_photo = ImageTk.PhotoImage(logo_img)
        self.logo_label = tk.Label(
            self.frame,
            image=self.logo_photo,
            bg=self.root.cget("background"),
        )
        self.logo_label.grid(row=0, column=0, columnspan=6, pady=(0, 10))

        # label for the upcoming warehouse code
        self.location_label = ctk.CTkLabel(self.frame, text="", text_color=TEXT_COLOR)
        self.location_label.grid(row=1, column=0, columnspan=6, pady=(0, 10))


        # Bottom frame for action buttons
        self.button_frame = tk.Frame(
            self.frame, bg=self.root.cget("background")
        )
        # Do not stretch the button frame so that buttons remain centered
        self.button_frame.grid(row=15, column=0, columnspan=6, pady=10)

        self.load_button = self.create_button(
            self.button_frame,
            text="Import",
            command=self.browse_scans,
        )
        self.load_button.pack(side="left", padx=5)

        self.end_button = self.create_button(
            self.button_frame,
            text="Zakończ i zapisz",
            command=self.export_csv,
        )
        self.end_button.pack(side="left", padx=5)

        self.back_button = self.create_button(
            self.button_frame,
            text="Powrót",
            command=self.back_to_welcome,
        )
        self.back_button.pack(side="left", padx=5)

        # Navigation buttons to move between loaded scans
        self.prev_button = self.create_button(
            self.button_frame,
            text="\u23ee Poprzednia",
            command=self.previous_card,
        )
        self.prev_button.pack(side="left", padx=5)

        self.next_button = self.create_button(
            self.button_frame,
            text="Nast\u0119pna \u23ed",
            command=self.next_card,
        )
        self.next_button.pack(side="left", padx=5)

        self.cheat_button = self.create_button(
            self.button_frame,
            text="\U0001F9FE \u015aci\u0105ga",
            command=self.toggle_cheatsheet,
        )
        self.cheat_button.pack(side="left", padx=5)

        # Keep a constant label size so the window does not resize when
        # scans of different dimensions are displayed
        self.image_label = ctk.CTkLabel(self.frame, width=400, height=560)
        self.image_label.grid(row=2, column=0, rowspan=12, sticky="nsew")
        self.image_label.grid_propagate(False)
        # Display only a textual progress indicator below the card image
        self.progress_label = ctk.CTkLabel(self.frame, textvariable=self.progress_var)
        self.progress_label.grid(row=14, column=0, pady=5, sticky="ew")

        # Container for card information fields
        self.info_frame = ctk.CTkFrame(self.frame)
        self.info_frame.grid(
            row=2, column=1, columnspan=4, rowspan=12, padx=10, sticky="nsew"
        )
        ctk.CTkLabel(self.info_frame, text="Informacje o karcie").grid(row=0, column=0, columnspan=8, pady=(0,5))
        start_row = 1
        for i in range(8):
            self.info_frame.columnconfigure(i, weight=1)

        self.entries = {}

        grid_opts = {"padx": 5, "pady": 2}

        tk.Label(
            self.info_frame, text="Język", bg=self.root.cget("background")
        ).grid(
            row=start_row, column=0, sticky="w", **grid_opts
        )
        self.lang_var = tk.StringVar(value="ENG")
        self.entries["język"] = self.lang_var
        lang_dropdown = ctk.CTkComboBox(
            self.info_frame, values=["ENG", "JP"], variable=self.lang_var, width=200
        )
        lang_dropdown.grid(row=start_row, column=1, sticky="ew", **grid_opts)
        lang_dropdown.bind("<<ComboboxSelected>>", self.update_set_options)

        tk.Label(
            self.info_frame, text="Nazwa", bg=self.root.cget("background")
        ).grid(
            row=start_row + 1, column=0, sticky="w", **grid_opts
        )
        self.entries["nazwa"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Nazwa"
        )
        self.entries["nazwa"].grid(row=start_row + 1, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Numer", bg=self.root.cget("background")
        ).grid(
            row=start_row + 2, column=0, sticky="w", **grid_opts
        )
        self.entries["numer"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Numer"
        )
        self.entries["numer"].grid(row=start_row + 2, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Set", bg=self.root.cget("background")
        ).grid(
            row=start_row + 3, column=0, sticky="w", **grid_opts
        )
        self.set_var = tk.StringVar()
        self.set_dropdown = ctk.CTkComboBox(
            self.info_frame, variable=self.set_var, width=20
        )
        self.set_dropdown.grid(row=start_row + 3, column=1, sticky="ew", **grid_opts)
        self.set_dropdown.bind("<KeyRelease>", self.filter_sets)
        self.set_dropdown.bind("<Tab>", self.autocomplete_set)
        self.entries["set"] = self.set_var

        tk.Label(
            self.info_frame, text="Typ", bg=self.root.cget("background")
        ).grid(
            row=start_row + 4, column=0, sticky="w", **grid_opts
        )
        self.type_vars = {}
        self.type_frame = ctk.CTkFrame(self.info_frame)
        self.type_frame.grid(row=start_row + 4, column=1, columnspan=7, sticky="w", **grid_opts)
        types = ["Common", "Holo", "Reverse", "Pokeball", "Masterball", "Stamp"]
        for t in types:
            var = tk.BooleanVar()
            self.type_vars[t] = var
            ctk.CTkCheckBox(
                self.type_frame,
                text=t,
                variable=var,
            ).pack(side="left", padx=2)

        tk.Label(
            self.info_frame, text="Rarity", bg=self.root.cget("background")
        ).grid(
            row=start_row + 5, column=0, sticky="w", **grid_opts
        )
        self.rarity_vars = {}
        self.rarity_frame = ctk.CTkFrame(self.info_frame)
        self.rarity_frame.grid(row=start_row + 5, column=1, columnspan=7, sticky="w", **grid_opts)
        rarities = ["RR", "AR", "SR", "SAR", "UR", "ACE", "PROMO"]
        for r in rarities:
            var = tk.BooleanVar()
            self.rarity_vars[r] = var
            ctk.CTkCheckBox(
                self.rarity_frame,
                text=r,
                variable=var,
            ).pack(side="left", padx=2)

        tk.Label(
            self.info_frame, text="Suffix", bg=self.root.cget("background")
        ).grid(
            row=start_row + 6, column=0, sticky="w", **grid_opts
        )
        self.suffix_var = tk.StringVar(value="")
        self.entries["suffix"] = self.suffix_var
        suffix_dropdown = ctk.CTkComboBox(
            self.info_frame,
            variable=self.suffix_var,
            values=["", "EX", "GX", "V", "VMAX", "VSTAR", "Shiny", "Promo"],
            width=20,
        )
        suffix_dropdown.grid(row=start_row + 6, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Stan", bg=self.root.cget("background")
        ).grid(
            row=start_row + 7, column=0, sticky="w", **grid_opts
        )
        self.stan_var = tk.StringVar(value="NM")
        self.entries["stan"] = self.stan_var
        stan_dropdown = ctk.CTkComboBox(
            self.info_frame,
            variable=self.stan_var,
            values=["NM", "LP", "PL", "MP", "HP", "DMG"],
            width=20,
        )
        stan_dropdown.grid(row=start_row + 7, column=1, sticky="ew", **grid_opts)

        tk.Label(
            self.info_frame, text="Cena", bg=self.root.cget("background")
        ).grid(
            row=start_row + 8, column=0, sticky="w", **grid_opts
        )
        self.entries["cena"] = ctk.CTkEntry(
            self.info_frame, width=200, placeholder_text="Cena"
        )
        self.entries["cena"].grid(row=start_row + 8, column=1, sticky="ew", **grid_opts)

        self.api_button = self.create_button(
            self.info_frame,
            text="Pobierz cenę z bazy",
            command=self.fetch_card_data,
        )
        self.api_button.grid(row=start_row + 9, column=0, columnspan=2, sticky="ew", **grid_opts)

        self.variants_button = self.create_button(
            self.info_frame,
            text="Inne warianty",
            command=self.show_variants,
        )
        self.variants_button.grid(
            row=start_row + 9, column=2, columnspan=2, sticky="ew", **grid_opts
        )

        self.cardmarket_button = self.create_button(
            self.info_frame,
            text="Cardmarket",
            command=self.open_cardmarket_search,
        )
        self.cardmarket_button.grid(
            row=start_row + 9, column=4, columnspan=2, sticky="ew", **grid_opts
        )

        self.save_button = self.create_button(
            self.info_frame,
            text="Zapisz i dalej",
            command=self.save_and_next,
        )
        self.save_button.grid(row=start_row + 10, column=0, columnspan=2, sticky="ew", **grid_opts)

        for entry in self.entries.values():
            if isinstance(entry, (tk.Entry, ctk.CTkEntry)):
                entry.bind("<Return>", lambda e: self.save_and_next())

        self.root.bind("<Return>", lambda e: self.save_and_next())
        self.update_set_options()

        self.log_widget = tk.Text(
            self.frame,
            height=4,
            state="disabled",
            bg=self.root.cget("background"),
            fg="white",
        )
        self.log_widget.grid(row=16, column=0, columnspan=6, sticky="ew")

    def update_set_options(self, event=None):
        lang = self.lang_var.get().strip().upper()
        if lang == "JP":
            self.set_dropdown.configure(values=tcg_sets_jp)
        else:
            self.set_dropdown.configure(values=tcg_sets_eng)
        if getattr(self, "cheat_frame", None) is not None:
            self.create_cheat_frame()

    def filter_sets(self, event=None):
        typed = self.set_var.get().lower()
        lang = self.lang_var.get().strip().upper()
        all_sets = tcg_sets_jp if lang == "JP" else tcg_sets_eng
        if typed:
            filtered = [s for s in all_sets if typed in s.lower()]
        else:
            filtered = all_sets
        self.set_dropdown.configure(values=filtered)

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

    def create_cheat_frame(self, show_headers: bool = True):
        """Create or refresh the cheatsheet frame with set logos."""
        if self.cheat_frame is not None:
            self.cheat_frame.destroy()
        self.cheat_frame = ctk.CTkScrollableFrame(
            self.frame,
            fg_color=self.root.cget("background"),
            width=240,
        )
        self.cheat_frame.grid(row=2, column=5, rowspan=12, sticky="nsew")

        lang = self.lang_var.get().strip().upper()
        sets_by_era = (
            tcg_sets_jp_by_era if lang == "JP" else tcg_sets_eng_by_era
        )

        row = 0
        for era, sets in sets_by_era.items():
            if show_headers:
                ctk.CTkLabel(
                    self.cheat_frame,
                    text=era,
                    font=("Segoe UI", 12, "bold"),
                ).grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=4)
                row += 1
            for item in sets:
                name = item["name"]
                code = item["code"]
                img = self.set_logos.get(code)
                if img:
                    tk.Label(
                        self.cheat_frame,
                        image=img,
                        bg=self.root.cget("background"),
                    ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
                else:
                    tk.Label(
                        self.cheat_frame,
                        text="",
                        width=2,
                        bg=self.root.cget("background"),
                    ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
                ctk.CTkLabel(
                    self.cheat_frame,
                    text=f"{name} ({code})",
                ).grid(row=row, column=1, sticky="w", padx=5, pady=2)
                row += 1

    def toggle_cheatsheet(self):
        """Show or hide the cheatsheet with set logos."""
        if self.cheat_frame is None:
            self.create_cheat_frame()
            return
        if self.cheat_frame.winfo_ismapped():
            self.cheat_frame.grid_remove()
        else:
            self.cheat_frame.grid()

    def start_browse_scans(self):
        """Wrapper for 'Dalej' button that closes the location frame."""
        if getattr(self, "location_frame", None):
            self.location_frame.destroy()
            self.location_frame = None
        self.browse_scans()

    def browse_scans(self):
        """Ask for a folder and load scans starting from the entered location."""
        try:
            box = int(self.start_box_var.get())
            column = int(self.start_col_var.get())
            pos = int(self.start_pos_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(
                "Błąd", "Podaj poprawne wartości (kolumna 1-4, pozycja 1-1000)"
            )
            return
        if column < 1 or column > 4 or pos < 1 or pos > 1000:
            messagebox.showerror(
                "Błąd", "Podaj poprawne wartości (kolumna 1-4, pozycja 1-1000)"
            )
            return
        folder = self.scan_folder_var.get().strip()
        if not folder:
            folder = filedialog.askdirectory()
            if not folder:
                return
            self.scan_folder_var.set(folder)
        self.starting_idx = (box - 1) * 4000 + (column - 1) * 1000 + (pos - 1)
        CardEditorApp.load_images(self, folder)

    def load_images(self, folder):
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
        self.output_data = [None] * len(self.cards)
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
        self.current_card_image = image.copy()
        if hasattr(ctk, "CTkImage"):
            img = ctk.CTkImage(light_image=image, size=image.size)
        else:
            img = ImageTk.PhotoImage(image)
        self.image_objects.append(img)
        self.image_objects = self.image_objects[-2:]
        self.current_card_photo = img
        self.image_label.configure(image=img)
        if hasattr(self, "location_label"):
            self.location_label.configure(text=self.next_free_location())

        for key, entry in self.entries.items():
            if isinstance(entry, (tk.Entry, ctk.CTkEntry)):
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
                if isinstance(entry, (tk.Entry, ctk.CTkEntry)):
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

        folder = os.path.basename(os.path.dirname(image_path))
        remote_url = f"{BASE_IMAGE_URL}/{folder}/{os.path.basename(image_path)}"
        self.start_scan_animation()
        threading.Thread(
            target=self._analyze_and_fill,
            args=(remote_url, self.index),
            daemon=True,
        ).start()

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

    def start_scan_animation(self, index=0):
        """Show the scanning GIF on top of the image label."""
        path = os.path.join(os.path.dirname(__file__), "scan.gif")
        w = self.image_label.winfo_width() or 400
        h = self.image_label.winfo_height() or 560
        if not hasattr(self, "scan_gif_frames") or getattr(self, "scan_gif_size", (None, None)) != (w, h):
            if os.path.exists(path) and hasattr(self, "current_card_image"):
                from PIL import ImageSequence

                img = Image.open(path)
                frames = []
                durations = []
                base = self.current_card_image.convert("RGBA").resize((w, h))
                for frame in ImageSequence.Iterator(img):
                    overlay = frame.convert("RGBA").resize((w, h))
                    composed = Image.alpha_composite(base, overlay)
                    if hasattr(ctk, "CTkImage"):
                        frames.append(ctk.CTkImage(light_image=composed, size=(w, h)))
                    else:
                        frames.append(ImageTk.PhotoImage(composed))
                    durations.append(frame.info.get("duration", 100))
                self.scan_gif_frames = frames
                self.scan_gif_durations = durations
                self.scan_gif_size = (w, h)
            else:
                self.scan_gif_frames = []
        if not self.scan_gif_frames:
            return
        self.scan_animation_running = True
        self._animate_scan_gif(index)

    def _animate_scan_gif(self, index=0):
        if not getattr(self, "scan_animation_running", False):
            return
        frame = self.scan_gif_frames[index]
        self.image_label.configure(image=frame)
        next_index = (index + 1) % len(self.scan_gif_frames)
        delay = self.scan_gif_durations[index] if hasattr(self, "scan_gif_durations") else 100
        self.scan_after_id = self.image_label.after(delay, self._animate_scan_gif, next_index)

    def stop_scan_animation(self):
        """Hide the scanning GIF."""
        self.scan_animation_running = False
        if hasattr(self, "scan_after_id"):
            try:
                self.image_label.after_cancel(self.scan_after_id)
            except Exception:
                pass
        if hasattr(self, "current_card_photo"):
            self.image_label.configure(image=self.current_card_photo)

    def _analyze_and_fill(self, url, idx):
        result = analyze_card_image(url)
        self.root.after(0, lambda: self._apply_analysis_result(result, idx))

    def _apply_analysis_result(self, result, idx):
        if idx != self.index:
            return
        self.stop_scan_animation()
        if result:
            name = result.get("name", "")
            number = result.get("number", "")
            set_name = result.get("set", "")
            suffix_val = result.get("suffix", "")
            self.entries["nazwa"].delete(0, tk.END)
            self.entries["nazwa"].insert(0, name)
            self.entries["numer"].delete(0, tk.END)
            self.entries["numer"].insert(0, number)
            self.entries["set"].set(set_name)
            self.entries.get("suffix").set(suffix_val)
            self.update_set_options()

    def generate_location(self, idx):
        return storage.generate_location(idx)

    def next_free_location(self):
        """Return the next unused warehouse_code."""
        return storage.next_free_location(self)

    def load_price_db(self):
        if not os.path.exists(PRICE_DB_PATH):
            return []
        with open(PRICE_DB_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def load_set_logos(self):
        """Load set logos from SET_LOGO_DIR into self.set_logos."""
        self.set_logos.clear()
        if not os.path.isdir(SET_LOGO_DIR):
            return
        for file in os.listdir(SET_LOGO_DIR):
            path = os.path.join(SET_LOGO_DIR, file)
            if not os.path.isfile(path):
                continue
            if not file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                continue
            code = os.path.splitext(file)[0]
            try:
                img = Image.open(path)
                img.thumbnail((40, 40))
                self.set_logos[code] = ImageTk.PhotoImage(img)
            except Exception:
                continue

    def show_loading_screen(self):
        """Display a temporary loading screen during startup."""
        self.root.minsize(1000, 700)
        self.loading_frame = ctk.CTkFrame(self.root, fg_color=BG_COLOR)
        self.loading_frame.pack(expand=True, fill="both")
        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            img.thumbnail((300, 150))
            self.loading_logo = ImageTk.PhotoImage(img)
            tk.Label(
                self.loading_frame,
                image=self.loading_logo,
                bg=self.loading_frame.cget("fg_color"),
            ).pack(pady=10)

        gif_path = os.path.join(os.path.dirname(__file__), "simple_pokeball.gif")
        if os.path.exists(gif_path):
            from PIL import ImageSequence

            img = Image.open(gif_path)
            self.gif_frames = []
            self.gif_durations = []
            for frame in ImageSequence.Iterator(img):
                self.gif_frames.append(ImageTk.PhotoImage(frame.copy()))
                self.gif_durations.append(frame.info.get("duration", 100))

            self.gif_label = tk.Label(
                self.loading_frame, bg=self.loading_frame.cget("fg_color")
            )
            self.gif_label.pack()
            self.animate_loading_gif(0)
        self.loading_label = ctk.CTkLabel(
            self.loading_frame,
            text="Ładowanie...",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 16),
        )
        self.loading_label.pack(pady=10)
        self.root.update()

    def animate_loading_gif(self, index=0):
        """Cycle through frames of the loading GIF."""
        if not hasattr(self, "gif_frames"):
            return
        frame = self.gif_frames[index]
        self.gif_label.configure(image=frame)
        next_index = (index + 1) % len(self.gif_frames)
        delay = 100
        if hasattr(self, "gif_durations"):
            try:
                delay = self.gif_durations[index]
            except IndexError:
                pass
        self.gif_label.after(delay, self.animate_loading_gif, next_index)

    def startup_tasks(self):
        """Run initial setup tasks in the background."""
        self.update_sets()
        self.load_set_logos()
        self.root.after(0, self.finish_startup)

    def finish_startup(self):
        """Finalize initialization after background tasks complete."""
        if self.loading_frame is not None:
            self.loading_frame.destroy()
        try:
            self.shoper_client = ShoperClient(SHOPER_API_URL, SHOPER_API_TOKEN)
        except Exception as e:
            print(f"[WARNING] ShoperClient init failed: {e}")
            self.shoper_client = None
        self.setup_welcome_screen()

    def download_set_symbols(self, sets):
        """Download logos for the provided set definitions."""
        os.makedirs(SET_LOGO_DIR, exist_ok=True)
        total = len(sets)
        for idx, item in enumerate(sets, start=1):
            name = item.get("name")
            code = item.get("code")
            if self.loading_label is not None:
                self.loading_label.configure(
                    text=f"Pobieram {idx}/{total}: {name}"
                )
                self.root.update()
            if not code:
                continue
            symbol_url = f"https://images.pokemontcg.io/{code}/symbol.png"
            try:
                res = requests.get(symbol_url, timeout=10)
                if res.status_code == 404:
                    alt = re.sub(r"(^sv)0(\d$)", r"\1\2", code)
                    if alt != code:
                        alt_url = f"https://images.pokemontcg.io/{alt}/symbol.png"
                        res = requests.get(alt_url, timeout=10)
                        if res.status_code == 200:
                            symbol_url = alt_url
                if res.status_code == 200:
                    parsed_path = urlparse(symbol_url).path
                    ext = os.path.splitext(parsed_path)[1] or ".png"
                    safe = code.replace("/", "_")
                    path = os.path.join(SET_LOGO_DIR, f"{safe}{ext}")
                    with open(path, "wb") as fh:
                        fh.write(res.content)
                else:
                    if res.status_code == 404:
                        print(f"[WARN] Symbol not found for {name}: {symbol_url}")
                    else:
                        print(
                            f"[ERROR] Failed to download symbol for {name} from {symbol_url}: {res.status_code}"
                        )
            except requests.RequestException as exc:
                print(f"[ERROR] {name}: {exc}")

    def update_sets(self):
        """Check remote API for new sets and update local files."""
        try:
            self.loading_label.configure(text="Sprawdzanie nowych setów...")
            self.root.update()
            with open("tcg_sets.json", encoding="utf-8") as f:
                current_sets = json.load(f)
        except Exception:
            current_sets = {}

        try:
            resp = requests.get("https://api.pokemontcg.io/v2/sets", timeout=10)
            resp.raise_for_status()
            remote = resp.json().get("data", [])
        except Exception as exc:
            print(f"[WARN] Unable to fetch sets: {exc}")
            return

        added = 0
        new_items = []
        existing_codes = {
            s.get("code", "").strip().lower()
            for sets in current_sets.values()
            for s in sets
        }

        for item in remote:
            series = item.get("series") or "Other"
            code = item.get("id")
            name = item.get("name")
            if not code or not name:
                continue
            code_key = code.strip().lower()
            if code_key in existing_codes:
                continue
            group = current_sets.setdefault(series, [])
            group.append({"name": name, "code": code})
            existing_codes.add(code_key)
            added += 1
            new_items.append({"name": name, "code": code})

        if added:
            with open("tcg_sets.json", "w", encoding="utf-8") as f:
                json.dump(current_sets, f, indent=2, ensure_ascii=False)
            reload_sets()
            names = ", ".join(item["name"] for item in new_items)
            self.loading_label.configure(
                text=f"Pobieram symbole setów 0/{added}..."
            )
            self.root.update()
            self.download_set_symbols(new_items)
            print(f"[INFO] Dodano {added} setów: {names}")

    def log(self, message: str):
        if self.log_widget:
            self.log_widget.configure(state="normal")
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state="disabled")
        print(message)

    def get_price_from_db(self, name, number, set_name):
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
        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_api,
                    "number": number_input,
                    "set": set_code,
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
                price_eur = extract_cardmarket_price(best)
                if price_eur is not None:
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
        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {
                    "name": name_api,
                    "number": number_input,
                    "set": set_code,
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
                    price_eur = extract_cardmarket_price(card)
                    price_pln = 0
                    if price_eur is not None:
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
        name_api = normalize(name, keep_spaces=True)
        name_input = normalize(name)
        number_input = number.strip().lower()
        set_input = set_name.strip().lower()
        if set_input == "prismatic evolutions: additionals":
            set_code = "xpre"
        else:
            set_code = get_set_code(set_name)

        try:
            headers = {}
            if RAPIDAPI_KEY and RAPIDAPI_HOST:
                url = f"https://{RAPIDAPI_HOST}/cards/search"
                params = {"search": name_api}
                headers = {
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                }
            else:
                url = "https://www.tcggo.com/api/cards/"
                params = {"name": name_api, "number": number_input, "set": set_code}

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
                    price_eur = extract_cardmarket_price(card) or 0
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

        top = ctk.CTkToplevel(self.root)
        top.title("Inne warianty")
        top.geometry("600x400")

        logo_path = os.path.join(os.path.dirname(__file__), "banner22.png")
        if os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            logo_img.thumbnail((140, 140))
            top.logo_image = ctk.CTkImage(light_image=logo_img, size=logo_img.size)
            ctk.CTkLabel(top, image=top.logo_image, text="").pack(pady=(10, 10))

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

        self.create_button(top, text="Ustaw cenę", command=set_selected_price).pack(pady=5)
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
        """Apply holo/reverse or special variant multiplier when needed."""
        if price is None:
            return None
        multiplier = 1
        if is_reverse or is_holo:
            multiplier *= HOLO_REVERSE_MULTIPLIER

        types = getattr(self, "type_vars", {})
        try:
            if types.get("Masterball") and types["Masterball"].get():
                multiplier *= MASTERBALL_MULTIPLIER
            elif types.get("Pokeball") and types["Pokeball"].get():
                multiplier *= POKEBALL_MULTIPLIER

            return round(float(price) * multiplier, 2)
        except (TypeError, ValueError):
            return price

    def save_current_data(self):
        """Store the data for the currently displayed card without changing
        the index."""
        data = {k: v.get() for k, v in self.entries.items()}
        data["typ"] = ",".join(
            [name for name, var in self.type_vars.items() if var.get()]
        )
        data["rarity"] = ",".join([k for k, v in self.rarity_vars.items() if v.get()])
        key = f"{data['nazwa']}|{data['numer']}|{data['set']}"
        data["ilość"] = 1
        self.card_cache[key] = {
            "entries": {k: v for k, v in data.items()},
            "types": {name: var.get() for name, var in self.type_vars.items()},
            "rarities": {name: var.get() for name, var in self.rarity_vars.items()},
        }

        front_path = self.cards[self.index]
        front_file = os.path.basename(front_path)
        self.file_to_key[front_file] = key

        data["image1"] = f"{BASE_IMAGE_URL}/{self.folder_name}/{front_file}"
        if key not in self.product_code_map:
            self.product_code_map[key] = self.next_product_code
            self.next_product_code += 1
        data["product_code"] = self.product_code_map[key]
        data["warehouse_code"] = self.next_free_location()
        data["active"] = 1
        data["vat"] = "23%"
        data["unit"] = "szt."
        data["category"] = f"Karty Pokémon > {data['set']}"
        data["producer"] = "Pokémon"
        data["other_price"] = ""
        data["pkwiu"] = ""
        data["weight"] = 0.01
        data["priority"] = 0

        name = html.escape(data["nazwa"])
        number = html.escape(data["numer"])
        set_name = html.escape(data["set"])
        card_type = html.escape(data["typ"])
        condition = html.escape(data["stan"])

        data["short_description"] = (
            f"<p><strong>{name}</strong></p>"
            "<ul>"
            f"<li>Zestaw: {set_name}</li>"
            f"<li>Numer karty: {number}</li>"
            f"<li>Typ: {card_type}</li>"
            f"<li>Stan: {condition}</li>"
            "</ul>"
        )

        desc_paragraphs = [
            f"{name} – Pokémon TCG",
            f"Karta pochodzi z zestawu {set_name} i ma numer {number}. Typ karty: {card_type}. Stan: {condition}.",
            "Każda karta jest dokładnie sprawdzana przed wysyłką i odpowiednio zabezpieczana – trafia do Ciebie w idealnym stanie, gotowa do gry lub kolekcji.",
            "Zdjęcia przedstawiają rzeczywisty produkt lub jego odpowiednik. Jeśli szukasz więcej kart z tego setu – sprawdź pozostałe oferty.",
        ]
        data["description"] = "".join(f"<p>{p}</p>" for p in desc_paragraphs)

        data["stock_warnlevel"] = 0
        data["availability"] = 1
        data["delivery"] = SHOPER_DELIVERY_ID
        data["views"] = ""
        data["rank"] = ""
        data["rank_votes"] = ""

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

        self.output_data[self.index] = data

    def save_and_next(self):
        """Save the current card data and display the next scan."""
        self.save_current_data()
        self.index += 1
        self.show_card()

    def previous_card(self):
        """Save current data and display the previous scan."""
        if self.index <= 0:
            return
        self.save_current_data()
        self.index -= 1
        self.show_card()

    def next_card(self):
        """Save current data and move forward without increasing stock."""
        if self.index >= len(self.cards) - 1:
            return
        self.save_current_data()
        self.index += 1
        self.show_card()

    def remove_warehouse_code(self, code: str):
        """Remove a code and repack the affected column."""
        match = re.match(r"K(\d+)R(\d)P(\d+)", code or "")
        if not match:
            return
        box = int(match.group(1))
        column = int(match.group(2))
        for row in list(self.output_data):
            if not row:
                continue
            codes = [c.strip() for c in str(row.get("warehouse_code") or "").split(";") if c.strip()]
            if code in codes:
                codes.remove(code)
                if codes:
                    row["warehouse_code"] = ";".join(codes)
                else:
                    self.output_data.remove(row)
                break
        self.repack_column(box, column)

    def load_csv_data(self):
        """Load a CSV file and merge duplicate rows."""
        csv_utils.load_csv_data(self)

    def export_csv(self):
        csv_utils.export_csv(self)

    def upload_images_dialog(self):
        """Upload images from a selected directory via FTP."""
        directory = filedialog.askdirectory()
        if not directory:
            return
        host = simpledialog.askstring("FTP", "Serwer", initialvalue=FTP_HOST or "")
        user = simpledialog.askstring("FTP", "Użytkownik", initialvalue=FTP_USER or "")
        password = simpledialog.askstring("FTP", "Hasło", show="*", initialvalue=FTP_PASSWORD or "")
        if not host or not user or not password:
            messagebox.showerror("Błąd", "Nie podano pełnych danych logowania")
            return
        try:
            with FTPClient(host, user, password) as ftp:
                ftp.upload_directory(directory)
            messagebox.showinfo("Sukces", "Obrazy zostały wysłane na serwer FTP")
        except Exception as exc:
            messagebox.showerror("Błąd", f"Nie udało się wysłać obrazów: {exc}")

    def send_csv_to_shoper(self, file_path: str):
        """Send a CSV file using the Shoper API or FTP fallback."""
        csv_utils.send_csv_to_shoper(self, file_path)


