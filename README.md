# Kartoteka

A small tkinter application for organizing Pokémon card scans and exporting data to CSV.

## Features
- Load images from a folder and review them one by one
- Fetch card prices from [TCGGO](https://www.tcggo.com/) API
- Save collected data to a CSV file

## Requirements
Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

The application also reads API credentials from a `.env` file:

```
RAPIDAPI_KEY=<your RapidAPI key>
RAPIDAPI_HOST=pokemon-tcg-api.p.rapidapi.com
```

## Running
Execute the main script with Python 3:

```bash
python main.py
```

The interface will allow you to load scans, fetch prices and export results to CSV.
