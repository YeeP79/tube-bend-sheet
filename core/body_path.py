"""Convert body face topology to bend sheet data.

Pure Python module. Takes a BodyPathResult (extracted from a BRepBody's
face adjacency graph) and produces the same StraightSection[] + BendData[]
that calculate_straights_and_bends() produces from sketch geometry.

Zero Fusion 360 dependencies. Fully unit-testable.
"""

from __future__ import annotations

import math

from ..models.types import Vector3D, Point3D
from ..models.body_path_data import BodyFaceSegment, BodyPathResult
from ..models.bend_data import StraightSection, BendData
from ..models.units import UnitConfig
from .geometry import (
    cross_product,
    magnitude,
    normalize,
    subtract_vectors,
    calculate_rotation,
)
from .tolerances import ZERO_MAGNITUDE


def body_path_to_straights_and_bends(
    path: BodyPathResult,
    units: UnitConfig,
) -> tuple[list[StraightSection], list[BendData], float]:
    """Convert body path segments to bend sheet input data.

    Walks the ordered segments, numbers straights and bends, converts
    units, computes bend angles, rotations, and arc lengths.

    Args:
        path: Extraction result from body face topology.
        units: Unit configuration for display conversion.

    Returns:
        Tuple of (straights, bends, clr_display) where:
        - straights: Straight sections with lengths in display units.
        - bends: Bend data with angles, rotations, arc lengths.
        - clr_display: Primary CLR in display units.
    """
    straights: list[StraightSection] = []
    bends: list[BendData] = []
    vectors: list[Vector3D] = []

    straight_num = 0
    bend_num = 0

    for seg in path.segments:
        if seg.face_type == "straight":
            straight_num += 1
            vector = _get_straight_vector(seg)
            vectors.append(vector)

            length_cm = seg.length
            length_display = length_cm * units.cm_to_unit

            # Convert endpoints to display units
            start_display = _scale_point(
                seg.start_center or seg.origin or (0.0, 0.0, 0.0),
                units.cm_to_unit,
            )
            end_display = _scale_point(
                seg.end_center or seg.origin or (0.0, 0.0, 0.0),
                units.cm_to_unit,
            )

            straights.append(StraightSection(
                number=straight_num,
                length=length_display,
                start=start_display,
                end=end_display,
                vector=vector,  # Internal units (cm)
            ))

        elif seg.face_type == "bend":
            bend_num += 1
            bend_angle = seg.bend_angle
            clr_cm = seg.clr
            arc_length_display = (clr_cm * math.radians(bend_angle)) * units.cm_to_unit

            # Compute rotation from adjacent straight vectors
            rotation = _compute_bend_rotation(
                bend_num, vectors, path.segments, seg,
            )

            bends.append(BendData(
                number=bend_num,
                angle=bend_angle,
                rotation=rotation,
                arc_length=arc_length_display,
            ))

    # Primary CLR in display units
    clr_display = path.clr_values[0] * units.cm_to_unit if path.clr_values else 0.0

    return straights, bends, clr_display


def detect_path_direction(
    path: BodyPathResult,
) -> tuple[str, str, str]:
    """Detect primary travel axis and direction labels from path endpoints.

    Args:
        path: Body path result with start/end points.

    Returns:
        Tuple of (primary_axis, travel_direction, opposite_direction).
        Uses Fusion 360 coordinate system names:
        - X axis: Left (-X) / Right (+X)
        - Y axis: Bottom (-Y) / Top (+Y)
        - Z axis: Front (-Z) / Back (+Z)
    """
    start = path.start_point
    end = path.end_point

    displacement = (
        end[0] - start[0],
        end[1] - start[1],
        end[2] - start[2],
    )
    abs_disp = (abs(displacement[0]), abs(displacement[1]), abs(displacement[2]))
    max_disp = max(abs_disp)

    direction_names: dict[str, tuple[str, str]] = {
        "X": ("Left", "Right"),
        "Y": ("Bottom", "Top"),
        "Z": ("Front", "Back"),
    }

    if abs_disp[0] == max_disp:
        axis, idx = "X", 0
    elif abs_disp[1] == max_disp:
        axis, idx = "Y", 1
    else:
        axis, idx = "Z", 2

    neg_name, pos_name = direction_names[axis]
    if displacement[idx] > 0:
        current = pos_name
        opposite = neg_name
    else:
        current = neg_name
        opposite = pos_name

    return axis, current, opposite


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_straight_vector(seg: BodyFaceSegment) -> Vector3D:
    """Compute direction vector for a straight segment.

    Prefers using circle edge centers (start_center → end_center) for
    accurate direction. Falls back to the cylinder axis direction
    scaled by length.

    Args:
        seg: A straight-type BodyFaceSegment.

    Returns:
        Direction vector in cm (not normalised).
    """
    if seg.start_center is not None and seg.end_center is not None:
        return subtract_vectors(seg.end_center, seg.start_center)

    # Fallback: use axis * length
    if seg.axis is not None:
        mag = magnitude(seg.axis)
        if mag > ZERO_MAGNITUDE:
            unit_axis = normalize(seg.axis)
            return (
                unit_axis[0] * seg.length,
                unit_axis[1] * seg.length,
                unit_axis[2] * seg.length,
            )

    return (0.0, 0.0, 0.0)


