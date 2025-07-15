# Kartoteka

A small tkinter application for organizing Pokémon card scans and exporting data to CSV.

## Features
- Load images from a folder and review them one by one
- Fetch card prices from a local database (`card_prices.csv`)
- Automatically query the TCGGO API when a price is missing
- Display card images when available, falling back to `image`,
  `imageUrl` or `image_url` if `images.large` is not provided
- Prices for "Holo" or "Reverse" variants are calculated by multiplying the
  base price by **3.5**
- View alternative API results via the **Inne warianty** button
- Convert API prices from EUR to PLN using a 1.23 multiplier rounded to two decimals
- Save collected data to a CSV file
- Autocomplete set selection (press <kbd>Tab</kbd> to accept a suggestion) and additional rarity checkboxes
- Toggle the **Reverse** switch on the pricing screen when pricing a reverse card

## Requirements
Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

If your version of `ttkbootstrap` is 1.10 or newer, the buttons will display
built-in icons. On older versions the icons are skipped automatically.

Ensure a `card_prices.csv` file with columns `name`, `number`, `set` and `price` exists in the project directory.

Create a `.env` file with API credentials:

```bash
RAPIDAPI_KEY=your-key-here
RAPIDAPI_HOST=pokemon-tcg-api.p.rapidapi.com
SHOPER_API_URL=https://your-store.shop/webapi/rest
SHOPER_API_TOKEN=your-token
```

The `RAPIDAPI_*` variables are used when a card price is not found in the local
database. `SHOPER_API_URL` and `SHOPER_API_TOKEN` configure access to your Shoper
store for the **Porządkuj** window. The application expects the `/webapi/rest`
endpoint and will append it automatically if it is missing.


## Running
Execute the main script with Python 3:

```bash
python main.py
```

The interface will allow you to load scans, fetch prices from the local database
or the API, and export results to CSV.

### Cache
Every time you press **Zapisz i dalej**, the entered values are stored in a
temporary cache under a key composed of `name|number|set`. When another scan of
the same card is loaded, the application pre-fills the form with the cached
data so you do not need to type them again.

### Shoper integration
Use the **Porządkuj** button to open a window with basic actions against your
Shoper store. You can list uploaded scans, send product data and check current
inventory. Make sure the Shoper credentials are set in `.env` before launching
the application.
