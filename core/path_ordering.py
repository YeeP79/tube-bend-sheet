"""Path ordering and validation for tube bend geometry.

This module provides functions to order path elements by connectivity
and validate path structure for tube bending operations.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import TypeVar

from ..models.types import Point3D, Vector3D
from .geometry import points_are_close, vectors_are_collinear
from .protocols import PathElementLike


# Type variable for preserving element types through functions
_T = TypeVar('_T', bound=PathElementLike)


def elements_are_connected(e1: PathElementLike, e2: PathElementLike) -> bool:
    """Check if two path elements share an endpoint."""
    for p1 in e1.endpoints:
        for p2 in e2.endpoints:
            if points_are_close(p1, p2):
                return True
    return False


def build_ordered_path(
    elements: list[_T],
) -> tuple[list[_T] | None, str]:
    """
    Sort path elements into connected order by traversing connectivity graph.

    Args:
        elements: Unordered list of path elements

    Returns:
        Tuple of (ordered_elements, error_message).
        If successful, ordered_elements is the list and error_message is empty.
        If failed, ordered_elements is None and error_message describes the problem.
    """
    if len(elements) == 0:
        return None, "Path must have at least 1 element."

    # Single element path (arc-only) - valid for simple single-bend tubes
    if len(elements) == 1:
        if elements[0].element_type == 'arc':
            return elements.copy(), ""
        else:
            return None, "Single element path must be an arc (bend), not a line."

    # Build adjacency list
    neighbors: dict[int, list[int]] = {i: [] for i in range(len(elements))}
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            if elements_are_connected(elements[i], elements[j]):
                neighbors[i].append(j)
                neighbors[j].append(i)

    # Check for disconnected elements
    disconnected = [i for i, n in neighbors.items() if len(n) == 0]
    if disconnected:
        return None, (
            f"Found {len(disconnected)} disconnected element(s). "
            "All elements must connect to form a continuous path."
        )

    # Find path endpoints (elements with only 1 neighbor)
    path_endpoints: list[int] = [i for i, n in neighbors.items() if len(n) == 1]

    if len(path_endpoints) == 0:
        return None, (
            "Path forms a closed loop. "
            "The path must have two free endpoints (start and end)."
        )
    elif len(path_endpoints) == 1:
        return None, (
            "Path has only one free endpoint. "
            "Check for disconnected segments or missing elements."
        )
    elif len(path_endpoints) > 2:
        return None, (
            f"Path has {len(path_endpoints)} branches. "
            "Only single continuous paths are supported (no Y-junctions)."
        )

    # Traverse from one endpoint to the other
    ordered: list[_T] = []
    visited: set[int] = set()
    current: int | None = path_endpoints[0]

    while current is not None:
        ordered.append(elements[current])
        visited.add(current)

        next_elem: int | None = None
        for n in neighbors[current]:
            if n not in visited:
                next_elem = n
                break
        current = next_elem

    return ordered, ""


def _find_shared_and_outer_points(
    ep1: tuple[Point3D, Point3D],
    ep2: tuple[Point3D, Point3D],
) -> tuple[Point3D, Point3D, Point3D] | None:
    """Find the shared endpoint and outer endpoints of two connected elements.

    Args:
        ep1: Endpoints of first element (start, end)
        ep2: Endpoints of second element (start, end)

    Returns:
        Tuple of (shared_point, outer1, outer2) or None if not connected.
        outer1 is the non-shared endpoint of ep1, outer2 of ep2.
    """
    for i, p1 in enumerate(ep1):
        for j, p2 in enumerate(ep2):
            if points_are_close(p1, p2):
                outer1 = ep1[1 - i]
                outer2 = ep2[1 - j]
                return p1, outer1, outer2
    return None


def merge_collinear_lines(path: list[_T]) -> list[_T]:
    """Merge consecutive collinear line elements in an ordered path.

    When two or more consecutive line elements are collinear (same direction),
    they are merged into a single element whose endpoints span the full range.
    Non-collinear consecutive lines pass through unchanged.

    Args:
        path: Ordered list of path elements

    Returns:
        New list with collinear consecutive lines merged
    """
    if len(path) <= 1:
        return list(path)

    result: list[_T] = []
    i = 0
    while i < len(path):
        current = path[i]

        # Only attempt merge for line elements
        if current.element_type != 'line':
            result.append(current)
            i += 1
            continue

        # Track the merged span endpoints
        merged_outer_start: Point3D = current.endpoints[0]
        merged_outer_end: Point3D = current.endpoints[1]
        merged_elem: _T = current

        # Look ahead for consecutive collinear lines
        while i + 1 < len(path) and path[i + 1].element_type == 'line':
            next_elem = path[i + 1]
            shared_result = _find_shared_and_outer_points(
                (merged_outer_start, merged_outer_end),
                next_elem.endpoints,
            )
            if shared_result is None:
                break

            shared, outer1, outer2 = shared_result

            # Direction vectors: from outer1 toward shared, from shared toward outer2
            v1: Vector3D = (
                shared[0] - outer1[0],
                shared[1] - outer1[1],
                shared[2] - outer1[2],
            )
            v2: Vector3D = (
                outer2[0] - shared[0],
                outer2[1] - shared[1],
                outer2[2] - shared[2],
            )

            if not vectors_are_collinear(v1, v2):
                break

            # Merge: update span to cover both elements
            merged_outer_start = outer1
            merged_outer_end = outer2
            i += 1

        # If we merged anything, copy the element before updating endpoints
        # so that the caller's original elements are not mutated.
        if (merged_outer_start, merged_outer_end) != merged_elem.endpoints:
            merged_elem = copy.copy(merged_elem)
            # PathElement and MockPathElement both support direct attribute assignment
            merged_elem.endpoints = (merged_outer_start, merged_outer_end)  # type: ignore[attr-defined]

        result.append(merged_elem)
        i += 1

    return result


def validate_path_alternation(path: Sequence[PathElementLike]) -> tuple[bool, str]:
    """
    Validate that path alternates between lines and arcs.

    Args:
        path: Ordered list of path elements

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "Empty path"

    first_type = path[0].element_type

    for i, elem in enumerate(path):
        expected = first_type if i % 2 == 0 else ('arc' if first_type == 'line' else 'line')
        if elem.element_type != expected:
            return False, f"Position {i+1}: expected {expected}, got {elem.element_type}"

    return True, ""
