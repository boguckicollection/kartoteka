import os
import json
import requests

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
            data = res.json().get("data", res.json())
            images = data.get("images") or {}
            logo_url = images.get("logo") or images.get("logoUrl") or images.get("logo_url")
            if not logo_url:
                print(f"[WARN] No logo for {name}")
                continue
            img_res = requests.get(logo_url, timeout=10)
            if img_res.status_code == 200:
                ext = os.path.splitext(logo_url)[1] or ".png"
                safe_name = code.replace("/", "_")
                path = os.path.join(LOGO_DIR, f"{safe_name}{ext}")
                with open(path, "wb") as out:
                    out.write(img_res.content)
                print(f"Saved {path}")
            else:
                print(f"[ERROR] Failed to download logo for {name}")
        except requests.RequestException as e:
            print(f"[ERROR] {name}: {e}")

