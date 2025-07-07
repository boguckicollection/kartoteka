# Kartoteka

A small tkinter application for organizing Pokémon card scans and exporting data to CSV.

## Features
- Load images from a folder and review them one by one
- Fetch card prices from a local database (`card_prices.csv`)
- Save collected data to a CSV file

## Requirements
Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

Ensure a `card_prices.csv` file with columns `name`, `number`, `set` and `price` exists in the project directory.


## Running
Execute the main script with Python 3:

```bash
python main.py
```

The interface will allow you to load scans, fetch prices from the local database and export results to CSV.
