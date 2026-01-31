"""Grip and tail material calculation for bend sheets.

This module calculates the extra material needed at the start (grip) and
end (tail) of a tube for bending operations. It handles:
- Paths starting/ending with arcs (synthetic grip/tail material)
- First straight section shorter than min_grip
- Grip/tail violation detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import StraightSection


@dataclass(slots=True)
class MaterialCalculation:
    """Result of grip/tail material calculations.

    Attributes:
        extra_material: Total extra material to add at the start
        synthetic_grip_material: Material added for paths starting with arc
        synthetic_tail_material: Material added for paths ending with arc
        has_synthetic_grip: Whether synthetic grip material was added
        has_synthetic_tail: Whether synthetic tail material was added
        grip_cut_position: Position to cut grip material from start (if synthetic)
        grip_violations: List of straight section numbers shorter than min_grip
        tail_violation: Whether last straight is shorter than min_tail
    """

    extra_material: float
    synthetic_grip_material: float
    synthetic_tail_material: float
    has_synthetic_grip: bool
    has_synthetic_tail: bool
    grip_cut_position: float | None
    grip_violations: list[int] = field(default_factory=list)
    tail_violation: bool = False


def calculate_material_requirements(
    straights: list["StraightSection"],
    min_grip: float,
    min_tail: float,
    die_offset: float,
    starts_with_arc: bool,
    ends_with_arc: bool,
    extra_allowance: float = 0.0,
) -> MaterialCalculation:
    """Calculate grip and tail material requirements.

    Determines how much extra material is needed at the start and end of
    a tube for proper bender operation, and detects any grip/tail violations.

    Args:
        straights: List of straight sections in the path
        min_grip: Minimum grip length required by the bender
        min_tail: Minimum tail length required after last bend
        die_offset: Die offset value (distance from die center to bend point)
        starts_with_arc: Whether path starts with an arc (needs synthetic grip)
        ends_with_arc: Whether path ends with an arc (needs synthetic tail)
        extra_allowance: Extra material added to each end for alignment tolerance

    Returns:
        MaterialCalculation with all grip/tail values and violation flags
    """
    # Track synthetic grip/tail additions
    has_synthetic_grip = False
    has_synthetic_tail = False
    grip_cut_position: float | None = None

    # Handle path starting with bend - add synthetic grip material
    synthetic_grip_material: float = 0.0
    if starts_with_arc and min_grip > 0:
        synthetic_grip_material = min_grip
        has_synthetic_grip = True
        grip_cut_position = min_grip

    # Handle path ending with bend - add synthetic tail material
    synthetic_tail_material: float = 0.0
    if ends_with_arc and min_tail > 0:
        synthetic_tail_material = min_tail
        has_synthetic_tail = True

    # Handle single-arc paths (no straights) - use synthetic grip/tail only
    if not straights:
        return MaterialCalculation(
            extra_material=synthetic_grip_material,
            synthetic_grip_material=synthetic_grip_material,
            synthetic_tail_material=synthetic_tail_material,
            has_synthetic_grip=has_synthetic_grip,
            has_synthetic_tail=has_synthetic_tail,
            grip_cut_position=grip_cut_position,
            grip_violations=[],
            tail_violation=False,
        )

    first_feed: float = straights[0].length - die_offset
    extra_grip_material: float = (
        max(0.0, min_grip - first_feed) if min_grip > 0 else 0.0
    )

    # Total extra material at start = max of synthetic grip or regular grip material
    extra_material: float = max(extra_grip_material, synthetic_grip_material)
    if has_synthetic_grip:
        extra_material = synthetic_grip_material

    # Validate straight sections against min_grip (all except last)
    # First straight gets extra_allowance added to its effective length
    grip_violations: list[int] = []
    if min_grip > 0 and len(straights) > 1:
        sections_to_check = straights[:-1]  # All except the last one
        for straight in sections_to_check:
            effective_length = straight.length
            # First straight benefits from extra allowance at start
            if straight.number == 1:
                effective_length += extra_allowance
            if effective_length < min_grip:
                grip_violations.append(straight.number)

    # Validate last straight section against min_tail
    # Last straight gets extra_allowance added to its effective length
    tail_violation: bool = False
    if min_tail > 0 and len(straights) > 0:
        last_straight = straights[-1]
        effective_tail_length = last_straight.length + extra_allowance
        if effective_tail_length < min_tail:
            tail_violation = True

    return MaterialCalculation(
        extra_material=extra_material,
        synthetic_grip_material=synthetic_grip_material,
        synthetic_tail_material=synthetic_tail_material,
        has_synthetic_grip=has_synthetic_grip,
        has_synthetic_tail=has_synthetic_tail,
        grip_cut_position=grip_cut_position,
        grip_violations=grip_violations,
        tail_violation=tail_violation,
    )
