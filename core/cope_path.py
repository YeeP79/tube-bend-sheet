"""Extract cope geometry from bend-sheet path data.

Pure functions that derive tube direction and extrados reference from
StraightSection and BendData lists. Zero Fusion dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..models.bend_data import BendData, StraightSection
from ..models.types import Vector3D
from .geometry import dot_product, magnitude, normalize, vectors_are_collinear
from .tolerances import ZERO_MAGNITUDE


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
        v_in = straights[1].vector
        v_out = terminal.vector
        extrados = _compute_extrados(v_in, v_out)

    return EndReference(
        tube_direction=tube_dir,
        extrados_direction=extrados,
        straight_length=terminal.length,
    )


def _compute_extrados(v_in: Vector3D, v_out: Vector3D) -> Vector3D | None:
    """Compute extrados direction from the vectors on either side of a bend.

    The extrados (back-of-bend) is the direction that points away from
    the bend centre. Given the straight *before* the bend (v_in) and the
    straight *after* the bend (v_out), the extrados at the v_out end is:

        extrados = -normalize(v_in - dot(v_in, v_out_hat) * v_out_hat)

    where v_out_hat = normalize(v_out).

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

    # Negate: extrados points *away* from bend centre
    return (
        -perp[0] / perp_mag,
        -perp[1] / perp_mag,
        -perp[2] / perp_mag,
    )
