"""Bend calculation logic."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from ..models.types import Vector3D, Point3D


class ArcLike(Protocol):
    """Protocol for objects with a radius property.

    This enables testing with mock objects that have a radius attribute
    but without Fusion API dependencies.
    """

    @property
    def radius(self) -> float: ...


class UnitConfigLike(Protocol):
    """Protocol for objects with unit conversion properties.

    This enables testing with mock objects without importing the full UnitConfig.
    """

    @property
    def cm_to_unit(self) -> float: ...
from .geometry import (
    cross_product,
    magnitude,
    angle_between_vectors,
    calculate_rotation,
    distance_between_points,
    ZERO_MAGNITUDE_TOLERANCE,
)
from .path_analysis import get_sketch_entity_endpoints
from .tolerances import CLR_RATIO, CLR_MIN_FLOOR

if TYPE_CHECKING:
    import adsk.fusion

from ..models.bend_data import StraightSection, BendData, PathSegment, MarkPosition
from ..models.units import UnitConfig

# Re-export for backward compatibility
CLR_TOLERANCE_RATIO: float = CLR_RATIO


def validate_clr_consistency(
    arcs: Sequence[ArcLike],
    units: UnitConfigLike
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

    # Check for invalid CLR values: NaN, infinity, zero, or negative
    # NaN comparisons always return False, so we must check explicitly
    if math.isnan(clr) or math.isinf(clr) or clr <= 0:
        return 0.0, True, clr_values

    # Check if any values in the list are invalid
    if any(math.isnan(c) or math.isinf(c) for c in clr_values):
        return clr, True, clr_values

    # Use ratio-based tolerance (0.2% of CLR) with minimum floor
    # The minimum floor prevents false mismatches with very small CLR values
    tolerance = max(clr * CLR_TOLERANCE_RATIO, CLR_MIN_FLOOR)
    has_mismatch = any(abs(c - clr) > tolerance for c in clr_values)

    return clr, has_mismatch, clr_values


def calculate_straights_and_bends(
    lines: list['adsk.fusion.SketchLine'],
    arcs: list['adsk.fusion.SketchArc'],
    path_start: Point3D,
    clr: float,
    units: UnitConfig,
    starts_with_arc: bool = False,
    ends_with_arc: bool = False,
) -> tuple[list[StraightSection], list[BendData]]:
    """
    Calculate all straight sections and bend data from geometry.

    Args:
        lines: Ordered list of sketch lines
        arcs: Ordered list of sketch arcs
        path_start: The starting point of the path (in cm)
        clr: Center line radius in display units
        units: Unit configuration for conversion
        starts_with_arc: Whether the path starts with an arc (no incoming vector)
        ends_with_arc: Whether the path ends with an arc (no outgoing vector)

    Returns:
        Tuple of (straights, bends) with lengths in display units
    """
    # Get line endpoints and orient them correctly
    line_points: list[tuple[Point3D, Point3D]] = []
    for line in lines:
        start, end = get_sketch_entity_endpoints(line)
        line_points.append((start, end))

    # Handle single-arc path (no lines) - valid for arc-only bend sheets
    if not line_points:
        straights: list[StraightSection] = []
        bends: list[BendData] = []

        for i, arc in enumerate(arcs):
            # Calculate bend angle from arc geometry (sweep angle)
            center = arc.centerSketchPoint.worldGeometry
            arc_start = arc.startSketchPoint.worldGeometry
            arc_end = arc.endSketchPoint.worldGeometry

            v_start: Vector3D = (
                arc_start.x - center.x,
                arc_start.y - center.y,
                arc_start.z - center.z,
            )
            v_end: Vector3D = (
                arc_end.x - center.x,
                arc_end.y - center.y,
                arc_end.z - center.z,
            )

            bend_angle = angle_between_vectors(v_start, v_end)
            arc_length = clr * math.radians(bend_angle)

            bends.append(BendData(
                number=i + 1,
                angle=bend_angle,
                rotation=None,  # No rotation for single arc
                arc_length=arc_length
            ))

        return straights, bends

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
            length=length_display,
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
    
    # Validate all vectors are non-zero (zero-length lines cannot define bend planes)
    for i, v in enumerate(vectors):
        if magnitude(v) < ZERO_MAGNITUDE_TOLERANCE:
            raise ValueError(
                f"Line {i + 1} has zero length - cannot calculate bend plane"
            )

    # Calculate expected vector count based on path structure
    # Standard: line-arc-line needs vectors = arcs + 1
    # Arc-first: arc-line-arc needs vectors = arcs (missing incoming vector for first arc)
    # Arc-last: line-arc-line-arc needs vectors = arcs (missing outgoing vector for last arc)
    # Both: arc-line-arc needs vectors = arcs - 1
    expected_vectors = len(arcs) + 1
    if starts_with_arc:
        expected_vectors -= 1
    if ends_with_arc:
        expected_vectors -= 1

    if len(vectors) < expected_vectors:
        raise ValueError(
            f"Insufficient vectors ({len(vectors)}) for {len(arcs)} arcs - "
            f"expected at least {expected_vectors} vectors"
        )

    # Calculate bend plane normals where possible
    # For arcs at path ends without adjacent vectors, we skip normal calculation
    normals: list[Vector3D | None] = []
    for i in range(len(arcs)):
        # Determine vector indices for this arc
        # When starts_with_arc, arc indices are shifted: arc 0 uses vectors[0] as outgoing
        incoming_idx = i if not starts_with_arc else i - 1
        outgoing_idx = incoming_idx + 1

        # Check if we have both vectors for normal calculation
        if incoming_idx >= 0 and outgoing_idx < len(vectors):
            n = cross_product(vectors[incoming_idx], vectors[outgoing_idx])
            normals.append(n)
        else:
            normals.append(None)

    # Calculate bend angles and rotations
    bends: list[BendData] = []
    for i in range(len(arcs)):
        arc = arcs[i]
        # Determine vector indices for this arc
        incoming_idx = i if not starts_with_arc else i - 1
        outgoing_idx = incoming_idx + 1

        # Calculate bend angle
        if incoming_idx >= 0 and outgoing_idx < len(vectors):
            # Standard case: compute from adjacent vectors
            bend_angle = angle_between_vectors(vectors[incoming_idx], vectors[outgoing_idx])
        else:
            # Arc at path end: use arc's geometric sweep angle
            # Get center and endpoints to calculate sweep angle
            center = arc.centerSketchPoint.worldGeometry
            arc_start = arc.startSketchPoint.worldGeometry
            arc_end = arc.endSketchPoint.worldGeometry

            # Vectors from center to start and end
            v_start: Vector3D = (
                arc_start.x - center.x,
                arc_start.y - center.y,
                arc_start.z - center.z,
            )
            v_end: Vector3D = (
                arc_end.x - center.x,
                arc_end.y - center.y,
                arc_end.z - center.z,
            )

            # Sweep angle is the angle between these radius vectors
            bend_angle = angle_between_vectors(v_start, v_end)

        arc_length = clr * math.radians(bend_angle)

        # Calculate rotation from previous bend (if applicable)
        rotation: float | None = None
        if i > 0 and normals[i - 1] is not None and normals[i] is not None:
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
    die_offset: float,
) -> tuple[list[PathSegment], list[MarkPosition]]:
    """
    Build cumulative path segments and mark positions.

    Args:
        straights: List of straight sections
        bends: List of bend data
        extra_material: Extra grip material at start
        die_offset: Die offset in display units

    Returns:
        Tuple of (segments, mark_positions)

    Note:
        Die offset moves the mark toward the straight section before the bend.
        The mark position is always measured from the start of the tube.
    """
    segments: list[PathSegment] = []
    cumulative = extra_material
    
    for i, straight in enumerate(straights):
        # Add straight segment
        segments.append(PathSegment(
            segment_type='straight',
            name=f'Straight {straight.number}',
            length=straight.length,
            starts_at=cumulative,
            ends_at=cumulative + straight.length,
            bend_angle=None,
            rotation=bends[i].rotation if i < len(bends) else None
        ))
        cumulative += straight.length
        
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
        
        # Die offset moves mark toward the straight before the bend.
        # This is always a subtraction since mark_position is measured from
        # the start of the tube (as laid out in the bend sheet).
        adjusted_mark = bend_starts_at - die_offset

        mark_positions.append(MarkPosition(
            bend_num=bend.number,
            mark_position=adjusted_mark,
            bend_angle=bend.angle,
            rotation=bend.rotation
        ))
    
    return segments, mark_positions
