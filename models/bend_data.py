"""Bend calculation data models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import Vector3D, Point3D, SegmentType
from .units import UnitConfig


@dataclass(slots=True)
class StraightSection:
    """Represents a straight section of tube between bends."""
    number: int
    length: float  # In display units
    start: Point3D
    end: Point3D
    vector: Vector3D  # In internal units (cm) for calculations


@dataclass(slots=True)
class BendData:
    """Represents a bend in the tube path."""

    number: int
    angle: float  # Degrees
    rotation: float | None  # Degrees, None for first bend
    arc_length: float = 0.0  # In display units

    def __repr__(self) -> str:
        rot = f", rot={self.rotation:.1f}" if self.rotation is not None else ""
        return f"BendData(#{self.number}, angle={self.angle:.1f}{rot})"


@dataclass(slots=True)
class PathSegment:
    """Represents a segment in the cumulative path table."""
    segment_type: SegmentType
    name: str
    length: float
    starts_at: float
    ends_at: float
    bend_angle: float | None
    rotation: float | None


@dataclass(slots=True)
class MarkPosition:
    """Represents a mark position for the bender setup."""
    bend_num: int
    mark_position: float
    bend_angle: float
    rotation: float | None


@dataclass(slots=True)
class BendSheetData:
    """All data needed to generate a bend sheet."""
    component_name: str
    tube_od: float
    clr: float
    die_offset: float
    precision: int
    min_grip: float
    travel_direction: str
    starts_with_arc: bool
    ends_with_arc: bool
    clr_mismatch: bool
    clr_values: list[float]
    continuity_errors: list[str]
    straights: list[StraightSection]
    bends: list[BendData]
    segments: list[PathSegment]
    mark_positions: list[MarkPosition]
    extra_material: float
    total_centerline: float
    total_cut_length: float
    units: UnitConfig
    bender_name: str = ""
    die_name: str = ""
    bender_notes: str = ""  # Notes from bender profile
    die_notes: str = ""  # Notes from die profile
    grip_violations: list[int] = field(default_factory=list)  # Straight section numbers too short for min_grip
    min_tail: float = 0.0  # Minimum length required after last bend
    tail_violation: bool = False  # True if last straight is shorter than min_tail
    # Synthetic grip/tail fields for paths starting/ending with bends
    has_synthetic_grip: bool = False  # True if synthetic grip material was added
    has_synthetic_tail: bool = False  # True if synthetic tail material was added
    grip_cut_position: float | None = None  # Where to cut grip material from start
    tail_cut_position: float | None = None  # Where to cut tail material from end
    # User-entered allowances (separate for each end)
    start_allowance: float = 0.0  # Extra material at start (grip end)
    end_allowance: float = 0.0  # Extra material at end (tail end)
    # Tail extension fields for paths ending with short straights
    extra_tail_material: float = 0.0  # Material added when last straight < min_tail
    has_tail_extension: bool = False  # True if tail was extended (not synthetic)
    # Effective allowances (may be 0 if grip/tail was extended)
    effective_start_allowance: float = 0.0  # Allowance at start (0 if grip extended)
    effective_end_allowance: float = 0.0  # Allowance at end (0 if tail extended)
    # Spring back warning
    spring_back_warning: bool = False  # True when tail extended but no end allowance
