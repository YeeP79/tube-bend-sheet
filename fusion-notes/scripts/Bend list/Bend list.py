"""
Tube Bend Rotation Calculator for Fusion 360

Calculates multi-plane tube bend rotations using the vector cross product method.
Generates printable HTML bend sheets with bender setup instructions.

USAGE:
1. Select ALL tube path elements (lines AND arcs) - any order is fine
2. Run this script
3. Confirm the travel direction when prompted
4. Enter tube OD, die offset, precision, and minimum grip when prompted
5. Results open in browser for printing

FEATURES:
- Auto-detects path order from connectivity (select in any order!)
- Detects primary travel axis and lets you confirm direction
- Automatically extracts CLR from arc geometry
- Validates CLR consistency across all bends
- Calculates rotation between bend planes using vector cross product method
- Outputs styled HTML for printing
"""

from __future__ import annotations

import math
import os
import tempfile
import traceback
import webbrowser
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import adsk.core
import adsk.fusion

if TYPE_CHECKING:
    pass

# =============================================================================
# CONSTANTS
# =============================================================================

CONNECTIVITY_TOLERANCE_CM: float = 0.1
"""Tolerance in cm for determining if two endpoints are connected."""

CLR_TOLERANCE_RATIO: float = 0.002
"""Tolerance ratio (0.2%) for CLR matching between arcs."""

VALID_PRECISIONS_IMPERIAL: tuple[int, ...] = (0, 4, 8, 16, 32)
"""Valid denominator values for fractional inch display."""

VALID_PRECISIONS_METRIC: tuple[int, ...] = (0, 1, 2, 5, 10)
"""Valid decimal places for metric display (0=auto, 1=0.1mm, 2=0.01mm, etc.)."""

DEFAULT_PRECISION_IMPERIAL: int = 16
"""Default precision denominator for imperial (1/16")."""

DEFAULT_PRECISION_METRIC: int = 1
"""Default precision for metric (0.1mm)."""


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

Vector3D = tuple[float, float, float]
"""A 3D vector represented as (x, y, z)."""

Point3D = tuple[float, float, float]
"""A 3D point represented as (x, y, z)."""


@dataclass
class UnitConfig:
    """Unit configuration extracted from Fusion design."""
    is_metric: bool
    unit_name: str  # "in", "mm", "cm", "m", "ft"
    unit_symbol: str  # '"', 'mm', 'cm', 'm', "'"
    cm_to_unit: float  # Conversion factor from internal cm to display unit
    default_tube_od: str
    default_precision: int
    valid_precisions: tuple[int, ...]

    @classmethod
    def from_design(cls, design: adsk.fusion.Design) -> 'UnitConfig':
        """
        Extract unit configuration from Fusion design.

        Args:
            design: The active Fusion design

        Returns:
            UnitConfig with appropriate settings for the design's units
        """
        units_mgr = design.unitsManager
        default_units = units_mgr.defaultLengthUnits

        # Map Fusion unit strings to our config
        unit_configs = {
            'in': cls(
                is_metric=False,
                unit_name='in',
                unit_symbol='"',
                cm_to_unit=1.0 / 2.54,
                default_tube_od='1.75',
                default_precision=DEFAULT_PRECISION_IMPERIAL,
                valid_precisions=VALID_PRECISIONS_IMPERIAL
            ),
            'ft': cls(
                is_metric=False,
                unit_name='ft',
                unit_symbol="'",
                cm_to_unit=1.0 / 30.48,
                default_tube_od='0.146',  # 1.75" in feet
                default_precision=DEFAULT_PRECISION_IMPERIAL,
                valid_precisions=VALID_PRECISIONS_IMPERIAL
            ),
            'mm': cls(
                is_metric=True,
                unit_name='mm',
                unit_symbol='mm',
                cm_to_unit=10.0,
                default_tube_od='44.45',  # 1.75" in mm
                default_precision=DEFAULT_PRECISION_METRIC,
                valid_precisions=VALID_PRECISIONS_METRIC
            ),
            'cm': cls(
                is_metric=True,
                unit_name='cm',
                unit_symbol='cm',
                cm_to_unit=1.0,
                default_tube_od='4.445',
                default_precision=DEFAULT_PRECISION_METRIC,
                valid_precisions=VALID_PRECISIONS_METRIC
            ),
            'm': cls(
                is_metric=True,
                unit_name='m',
                unit_symbol='m',
                cm_to_unit=0.01,
                default_tube_od='0.04445',
                default_precision=DEFAULT_PRECISION_METRIC,
                valid_precisions=VALID_PRECISIONS_METRIC
            ),
        }

        # Default to inches if unknown
        return unit_configs.get(default_units, unit_configs['in'])


@dataclass
class StraightSection:
    """Represents a straight section of tube between bends."""
    number: int
    length_in: float
    start: Point3D
    end: Point3D
    vector: Vector3D


@dataclass
class BendData:
    """Represents a bend in the tube path."""
    number: int
    angle: float
    rotation: float | None
    arc_length: float = 0.0


@dataclass
class PathSegment:
    """Represents a segment in the cumulative path table."""
    segment_type: str  # 'straight' or 'bend'
    name: str
    length: float
    starts_at: float
    ends_at: float
    bend_angle: float | None
    rotation: float | None


@dataclass
class MarkPosition:
    """Represents a mark position for the bender setup."""
    bend_num: int
    mark_position: float
    bend_angle: float
    rotation: float | None


