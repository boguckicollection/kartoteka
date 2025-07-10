# Kartoteka

A small tkinter application for organizing Pokémon card scans and exporting data to CSV.

## Features
- Load images from a folder and review them one by one
- Fetch card prices from a local database (`card_prices.csv`)
- Automatically query the TCGGO API when a price is missing
- Prices for "Holo" or "Reverse" variants are calculated by multiplying the
  base price by **3.5**
- View alternative API results via the **Inne warianty** button
- Convert API prices from EUR to PLN using a 1.23 multiplier rounded to two decimals
- Save collected data to a CSV file
- Autocomplete set selection (press <kbd>Tab</kbd> to accept a suggestion) and additional rarity checkboxes

## Requirements
Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

If your version of `ttkbootstrap` is 1.10 or newer, the buttons will display
built-in icons. On older versions the icons are skipped automatically.

Ensure a `card_prices.csv` file with columns `name`, `number`, `set` and `price` exists in the project directory.

Create a `.env` file with your RapidAPI credentials:

```bash
RAPIDAPI_KEY=your-key-here
RAPIDAPI_HOST=pokemon-tcg-api.p.rapidapi.com
```

These credentials are used when a card price is not found in the local
database. A valid `RAPIDAPI_KEY` allows the application to query the API
and fill in the missing price automatically.


## Running
Execute the main script with Python 3:

```bash
python main.py
```

The interface will allow you to load scans, fetch prices from the local database
or the API, and export results to CSV.
