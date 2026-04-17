"""Data models for tube cope calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .types import Vector3D


@dataclass(slots=True)
class ReceivingTube:
    """A tube at the node that the incoming tube must be coped around."""
    vector: Vector3D
    od: float
    name: str = ""


@dataclass(slots=True)
class CopePass:
    """Settings for a single notcher pass."""
    notcher_angle: float
    rotation_mark: float
    plunge_depth: float
    is_pass_through: bool
    lobe_span_degrees: float
    dominant: bool
    holesaw_depth_required: float
    holesaw_warning: str | None = None
    receiver_name: str = ""


@dataclass(slots=True)
class CopeResult:
    """Complete result of a cope calculation."""
    passes: list[CopePass]
    is_multi_pass: bool
    method: Literal["A", "B", "C"]
    method_description: str
    z_profile: list[float]
    has_bend_reference: bool = False
    reference_description: str = ""
    warnings: list[str] = field(default_factory=list)
    all_receiver_names: list[str] = field(default_factory=list)