@dataclass
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


# =============================================================================
# VECTOR MATH UTILITIES
# =============================================================================

def cross_product(v1: Vector3D, v2: Vector3D) -> Vector3D:
    """
    Calculate the cross product of two 3D vectors.

    Args:
        v1: First vector (x, y, z)
        v2: Second vector (x, y, z)

    Returns:
        Cross product vector (x, y, z)
    """
    return (
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0]
    )


def dot_product(v1: Vector3D, v2: Vector3D) -> float:
    """
    Calculate the dot product of two 3D vectors.

    Args:
        v1: First vector (x, y, z)
        v2: Second vector (x, y, z)

    Returns:
        Scalar dot product
    """
    return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]


def magnitude(v: Vector3D) -> float:
    """
    Calculate the magnitude (length) of a 3D vector.

    Args:
        v: Vector (x, y, z)

    Returns:
        Scalar magnitude
    """
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


def angle_between_vectors(v1: Vector3D, v2: Vector3D) -> float:
    """
    Calculate the angle between two vectors in degrees.

    Args:
        v1: First vector
        v2: Second vector

    Returns:
        Angle in degrees
    """
    cos_angle: float = dot_product(v1, v2) / (magnitude(v1) * magnitude(v2))
    cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp for floating point errors
    return math.degrees(math.acos(cos_angle))


def calculate_rotation(n1: Vector3D, n2: Vector3D) -> float:
    """
    Calculate the rotation angle between two bend plane normals.

    This is the angle you rotate the tube between bends on the bender.

    Args:
        n1: Normal vector of first bend plane
        n2: Normal vector of second bend plane

    Returns:
        Rotation angle in degrees
    """
    cos_theta: float = dot_product(n1, n2) / (magnitude(n1) * magnitude(n2))
    cos_theta = max(-1.0, min(1.0, cos_theta))  # Clamp for floating point errors
    return math.degrees(math.acos(cos_theta))


def distance_between_points(p1: Point3D, p2: Point3D) -> float:
    """
    Calculate the Euclidean distance between two 3D points.

    Args:
        p1: First point (x, y, z)
        p2: Second point (x, y, z)

    Returns:
        Distance between points
    """
    return math.sqrt(
        (p2[0] - p1[0])**2 +
        (p2[1] - p1[1])**2 +
        (p2[2] - p1[2])**2
    )


def points_are_close(p1: Point3D, p2: Point3D, tolerance: float = CONNECTIVITY_TOLERANCE_CM) -> bool:
    """
    Check if two points are within tolerance of each other.

    Args:
        p1: First point
        p2: Second point
        tolerance: Maximum distance to consider "close"

    Returns:
        True if points are within tolerance
    """
    return distance_between_points(p1, p2) < tolerance


# =============================================================================
# FORMATTING UTILITIES
# =============================================================================

def gcd(a: int, b: int) -> int:
    """Calculate greatest common divisor using Euclidean algorithm."""
    while b:
        a, b = b, a % b
    return a


def decimal_to_fraction(value: float, denominator: int) -> str:
    """
    Convert decimal to fractional string (for imperial units).

    Args:
        value: Decimal value
        denominator: Fraction denominator (16 for 1/16", 8 for 1/8", etc.)
                    Use 0 for exact decimal display

    Returns:
        Formatted string like "3 1/16" or "14" or "3.7890" (if exact)
    """
    if denominator == 0:
        return f"{value:.4f}"

    total_parts: int = round(value * denominator)
    whole: int = total_parts // denominator
    numerator: int = total_parts % denominator

    if numerator == 0:
        return f"{whole}"

    common: int = gcd(numerator, denominator)
    num_simplified: int = numerator // common
    denom_simplified: int = denominator // common

    if whole == 0:
        return f"{num_simplified}/{denom_simplified}"
    return f"{whole} {num_simplified}/{denom_simplified}"


def format_metric(value: float, decimal_places: int) -> str:
    """
    Format a metric value with appropriate decimal places.

    Args:
        value: Value in metric units
        decimal_places: Number of decimal places (0=auto/smart rounding)

    Returns:
        Formatted string like "10.5" or "100.25"
    """
    if decimal_places == 0:
        # Auto mode - use reasonable precision
        if abs(value) < 1:
            return f"{value:.2f}"
        elif abs(value) < 10:
            return f"{value:.1f}"
        else:
            return f"{value:.1f}"
    else:
        return f"{value:.{decimal_places}f}"


def format_length(value: float, precision: int, units: UnitConfig) -> str:
    """
    Format a length value with appropriate unit symbol.

    Args:
        value: Value in display units (already converted from cm)
        precision: Precision setting (denominator for imperial, decimal places for metric)
        units: Unit configuration

    Returns:
        Formatted string with unit symbol
    """
    if units.is_metric:
        return f"{format_metric(value, precision)}{units.unit_symbol}"
    else:
        return f'{decimal_to_fraction(value, precision)}{units.unit_symbol}'


def get_precision_label(precision: int, units: UnitConfig) -> str:
    """Get human-readable label for precision value."""
    if units.is_metric:
        if precision == 0:
            return 'Auto'
        elif precision == 1:
            return f'0.1{units.unit_symbol}'
        elif precision == 2:
            return f'0.01{units.unit_symbol}'
        else:
            return f'{precision} decimal places'
    else:
        labels: dict[int, str] = {
            0: 'Exact (decimal)',
            4: '1/4"',
            8: '1/8"',
            16: '1/16"',
            32: '1/32"'
        }
        return labels.get(precision, f"1/{precision}\"")


