"""Data models for body-to-sketch matching.

Fusion-free dataclasses that define the vocabulary for matching
a tube body's cylinder/torus geometry to sketch line/arc geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .types import Vector3D, Point3D


@dataclass(slots=True)
class BodyStraight:
    """A straight cylinder segment extracted from a tube body.

    Attributes:
        axis: Normalized cylinder axis direction.
        origin: Cylinder surface origin (cm).
        radius: Cylinder radius (cm).
        length: Estimated length along the axis (cm).
        centroid: Face centroid for proximity scoring (cm).
    """
    axis: Vector3D
    origin: Point3D
    radius: float
    length: float
    centroid: Point3D


@dataclass(slots=True)
class BodyBend:
    """A bend (torus) segment extracted from a tube body.

    Attributes:
        axis: Bend plane normal (normalized).
        origin: Torus center point (cm).
        major_radius: Center-line radius / CLR (cm).
        minor_radius: Tube OD radius (cm).
    """
    axis: Vector3D
    origin: Point3D
    major_radius: float
    minor_radius: float


@dataclass(slots=True)
class BodyProfile:
    """Processed body geometry ready for sketch matching.

    Contains only OD-radius segments after merging coaxial cylinders.

    Attributes:
        straights: OD-only straight segments (merged coaxial).
        bends: OD-only bend segments.
        od_radius: Detected outer-diameter radius (cm).
    """
    straights: list[BodyStraight]
    bends: list[BodyBend]
    od_radius: float


@dataclass(slots=True)
class SketchLineData:
    """A non-construction sketch line's geometry.

    All coordinates are in sketch space (cm).

    Attributes:
        direction: Normalized line direction vector.
        start: Start point.
        end: End point.
        midpoint: Midpoint for proximity scoring.
        length: Line length (cm).
    """
    direction: Vector3D
    start: Point3D
    end: Point3D
    midpoint: Point3D
    length: float


@dataclass(slots=True)
class SketchArcData:
    """A non-construction sketch arc's geometry.

    All coordinates are in sketch space (cm).

    Attributes:
        center: Arc center point.
        radius: Arc radius (cm).
        normal: Arc plane normal (normalized).
        sweep: Sweep angle in radians.
        start: Start point.
        end: End point.
    """
    center: Point3D
    radius: float
    normal: Vector3D
    sweep: float
    start: Point3D
    end: Point3D


@dataclass(slots=True)
class SketchProfile:
    """All non-construction lines and arcs from a single sketch.

    Attributes:
        name: Sketch name.
        lines: Non-construction sketch lines.
        arcs: Non-construction sketch arcs.
    """
    name: str
    lines: list[SketchLineData]
    arcs: list[SketchArcData]


@dataclass(slots=True)
class TransformedSketchProfile:
    """Sketch profile with geometry transformed to model space.

    Attributes:
        name: Sketch name.
        lines: Lines transformed to model space.
        arcs: Arcs transformed to model space.
    """
    name: str
    lines: list[SketchLineData]
    arcs: list[SketchArcData]


@dataclass(slots=True)
class MatchResult:
    """Result of scoring a single sketch against a body profile.

    Attributes:
        sketch_name: Name of the scored sketch.
        score: Total match score (higher = better).
        confidence: Confidence level based on margin over next best.
        matched_straights: Number of body straights matched.
        total_straights: Total body straights.
        matched_bends: Number of body bends matched.
        total_bends: Total body bends.
        connected_line_indices: Sketch line indices in the connected path.
        connected_arc_indices: Sketch arc indices in the connected path.
        details: Human-readable scoring breakdown lines.
    """
    sketch_name: str
    score: int
    confidence: Literal["high", "medium", "low", "none"]
    matched_straights: int
    total_straights: int
    matched_bends: int
    total_bends: int
    connected_line_indices: set[int]
    connected_arc_indices: set[int]
    details: list[str] = field(default_factory=list)
