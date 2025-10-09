"""Shared configuration for storage boxes.

This module centralizes storage-related constants used by both the backend
and UI.  Adjust the values here to match the physical warehouse layout and
all modules will pick up the changes automatically.
"""

from __future__ import annotations

# Basic box layout -----------------------------------------------------------

# Number of regularly sized boxes available.
BOX_COUNT = 10

# Regular boxes have four columns and each column can hold ``BOX_COLUMN_CAPACITY``
# cards.  Adjust these numbers to match the real storage boxes.
STANDARD_BOX_COLUMNS = 4
BOX_COLUMN_CAPACITY = 1000

# Total capacity for a standard box.
STANDARD_BOX_CAPACITY = STANDARD_BOX_COLUMNS * BOX_COLUMN_CAPACITY

# Special overflow box -------------------------------------------------------

# Identifier of the overflow box.  It differs in layout from the regular ones
# and typically has reduced capacity.
SPECIAL_BOX_NUMBER = 100
SPECIAL_BOX_COLUMNS = 2
SPECIAL_BOX_CAPACITY = 2000

# Derived mappings -----------------------------------------------------------

# Mapping of ``box -> total capacity``.  Regular boxes use
# ``STANDARD_BOX_CAPACITY`` while the overflow box has
# ``SPECIAL_BOX_CAPACITY``.
BOX_CAPACITY: dict[int, int] = {
    **{b: STANDARD_BOX_CAPACITY for b in range(1, BOX_COUNT + 1)},
    SPECIAL_BOX_NUMBER: SPECIAL_BOX_CAPACITY,
}

# Mapping of ``box -> column count``.  Regular boxes share the same column
# layout while the overflow box has its own.
BOX_COLUMNS: dict[int, int] = {
    **{b: STANDARD_BOX_COLUMNS for b in range(1, BOX_COUNT + 1)},
    SPECIAL_BOX_NUMBER: SPECIAL_BOX_COLUMNS,
}