# =============================================================================
# GEOMETRY EXTRACTION
# =============================================================================

SketchEntity = adsk.fusion.SketchLine | adsk.fusion.SketchArc


def get_sketch_entity_endpoints(entity: SketchEntity) -> tuple[Point3D, Point3D]:
    """
    Extract world-space endpoints from a sketch entity.

    Args:
        entity: A SketchLine or SketchArc

    Returns:
        Tuple of (start_point, end_point) in world coordinates (cm)
    """
    start: adsk.core.Point3D = entity.startSketchPoint.worldGeometry
    end: adsk.core.Point3D = entity.endSketchPoint.worldGeometry
    return (
        (start.x, start.y, start.z),
        (end.x, end.y, end.z)
    )


def get_component_name(entity: SketchEntity) -> str:
    """
    Extract the parent component name from a sketch entity.

    Args:
        entity: A sketch entity

    Returns:
        Component name or empty string if not found
    """
    try:
        parent_sketch = entity.parentSketch
        if parent_sketch and parent_sketch.parentComponent:
            return parent_sketch.parentComponent.name
    except Exception:
        pass
    return ""


# =============================================================================
# PATH ANALYSIS
# =============================================================================

@dataclass
class PathElement:
    """Wrapper for a path element (line or arc) with metadata."""
    element_type: str  # 'line' or 'arc'
    entity: SketchEntity
    endpoints: tuple[Point3D, Point3D] = field(init=False)

    def __post_init__(self) -> None:
        self.endpoints = get_sketch_entity_endpoints(self.entity)


def elements_are_connected(e1: PathElement, e2: PathElement) -> bool:
    """Check if two path elements share an endpoint."""
    for p1 in e1.endpoints:
        for p2 in e2.endpoints:
            if points_are_close(p1, p2):
                return True
    return False


def build_ordered_path(elements: list[PathElement]) -> list[PathElement] | None:
    """
    Sort path elements into connected order by traversing connectivity graph.

    Args:
        elements: Unordered list of path elements

    Returns:
        Ordered list of elements, or None if path is invalid
    """
    if len(elements) < 2:
        return None

    # Build adjacency list
    neighbors: dict[int, list[int]] = {i: [] for i in range(len(elements))}
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            if elements_are_connected(elements[i], elements[j]):
                neighbors[i].append(j)
                neighbors[j].append(i)

    # Find path endpoints (elements with only 1 neighbor)
    path_endpoints: list[int] = [i for i, n in neighbors.items() if len(n) == 1]

    if len(path_endpoints) != 2:
        return None

    # Traverse from one endpoint to the other
    ordered: list[PathElement] = []
    visited: set[int] = set()
    current: int | None = path_endpoints[0]

    while current is not None:
        ordered.append(elements[current])
        visited.add(current)

        next_elem: int | None = None
        for n in neighbors[current]:
            if n not in visited:
                next_elem = n
                break
        current = next_elem

    return ordered


def validate_path_alternation(path: list[PathElement]) -> tuple[bool, str]:
    """
    Validate that path alternates between lines and arcs.

    Args:
        path: Ordered list of path elements

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "Empty path"

    first_type = path[0].element_type

    for i, elem in enumerate(path):
        expected = first_type if i % 2 == 0 else ('arc' if first_type == 'line' else 'line')
        if elem.element_type != expected:
            return False, f"Position {i+1}: expected {expected}, got {elem.element_type}"

    return True, ""


def get_free_endpoint(element: PathElement, all_elements: list[PathElement]) -> Point3D:
    """Get the endpoint of an element that doesn't connect to any other element."""
    for ep in element.endpoints:
        connected = False
        for other in all_elements:
            if other is element:
                continue
            if points_are_close(ep, other.endpoints[0]) or points_are_close(ep, other.endpoints[1]):
                connected = True
                break
        if not connected:
            return ep
    return element.endpoints[0]


def determine_primary_axis(start: Point3D, end: Point3D) -> tuple[str, int, str, str]:
    """
    Determine the primary travel axis and direction.

    Args:
        start: Start point of path
        end: End point of path

    Returns:
        Tuple of (axis_name, axis_index, current_direction, opposite_direction)
    """
    displacement = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    abs_disp = (abs(displacement[0]), abs(displacement[1]), abs(displacement[2]))
    max_disp = max(abs_disp)

    if abs_disp[0] == max_disp:
        axis, idx = 'X', 0
    elif abs_disp[1] == max_disp:
        axis, idx = 'Y', 1
    else:
        axis, idx = 'Z', 2

    current = f"+{axis}" if displacement[idx] > 0 else f"-{axis}"
    opposite = f"-{axis}" if displacement[idx] > 0 else f"+{axis}"

    return axis, idx, current, opposite


# =============================================================================
# VALIDATION
# =============================================================================

def validate_clr_consistency(
    arcs: list[adsk.fusion.SketchArc],
    units: UnitConfig
) -> tuple[float, bool, list[float]]:
    """
    Extract and validate CLR from arc geometry.

    Args:
        arcs: List of sketch arcs
        units: Unit configuration for conversion

    Returns:
        Tuple of (primary_clr, has_mismatch, all_clr_values) in display units
    """
    clr_values: list[float] = []
    for arc in arcs:
        # arc.radius is in cm (Fusion internal)
        clr_display = arc.radius * units.cm_to_unit
        clr_values.append(clr_display)

    if not clr_values:
        return 0.0, False, []

    clr = clr_values[0]
    # Use ratio-based tolerance (0.2% of CLR)
    tolerance = clr * CLR_TOLERANCE_RATIO
    has_mismatch = any(abs(c - clr) > tolerance for c in clr_values)

    return clr, has_mismatch, clr_values


