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
    compensated_angle: float | None = None  # What bender readout should show


# ---------------------------------------------------------------------------
# BendSheetData sub-groups
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolingInfo:
    """Component identity, bender/die names+notes, tube info, compensation flag."""
    component_name: str
    bender_name: str = ""
    die_name: str = ""
    bender_notes: str = ""
    die_notes: str = ""
    tube_name: str = ""
    wall_thickness: float = 0.0
    material_type: str = ""
    apply_compensation: bool = False


@dataclass(slots=True)
class GeometrySpecs:
    """Tube OD, CLR, die offset, precision, units, CLR mismatch."""
    tube_od: float
    clr: float
    die_offset: float
    precision: int
    units: UnitConfig
    clr_mismatch: bool = False
    clr_values: list[float] = field(default_factory=list)


@dataclass(slots=True)
class PathData:
    """Straights, bends, segments, marks, arc flags, totals, direction, continuity errors."""
    straights: list[StraightSection]
    bends: list[BendData]
    segments: list[PathSegment]
    mark_positions: list[MarkPosition]
    total_centerline: float
    total_cut_length: float
    travel_direction: str
    starts_with_arc: bool = False
    ends_with_arc: bool = False
    continuity_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MaterialInfo:
    """Grip/tail/allowance: min values, violations, extensions, synthetic flags, cut positions."""
    min_grip: float
    extra_material: float
    min_tail: float = 0.0
    grip_violations: list[int] = field(default_factory=list)
    tail_violation: bool = False
    has_synthetic_grip: bool = False
    has_synthetic_tail: bool = False
    grip_cut_position: float | None = None
    tail_cut_position: float | None = None
    start_allowance: float = 0.0
    end_allowance: float = 0.0
    extra_tail_material: float = 0.0
    has_tail_extension: bool = False
    effective_start_allowance: float = 0.0
    effective_end_allowance: float = 0.0


