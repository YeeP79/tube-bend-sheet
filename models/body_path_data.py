"""Data models for body-based tube path extraction.

These models represent the geometry extracted directly from a BRepBody's
face topology (OD cylinders and torus faces). They are Fusion-free and
fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .types import Vector3D, Point3D


@dataclass(slots=True)
class BodyFaceSegment:
    """A single OD face in the ordered body path.

    Represents either a straight (cylinder) or bend (torus) segment
    extracted from a tube body's face topology.

    Attributes:
        face_type: Whether this segment is a straight or bend.
        axis: Cylinder axis direction (straights only).
        origin: Cylinder origin point (straights only).
        length: Cylinder length in cm (straights only).
        start_center: Circle edge center at the start end (straights only).
        end_center: Circle edge center at the end end (straights only).
        non_circle_edges: Count of non-circle edges (>0 means coped).
        bend_angle: Bend angle in degrees (bends only).
        clr: Center line radius in cm — torus major radius (bends only).
        torus_axis: Torus rotation axis (bends only).
        torus_origin: Torus center point (bends only).
    """
    face_type: Literal["straight", "bend"]
    # Straight fields (cylinder)
    axis: Vector3D | None = None
    origin: Point3D | None = None
    length: float = 0.0
    start_center: Point3D | None = None
    end_center: Point3D | None = None
    non_circle_edges: int = 0
    # Bend fields (torus)
    bend_angle: float = 0.0
    clr: float = 0.0
    torus_axis: Vector3D | None = None
    torus_origin: Point3D | None = None


@dataclass(slots=True)
class BodyPathResult:
    """Complete extraction from a tube body's face topology.

    Contains the ordered path of face segments plus tube dimension data
    needed to generate a bend sheet.

    Attributes:
        segments: Ordered list of face segments (straights and bends).
        od_radius: Outer diameter radius in cm.
        id_radius: Inner diameter radius in cm (None if not detected).
        clr_values: CLR values in cm, one per bend.
        clr_consistent: Whether all CLR values match.
        start_is_coped: Whether the start end has cope geometry.
        end_is_coped: Whether the end end has cope geometry.
        start_point: Center point of the path start (cm).
        end_point: Center point of the path end (cm).
    """
    segments: list[BodyFaceSegment]
    od_radius: float
    id_radius: float | None = None
    clr_values: list[float] = field(default_factory=list)
    clr_consistent: bool = True
    start_is_coped: bool = False
    end_is_coped: bool = False
    start_point: Point3D = (0.0, 0.0, 0.0)
    end_point: Point3D = (0.0, 0.0, 0.0)
