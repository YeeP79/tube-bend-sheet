"""Context dataclasses for material/compensation edit dialogs.

These dataclasses pass context (existing values, IDs) to the dialog commands
and define the structure of data returned from dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EditMaterialContext:
    """Context for editing a material via form dialog.

    Attributes:
        material_id: ID of material being edited, or None if adding new
        current_name: Pre-populated name value
        current_tube_od: Pre-populated tube OD in cm (internal units)
        current_batch: Pre-populated batch number
        current_notes: Pre-populated notes
    """

    material_id: str | None
    current_name: str
    current_tube_od: float
    current_batch: str
    current_notes: str


@dataclass(slots=True)
class EditCompensationContext:
    """Context for managing compensation data via dialog.

    Attributes:
        die_id: ID of the die
        die_name: Display name of the die
        material_id: ID of the material
        material_name: Display name of the material
    """

    die_id: str
    die_name: str
    material_id: str
    material_name: str
