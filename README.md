![Kartoteka banner](banner22.png)
# Kartoteka

## Overview
Kartoteka is a lightweight Tkinter app for organizing Pokémon card scans and exporting pricing data to CSV.

## Running the App
With dependencies installed, launch the interface:

```bash
python main.py
```

## Card Identifier Format and CSV Export
Cards are identified with the pattern `PKM-<SET>-<NR>-<VARIANT>`:

* `SET` – the set code, e.g. `BS` for Base Set.
* `NR` – the card number within that set.
* `VARIANT` – optional variant flag such as `H` (holofoil) or `R` (reverse).

Examples:

* `PKM-BS-1-H`
* `PKM-BS-1-R`

When exporting, the application creates a single consolidated CSV file. Entries with the same card code are merged so duplicates appear only once.
