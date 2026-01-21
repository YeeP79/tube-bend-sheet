"""Path ordering and validation for tube bend geometry.

This module provides functions to order path elements by connectivity
and validate path structure for tube bending operations.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from .geometry import points_are_close
from .geometry_extraction import PathElementLike


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
    if len(elements) < 2:
        return None, "Path must have at least 2 elements (1 straight + 1 bend minimum)."

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
