import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from ttkbootstrap import Style
from PIL import Image, ImageTk
import os
import csv
import json
import requests
import re
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

BASE_IMAGE_URL = "https://sklep839679.shoparena.pl/upload/images"

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

PRICE_DB_PATH = "card_prices.csv"
PRICE_MULTIPLIER = 1.23

# Wczytanie danych setów
with open("tcg_sets.json", encoding="utf-8") as f:
    tcg_sets_eng = list(json.load(f).keys())

with open("tcg_sets_jp.json", encoding="utf-8") as f:
    tcg_sets_jp = list(json.load(f).keys())

class CardEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Edytor Kart Pokémon")
        self.index = 0
        self.cards = []
        self.image_objects = []
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.price_db = self.load_price_db()
        self.folder_name = ""
        self.folder_path = ""

        self.setup_ui()

    def setup_ui(self):
        self.frame = tk.Frame(self.root)
        self.frame.pack(padx=10, pady=10)

        self.load_button = ttk.Button(self.frame, text="Załaduj folder skanów", command=self.load_images)
        self.load_button.grid(row=0, column=0, columnspan=3, pady=5)

        self.end_button = ttk.Button(self.frame, text="Zakończ i zapisz CSV", command=self.export_csv)
        self.end_button.grid(row=0, column=3, columnspan=2, pady=5)

        self.image_label = tk.Label(self.frame)
        self.image_label.grid(row=1, column=0, rowspan=12)

        self.entries = {}

        tk.Label(self.frame, text="Język").grid(row=1, column=1, sticky='w')
        self.lang_var = tk.StringVar(value="ENG")
        self.entries['język'] = self.lang_var
        lang_dropdown = ttk.Combobox(self.frame, textvariable=self.lang_var, values=["ENG", "JP"])
        lang_dropdown.grid(row=1, column=2)
        lang_dropdown.bind("<<ComboboxSelected>>", self.update_set_options)
 

        tk.Label(self.frame, text="Nazwa").grid(row=2, column=1, sticky='w')
        self.entries['nazwa'] = tk.Entry(self.frame)
        self.entries['nazwa'].grid(row=2, column=2)

        tk.Label(self.frame, text="Numer").grid(row=3, column=1, sticky='w')
        self.entries['numer'] = tk.Entry(self.frame)
        self.entries['numer'].grid(row=3, column=2)

        tk.Label(self.frame, text="Set").grid(row=4, column=1, sticky='w')
        self.set_var = tk.StringVar()
        self.set_dropdown = ttk.Combobox(self.frame, textvariable=self.set_var)
        self.set_dropdown.grid(row=4, column=2)
        self.set_dropdown.bind('<KeyRelease>', self.filter_sets)
        self.entries['set'] = self.set_var

        tk.Label(self.frame, text="Typ").grid(row=5, column=1, sticky='w')
        self.type_var = tk.StringVar(value="")
        self.entries['typ'] = self.type_var
        typy = ["", "Common", "Holo", "Reverse"]
        typ_dropdown = ttk.Combobox(self.frame, textvariable=self.type_var, values=typy, state="readonly")
        typ_dropdown.grid(row=5, column=2, columnspan=3)

        tk.Label(self.frame, text="Rarity").grid(row=6, column=1, sticky='w')
        self.rarity_vars = {}
        rarities = ["RR", "AR", "SR", "SAR", "UR", "ACE", "PROMO"]
        for i, r in enumerate(rarities):
            var = tk.BooleanVar()
            self.rarity_vars[r] = var
            tk.Checkbutton(self.frame, text=r, variable=var).grid(row=6, column=2+i, padx=5)

        tk.Label(self.frame, text="Suffix").grid(row=7, column=1, sticky='w')
        self.suffix_var = tk.StringVar(value="")
        self.entries['suffix'] = self.suffix_var
        suffix_dropdown = ttk.Combobox(self.frame, textvariable=self.suffix_var, values=["", "EX", "GX", "V", "VMAX", "VSTAR", "Shiny", "Promo"])
        suffix_dropdown.grid(row=7, column=2)

        tk.Label(self.frame, text="Stan").grid(row=8, column=1, sticky='w')
        self.stan_var = tk.StringVar(value="NM")
        self.entries['stan'] = self.stan_var
        stan_dropdown = ttk.Combobox(self.frame, textvariable=self.stan_var, values=["NM", "LP", "PL", "MP", "HP", "DMG"])
        stan_dropdown.grid(row=8, column=2)

        tk.Label(self.frame, text="Cena").grid(row=9, column=1, sticky='w')
        self.entries['cena'] = tk.Entry(self.frame)
        self.entries['cena'].grid(row=9, column=2)

        self.api_button = ttk.Button(self.frame, text="Pobierz cenę z bazy", command=self.fetch_card_data)
        self.api_button.grid(row=10, column=1, columnspan=2, pady=5)

        self.save_button = ttk.Button(self.frame, text="Zapisz i dalej", command=self.save_and_next)
        self.save_button.grid(row=11, column=1, columnspan=2, pady=5)

        for entry in self.entries.values():
            if isinstance(entry, tk.Entry):
                entry.bind("<Return>", lambda e: self.save_and_next())

        self.root.bind("<Return>", lambda e: self.save_and_next())
        self.update_set_options()

    def update_set_options(self, event=None):
        lang = self.lang_var.get().strip().upper()
        if lang == "JP":
            self.set_dropdown['values'] = sorted(tcg_sets_jp)
        else:
            self.set_dropdown['values'] = sorted(tcg_sets_eng)

    def filter_sets(self, event=None):
        typed = self.set_var.get().lower()
        lang = self.lang_var.get().strip().upper()
        all_sets = tcg_sets_jp if lang == "JP" else tcg_sets_eng
        if typed:
            filtered = [s for s in all_sets if typed in s.lower()]
        else:
            filtered = all_sets
        self.set_dropdown['values'] = sorted(filtered)
        self.set_dropdown.event_generate("<Down>")

    def load_images(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.folder_path = folder
        self.folder_name = os.path.basename(folder)
        self.cards = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.png'))]
        self.cards.sort()
        self.index = 0
        self.output_data = []
        self.card_counts = defaultdict(int)
        self.show_card()

    def show_card(self):
        if self.index >= len(self.cards):
            messagebox.showinfo("Koniec", "Wszystkie karty zostały zapisane.")
            self.export_csv()
            return

        image_path = self.cards[self.index]
        image = Image.open(image_path)
        image.thumbnail((400, 560))
        img = ImageTk.PhotoImage(image)
        self.image_objects.append(img)
        self.image_label.configure(image=img)

        for key, entry in self.entries.items():
            if isinstance(entry, tk.Entry):
                entry.delete(0, tk.END)
            elif isinstance(entry, tk.StringVar):
                if key == 'język':
                    entry.set('ENG')
                elif key == 'stan':
                    entry.set('NM')
                else:
                    entry.set('')
            elif isinstance(entry, tk.BooleanVar):
                entry.set(False)

        for var in self.rarity_vars.values():
            var.set(False)

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

    def fetch_card_price(self, name, number, set_name):
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
                price_eur = best.get("prices", {}).get("cardmarket", {}).get("30d_average", 0)
                if price_eur:
                    eur_pln = self.get_exchange_rate()
                    price_pln = round(float(price_eur) * eur_pln * PRICE_MULTIPLIER)
                    print(f"[INFO] Cena {best.get('name')} ({number_input}, {set_input}) = {price_pln} PLN")
                    return price_pln

            print("\n[DEBUG] Nie znaleziono dokładnej karty. Zbliżone:")
            for card in cards:
                card_number = str(card.get("card_number", "")).lower()
                card_set = str(card.get("episode", {}).get("name", "")).lower()
                if number_input == card_number and set_input in card_set:
                    print(f"- {card.get('name')} | {card_number} | {card.get('episode', {}).get('name')}")

        except requests.Timeout:
            print("[ERROR] Request timed out")
        except Exception as e:
            print(f"[ERROR] Fetching price from TCGGO failed: {e}")
        return None




    def fetch_card_data(self):
        name = self.entries['nazwa'].get()
        number = self.entries['numer'].get()
        set_name = self.entries['set'].get()

        cena = self.get_price_from_db(name, number, set_name)
        if cena is not None:
            self.entries['cena'].delete(0, tk.END)
            self.entries['cena'].insert(0, str(cena))
        else:
            fetched = self.fetch_card_price(name, number, set_name)
            if fetched is not None:
                self.entries['cena'].delete(0, tk.END)
                self.entries['cena'].insert(0, str(fetched))
            else:
                messagebox.showinfo(
                    "Brak wyników",
                    "Nie znaleziono ceny dla podanej karty w bazie danych.",
                )


    def get_exchange_rate(self):
        try:
            res = requests.get(
                "https://api.nbp.pl/api/exchangerates/rates/A/EUR/?format=json",
                timeout=10,
            )
            if res.status_code == 200:
                return res.json()['rates'][0]['mid']
        except requests.Timeout:
            print("[ERROR] Exchange rate request timed out")
        except Exception:
            pass
        return 4.5

    def save_and_next(self):
        data = {k: v.get() for k, v in self.entries.items()}
        data['rarity'] = ",".join([k for k, v in self.rarity_vars.items() if v.get()])
        key = f"{data['nazwa']}|{data['numer']}|{data['set']}"
        self.card_counts[key] += 1
        data['ilość'] = self.card_counts[key]
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
        data["description"] = f"{data['nazwa']} karta Pokémon z setu {data['set']}, nr {data['numer']}, stan {data['stan']}."
        data["stock_warnlevel"] = 0
        data["availability"] = 1
        data["delivery"] = 1
        data["views"] = ""
        data["rank"] = ""
        data["rank_votes"] = ""

        # Automatyczne pobranie ceny z bazy
        cena_local = self.get_price_from_db(data['nazwa'], data['numer'], data['set'])
        if cena_local is not None:
            data["cena"] = str(cena_local)
        else:
            fetched = self.fetch_card_price(data['nazwa'], data['numer'], data['set'])
            if fetched is not None:
                data["cena"] = str(fetched)
            else:
                data["cena"] = ""

        self.output_data.append(data)
        self.index += 1
        self.show_card()

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return

        combined = {}
        for row in self.output_data:
            key = f"{row['nazwa']}|{row['numer']}|{row['set']}"
            if key in combined:
                combined[key]['stock'] += 1
            else:
                combined[key] = row.copy()
                combined[key]['stock'] = 1

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

if __name__ == "__main__":
    style = Style("flatly")
    app = CardEditorApp(style.master)
    style.master.mainloop()
