"""Protocol classes for duck-typed interfaces.

Consolidates Protocol definitions used across core modules to enable
testing with mock objects without Fusion API dependencies.
"""

from __future__ import annotations

from typing import Protocol

from ..models.types import Point3D, ElementType


class ArcLike(Protocol):
    """Protocol for objects with a radius property.

    This enables testing with mock objects that have a radius attribute
    but without Fusion API dependencies.
    """

    @property
    def radius(self) -> float: ...


class UnitConfigLike(Protocol):
    """Protocol for objects with unit conversion properties.

    This enables testing with mock objects without importing the full UnitConfig.
    """

    @property
    def cm_to_unit(self) -> float: ...


class PathElementLike(Protocol):
    """Protocol for objects that behave like PathElement.

    This enables testing with mock objects that have the same structure
    as PathElement but without Fusion API dependencies.
    """

    @property
    def element_type(self) -> ElementType: ...

    @property
    def endpoints(self) -> tuple[Point3D, Point3D]: ...
