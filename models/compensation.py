"""Compensation data models for bender angle correction.

Bender compensation captures the relationship between what the bender
readout shows and the actual measured angle after bending. This includes
all factors: material springback, bender calibration, and die wear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


class CompensationDataPointDict(TypedDict):
    """Type definition for CompensationDataPoint serialization."""

    readout_angle: float
    measured_angle: float


class DieMaterialCompensationDict(TypedDict):
    """Type definition for DieMaterialCompensation serialization."""

    die_id: str
    material_id: str
    data_points: list[CompensationDataPointDict]


def validate_compensation_values(
    readout_angle: float | None = None,
    measured_angle: float | None = None,
) -> None:
    """Validate compensation data point values.

    Args:
        readout_angle: What bender readout showed (must be positive and ≤180 if provided)
        measured_angle: Actual measured angle (must be positive and ≤180 if provided)

    Raises:
        ValueError: If any value violates its constraint
    """
    if readout_angle is not None and readout_angle <= 0:
        raise ValueError(f"readout_angle must be positive, got {readout_angle}")
    if readout_angle is not None and readout_angle > 180:
        raise ValueError(f"readout_angle must be ≤180 degrees, got {readout_angle}")
    if measured_angle is not None and measured_angle <= 0:
        raise ValueError(f"measured_angle must be positive, got {measured_angle}")
    if measured_angle is not None and measured_angle > 180:
        raise ValueError(f"measured_angle must be ≤180 degrees, got {measured_angle}")
    if (
        readout_angle is not None
        and measured_angle is not None
        and measured_angle >= readout_angle
    ):
        raise ValueError(
            f"measured_angle ({measured_angle}) must be less than "
            f"readout_angle ({readout_angle}) due to springback/calibration"
        )


@dataclass(slots=True)
class CompensationDataPoint:
    """
    A single bender compensation data point.

    Records the relationship between what the bender readout showed
    and what was actually measured after bending. This captures all
    compensation factors: springback, calibration error, and die wear.

    Attributes:
        readout_angle: What the bender readout showed when bending stopped (degrees)
        measured_angle: Actual angle measured after removing from bender (degrees)

    Invariant:
        measured_angle < readout_angle (material springs back, bender may be off)
    """

    readout_angle: float
    measured_angle: float

    def __post_init__(self) -> None:
        """Validate that readout > measured."""
        validate_compensation_values(
            readout_angle=self.readout_angle,
            measured_angle=self.measured_angle,
        )

    def __repr__(self) -> str:
        return (
            f"CompensationDataPoint(readout={self.readout_angle}°, "
            f"measured={self.measured_angle}°)"
        )

    @property
    def compensation_factor(self) -> float:
        """
        Calculate the compensation factor for this data point.

        The factor represents how much to overbend to achieve the target:
        compensated_angle = target_angle * factor

        Returns:
            Ratio of readout to measured angle (always > 1.0)
        """
        return self.readout_angle / self.measured_angle

    def to_dict(self) -> CompensationDataPointDict:
        """Convert to dictionary for JSON serialization."""
        return CompensationDataPointDict(
            readout_angle=self.readout_angle,
            measured_angle=self.measured_angle,
        )

    @classmethod
    def from_dict(cls, data: CompensationDataPointDict) -> CompensationDataPoint:
        """Create CompensationDataPoint from dictionary.

        Clamps invalid values to valid ranges to handle legacy data.
        """
        readout = max(0.001, data['readout_angle'])
        measured = max(0.001, data['measured_angle'])

        # Ensure measured < readout (clamp if needed)
        if measured >= readout:
            measured = readout * 0.95  # Assume 5% springback if invalid

        return cls(
            readout_angle=readout,
            measured_angle=measured,
        )


@dataclass(slots=True)
class DieMaterialCompensation:
    """
    Compensation data for a specific die-material combination.

    Stores multiple data points to enable accurate interpolation
    across different bend angles. More data points = better accuracy.

    Attributes:
        die_id: ID of the die this compensation data applies to
        material_id: ID of the material this compensation data applies to
        data_points: List of recorded compensation measurements
    """

    die_id: str
    material_id: str
    data_points: list[CompensationDataPoint] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"DieMaterialCompensation(die={self.die_id!r}, "
            f"material={self.material_id!r}, points={len(self.data_points)})"
        )

    def add_data_point(self, readout_angle: float, measured_angle: float) -> None:
        """
        Add a new compensation data point.

        Args:
            readout_angle: What bender readout showed (degrees)
            measured_angle: Actual measured angle (degrees)

        Raises:
            ValueError: If a data point with same readout_angle already exists
        """
        # Check for duplicate readout_angle
        for point in self.data_points:
            if abs(point.readout_angle - readout_angle) < 0.01:
                raise ValueError(
                    f"Data point for readout angle {readout_angle}° already exists"
                )

        self.data_points.append(
            CompensationDataPoint(
                readout_angle=readout_angle,
                measured_angle=measured_angle,
            )
        )

    def remove_data_point(self, index: int) -> bool:
        """
        Remove a data point by index.

        Args:
            index: Index of data point to remove

        Returns:
            True if removed, False if index out of range
        """
        if 0 <= index < len(self.data_points):
            self.data_points.pop(index)
            return True
        return False

    def clear_data_points(self) -> None:
        """Remove all data points. Use when bender is recalibrated."""
        self.data_points.clear()

    def get_sorted_by_measured(self) -> list[CompensationDataPoint]:
        """Get data points sorted by measured angle (ascending)."""
        return sorted(self.data_points, key=lambda p: p.measured_angle)

    def to_dict(self) -> DieMaterialCompensationDict:
        """Convert to dictionary for JSON serialization."""
        return DieMaterialCompensationDict(
            die_id=self.die_id,
            material_id=self.material_id,
            data_points=[p.to_dict() for p in self.data_points],
        )

    @classmethod
    def from_dict(cls, data: DieMaterialCompensationDict) -> DieMaterialCompensation:
        """Create DieMaterialCompensation from dictionary."""
        data_points = [
            CompensationDataPoint.from_dict(p)
            for p in data.get('data_points', [])
        ]

        return cls(
            die_id=data['die_id'],
            material_id=data['material_id'],
            data_points=data_points,
        )