@dataclass(slots=True)
class SheetWarnings:
    """Spring back warning, compensation warnings."""
    spring_back_warning: bool = False
    compensation_warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BendSheetData:
    """All data needed to generate a bend sheet.

    Fields are grouped into sub-dataclasses for readability:
    - tooling: Component identity, bender/die/tube info
    - geometry: Tube OD, CLR, die offset, precision, units
    - path: Straights, bends, segments, marks, totals
    - material: Grip/tail/allowance details
    - warnings: Spring back and compensation warnings

    The flat fields are preserved for backward compatibility. Use
    ``from_groups()`` for new construction.
    """
    # --- Required positional fields (no defaults) ---
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

    # --- Optional fields with defaults ---
    bender_name: str = ""
    die_name: str = ""
    bender_notes: str = ""
    die_notes: str = ""
    grip_violations: list[int] = field(default_factory=list)
    min_tail: float = 0.0
    tail_violation: bool = False
    has_synthetic_grip: bool = False
    has_synthetic_tail: bool = False
    grip_cut_position: float | None = None
    tail_cut_position: float | None = None
    start_allowance: float = 0.0
    end_allowance: float = 0.0
    extra_tail_material: float = 0.0
    has_tail_extension: bool = False
    effective_start_allowance: float = 0.0
    effective_end_allowance: float = 0.0
    spring_back_warning: bool = False
    tube_name: str = ""
    wall_thickness: float = 0.0
    material_type: str = ""
    apply_compensation: bool = False
    compensation_warnings: list[str] = field(default_factory=list)

    # --- Sub-group accessors (populated by from_groups or lazily) ---

    @property
    def tooling(self) -> ToolingInfo:
        """Access tooling-related fields as a group."""
        return ToolingInfo(
            component_name=self.component_name,
            bender_name=self.bender_name,
            die_name=self.die_name,
            bender_notes=self.bender_notes,
            die_notes=self.die_notes,
            tube_name=self.tube_name,
            wall_thickness=self.wall_thickness,
            material_type=self.material_type,
            apply_compensation=self.apply_compensation,
        )

    @property
    def geometry(self) -> GeometrySpecs:
        """Access geometry-related fields as a group."""
        return GeometrySpecs(
            tube_od=self.tube_od,
            clr=self.clr,
            die_offset=self.die_offset,
            precision=self.precision,
            units=self.units,
            clr_mismatch=self.clr_mismatch,
            clr_values=self.clr_values,
        )

    @property
    def path(self) -> PathData:
        """Access path-related fields as a group."""
        return PathData(
            straights=self.straights,
            bends=self.bends,
            segments=self.segments,
            mark_positions=self.mark_positions,
            total_centerline=self.total_centerline,
            total_cut_length=self.total_cut_length,
            travel_direction=self.travel_direction,
            starts_with_arc=self.starts_with_arc,
            ends_with_arc=self.ends_with_arc,
            continuity_errors=self.continuity_errors,
        )

    @property
    def material(self) -> MaterialInfo:
        """Access material-related fields as a group."""
        return MaterialInfo(
            min_grip=self.min_grip,
            extra_material=self.extra_material,
            min_tail=self.min_tail,
            grip_violations=self.grip_violations,
            tail_violation=self.tail_violation,
            has_synthetic_grip=self.has_synthetic_grip,
            has_synthetic_tail=self.has_synthetic_tail,
            grip_cut_position=self.grip_cut_position,
            tail_cut_position=self.tail_cut_position,
            start_allowance=self.start_allowance,
            end_allowance=self.end_allowance,
            extra_tail_material=self.extra_tail_material,
            has_tail_extension=self.has_tail_extension,
            effective_start_allowance=self.effective_start_allowance,
            effective_end_allowance=self.effective_end_allowance,
        )

    @property
    def warnings(self) -> SheetWarnings:
        """Access warning-related fields as a group."""
        return SheetWarnings(
            spring_back_warning=self.spring_back_warning,
            compensation_warnings=self.compensation_warnings,
        )

    @classmethod
    def from_groups(
        cls,
        tooling: ToolingInfo,
        geometry: GeometrySpecs,
        path: PathData,
        material: MaterialInfo,
        warnings: SheetWarnings,
    ) -> BendSheetData:
        """Construct BendSheetData from sub-group dataclasses.

        This is the preferred constructor for new code. It builds the flat
        dataclass from the five focused sub-groups for readability.
        """
        return cls(
            # ToolingInfo
            component_name=tooling.component_name,
            bender_name=tooling.bender_name,
            die_name=tooling.die_name,
            bender_notes=tooling.bender_notes,
            die_notes=tooling.die_notes,
            tube_name=tooling.tube_name,
            wall_thickness=tooling.wall_thickness,
            material_type=tooling.material_type,
            apply_compensation=tooling.apply_compensation,
            # GeometrySpecs
            tube_od=geometry.tube_od,
            clr=geometry.clr,
            die_offset=geometry.die_offset,
            precision=geometry.precision,
            units=geometry.units,
            clr_mismatch=geometry.clr_mismatch,
            clr_values=geometry.clr_values,
            # PathData
            straights=path.straights,
            bends=path.bends,
            segments=path.segments,
            mark_positions=path.mark_positions,
            total_centerline=path.total_centerline,
            total_cut_length=path.total_cut_length,
            travel_direction=path.travel_direction,
            starts_with_arc=path.starts_with_arc,
            ends_with_arc=path.ends_with_arc,
            continuity_errors=path.continuity_errors,
            # MaterialInfo
            min_grip=material.min_grip,
            extra_material=material.extra_material,
            min_tail=material.min_tail,
            grip_violations=material.grip_violations,
            tail_violation=material.tail_violation,
            has_synthetic_grip=material.has_synthetic_grip,
            has_synthetic_tail=material.has_synthetic_tail,
            grip_cut_position=material.grip_cut_position,
            tail_cut_position=material.tail_cut_position,
            start_allowance=material.start_allowance,
            end_allowance=material.end_allowance,
            extra_tail_material=material.extra_tail_material,
            has_tail_extension=material.has_tail_extension,
            effective_start_allowance=material.effective_start_allowance,
            effective_end_allowance=material.effective_end_allowance,
            # SheetWarnings
            spring_back_warning=warnings.spring_back_warning,
            compensation_warnings=warnings.compensation_warnings,
        )