# =============================================================================
# USER INPUT DIALOGS
# =============================================================================

def prompt_for_direction(
    ui: adsk.core.UserInterface,
    axis: str,
    start: Point3D,
    end: Point3D,
    current_dir: str,
    opposite_dir: str,
    starts_with_arc: bool,
    ends_with_arc: bool,
    units: UnitConfig
) -> bool | None:
    """
    Prompt user to confirm or reverse path direction.

    Returns:
        True if user wants to reverse, False to keep, None if cancelled
    """
    start_disp = (
        start[0] * units.cm_to_unit,
        start[1] * units.cm_to_unit,
        start[2] * units.cm_to_unit
    )
    end_disp = (
        end[0] * units.cm_to_unit,
        end[1] * units.cm_to_unit,
        end[2] * units.cm_to_unit
    )

    notes = ""
    if starts_with_arc:
        notes += "⚠️ Path STARTS with a bend (arc)\n"
    if ends_with_arc:
        notes += "⚠️ Path ENDS with a bend (arc)\n"
    if notes:
        notes += "\n"

    result = ui.inputBox(
        f'🧭 CONFIRM TUBE DIRECTION\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'Units: {units.unit_name}\n\n'
        f'{notes}'
        f'Tube travels primarily in {axis} direction.\n\n'
        f'Current path:\n'
        f'  Start: ({start_disp[0]:.2f}, {start_disp[1]:.2f}, {start_disp[2]:.2f})\n'
        f'  End:   ({end_disp[0]:.2f}, {end_disp[1]:.2f}, {end_disp[2]:.2f})\n'
        f'  Direction: {current_dir}\n\n'
        f'The bender sequence will start from the "Start" end.\n\n'
        f'Enter 1 to keep this direction\n'
        f'Enter 2 to reverse (start from {opposite_dir} end)',
        'Confirm Direction',
        '1'
    )

    if result[1]:  # cancelled
        return None

    return result[0].strip() == '2'


def prompt_for_tube_od(ui: adsk.core.UserInterface, units: UnitConfig) -> float | None:
    """Prompt user for tube outer diameter."""
    if units.is_metric:
        examples = '• 38.1mm (1.5")\n• 44.45mm (1.75")\n• 50.8mm (2.0")'
    else:
        examples = '• 1.5"\n• 1.75"\n• 2.0"'

    result = ui.inputBox(
        f'📏 TUBE OD (Outside Diameter)\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'The outer diameter of your tube.\n\n'
        f'Common sizes ({units.unit_name}):\n{examples}\n\n'
        f'Enter tube OD in {units.unit_name}:',
        'Tube OD',
        units.default_tube_od
    )

    if result[1]:
        return None

    try:
        return float(result[0])
    except ValueError:
        ui.messageBox('Invalid tube OD value. Please enter a number.', 'Error')
        return None


def prompt_for_die_offset(ui: adsk.core.UserInterface, clr: float, units: UnitConfig) -> float | None:
    """Prompt user for die offset."""
    result = ui.inputBox(
        f'📐 DIE OFFSET\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'Detected CLR from model: {clr:.4f}{units.unit_symbol}\n\n'
        f'The die offset is the distance from the edge of\n'
        f'the die to where the bend tangent point begins.\n\n'
        f'How to measure:\n'
        f'1. Place tube in die at bend start position\n'
        f'2. Measure from die edge to tangent point\n\n'
        f'This lets you mark the tube and align the mark\n'
        f'with the die edge for accurate positioning.\n\n'
        f'Enter 0 if unknown (will show raw tangent lengths).\n\n'
        f'Enter die offset in {units.unit_name}:',
        'Die Offset',
        '0'
    )

    if result[1]:
        return None

    try:
        return float(result[0])
    except ValueError:
        ui.messageBox('Invalid die offset value. Please enter a number.', 'Error')
        return None


def prompt_for_precision(ui: adsk.core.UserInterface, units: UnitConfig) -> int | None:
    """Prompt user for measurement precision."""
    if units.is_metric:
        options = (
            '• 0 = Auto (smart rounding)\n'
            '• 1 = 0.1mm precision\n'
            '• 2 = 0.01mm precision\n'
        )
        valid_str = '0, 1, 2, 5, or 10'
    else:
        options = (
            '• 0 = Exact decimals (3.7890")\n'
            '• 32 = Nearest 1/32" (3 25/32")\n'
            '• 16 = Nearest 1/16" (3 13/16") ← Most common\n'
            '• 8 = Nearest 1/8" (3 3/4")\n'
            '• 4 = Nearest 1/4" (3 3/4")\n'
        )
        valid_str = '0, 32, 16, 8, or 4'

    result = ui.inputBox(
        f'📏 MEASUREMENT PRECISION\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'How precise should measurements be displayed?\n\n'
        f'Options:\n{options}\n'
        f'Note: Rounding is display-only. Calculations\n'
        f'use exact values to avoid compounding errors.\n\n'
        f'Enter precision ({valid_str}):',
        'Measurement Precision',
        str(units.default_precision)
    )

    if result[1]:
        return None

    try:
        precision = int(result[0])
        if precision not in units.valid_precisions:
            ui.messageBox(
                f'Invalid precision. Please enter one of: {units.valid_precisions}',
                'Error'
            )
            return None
        return precision
    except ValueError:
        ui.messageBox('Invalid precision value. Please enter a number.', 'Error')
        return None


