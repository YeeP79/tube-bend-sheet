"""Build and validate ordered path from geometry elements.

This module handles the single responsibility of constructing an ordered
path from extracted geometry and validating its structure.
"""

from __future__ import annotations

from dataclasses import dataclass

import adsk.fusion

from ...core import (
    PathElement,
    build_ordered_path,
    validate_path_alternation,
)


@dataclass(slots=True)
class PathBuildResult:
    """Result of path building and validation.

    Attributes:
        success: Whether path was built successfully
        error_message: Error description if failed
        ordered_path: Ordered list of path elements if successful
        starts_with_arc: Whether path starts with an arc
        ends_with_arc: Whether path ends with an arc
    """

    success: bool
    error_message: str | None = None
    ordered_path: list[PathElement] | None = None
    starts_with_arc: bool = False
    ends_with_arc: bool = False


def build_path_from_geometry(
    lines: list[adsk.fusion.SketchLine],
    arcs: list[adsk.fusion.SketchArc],
) -> PathBuildResult:
    """Build and validate ordered path from lines and arcs.

    Creates PathElement objects from lines and arcs, orders them by
    connectivity, and validates the alternating line-arc pattern.

    Args:
        lines: Extracted sketch lines
        arcs: Extracted sketch arcs

    Returns:
        PathBuildResult with ordered path or error
    """
    # Build path elements
    elements: list[PathElement] = []
    for line in lines:
        elements.append(PathElement("line", line))
    for arc in arcs:
        elements.append(PathElement("arc", arc))

    # Order path by connectivity
    ordered, path_error = build_ordered_path(elements)
    if ordered is None:
        return PathBuildResult(
            success=False,
            error_message=f"Path ordering error: {path_error}",
        )

    # Validate alternating line-arc pattern
    is_valid, error_msg = validate_path_alternation(ordered)
    if not is_valid:
        return PathBuildResult(
            success=False,
            error_message=f"Path structure error: {error_msg}",
        )

    return PathBuildResult(
        success=True,
        ordered_path=ordered,
        starts_with_arc=ordered[0].element_type == "arc",
        ends_with_arc=ordered[-1].element_type == "arc",
    )
