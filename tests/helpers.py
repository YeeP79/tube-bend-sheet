"""
Shared test helpers for TubeBendSheet tests.

This module contains mock classes and utilities used across multiple test files.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.types import ElementType, Point3D


@dataclass
class MockPathElement:
    """Mock PathElement for testing without Fusion API.

    Satisfies PathElementLike Protocol from core.geometry_extraction.
    """

    element_type: ElementType
    endpoints: tuple[Point3D, Point3D]
    entity: None = None  # Not needed for tests
