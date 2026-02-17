"""Tube model for tube bending specifications and compensation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypedDict


MATERIAL_TYPES: tuple[str, ...] = (
    "",  # Not specified
    "DOM",
    "HREW",
    "ERW",
    "Seamless",
    "Aluminum",
    "Stainless Steel",
    "Chromoly",
    "Other",
)


class TubeDict(TypedDict):
    """Type definition for Tube serialization."""

    id: str
    name: str
    tube_od: float
    wall_thickness: float
    material_type: str
    batch: str
    notes: str


def validate_tube_values(
    tube_od: float | None = None,
    wall_thickness: float | None = None,
) -> None:
    """Validate tube numeric values.

    Args:
        tube_od: Tube outer diameter (must be positive if provided)
        wall_thickness: Wall thickness (must be non-negative if provided)

    Raises:
        ValueError: If any value violates its constraint
    """
    if tube_od is not None and tube_od <= 0:
        raise ValueError(f"tube_od must be positive, got {tube_od}")
    if wall_thickness is not None and wall_thickness < 0:
        raise ValueError(f"wall_thickness must be non-negative, got {wall_thickness}")
    if tube_od is not None and wall_thickness is not None:
        if wall_thickness > 0 and wall_thickness >= tube_od / 2:
            raise ValueError(
                f"wall_thickness ({wall_thickness}) must be less than half "
                f"of tube_od ({tube_od})"
            )


@dataclass(slots=True)
class Tube:
    """
    Represents a tube specification for bender compensation tracking.

    Tubes are used to track bender compensation data for specific
    die-tube combinations. Different tubes and batches may
    exhibit different compensation characteristics.

    Attributes:
        id: Unique identifier for the tube
        name: Display name (e.g., "DOM 1020 1.75x0.120")
        tube_od: Tube outer diameter (in cm)
        wall_thickness: Wall thickness (in cm, 0 = not specified)
        material_type: Material type from MATERIAL_TYPES (empty = not specified)
        batch: Optional batch/lot number for tracking
        notes: Optional notes about the tube
    """

    id: str
    name: str
    tube_od: float
    wall_thickness: float = 0.0
    material_type: str = ""
    batch: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        """Validate numeric fields."""
        validate_tube_values(tube_od=self.tube_od, wall_thickness=self.wall_thickness)

    def __repr__(self) -> str:
        parts = f"Tube(name={self.name!r}, tube_od={self.tube_od}"
        if self.material_type:
            parts += f", material_type={self.material_type!r}"
        parts += ")"
        return parts

    def to_dict(self) -> TubeDict:
        """Convert to dictionary for JSON serialization."""
        return TubeDict(
            id=self.id,
            name=self.name,
            tube_od=self.tube_od,
            wall_thickness=self.wall_thickness,
            material_type=self.material_type,
            batch=self.batch,
            notes=self.notes,
        )

    @classmethod
    def from_dict(cls, data: TubeDict) -> Tube:
        """Create Tube from dictionary.

        Clamps invalid values to valid ranges to handle legacy data
        that may have been saved before validation was added.
        """
        # Clamp tube_od to valid range
        tube_od = max(0.001, data['tube_od'])
        # Clamp wall_thickness to non-negative and less than half tube_od
        wall_thickness = max(0.0, data.get('wall_thickness', 0.0))
        if wall_thickness > 0 and wall_thickness >= tube_od / 2:
            wall_thickness = tube_od / 2 - 0.001

        return cls(
            id=data['id'],
            name=data['name'],
            tube_od=tube_od,
            wall_thickness=wall_thickness,
            material_type=data.get('material_type', ''),
            batch=data.get('batch', ''),
            notes=data.get('notes', ''),
        )

    def matches_tube_od(self, tube_od: float, tolerance: float = 0.01) -> bool:
        """
        Check if this tube matches the given tube OD within tolerance.

        Args:
            tube_od: Tube outer diameter to check (must be positive)
            tolerance: Matching tolerance (must be non-negative)

        Returns:
            True if tube tube_od matches within tolerance, False otherwise.
            Returns False for invalid inputs (negative values, NaN).
        """
        if tube_od <= 0 or tolerance < 0:
            return False
        if math.isnan(tube_od) or math.isnan(tolerance):
            return False
        if math.isnan(self.tube_od):
            return False
        return abs(self.tube_od - tube_od) <= tolerance
