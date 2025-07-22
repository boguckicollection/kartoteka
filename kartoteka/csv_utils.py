import os
import re
import csv
from tkinter import filedialog, messagebox
from ftp_client import FTPClient

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASSWORD = os.getenv("FTP_PASSWORD")


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
        map_key = (
            f"{row.get('nazwa', '').strip()}|{row.get('numer', '').strip()}|{row.get('set', '').strip()}"
        )
        code_str = str(row.get("product_code", "")).strip()
        if map_key not in app.product_code_map:
            if code_str.isdigit():
                code_int = int(code_str)
                app.product_code_map[map_key] = code_int
                if code_int >= app.next_product_code:
                    app.next_product_code = code_int + 1
            else:
                app.product_code_map[map_key] = app.next_product_code
                app.next_product_code += 1
        row["product_code"] = app.product_code_map[map_key]

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
        "views",
        "rank",
        "rank_votes",
        "images 1",
    ]
    fieldnames.append("warehouse_code")

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
                    "active": row.get("active", 1),
                    "name": formatted_name,
                    "price": row["cena"],
                    "vat": row.get("vat", "23%"),
                    "unit": row.get("unit", "szt."),
                    "category": row["category"],
                    "producer": row["producer"],
                    "other_price": row.get("other_price", ""),
                    "pkwiu": row.get("pkwiu", ""),
                    "weight": row.get("weight", 0.01),
                    "priority": row.get("priority", 0),
                    "short_description": row["short_description"],
                    "description": row["description"],
                    "stock": row["stock"],
                    "stock_warnlevel": row.get("stock_warnlevel", 0),
                    "availability": row.get("availability", 1),
                    "views": row.get("views", ""),
                    "rank": row.get("rank", ""),
                    "rank_votes": row.get("rank_votes", ""),
                    "images 1": row.get("image1", row.get("images", "")),
                    "warehouse_code": row.get("warehouse_code", ""),
                }
            )
    messagebox.showinfo("Sukces", "Plik CSV został zapisany.")
    if messagebox.askyesno("Wysyłka", "Czy wysłać plik do Shoper?"):
        send_csv_to_shoper(app, file_path)
    app.back_to_welcome()


def send_csv_to_shoper(app, file_path: str):
    """Send a CSV file using the Shoper API or FTP fallback."""
    try:
        if getattr(app, "shoper_client", None):
            app.shoper_client.import_csv(file_path)
        else:
            with FTPClient(app.FTP_HOST, app.FTP_USER, app.FTP_PASSWORD) as ftp:
                ftp.upload_file(file_path)
        messagebox.showinfo("Sukces", "Plik CSV został wysłany.")
    except Exception as exc:  # pragma: no cover - network failure
        messagebox.showerror("Błąd", f"Nie udało się wysłać pliku: {exc}")

