"""Material model for tube bending compensation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class MaterialDict(TypedDict):
    """Type definition for Material serialization."""

    id: str
    name: str
    tube_od: float
    batch: str
    notes: str


def validate_material_values(
    tube_od: float | None = None,
) -> None:
    """Validate material numeric values.

    Args:
        tube_od: Tube outer diameter (must be positive if provided)

    Raises:
        ValueError: If any value violates its constraint
    """
    if tube_od is not None and tube_od <= 0:
        raise ValueError(f"tube_od must be positive, got {tube_od}")


@dataclass(slots=True)
class Material:
    """
    Represents a tube material for bender compensation tracking.

    Materials are used to track bender compensation data for specific
    die-material combinations. Different materials and batches may
    exhibit different compensation characteristics.

    Attributes:
        id: Unique identifier for the material
        name: Display name (e.g., "DOM 1020", "4130 Chromoly")
        tube_od: Tube outer diameter this material is for (in cm)
        batch: Optional batch/lot number for tracking
        notes: Optional notes about the material
    """

    id: str
    name: str
    tube_od: float
    batch: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        """Validate numeric fields are positive."""
        validate_material_values(tube_od=self.tube_od)

    def __repr__(self) -> str:
        return f"Material(name={self.name!r}, tube_od={self.tube_od})"

    def to_dict(self) -> MaterialDict:
        """Convert to dictionary for JSON serialization."""
        return MaterialDict(
            id=self.id,
            name=self.name,
            tube_od=self.tube_od,
            batch=self.batch,
            notes=self.notes,
        )

    @classmethod
    def from_dict(cls, data: MaterialDict) -> Material:
        """Create Material from dictionary.

        Clamps invalid values to valid ranges to handle legacy data
        that may have been saved before validation was added.
        """
        # Clamp tube_od to valid range
        tube_od = max(0.001, data['tube_od'])

        return cls(
            id=data['id'],
            name=data['name'],
            tube_od=tube_od,
            batch=data.get('batch', ''),
            notes=data.get('notes', ''),
        )

    def matches_tube_od(self, tube_od: float, tolerance: float = 0.01) -> bool:
        """
        Check if this material matches the given tube OD within tolerance.

        Args:
            tube_od: Tube outer diameter to check (must be positive)
            tolerance: Matching tolerance (must be non-negative)

        Returns:
            True if material tube_od matches within tolerance, False otherwise.
            Returns False for invalid inputs (negative values).
        """
        if tube_od <= 0 or tolerance < 0:
            return False
        return abs(self.tube_od - tube_od) <= tolerance
