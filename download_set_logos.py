import os
import json
import re
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

    for era_sets in sets.values():
        for item in era_sets:
            name = item["name"]
            code = item["code"]
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
                    safe_name = code.replace("/", "_")
                    path = os.path.join(LOGO_DIR, f"{safe_name}{ext}")
                    with open(path, "wb") as out:
                        out.write(res.content)
                    print(f"Saved {path}")
                else:
                    if res.status_code == 404:
                        print(f"[WARN] Symbol not found for {name}: {symbol_url}")
                    else:
                        print(
                            f"[ERROR] Failed to download symbol for {name} from {symbol_url}: {res.status_code}"
                        )
            except requests.RequestException as e:
                print(f"[ERROR] {name}: {e}")

