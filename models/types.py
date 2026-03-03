"""Shared type definitions for TubeFabrication.

This module provides common type aliases and Literal types used
throughout the codebase to ensure type safety and consistency.
"""

from typing import Literal

# 3D coordinate types
Vector3D = tuple[float, float, float]
Point3D = tuple[float, float, float]

# Path element types - 'line' for straight sections, 'arc' for bends
ElementType = Literal["line", "arc"]

# Segment types in the bend sheet output
SegmentType = Literal["straight", "bend"]