def prompt_for_min_grip(ui: adsk.core.UserInterface, units: UnitConfig) -> float | None:
    """Prompt user for minimum grip length."""
    if units.is_metric:
        typical = '100mm to 200mm'
    else:
        typical = '4" to 8"'

    result = ui.inputBox(
        f'✊ MINIMUM GRIP LENGTH\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'The minimum tube length you need sticking out\n'
        f'of the bender before the first bend.\n\n'
        f'Why it matters:\n'
        f'• You need enough tube to grip/hold securely\n'
        f'• Too short = tube slips during bend\n'
        f'• If Straight 1 is shorter than this, extra\n'
        f'  material will be added (cut off after bending)\n\n'
        f'Typical values: {typical} depending on bender\n\n'
        f'Enter 0 to skip this check.\n\n'
        f'Enter minimum grip length in {units.unit_name}:',
        'Minimum Grip Length',
        '0'
    )

    if result[1]:
        return None

    try:
        return float(result[0])
    except ValueError:
        ui.messageBox('Invalid grip length value. Please enter a number.', 'Error')
        return None


# =============================================================================
# BEND CALCULATIONS
# =============================================================================

def calculate_straights_and_bends(
    lines: list[adsk.fusion.SketchLine],
    arcs: list[adsk.fusion.SketchArc],
    path_start: Point3D,
    clr: float,
    units: UnitConfig
) -> tuple[list[StraightSection], list[BendData]]:
    """
    Calculate all straight sections and bend data from geometry.

    Args:
        lines: Ordered list of sketch lines
        arcs: Ordered list of sketch arcs
        path_start: The starting point of the path (in cm)
        clr: Center line radius in display units
        units: Unit configuration for conversion

    Returns:
        Tuple of (straights, bends) with lengths in display units
    """
    # Get line endpoints and orient them correctly
    line_points: list[tuple[Point3D, Point3D]] = []
    for line in lines:
        start, end = get_sketch_entity_endpoints(line)
        line_points.append((start, end))

    # Orient first line so start is at path_start
    corrected: list[tuple[Point3D, Point3D]] = []
    first_start, first_end = line_points[0]

    if distance_between_points(first_end, path_start) < distance_between_points(first_start, path_start):
        corrected.append((first_end, first_start))
    else:
        corrected.append((first_start, first_end))

    # Orient remaining lines based on connectivity
    for i in range(1, len(line_points)):
        prev_end = corrected[i - 1][1]
        curr_start, curr_end = line_points[i]

        if distance_between_points(curr_end, prev_end) < distance_between_points(curr_start, prev_end):
            corrected.append((curr_end, curr_start))
        else:
            corrected.append((curr_start, curr_end))

    # Build straight sections
    straights: list[StraightSection] = []
    vectors: list[Vector3D] = []

    for i, (start, end) in enumerate(corrected):
        vector: Vector3D = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        vectors.append(vector)

        length_cm = magnitude(vector)
        length_display = length_cm * units.cm_to_unit

        straights.append(StraightSection(
            number=i + 1,
            length_in=length_display,  # Note: field name kept for compatibility, but value is in display units
            start=(
                start[0] * units.cm_to_unit,
                start[1] * units.cm_to_unit,
                start[2] * units.cm_to_unit
            ),
            end=(
                end[0] * units.cm_to_unit,
                end[1] * units.cm_to_unit,
                end[2] * units.cm_to_unit
            ),
            vector=vector
        ))

    # Calculate bend plane normals
    normals: list[Vector3D] = []
    for i in range(len(arcs)):
        n = cross_product(vectors[i], vectors[i + 1])
        normals.append(n)

    # Calculate bend angles and rotations
    bends: list[BendData] = []
    for i in range(len(arcs)):
        bend_angle = angle_between_vectors(vectors[i], vectors[i + 1])
        arc_length = clr * math.radians(bend_angle)

        rotation: float | None = None
        if i > 0:
            rotation = calculate_rotation(normals[i - 1], normals[i])

        bends.append(BendData(
            number=i + 1,
            angle=bend_angle,
            rotation=rotation,
            arc_length=arc_length
        ))

    return straights, bends


def build_segments_and_marks(
    straights: list[StraightSection],
    bends: list[BendData],
    extra_material: float,
    die_offset: float
) -> tuple[list[PathSegment], list[MarkPosition]]:
    """
    Build cumulative path segments and mark positions.

    Args:
        straights: List of straight sections
        bends: List of bend data
        extra_material: Extra grip material at start
        die_offset: Die offset in inches

    Returns:
        Tuple of (segments, mark_positions)
    """
    segments: list[PathSegment] = []
    cumulative = extra_material

    for i, straight in enumerate(straights):
        # Add straight segment
        segments.append(PathSegment(
            segment_type='straight',
            name=f'Straight {straight.number}',
            length=straight.length_in,
            starts_at=cumulative,
            ends_at=cumulative + straight.length_in,
            bend_angle=None,
            rotation=bends[i].rotation if i < len(bends) else None
        ))
        cumulative += straight.length_in

        # Add bend segment (if not last straight)
        if i < len(bends):
            bend = bends[i]
            segments.append(PathSegment(
                segment_type='bend',
                name=f'BEND {bend.number}',
                length=bend.arc_length,
                starts_at=cumulative,
                ends_at=cumulative + bend.arc_length,
                bend_angle=bend.angle,
                rotation=None
            ))
            cumulative += bend.arc_length

    # Calculate mark positions
    mark_positions: list[MarkPosition] = []
    for bend in bends:
        # Find where this bend starts
        bend_starts_at = 0.0
        for seg in segments:
            if seg.segment_type == 'bend' and seg.name == f'BEND {bend.number}':
                bend_starts_at = seg.starts_at
                break

        mark_positions.append(MarkPosition(
            bend_num=bend.number,
            mark_position=bend_starts_at - die_offset,
            bend_angle=bend.angle,
            rotation=bend.rotation
        ))

    return segments, mark_positions


