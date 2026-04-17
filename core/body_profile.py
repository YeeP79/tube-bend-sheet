"""Body segment processing for body-to-sketch matching.

Merges coaxial cylinder faces, determines OD, and filters to OD-only
segments. Fusion-free — operates entirely on BodyStraight/BodyBend
dataclasses.
"""

from __future__ import annotations

from ..models.match_data import BodyBend, BodyProfile, BodyStraight
from .geometry import point_to_line_distance, unsigned_angle_between, ZeroVectorError
from .tolerances import (
    COAXIAL_MERGE_ANGLE_DEG,
    COAXIAL_MERGE_DISTANCE_CM,
    OD_FILTER_TOLERANCE_CM,
)


def merge_coaxial_straights(
    straights: list[BodyStraight],
    angle_tol: float = COAXIAL_MERGE_ANGLE_DEG,
    dist_tol: float = COAXIAL_MERGE_DISTANCE_CM,
) -> list[BodyStraight]:
    """Merge cylinder faces that share the same axis.

    Cylinder faces on the same tube section get split by boolean
    operations (cope cuts, trims). This merges them back by checking
    axis alignment and perpendicular distance.

    Args:
        straights: Raw cylinder segments extracted from the body.
        angle_tol: Maximum angle between axes (degrees) to consider coaxial.
        dist_tol: Maximum perpendicular distance between axes (cm).

    Returns:
        Merged list of BodyStraight segments.
    """
    if not straights:
        return []

    merged: list[BodyStraight] = [BodyStraight(
        axis=straights[0].axis,
        origin=straights[0].origin,
        radius=straights[0].radius,
        length=straights[0].length,
        centroid=straights[0].centroid,
    )]

    for seg in straights[1:]:
        found_merge = False
        for m in merged:
            try:
                angle = unsigned_angle_between(seg.axis, m.axis)
            except ZeroVectorError:
                continue

            if angle < angle_tol:
                dist = point_to_line_distance(seg.origin, m.origin, m.axis)
                if dist < dist_tol and abs(seg.radius - m.radius) < OD_FILTER_TOLERANCE_CM:
                    m.length = max(m.length, seg.length)
                    found_merge = True
                    break

        if not found_merge:
            merged.append(BodyStraight(
                axis=seg.axis,
                origin=seg.origin,
                radius=seg.radius,
                length=seg.length,
                centroid=seg.centroid,
            ))

    return merged


def determine_od_radius(straights: list[BodyStraight]) -> float:
    """Determine the outer-diameter radius from merged straights.

    The OD is the largest cylinder radius found. Inner bore cylinders
    will have a smaller radius.

    Args:
        straights: Merged cylinder segments.

    Returns:
        OD radius in cm. Returns 0.0 if straights is empty.
    """
    if not straights:
        return 0.0
    return max(s.radius for s in straights)


def filter_od_straights(
    straights: list[BodyStraight],
    od_radius: float,
    tol: float = OD_FILTER_TOLERANCE_CM,
) -> list[BodyStraight]:
    """Keep only cylinder segments whose radius matches the OD.

    Args:
        straights: Merged cylinder segments.
        od_radius: The detected OD radius (cm).
        tol: Radius matching tolerance (cm).

    Returns:
        Filtered list containing only OD segments.
    """
    return [s for s in straights if abs(s.radius - od_radius) < tol]


def filter_od_bends(
    bends: list[BodyBend],
    od_radius: float,
    tol: float = OD_FILTER_TOLERANCE_CM,
) -> list[BodyBend]:
    """Keep only torus faces whose minor radius matches the OD.

    Args:
        bends: Raw bend segments from the body.
        od_radius: The detected OD radius (cm).
        tol: Radius matching tolerance (cm).

    Returns:
        Filtered list containing only OD bend segments.
    """
    return [b for b in bends if abs(b.minor_radius - od_radius) < tol]


def build_body_profile(
    raw_straights: list[BodyStraight],
    raw_bends: list[BodyBend],
) -> BodyProfile:
    """Build a processed BodyProfile from raw extracted segments.

    Pipeline:
    1. Merge coaxial cylinder faces.
    2. Determine OD radius from merged straights.
    3. Filter to OD-only straights and bends.

    Args:
        raw_straights: Unprocessed cylinder segments.
        raw_bends: Unprocessed torus segments.

    Returns:
        A BodyProfile ready for sketch matching.
    """
    merged = merge_coaxial_straights(raw_straights)
    od_radius = determine_od_radius(merged)
    od_straights = filter_od_straights(merged, od_radius)
    od_bends = filter_od_bends(raw_bends, od_radius)

    return BodyProfile(
        straights=od_straights,
        bends=od_bends,
        od_radius=od_radius,
    )
