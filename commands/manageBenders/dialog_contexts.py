"""Context dataclasses for bender/die edit dialogs.

These dataclasses pass context (existing values, IDs) to the dialog commands
and define the structure of data returned from dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EditBenderContext:
    """Context for editing a bender via form dialog.

    Attributes:
        bender_id: ID of bender being edited, or None if adding new
        current_name: Pre-populated name value
        current_min_grip: Pre-populated min grip in cm (internal units)
        current_notes: Pre-populated notes
    """

    bender_id: str | None
    current_name: str
    current_min_grip: float
    current_notes: str


@dataclass(slots=True)
class EditDieContext:
    """Context for editing a die via form dialog.

    Attributes:
        bender_id: Parent bender ID (always required)
        die_id: ID of die being edited, or None if adding new
        current_name: Pre-populated name value
        current_tube_od: Pre-populated tube OD in cm (internal units)
        current_clr: Pre-populated CLR in cm (internal units)
        current_offset: Pre-populated die offset in cm (internal units)
        current_min_tail: Pre-populated min tail in cm (internal units)
        current_notes: Pre-populated notes
    """

    bender_id: str
    die_id: str | None
    current_name: str
    current_tube_od: float
    current_clr: float
    current_offset: float
    current_min_tail: float
    current_notes: str
