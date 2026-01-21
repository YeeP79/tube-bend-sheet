"""Path direction detection and normalization.

This module handles the single responsibility of determining path direction
and normalizing it for consistent UI presentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core import (
    PathElement,
    get_free_endpoint,
    get_component_name,
    determine_primary_axis,
    should_reverse_path_direction,
)


@dataclass(slots=True)
class DirectionResult:
    """Result of path direction analysis and normalization.

    Attributes:
        ordered_path: Path elements (possibly reversed for direction)
        start_point: Start point coordinates after normalization
        end_point: End point coordinates after normalization
        primary_axis: Primary axis of travel (X, Y, or Z)
        travel_direction: Direction label (e.g., "Right", "Top", "Front")
        opposite_direction: Opposite direction label
        starts_with_arc: Whether normalized path starts with arc
        ends_with_arc: Whether normalized path ends with arc
        component_name: Name of the component containing the sketch
    """

    ordered_path: list[PathElement]
    start_point: tuple[float, float, float]
    end_point: tuple[float, float, float]
    primary_axis: str
    travel_direction: str
    opposite_direction: str
    starts_with_arc: bool
    ends_with_arc: bool
    component_name: str


def normalize_path_direction(
    ordered_path: list[PathElement],
    starts_with_arc: bool,
    ends_with_arc: bool,
) -> DirectionResult:
    """Analyze and normalize path direction.

    Ensures path goes toward positive axis direction (Right, Top, Front)
    for consistent UI labels. This makes direction dropdown options
    predictable regardless of how the user selected the geometry.

    Args:
        ordered_path: Ordered path elements from path builder
        starts_with_arc: Whether original path starts with arc
        ends_with_arc: Whether original path ends with arc

    Returns:
        DirectionResult with normalized path and direction info
    """
    # Get endpoints of the path
    start_point = get_free_endpoint(ordered_path[0], ordered_path)
    end_point = get_free_endpoint(ordered_path[-1], ordered_path)

    # Get component name from first entity
    component_name = get_component_name(ordered_path[0].entity)

    # Determine primary axis and directions
    axis, axis_idx, current_dir, opposite_dir = determine_primary_axis(
        start_point, end_point
    )

    # Check if we need to reverse for consistent direction
    should_reverse = should_reverse_path_direction(start_point, end_point, axis_idx)

    if should_reverse:
        # Reverse path to normalize direction
        ordered_path = ordered_path[::-1]
        start_point, end_point = end_point, start_point
        current_dir, opposite_dir = opposite_dir, current_dir
        starts_with_arc, ends_with_arc = ends_with_arc, starts_with_arc

    return DirectionResult(
        ordered_path=ordered_path,
        start_point=start_point,
        end_point=end_point,
        primary_axis=axis,
        travel_direction=current_dir,
        opposite_direction=opposite_dir,
        starts_with_arc=starts_with_arc,
        ends_with_arc=ends_with_arc,
        component_name=component_name,
    )
