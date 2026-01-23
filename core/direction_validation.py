"""Direction-aware validation for bend sequences.

This module provides validation functions to check if a bend sequence
can be fabricated in a given direction, considering grip and tail
requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import StraightSection


@dataclass(slots=True)
class GripValidationResult:
    """Result of grip/tail validation for a given direction."""

    is_valid: bool
    violations: list[int] = field(default_factory=list)  # Straight section numbers
    error_message: str = ""


@dataclass(slots=True)
class DirectionValidationResult:
    """Result of direction-aware validation."""

    can_fabricate: bool
    current_direction_valid: bool
    reversed_direction_valid: bool
    violations: list[int] = field(default_factory=list)
    error_message: str = ""
    suggestion: str = ""


def validate_grip_for_direction(
    straights: list[StraightSection],
    min_grip: float,
    min_tail: float,
    reversed: bool = False,
) -> GripValidationResult:
    """
    Validate if bend sequence is possible in given direction.

    For normal direction:
      - straights[:-1] must be >= min_grip (grip before each bend)
      - straights[-1] must be >= min_tail

    For reversed direction:
      - straights[0] must be >= min_tail (now the tail)
      - straights[1:] must be >= min_grip (grip before each bend)

    Args:
        straights: List of straight sections in order
        min_grip: Minimum grip length required
        min_tail: Minimum tail length required
        reversed: Whether to check reversed direction

    Returns:
        GripValidationResult with validity and any violations
    """
    if len(straights) <= 1:
        # Single or no straights - no middle sections to validate
        return GripValidationResult(is_valid=True)

    violations: list[int] = []

    if reversed:
        # Reversed: first becomes tail, rest need grip
        # Check middle sections (indices 1 to n-2) for min_grip
        for straight in straights[1:-1]:
            if min_grip > 0 and straight.length < min_grip:
                violations.append(straight.number)
    else:
        # Normal: last is tail, first and middle need grip
        # Check middle sections (indices 1 to n-2) for min_grip
        for straight in straights[1:-1]:
            if min_grip > 0 and straight.length < min_grip:
                violations.append(straight.number)

    if violations:
        direction_str = "reversed" if reversed else "current"
        sections_str = ", ".join(f"Straight {n}" for n in violations)
        return GripValidationResult(
            is_valid=False,
            violations=violations,
            error_message=f"In {direction_str} direction: {sections_str} shorter than min grip ({min_grip:.2f})",
        )

    return GripValidationResult(is_valid=True)


def validate_direction_aware(
    straights: list[StraightSection],
    min_grip: float,
    min_tail: float,
    current_direction: str,
    opposite_direction: str,
) -> DirectionValidationResult:
    """
    Validate grip requirements and check if reversing direction would help.

    Args:
        straights: List of straight sections in current order
        min_grip: Minimum grip length required
        min_tail: Minimum tail length required
        current_direction: Label for current direction (e.g., "Back to Front")
        opposite_direction: Label for opposite direction (e.g., "Front to Back")

    Returns:
        DirectionValidationResult with validation status and suggestions
    """
    current_result = validate_grip_for_direction(
        straights, min_grip, min_tail, reversed=False
    )
    reversed_result = validate_grip_for_direction(
        straights, min_grip, min_tail, reversed=True
    )

    if current_result.is_valid:
        return DirectionValidationResult(
            can_fabricate=True,
            current_direction_valid=True,
            reversed_direction_valid=reversed_result.is_valid,
        )

    if reversed_result.is_valid:
        # Current direction fails, but reversed would work
        return DirectionValidationResult(
            can_fabricate=True,
            current_direction_valid=False,
            reversed_direction_valid=True,
            violations=current_result.violations,
            error_message=current_result.error_message,
            suggestion=f"This path CAN be fabricated if you reverse the direction to \"{opposite_direction}\". "
                       f"Select the reversed direction and try again.",
        )

    # Neither direction works
    all_violations = list(set(current_result.violations + reversed_result.violations))
    all_violations.sort()
    sections_str = ", ".join(f"Straight {n}" for n in all_violations)
    return DirectionValidationResult(
        can_fabricate=False,
        current_direction_valid=False,
        reversed_direction_valid=False,
        violations=all_violations,
        error_message=f"{sections_str} shorter than minimum grip ({min_grip:.2f}). "
                      f"This bend sequence cannot be fabricated in either direction. "
                      f"Consider redesigning the path with longer straight sections between bends.",
    )
