"""Bender and die configuration models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TypedDict

# Default tolerance for die CLR matching (in display units).
# This value is also defined in core/tolerances.py as DIE_CLR_MATCH_DEFAULT.
# We duplicate it here to avoid circular imports (models -> core -> models).
_DIE_CLR_MATCH_DEFAULT: float = 0.01


class DieDict(TypedDict):
    """Type definition for Die serialization."""

    id: str
    name: str
    tube_od: float
    clr: float
    offset: float
    min_tail: float
    notes: str


class BenderDict(TypedDict):
    """Type definition for Bender serialization."""

    id: str
    name: str
    min_grip: float
    dies: list[DieDict]
    notes: str


def validate_die_values(
    tube_od: float | None = None,
    clr: float | None = None,
    offset: float | None = None,
    min_tail: float | None = None,
) -> None:
    """Validate die numeric values.

    Args:
        tube_od: Tube outer diameter (must be positive if provided)
        clr: Center line radius (must be positive if provided)
        offset: Die offset (must be non-negative if provided)
        min_tail: Minimum tail length (must be non-negative if provided)

    Raises:
        ValueError: If any value violates its constraint
    """
    if tube_od is not None and tube_od <= 0:
        raise ValueError(f"tube_od must be positive, got {tube_od}")
    if clr is not None and clr <= 0:
        raise ValueError(f"clr must be positive, got {clr}")
    if offset is not None and offset < 0:
        raise ValueError(f"offset cannot be negative, got {offset}")
    if min_tail is not None and min_tail < 0:
        raise ValueError(f"min_tail cannot be negative, got {min_tail}")


def validate_bender_values(
    min_grip: float | None = None,
) -> None:
    """Validate bender numeric values.

    Args:
        min_grip: Minimum grip length (must be positive if provided)

    Raises:
        ValueError: If any value violates its constraint
    """
    if min_grip is not None and min_grip <= 0:
        raise ValueError(f"min_grip must be positive, got {min_grip}")


@dataclass(slots=True)
class Die:
    """
    Represents a tube bending die.

    Attributes:
        id: Unique identifier for the die
        name: Display name (e.g., "1.75 x 5.5 CLR")
        tube_od: Tube outer diameter this die accepts
        clr: Center line radius of the die
        offset: Distance from die edge to bend tangent point
        min_tail: Minimum length required after the last bend
        notes: Optional notes about the die
    """

    id: str
    name: str
    tube_od: float
    clr: float
    offset: float
    min_tail: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        """Validate numeric fields are positive."""
        validate_die_values(
            tube_od=self.tube_od,
            clr=self.clr,
            offset=self.offset,
            min_tail=self.min_tail,
        )

    def __repr__(self) -> str:
        return f"Die(name={self.name!r}, clr={self.clr}, tube_od={self.tube_od})"

    def to_dict(self) -> DieDict:
        """Convert to dictionary for JSON serialization."""
        return DieDict(
            id=self.id,
            name=self.name,
            tube_od=self.tube_od,
            clr=self.clr,
            offset=self.offset,
            min_tail=self.min_tail,
            notes=self.notes,
        )

    @classmethod
    def from_dict(cls, data: DieDict) -> Die:
        """Create Die from dictionary.

        Clamps invalid values to valid ranges to handle legacy data
        that may have been saved before validation was added.
        """
        # Clamp values to valid ranges to handle legacy data
        tube_od = max(0.001, data['tube_od'])
        clr = max(0.001, data['clr'])
        offset = max(0.0, data['offset'])
        min_tail = max(0.0, data.get('min_tail', 0.0))

        return cls(
            id=data['id'],
            name=data['name'],
            tube_od=tube_od,
            clr=clr,
            offset=offset,
            min_tail=min_tail,
            notes=data.get('notes', ''),
        )

    def matches_clr(self, clr: float, tolerance: float = _DIE_CLR_MATCH_DEFAULT) -> bool:
        """
        Check if this die matches the given CLR within tolerance.

        Args:
            clr: Center line radius to check (must be positive)
            tolerance: Matching tolerance (must be non-negative)

        Returns:
            True if die CLR matches within tolerance, False otherwise.
            Returns False for invalid inputs (negative values, NaN).
        """
        # Validate inputs - return False for invalid rather than raising
        if clr <= 0 or tolerance < 0:
            return False
        if math.isnan(clr) or math.isnan(tolerance):
            return False
        if math.isnan(self.clr):
            return False

        return abs(self.clr - clr) <= tolerance


@dataclass(slots=True)
class Bender:
    """
    Represents a tube bender with its dies and settings.

    Attributes:
        id: Unique identifier for the bender
        name: Display name (e.g., "JD2 Model 3")
        min_grip: Minimum grip length required
        dies: List of dies available for this bender
        notes: Optional notes about the bender
    """

    id: str
    name: str
    min_grip: float
    dies: list[Die] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        """Validate numeric fields are positive."""
        validate_bender_values(min_grip=self.min_grip)

    def __repr__(self) -> str:
        return f"Bender(name={self.name!r}, min_grip={self.min_grip}, dies={len(self.dies)})"

    def to_dict(self) -> BenderDict:
        """Convert to dictionary for JSON serialization."""
        return BenderDict(
            id=self.id,
            name=self.name,
            min_grip=self.min_grip,
            dies=[die.to_dict() for die in self.dies],
            notes=self.notes,
        )

    @classmethod
    def from_dict(cls, data: BenderDict) -> Bender:
        """Create Bender from dictionary.

        Clamps invalid values to valid ranges to handle legacy data
        that may have been saved before validation was added.
        """
        dies = [Die.from_dict(d) for d in data.get('dies', [])]
        # Clamp min_grip to valid range
        min_grip = max(0.001, data['min_grip'])

        return cls(
            id=data['id'],
            name=data['name'],
            min_grip=min_grip,
            dies=dies,
            notes=data.get('notes', ''),
        )
    
    def get_die_by_id(self, die_id: str) -> Die | None:
        """Find a die by its ID."""
        for die in self.dies:
            if die.id == die_id:
                return die
        return None
    
    def find_die_for_clr(self, clr: float, tolerance: float = _DIE_CLR_MATCH_DEFAULT) -> Die | None:
        """Find a die that matches the given CLR."""
        for die in self.dies:
            if die.matches_clr(clr, tolerance):
                return die
        return None
    
    def add_die(self, die: Die) -> None:
        """Add a die to this bender."""
        self.dies.append(die)
    
    def remove_die(self, die_id: str) -> bool:
        """Remove a die by ID. Returns True if found and removed."""
        for i, die in enumerate(self.dies):
            if die.id == die_id:
                self.dies.pop(i)
                return True
        return False
