import os
import re
import csv
from tkinter import filedialog, messagebox
from ftp_client import FTPClient

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASSWORD = os.getenv("FTP_PASSWORD")
INVENTORY_CSV = os.getenv(
    "INVENTORY_CSV", os.getenv("WAREHOUSE_CSV", "magazyn.csv")
)
WAREHOUSE_CSV = os.getenv("WAREHOUSE_CSV", INVENTORY_CSV)

# column order for exported CSV files
STORE_FIELDNAMES = [
    "product_code",
    "name",
    "producer_code",
    "category",
    "producer",
    "short_description",
    "description",
    "price",
    "currency",
    "availability",
    "unit",
    "delivery",
    "stock",
    "active",
    "seo_title",
    "vat",
    "images 1",
]

WAREHOUSE_FIELDNAMES = ["name", "warehouse_code", "image"]


def format_store_row(row):
    """Return a row formatted for the store CSV."""
    formatted_name = row["nazwa"]

    return {
        "product_code": row["product_code"],
        "name": formatted_name,
        "producer_code": row.get("producer_code") or row.get("numer", ""),
        "category": row["category"],
        "producer": row["producer"],
        "short_description": row["short_description"],
        "description": row["description"],
        "price": row["cena"],
        "currency": row.get("currency", "PLN"),
        "availability": row.get("availability", 1),
        "unit": row.get("unit", "szt."),
        "delivery": "3 dni",
        "stock": row.get("stock", 1),
        "active": row.get("active", 1),
        "seo_title": row.get("seo_title", ""),
        "vat": row.get("vat", "23%"),
        "images 1": row.get("image1", row.get("images", "")),
    }


def format_warehouse_row(row):
    """Return a row formatted for the warehouse CSV."""
    name_parts = [row.get("nazwa"), row.get("numer")]
    formatted_name = " ".join(part for part in name_parts if part)

    return {
        "name": formatted_name,
        "warehouse_code": row.get("warehouse_code", ""),
        "image": row.get("image1", row.get("images", "")),
    }


def load_csv_data(app):
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

        def norm_header(name: str) -> str:
            normalized = name.strip().lower()
            if normalized == "images 1":
                return "image1"
            return normalized

        fieldnames = [norm_header(fn) for fn in reader.fieldnames or []]
        rows = []
        for raw_row in reader:
            row = {(norm_header(k) if k else k): v for k, v in raw_row.items()}
            if "warehouse_code" not in row and re.match(r"k\d+r\d+p\d+", str(row.get("product_code", "")).lower()):
                row["warehouse_code"] = row["product_code"]
                row["product_code"] = ""
                if "warehouse_code" not in fieldnames:
                    fieldnames.append("warehouse_code")
            rows.append(row)

    combined = {}
    qty_field = None
    qty_variants = {"stock", "ilość", "ilosc", "quantity", "qty"}

    for row in rows:
        img_val = row.get("image1") or row.get("images", "")
        row["image1"] = img_val
        row["images"] = img_val

        key = (
            f"{row.get('nazwa', '').strip()}|{row.get('numer', '').strip()}|{row.get('set', '').strip()}"
        )
        if qty_field is None:
            for variant in qty_variants:
                if variant in row:
                    qty_field = variant
                    break
        qty = 1
        if qty_field:
            try:
                qty = int(row.get(qty_field, 0))
            except ValueError:
                qty = 1

        warehouse = str(row.get("warehouse_code", "")).strip()

        if key in combined:
            combined[key]["qty"] += qty
            if warehouse:
                combined[key]["warehouses"].add(warehouse)
        else:
            new_row = row.copy()
            new_row["qty"] = qty
            new_row["warehouses"] = set()
            if warehouse:
                new_row["warehouses"].add(warehouse)
            combined[key] = new_row

    for row in combined.values():
        row["product_code"] = app.next_product_code
        app.next_product_code += 1

    if qty_field is None:
        qty_field = "ilość"
        if qty_field not in fieldnames:
            fieldnames.append(qty_field)

    if "image1" in fieldnames:
        fieldnames[fieldnames.index("image1")] = "images 1"

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
            row_out["warehouse_code"] = ";".join(sorted(row_out.pop("warehouses", [])))
            row_out["images 1"] = row_out.get("image1", row_out.get("images", ""))
            if qty_field != "stock":
                row_out.pop("stock", None)
            if qty_field != "ilość":
                row_out.pop("ilość", None)
            writer.writerow({k: row_out.get(k, "") for k in fieldnames})

    messagebox.showinfo("Sukces", "Plik CSV został scalony i zapisany.")


def export_csv(app):
    """Export collected data to a CSV file."""
    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
    )
    if not file_path:
        return

    combined = {}
    for row in app.output_data:
        if row is None:
            continue
        key = f"{row['nazwa']}|{row['numer']}|{row['set']}"
        if key in combined:
            combined[key]["stock"] += 1
        else:
            combined[key] = row.copy()
            combined[key]["stock"] = 1

    fieldnames = STORE_FIELDNAMES

    with open(file_path, mode="w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in combined.values():
            writer.writerow(format_store_row(row))
    append_warehouse_csv(app)
    messagebox.showinfo("Sukces", "Plik CSV został zapisany.")
    if messagebox.askyesno("Wysyłka", "Czy wysłać plik do Shoper?"):
        send_csv_to_shoper(app, file_path)
    app.back_to_welcome()


def append_warehouse_csv(app, path: str = WAREHOUSE_CSV):
    """Append all collected rows to the warehouse CSV."""
    fieldnames = WAREHOUSE_FIELDNAMES

    file_exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        if not file_exists:
            writer.writeheader()
        for row in app.output_data:
            if row is None:
                continue
            writer.writerow(format_warehouse_row(row))


def send_csv_to_shoper(app, file_path: str):
    """Send a CSV file using the Shoper API or FTP fallback."""
    try:
        if getattr(app, "shoper_client", None):
            result = app.shoper_client.import_csv(file_path)
            status = result.get("status", "ok")
            messagebox.showinfo("Sukces", f"Import zakończony: {status}")
        else:
            with FTPClient(app.FTP_HOST, app.FTP_USER, app.FTP_PASSWORD) as ftp:
                ftp.upload_file(file_path)
            messagebox.showinfo("Sukces", "Plik CSV został wysłany.")
    except Exception as exc:  # pragma: no cover - network failure
        messagebox.showerror("Błąd", f"Nie udało się wysłać pliku: {exc}")

