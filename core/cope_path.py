"""Extract cope geometry from bend-sheet path data.

Pure functions that derive tube direction and extrados reference from
StraightSection and BendData lists. Zero Fusion dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ..models.bend_data import BendData, StraightSection
from ..models.types import Point3D, Vector3D
from .geometry import dot_product, magnitude, normalize, vectors_are_collinear
from .tolerances import COPE_AXIS_SKEW_RATIO, ZERO_MAGNITUDE


@dataclass(slots=True)
class EndReference:
    """Tube direction and extrados reference at one end of the path.

    Attributes:
        tube_direction: Unit vector pointing outward from the cope end.
        extrados_direction: Unit vector toward the back-of-bend (extrados)
            relative to the last bend. None when no bends exist.
        straight_length: Length of the terminal straight section
            (display units, matching StraightSection.length).
    """
    tube_direction: Vector3D
    extrados_direction: Vector3D | None
    straight_length: float


def compute_end_reference(
    straights: list[StraightSection],
    bends: list[BendData],
    end: Literal["start", "end"],
) -> EndReference:
    """Derive tube direction and extrados reference for a cope end.

    Args:
        straights: Ordered straight sections from the bend sheet.
        bends: Ordered bends from the bend sheet.
        end: Which end of the tube path to compute for.

    Returns:
        EndReference with tube direction, extrados (if bends exist),
        and terminal straight length.

    Raises:
        ValueError: If straights is empty.
    """
    if not straights:
        raise ValueError("Cannot compute end reference from empty straights list")

    if end == "end":
        return _end_reference(straights, bends)
    return _start_reference(straights, bends)


def _end_reference(
    straights: list[StraightSection],
    bends: list[BendData],
) -> EndReference:
    """Compute reference at the end of the path."""
    terminal = straights[-1]
    tube_dir = normalize(terminal.vector)

    extrados: Vector3D | None = None
    if len(straights) >= 2 and bends:
        v_in = straights[-2].vector
        v_out = terminal.vector
        extrados = _compute_extrados(v_in, v_out)

    return EndReference(
        tube_direction=tube_dir,
        extrados_direction=extrados,
        straight_length=terminal.length,
    )


def _start_reference(
    straights: list[StraightSection],
    bends: list[BendData],
) -> EndReference:
    """Compute reference at the start of the path."""
    terminal = straights[0]
    v = terminal.vector
    tube_dir = normalize((-v[0], -v[1], -v[2]))

    extrados: Vector3D | None = None
    if len(straights) >= 2 and bends:
        # Walk the path toward the start end: reverse both vectors so
        # v_in/v_out follow the direction of travel into the cope end.
        s1 = straights[1].vector
        v_in = (-s1[0], -s1[1], -s1[2])
        v_out = (-v[0], -v[1], -v[2])
        extrados = _compute_extrados(v_in, v_out)

    return EndReference(
        tube_direction=tube_dir,
        extrados_direction=extrados,
        straight_length=terminal.length,
    )


def _compute_extrados(v_in: Vector3D, v_out: Vector3D) -> Vector3D | None:
    """Compute extrados direction from the vectors on either side of a bend.

    The extrados (back-of-bend) is the direction that points away from
    the bend center. Given the straight *before* the bend (v_in) and the
    straight *after* the bend (v_out), both oriented in the direction of
    travel toward the cope end, the extrados on the v_out straight is:

        extrados = normalize(v_in - dot(v_in, v_out_hat) * v_out_hat)

    where v_out_hat = normalize(v_out). The path turns toward the bend
    center, so v_in's component perpendicular to v_out points away from it.

    Returns None if the vectors are collinear (no bend) or if either
    vector has zero length.
    """
    mag_in = magnitude(v_in)
    mag_out = magnitude(v_out)
    if mag_in < ZERO_MAGNITUDE or mag_out < ZERO_MAGNITUDE:
        return None

    if vectors_are_collinear(v_in, v_out):
        return None

    v_out_hat = normalize(v_out)
    proj = dot_product(v_in, v_out_hat)
    # Component of v_in perpendicular to v_out
    perp = (
        v_in[0] - proj * v_out_hat[0],
        v_in[1] - proj * v_out_hat[1],
        v_in[2] - proj * v_out_hat[2],
    )

    perp_mag = magnitude(perp)
    if perp_mag < ZERO_MAGNITUDE:
        return None

    # v_in's perpendicular component already points away from bend center
    return (
        perp[0] / perp_mag,
        perp[1] / perp_mag,
        perp[2] / perp_mag,
    )


def compute_long_point_adjustment(
    end_point: Point3D,
    tube_direction: Vector3D,
    receiver_origin: Point3D,
    receiver_axis: Vector3D,
    z_min: float,
    od_radius: float,
) -> float | None:
    """Length to add at a cope end so the tube ends at the cope's long point.

    The saddle formula measures z back along the incoming tube from where
    its centerline crosses the receiver's centerline; the long point (where
    the template's TUBE END edge goes) is z_min behind that crossing.  The
    modelled tube may end anywhere — at the long point if it was coped in
    the model, or at the receiver's surface/centerline if it was not.

    All arguments share one length unit (the result is in that unit).

    Args:
        end_point: Centerline end point of the modelled tube.
        tube_direction: Unit vector pointing outward from this end.
        receiver_origin: Any point on the receiving tube's centerline.
        receiver_axis: Receiving tube axis direction (either sign).
        z_min: Minimum of the cope z-profile (long-point offset from the
            centerline crossing).
        od_radius: Incoming tube OD radius, used for the skew tolerance.

    Returns:
        Signed length to add to the terminal straight (negative = trim),
        or None when the centerlines are parallel or too far from
        intersecting for the formula's long point to be trusted.
    """
    try:
        v1 = normalize(tube_direction)
        a = normalize(receiver_axis)
    except ValueError:
        return None

    b = dot_product(v1, a)
    denom = 1.0 - b * b
    if denom < ZERO_MAGNITUDE:
        return None

    w0 = (
        end_point[0] - receiver_origin[0],
        end_point[1] - receiver_origin[1],
        end_point[2] - receiver_origin[2],
    )
    d = dot_product(v1, w0)
    e = dot_product(a, w0)
    # Closest points: end_point + s*v1 on the tube, receiver_origin + u*a
    s = (b * e - d) / denom
    u = (e - b * d) / denom
    gap = (
        w0[0] + s * v1[0] - u * a[0],
        w0[1] + s * v1[1] - u * a[1],
        w0[2] + s * v1[2] - u * a[2],
    )
    if magnitude(gap) > COPE_AXIS_SKEW_RATIO * od_radius:
        return None

    # Crossing is s ahead of the modelled end; long point is z_min behind it
    return s - z_min


def apply_end_length_adjustments(
    straights: list[StraightSection],
    start_adjustment: float | None,
    end_adjustment: float | None,
) -> list[StraightSection]:
    """Lengthen/trim the end straights so coped ends finish at their long point.

    Args:
        straights: Straights in path order (display units).
        start_adjustment: Length to add to the first straight, or None.
        end_adjustment: Length to add to the last straight, or None.

    Returns:
        A new list; the input sections are not modified. Lengths never go
        below zero. With a single straight both adjustments apply to it.
    """
    adjusted = list(straights)
    if not adjusted:
        return adjusted
    for idx, delta in ((0, start_adjustment), (len(adjusted) - 1, end_adjustment)):
        if delta is None:
            continue
        section = adjusted[idx]
        adjusted[idx] = replace(section, length=max(0.0, section.length + delta))
    return adjusted