# =============================================================================
# HTML GENERATION
# =============================================================================

def generate_html_bend_sheet(data: BendSheetData) -> str:
    """
    Generate a styled HTML bend sheet for printing.

    Args:
        data: All bend sheet data

    Returns:
        Complete HTML document as string
    """
    precision = data.precision
    units = data.units

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tube Bend Sheet</title>
    <style>
        * { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
        body { max-width: 8.5in; margin: 0 auto; padding: 0.5in; font-size: 11pt; line-height: 1.4; }
        h1 { font-size: 18pt; margin-bottom: 0.1in; border-bottom: 2px solid #333; padding-bottom: 0.1in; }
        h2 { font-size: 14pt; color: #444; margin-top: 0; margin-bottom: 0.2in; }
        h3 { font-size: 12pt; margin-top: 0.3in; margin-bottom: 0.1in; color: #333; }
        .header-info { font-size: 12pt; font-weight: bold; margin-bottom: 0.2in; }
        .warning { color: #c00; font-weight: bold; margin-bottom: 0.1in; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 0.2in; font-size: 10pt; }
        th, td { border: 1px solid #333; padding: 4px 8px; text-align: left; }
        th { background-color: #f0f0f0; font-weight: bold; }
        .right { text-align: right; }
        .center { text-align: center; }
        .bend-row { background-color: #e8e8e8; }
        .procedure { margin-top: 0.2in; }
        .procedure ol { margin: 0; padding-left: 0.3in; }
        .procedure li { margin-bottom: 0.05in; }
        hr { border: none; border-top: 1px solid #999; margin: 0.2in 0; }
        .specs-table { width: auto; min-width: 3in; }
        .specs-table td:first-child { font-weight: bold; background-color: #f8f8f8; }
        @media print { body { padding: 0; } }
    </style>
</head>
<body>
"""

    # Title
    html += "<h1>TUBE BEND SHEET</h1>\n"
    if data.component_name:
        html += f"<h2>{data.component_name}</h2>\n"

    # Header info
    html += f'<div class="header-info">Cut Length: {format_length(data.total_cut_length, precision, units)} '
    html += f'&nbsp;|&nbsp; CLR: {format_length(data.clr, precision, units)}</div>\n'

    # Validation warnings
    if data.clr_mismatch:
        clr_list = ", ".join([f"{c:.3f}{units.unit_symbol}" for c in data.clr_values])
        html += f'<div class="warning">⚠️ CLR Mismatch: {clr_list}</div>\n'
    if data.continuity_errors:
        html += f'<div class="warning">⚠️ Continuity Errors: {", ".join(data.continuity_errors)}</div>\n'

    html += "<hr>\n"

    # Bend Data table
    html += "<h3>Bend Data</h3>\n<table>\n"
    html += "<tr><th class='center'>Step</th><th>Segment</th><th class='right'>Length</th>"
    html += "<th class='right'>Starts At</th><th class='right'>Ends At</th>"
    html += "<th class='right'>Bend Angle</th><th class='right'>Rotation Before</th></tr>\n"

    for i, seg in enumerate(data.segments):
        row_class = ' class="bend-row"' if seg.segment_type == 'bend' else ''

        if seg.segment_type == 'bend':
            angle_str = f"{seg.bend_angle:.1f}°"
            rot_str = "—"
        else:
            angle_str = "—"
            rot_str = f"<b>{seg.rotation:.1f}°</b>" if seg.rotation is not None else "—"

        html += f"<tr{row_class}><td class='center'>{i + 1}</td><td>{seg.name}</td>"
        html += f"<td class='right'>{format_length(seg.length, precision, units)}</td>"
        html += f"<td class='right'>{format_length(seg.starts_at, precision, units)}</td>"
        html += f"<td class='right'>{format_length(seg.ends_at, precision, units)}</td>"
        html += f"<td class='right'>{angle_str}</td><td class='right'>{rot_str}</td></tr>\n"

    html += "</table>\n<hr>\n"

    # Bender Setup
    html += "<h3>Bender Setup</h3>\n"
    if data.die_offset > 0:
        html += f"<p><b>Die Offset:</b> {format_length(data.die_offset, precision, units)} "
        html += "(bend tangent point distance from die end)</p>\n"
    else:
        html += "<p><b>Die Offset:</b> Not specified (mark positions show tangent points)</p>\n"

    html += "<table>\n"
    html += "<tr><th class='center'>Bend</th><th class='right'>Mark Position</th>"
    html += "<th>Align Mark To</th><th class='right'>Bend Angle</th><th class='right'>Rotation Before</th></tr>\n"

    for mp in data.mark_positions:
        rot_str = f"<b>{mp.rotation:.1f}°</b>" if mp.rotation is not None else "—"
        html += f"<tr><td class='center'>BEND {mp.bend_num}</td>"
        html += f"<td class='right'>{format_length(mp.mark_position, precision, units)}</td>"
        html += f"<td>Die end</td><td class='right'>{mp.bend_angle:.1f}°</td>"
        html += f"<td class='right'>{rot_str}</td></tr>\n"

    html += "</table>\n"

    # Procedure
    html += '<div class="procedure">\n<p><b>Procedure:</b></p>\n<ol>\n'
    html += f"<li>Cut tube to {format_length(data.total_cut_length, precision, units)}</li>\n"

    if data.extra_material > 0:
        html += f"<li>Note: First {format_length(data.extra_material, precision, units)} "
        html += "is extra grip material (cut off after bending)</li>\n"

    for mp in data.mark_positions:
        if mp.rotation is not None:
            html += f"<li>Rotate tube <b>{mp.rotation:.1f}°</b></li>\n"
        html += f"<li>Mark at {format_length(mp.mark_position, precision, units)} from start "
        html += f"— align mark to die end, bend {mp.bend_angle:.1f}°</li>\n"

    if data.extra_material > 0:
        html += f"<li>Cut off {format_length(data.extra_material, precision, units)} from start of tube</li>\n"

    html += "</ol>\n</div>\n<hr>\n"

    # Specifications
    html += "<h3>Specifications</h3>\n<table class='specs-table'>\n"

    if data.component_name:
        html += f"<tr><td>Component</td><td>{data.component_name}</td></tr>\n"
    html += f"<tr><td>Units</td><td>{units.unit_name}</td></tr>\n"
    html += f"<tr><td>Tube OD</td><td>{data.tube_od}{units.unit_symbol}</td></tr>\n"
    html += f"<tr><td>CLR</td><td>{format_length(data.clr, precision, units)}</td></tr>\n"
    html += f"<tr><td>Die Offset</td><td>{format_length(data.die_offset, precision, units) if data.die_offset > 0 else 'None'}</td></tr>\n"
    html += f"<tr><td>Direction</td><td>{data.travel_direction}</td></tr>\n"
    html += f"<tr><td>Precision</td><td>{get_precision_label(precision, units)}</td></tr>\n"
    html += f"<tr><td>Total Centerline</td><td>{format_length(data.total_centerline, precision, units)}</td></tr>\n"
    html += f"<tr><td>Cut Length</td><td>{format_length(data.total_cut_length, precision, units)}</td></tr>\n"

    if data.extra_material > 0:
        html += f"<tr><td>Extra Grip Material</td><td>{format_length(data.extra_material, precision, units)}</td></tr>\n"
    if data.starts_with_arc:
        html += "<tr><td>Starts With</td><td>Bend</td></tr>\n"
    if data.ends_with_arc:
        html += "<tr><td>Ends With</td><td>Bend</td></tr>\n"

    html += "</table>\n</body>\n</html>"

    return html


def save_and_prompt_open(
    ui: adsk.core.UserInterface,
    html: str,
    component_name: str,
    data: BendSheetData
) -> None:
    """Save HTML file and prompt user to open it."""
    safe_name = (
        component_name.replace(" ", "_").replace("/", "-").replace("\\", "-")
        if component_name
        else "tube_bend_sheet"
    )

    temp_dir = tempfile.gettempdir()
    html_path = os.path.join(temp_dir, f"{safe_name}.html")

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    title = component_name if component_name else "Tube Bend Sheet"
    units = data.units

    result = ui.messageBox(
        f'✓ Bend sheet created successfully!\n\n'
        f'Component: {component_name if component_name else "N/A"}\n'
        f'Cut Length: {format_length(data.total_cut_length, data.precision, units)}\n'
        f'Bends: {len(data.bends)}\n\n'
        f'File saved to:\n{html_path}\n\n'
        'Click YES to open in browser for printing.\n'
        'Click NO to close.',
        title,
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )

    if result == adsk.core.DialogResults.DialogYes:
        webbrowser.open(f'file://{html_path}')


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

# Initialize Fusion 360 application and UI
app: adsk.core.Application = adsk.core.Application.get()
ui: adsk.core.UserInterface = app.userInterface


def run(_context: str) -> None:
    """Main entry point called by Fusion 360 when script is run."""
    try:
        # Get active design and extract unit settings
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox(
                'No active design found.\n\n'
                'Please open a design before running this script.',
                'Error'
            )
            return

        units = UnitConfig.from_design(design)

        # Get selections
        sels = ui.activeSelections

        if sels.count < 3:
            ui.messageBox(
                f'Please select the tube path elements:\n\n'
                f'Select all straight sections (lines) AND bends (arcs).\n\n'
                f'You can select them in any order - the script will auto-detect the path.\n\n'
                f'(Design units: {units.unit_name})',
                'Tube Bend Rotation Calculator'
            )
            return

        # Collect and categorize selections
        all_lines: list[adsk.fusion.SketchLine] = []
        all_arcs: list[adsk.fusion.SketchArc] = []

        for i in range(sels.count):
            entity = sels.item(i).entity

            line = adsk.fusion.SketchLine.cast(entity)
            if line:
                all_lines.append(line)
                continue

            arc = adsk.fusion.SketchArc.cast(entity)
            if arc:
                all_arcs.append(arc)
                continue

            ui.messageBox(
                f'Selection {i+1} is not a sketch line or arc.\n'
                'Please select only sketch lines and arcs.',
                'Error'
            )
            return

        # Validate counts
        num_lines = len(all_lines)
        num_arcs = len(all_arcs)

        valid_combo = (
            (num_lines == num_arcs + 1) or
            (num_lines == num_arcs) or
            (num_lines == num_arcs - 1)
        )

        if not valid_combo or num_lines < 1 or num_arcs < 1:
            ui.messageBox(
                f'Invalid selection: {num_lines} lines and {num_arcs} arcs.\n\n'
                f'Valid patterns:\n'
                f'• Standard (2 bends): 3 lines + 2 arcs\n'
                f'• Ends in bend: 2 lines + 2 arcs\n'
                f'• Starts with bend: 2 lines + 2 arcs\n'
                f'• Both ends bend: 1 line + 2 arcs',
                'Error'
            )
            return

        # Build path elements
        elements: list[PathElement] = []
        for line in all_lines:
            elements.append(PathElement('line', line))
        for arc in all_arcs:
            elements.append(PathElement('arc', arc))

        # Sort by connectivity
        ordered = build_ordered_path(elements)
        if ordered is None:
            ui.messageBox(
                'Could not determine path order.\n\n'
                'Make sure all elements are connected in a single path.',
                'Error'
            )
            return

        # Validate alternation
        is_valid, error_msg = validate_path_alternation(ordered)
        if not is_valid:
            ui.messageBox(
                f'Path structure error: {error_msg}\n\n'
                'The path should alternate: Line-Arc-Line or Arc-Line-Arc...',
                'Error'
            )
            return

        # Extract ordered lines and arcs
        lines = [e.entity for e in ordered if e.element_type == 'line']
        arcs = [e.entity for e in ordered if e.element_type == 'arc']

        starts_with_arc = ordered[0].element_type == 'arc'
        ends_with_arc = ordered[-1].element_type == 'arc'

        # Get component name
        component_name = get_component_name(ordered[0].entity)

        # Get path endpoints
        start_point = get_free_endpoint(ordered[0], ordered)
        end_point = get_free_endpoint(ordered[-1], ordered)

        # Determine direction
        axis, _, current_dir, opposite_dir = determine_primary_axis(start_point, end_point)

        # Prompt for direction
        reverse = prompt_for_direction(
            ui, axis, start_point, end_point,
            current_dir, opposite_dir,
            starts_with_arc, ends_with_arc,
            units
        )
        if reverse is None:
            return

        if reverse:
            lines = lines[::-1]
            arcs = arcs[::-1]
            ordered = ordered[::-1]
            start_point, end_point = end_point, start_point
            starts_with_arc, ends_with_arc = ends_with_arc, starts_with_arc
            travel_direction = opposite_dir
        else:
            travel_direction = current_dir

        # Validate CLR
        clr, clr_mismatch, clr_values = validate_clr_consistency(arcs, units)

        if clr_mismatch:
            clr_list = ", ".join([f'{c:.3f}{units.unit_symbol}' for c in clr_values])
            ui.messageBox(
                f'CLR mismatch detected!\n\n'
                f'Arc CLRs: {clr_list}\n\n'
                'All bends should have the same CLR for a single die setup.',
                'Warning'
            )

        # Get user inputs
        tube_od = prompt_for_tube_od(ui, units)
        if tube_od is None:
            return

        die_offset = prompt_for_die_offset(ui, clr, units)
        if die_offset is None:
            return

        precision = prompt_for_precision(ui, units)
        if precision is None:
            return

        min_grip = prompt_for_min_grip(ui, units)
        if min_grip is None:
            return

        # Calculate straights and bends
        straights, bends = calculate_straights_and_bends(lines, arcs, start_point, clr, units)

        # Calculate extra material
        first_feed = straights[0].length_in - die_offset
        extra_material = max(0.0, min_grip - first_feed) if min_grip > 0 else 0.0

        # Build segments and marks
        segments, mark_positions = build_segments_and_marks(
            straights, bends, extra_material, die_offset
        )

        # Calculate totals
        total_straights = sum(s.length_in for s in straights)
        total_arcs = sum(b.arc_length for b in bends)
        total_centerline = total_straights + total_arcs
        total_cut_length = total_centerline + extra_material

        # Build data object
        sheet_data = BendSheetData(
            component_name=component_name,
            tube_od=tube_od,
            clr=clr,
            die_offset=die_offset,
            precision=precision,
            min_grip=min_grip,
            travel_direction=travel_direction,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
            clr_mismatch=clr_mismatch,
            clr_values=clr_values,
            continuity_errors=[],  # Already validated via connectivity
            straights=straights,
            bends=bends,
            segments=segments,
            mark_positions=mark_positions,
            extra_material=extra_material,
            total_centerline=total_centerline,
            total_cut_length=total_cut_length,
            units=units
        )

        # Generate and save HTML
        html = generate_html_bend_sheet(sheet_data)
        save_and_prompt_open(ui, html, component_name, sheet_data)

    except Exception as e:
        # Log full traceback for debugging
        app.log(f'TubeBendRotation failed:\n{traceback.format_exc()}')
        ui.messageBox(
            f'An error occurred:\n\n{str(e)}\n\n'
            'Check the Text Commands window for details.',
            'Error'
        )