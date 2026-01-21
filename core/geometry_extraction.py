"""Geometry extraction utilities for sketch entities.

This module provides functions to extract geometric properties from
Fusion 360 sketch entities (lines and arcs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, TypeAlias

from ..models.types import Point3D, ElementType
from .geometry import points_are_close

if TYPE_CHECKING:
    import adsk.fusion

    # Type alias for sketch entities we work with
    SketchEntity: TypeAlias = adsk.fusion.SketchLine | adsk.fusion.SketchArc


class PathElementLike(Protocol):
    """Protocol for objects that behave like PathElement.

    This enables testing with mock objects that have the same structure
    as PathElement but without Fusion API dependencies.
    """

    @property
    def element_type(self) -> ElementType: ...

    @property
    def endpoints(self) -> tuple[Point3D, Point3D]: ...


def get_sketch_entity_endpoints(
    entity: 'adsk.fusion.SketchLine | adsk.fusion.SketchArc',
) -> tuple[Point3D, Point3D]:
    """
    Extract world-space endpoints from a sketch entity.

    Args:
        entity: A SketchLine or SketchArc

    Returns:
        Tuple of (start_point, end_point) in world coordinates (cm)
    """
    start = entity.startSketchPoint.worldGeometry
    end = entity.endSketchPoint.worldGeometry
    return (
        (start.x, start.y, start.z),
        (end.x, end.y, end.z)
    )


def get_component_name(entity: 'adsk.fusion.SketchLine | adsk.fusion.SketchArc') -> str:
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
    except Exception as e:
        # Log but don't fail - component name is optional for bend sheet
        try:
            from ..lib.fusionAddInUtils import log
            log(f"Could not get component name: {e}")
        except ImportError:
            # Fallback for unit tests without Fusion
            pass
    return ""


@dataclass(slots=True)
class PathElement:
    """Wrapper for a path element (line or arc) with metadata."""

    element_type: ElementType
    entity: 'adsk.fusion.SketchLine | adsk.fusion.SketchArc'
    endpoints: tuple[Point3D, Point3D] = field(init=False)

    def __post_init__(self) -> None:
        self.endpoints = get_sketch_entity_endpoints(self.entity)


def get_free_endpoint(element: PathElementLike, all_elements: Sequence[PathElementLike]) -> Point3D:
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


def should_reverse_path_direction(
    start: Point3D,
    end: Point3D,
    axis_idx: int,
) -> bool:
    """
    Determine if path should be reversed to ensure positive axis direction.

    Paths should be normalized to go toward positive axis direction:
    - X: Left to Right (+X)
    - Y: Bottom to Top (+Y)
    - Z: Back to Front (+Z)

    Args:
        start: Start point of path
        end: End point of path
        axis_idx: Index of primary axis (0=X, 1=Y, 2=Z)

    Returns:
        True if path should be reversed, False otherwise
    """
    displacement = end[axis_idx] - start[axis_idx]
    return displacement < 0


def determine_primary_axis(start: Point3D, end: Point3D) -> tuple[str, int, str, str]:
    """
    Determine the primary travel axis and direction.

    Args:
        start: Start point of path
        end: End point of path

    Returns:
        Tuple of (axis_name, axis_index, current_direction, opposite_direction)
        Direction names use Fusion 360's coordinate system:
        - X axis: Left (-X) / Right (+X)
        - Y axis: Front (-Y) / Back (+Y)
        - Z axis: Bottom (-Z) / Top (+Z)
    """
    displacement = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    abs_disp = (abs(displacement[0]), abs(displacement[1]), abs(displacement[2]))
    max_disp = max(abs_disp)

    # Direction name mappings for Fusion 360's coordinate system
    # When looking at Front view: -Z goes toward you, +Z goes away
    direction_names: dict[str, tuple[str, str]] = {
        'X': ('Left', 'Right'),    # -X is Left, +X is Right
        'Y': ('Bottom', 'Top'),    # -Y is Bottom, +Y is Top
        'Z': ('Front', 'Back'),    # -Z is Front, +Z is Back
    }

    if abs_disp[0] == max_disp:
        axis, idx = 'X', 0
    elif abs_disp[1] == max_disp:
        axis, idx = 'Y', 1
    else:
        axis, idx = 'Z', 2

    neg_name, pos_name = direction_names[axis]
    if displacement[idx] > 0:
        current = pos_name
        opposite = neg_name
    else:
        current = neg_name
        opposite = pos_name

    return axis, idx, current, opposite