def _scale_point(point: Point3D, factor: float) -> Point3D:
    """Scale a point by a conversion factor."""
    return (point[0] * factor, point[1] * factor, point[2] * factor)


def _compute_bend_rotation(
    bend_num: int,
    vectors: list[Vector3D],
    segments: list[BodyFaceSegment],
    current_bend: BodyFaceSegment,
) -> float | None:
    """Compute rotation angle for a bend from adjacent straight vectors.

    Uses the cross-product method: the bend plane normal is the cross
    product of the incoming and outgoing straight vectors. Rotation is
    the angle between consecutive bend plane normals.

    Args:
        bend_num: 1-based bend number.
        vectors: List of straight vectors accumulated so far.
        segments: All path segments.
        current_bend: The current bend segment.

    Returns:
        Rotation angle in degrees, or None for the first bend.
    """
    if bend_num <= 1:
        return None

    # We need at least 3 straight vectors to compute a rotation:
    # vectors[-2] is the incoming for the previous bend
    # vectors[-1] is the outgoing for the previous bend / incoming for current
    # The next straight (not yet in vectors) is the outgoing for current bend.
    # But vectors only has straights seen so far, and the outgoing straight for
    # the current bend hasn't been added yet.

    # For bend N (1-based), we need vectors at indices:
    # prev bend: incoming = vectors[bend_num-2], outgoing = vectors[bend_num-1]
    # curr bend: incoming = vectors[bend_num-1], outgoing = vectors[bend_num]
    # But vectors[bend_num] hasn't been added yet — find it from segments.

    incoming_idx_prev = bend_num - 2  # 0-based index for prev bend incoming
    outgoing_idx_prev = bend_num - 1  # 0-based index for prev bend outgoing

    incoming_idx_curr = bend_num - 1  # Same as prev outgoing
    # The outgoing vector for the current bend is the NEXT straight after this bend
    outgoing_vector_curr = _find_next_straight_vector(segments, current_bend)

    if outgoing_vector_curr is None:
        return None

    if incoming_idx_prev < 0 or outgoing_idx_prev >= len(vectors):
        return None
    if incoming_idx_curr >= len(vectors):
        return None

    # Compute bend plane normals
    prev_normal = cross_product(vectors[incoming_idx_prev], vectors[outgoing_idx_prev])
    curr_normal = cross_product(vectors[incoming_idx_curr], outgoing_vector_curr)

    prev_mag = magnitude(prev_normal)
    curr_mag = magnitude(curr_normal)

    if prev_mag < ZERO_MAGNITUDE or curr_mag < ZERO_MAGNITUDE:
        return None

    return calculate_rotation(prev_normal, curr_normal)


def _find_next_straight_vector(
    segments: list[BodyFaceSegment],
    bend_seg: BodyFaceSegment,
) -> Vector3D | None:
    """Find the direction vector of the straight segment after a bend.

    Args:
        segments: All ordered path segments.
        bend_seg: The bend segment to search after.

    Returns:
        Direction vector (cm) or None if no straight follows.
    """
    found_bend = False
    for seg in segments:
        if seg is bend_seg:
            found_bend = True
            continue
        if found_bend and seg.face_type == "straight":
            vec = _get_straight_vector(seg)
            if magnitude(vec) > ZERO_MAGNITUDE:
                return vec
            return None
    return None
