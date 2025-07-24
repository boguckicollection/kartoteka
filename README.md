# Kartoteka

## Overview
A small tkinter application for organizing Pokémon card scans and exporting data to CSV.

## Features
- Load images from a folder and review them one by one
- Fetch card prices from a local database (`card_prices.csv`)
- Automatically query the TCGGO API when a price is missing
- Display card images when available, falling back to `image`, `imageUrl` or `image_url` if `images.large` is not provided
- Prices for "Holo" or "Reverse" variants are calculated by multiplying the base price by **3.5**
- View alternative API results via the **Inne warianty** button
- Convert API prices from EUR to PLN using a 1.23 multiplier rounded to two decimals
- Save collected data to a CSV file
- Autocomplete set selection (press <kbd>Tab</kbd> to accept a suggestion) and additional rarity checkboxes
- Toggle the **Reverse** switch on the pricing screen when pricing a reverse card
- Import CSV files and merge duplicates automatically
- Automatically updates the list of card sets and downloads new logos on startup

## Requirements
Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

If your version of `ttkbootstrap` is 1.10 or newer, the buttons will display built-in icons. On older versions the icons are skipped automatically.

Ensure a `card_prices.csv` file with columns `name`, `number`, `set` and `price` exists in the project directory.

## Configuration (.env variables)
Create a `.env` file with API credentials and optional FTP settings:

```bash
RAPIDAPI_KEY=your-key-here
RAPIDAPI_HOST=pokemon-tcg-api.p.rapidapi.com
SHOPER_API_URL=https://your-store.shop/webapi/rest
SHOPER_API_TOKEN=your-token
SHOPER_DELIVERY_ID=1
FTP_HOST=example.com
FTP_USER=username
FTP_PASSWORD=secret
```

The `RAPIDAPI_*` variables are used when a card price is not found in the local database. `SHOPER_API_URL` and `SHOPER_API_TOKEN` configure access to your Shoper store for the **Porządkuj** window. The application expects the `/webapi/rest` endpoint and will append it automatically if it is missing. `SHOPER_DELIVERY_ID` sets the default shipping method id for exported CSV files. `FTP_HOST`, `FTP_USER` and `FTP_PASSWORD` configure optional FTP uploads.

## Running the App
Execute the main script with Python 3:

```bash
python main.py
```

The interface will allow you to load scans, fetch prices from the local database
or the API, and export results to CSV.  Use the **Skanuj** button to reveal a
panel for entering the starting box, column and position.  After clicking
**Dalej** and selecting a folder of images the application loads the scans
starting from the specified location.

## Running Tests
The automated tests are written with `pytest` and mock out all GUI components,
so they can run headlessly.

Install the dependencies and execute the suite with:

```bash
pip install -r requirements.txt
pytest
```

### Cheatsheet
Press the **Ściąga** button on the editor window to open a scrollable cheat sheet with the names and codes of all card sets. When set symbols are available they are displayed alongside the entries.

The application now fetches missing set symbols automatically on startup. If you need to refresh them manually run:

```bash
python download_set_logos.py
```

This creates a `set_logos/` directory that should stay next to `main.py` so the cheatsheet can load the images.

### Importing CSV files
Use the **Import CSV** button on the welcome screen to merge an existing CSV file. Rows that share the `nazwa`, `numer` and `set` columns are combined and their quantity summed. The importer recognises quantity columns named `stock`, `ilość`, `ilosc`, `quantity` or `qty` (case and spacing are ignored). If no such column is found, the merged output adds an `ilość` column with the calculated totals. The importer accepts both `image1` and the legacy `images 1` column when loading existing files. All unique `warehouse_code` values from the merged rows are preserved and joined with semicolons so you can still locate every individual card after deduplication.

### Cache
Every time you press **Zapisz i dalej**, the entered values are stored in a temporary cache under a key composed of `name|number|set`. When another scan of the same card is loaded, the application pre-fills the form with the cached data so you do not need to type them again.

### Shoper integration
Use the **Porządkuj** button to open a window with actions against your Shoper store. The interface now lets you search products by name or card number, apply sorting options and view new orders. Each order item is matched with the `warehouse_code` so you can quickly locate it in storage. Every card is assigned its own `warehouse_code` while the per-product `product_code` stays the same for duplicates. Make sure the Shoper credentials are set in `.env` before launching the application.

### Dashboard
The welcome screen displays a small dashboard with store statistics fetched from your Shoper account: counts of new orders, pending shipments or payments and recent sales totals. To populate these fields the token must have permissions to read orders and statistics. Use the **Pokaż szczegóły** button to open the Shoper window with full functionality.

### CSV and image upload
After exporting a CSV file the application prompts to send it directly to Shoper. When Shoper API credentials are configured the file is uploaded via the REST API. If not, the exporter falls back to FTP using the credentials from `.env`. The exported CSV includes `images 1` and `warehouse_code` columns with the remote image path and storage location. Use the **FTP Obrazy** button on the welcome screen to upload a folder of images to the configured FTP server.

## License
This project is licensed under the terms of the [MIT License](LICENSE).
