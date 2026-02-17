"""Context dataclasses for tube/compensation edit dialogs.

These dataclasses pass context (existing values, IDs) to the dialog commands
and define the structure of data returned from dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EditTubeContext:
    """Context for editing a tube via form dialog.

    Attributes:
        tube_id: ID of tube being edited, or None if adding new
        current_name: Pre-populated name value
        current_tube_od: Pre-populated tube OD in cm (internal units)
        current_wall_thickness: Pre-populated wall thickness in cm
        current_material_type: Pre-populated material type
        current_batch: Pre-populated batch number
        current_notes: Pre-populated notes
    """

    tube_id: str | None
    current_name: str
    current_tube_od: float
    current_wall_thickness: float
    current_material_type: str
    current_batch: str
    current_notes: str


@dataclass(slots=True)
class EditCompensationContext:
    """Context for managing compensation data via dialog.

    Attributes:
        die_id: ID of the die
        die_name: Display name of the die
        material_id: ID of the tube
        material_name: Display name of the tube
    """

    die_id: str
    die_name: str
    material_id: str
    material_name: str
