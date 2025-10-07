![Kartoteka banner](banner22.png)
# Kartoteka

## Overview
Kartoteka is a lightweight Tkinter app for organizing Pokémon card scans and exporting pricing data to CSV.

## Python Compatibility
Kartoteka supports Python 3.9 through 3.13. The default requirements use `Pillow>=10.4`, which ships pre-built wheels for Python 3.13.

If you must stay on an older Python release that cannot install Pillow 10.4 or later, pin `Pillow<10.4` in `requirements.txt` and use a compatible Python version (for example, Python 3.12).

## Running the App
With dependencies installed, launch the interface:

```bash
python main.py
```

## Set validation

OpenAI responses normally validate set and era names against a built-in list.
To allow unrecognised values and rely on internal mapping instead, disable
strict validation:

```bash
STRICT_SET_VALIDATION=0 python main.py
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

## Storage configuration

Box layout and capacities are centralised in `kartoteka/storage_config.py`.
The module defines shared constants such as the number of regular boxes
(`BOX_COUNT`), column counts (`STANDARD_BOX_COLUMNS`), per-column capacity
(`BOX_COLUMN_CAPACITY`), total capacity of each box (`BOX_CAPACITY`), and
details for the overflow box (`SPECIAL_BOX_NUMBER`, `SPECIAL_BOX_CAPACITY`).
Both `storage.py` and `ui.py` import these values so any changes to the
physical warehouse setup only need to be made in a single place.

## Inspecting Shoper order statuses

To verify what the Shoper API returns without any GUI filters, export your
credentials and run the helper script:

```bash
export SHOPER_API_URL="https://twoj-sklep"
export SHOPER_API_TOKEN="sekretny-token"
python inspect_shoper_orders.py --per-page 5
```

The output lists each order with the textual status and the numeric
`status.type` value used by the API. You can pass additional filters via the
`--filter` option, for example
`--filter filters[status.type]=2` to restrict the query to a specific type. Use
`--raw` if you prefer the unmodified JSON response.
