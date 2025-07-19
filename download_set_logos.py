import os
import json
import requests
from urllib.parse import urlparse

SET_FILES = ["tcg_sets.json", "tcg_sets_jp.json"]
LOGO_DIR = "set_logos"

os.makedirs(LOGO_DIR, exist_ok=True)

for file in SET_FILES:
    try:
        with open(file, encoding="utf-8") as f:
            sets = json.load(f)
    except FileNotFoundError:
        print(f"[WARN] Missing {file}")
        continue

    for name, code in sets.items():
        url = f"https://api.pokemontcg.io/v2/sets/{code}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                print(f"[ERROR] Failed to fetch {name}: {res.status_code}")
                continue
            json_data = res.json()
            data = json_data.get("data", json_data)
            images = data.get("images") or {}
            symbol_url = (
                images.get("symbol")
                or images.get("symbolUrl")
                or images.get("symbol_url")
            )
            if not symbol_url:
                print(f"[WARN] No symbol for {name}")
                continue
            img_res = requests.get(symbol_url, timeout=10)
            if img_res.status_code == 200:
                parsed_path = urlparse(symbol_url).path
                ext = os.path.splitext(parsed_path)[1] or ".png"
                safe_name = code.replace("/", "_")
                path = os.path.join(LOGO_DIR, f"{safe_name}{ext}")
                with open(path, "wb") as out:
                    out.write(img_res.content)
                print(f"Saved {path}")
            else:
                if img_res.status_code == 404:
                    print(f"[WARN] Symbol not found for {name}: {symbol_url}")
                else:
                    print(
                        f"[ERROR] Failed to download symbol for {name} from {symbol_url}: {img_res.status_code}"
                    )
        except requests.RequestException as e:
            print(f"[ERROR] {name}: {e}")

