"""Bender compensation calculation functions.

This module calculates what bender readout should show to achieve a target
measured angle, based on recorded compensation data points.

The compensation factor captures ALL factors:
- Material springback (elastic recovery after bending)
- Bender calibration (readout may not be accurate)
- Die wear (worn dies may behave differently)

Compensation is NOT a fixed percentage - it varies with bend angle. For
best accuracy, users should record multiple data points at different angles.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.compensation import CompensationDataPoint


@dataclass(frozen=True, slots=True)
class CompensationResult:
    """Result of a compensation calculation.

    Attributes:
        compensated_angle: What bender readout should show to achieve target
        warning: Optional warning message (e.g., for extrapolation)
    """

    compensated_angle: float
    warning: str | None = None


def calculate_compensated_angle(
    target_angle: float,
    data_points: list[CompensationDataPoint],
) -> CompensationResult:
    """
    Calculate what bender readout should show to achieve target measured angle.

    Uses linear interpolation between data points for best accuracy.
    When extrapolating outside the recorded data range, includes a warning.

    Args:
        target_angle: The desired final angle (what you want the tube to measure)
        data_points: Recorded compensation measurements (readout vs measured)

    Returns:
        CompensationResult with compensated_angle and optional warning

    Raises:
        ValueError: If target_angle is not positive or data_points is empty

    Example:
        Data: readout=72.2°, measured=65.95°
        Target: 45°
        Factor = 72.2 / 65.95 = 1.095
        Result = 45 * 1.095 = 49.3° (bend to 49.3° on readout to get 45° actual)
    """
    if target_angle <= 0:
        raise ValueError(f"target_angle must be positive, got {target_angle}")
    if target_angle > 180:
        raise ValueError(f"target_angle must be ≤180 degrees, got {target_angle}")

    if not data_points:
        raise ValueError("data_points cannot be empty")

    # Sort by measured angle for interpolation
    sorted_points = sorted(data_points, key=lambda p: p.measured_angle)

    min_measured = sorted_points[0].measured_angle
    max_measured = sorted_points[-1].measured_angle

    # Single data point: use constant factor
    if len(sorted_points) == 1:
        factor = sorted_points[0].compensation_factor
        compensated = target_angle * factor
        return CompensationResult(
            compensated_angle=compensated,
            warning="Single data point: using constant factor. "
            "Add more points at different angles for better accuracy.",
        )

    # Check for extrapolation
    warning: str | None = None
    if target_angle < min_measured:
        warning = (
            f"Extrapolating below recorded data (min: {min_measured:.1f}°). "
            "Results may be less accurate."
        )
    elif target_angle > max_measured:
        warning = (
            f"Extrapolating above recorded data (max: {max_measured:.1f}°). "
            "Results may be less accurate."
        )

    # Linear interpolation/extrapolation
    compensated = _interpolate(target_angle, sorted_points)

    return CompensationResult(
        compensated_angle=compensated,
        warning=warning,
    )


def _interpolate(
    target: float,
    sorted_points: list[CompensationDataPoint],
) -> float:
    """
    Linearly interpolate/extrapolate compensated angle.

    For a target measured angle, finds the two bracketing data points
    and interpolates between them. Extrapolates if outside range.

    Args:
        target: Target measured angle (degrees)
        sorted_points: Data points sorted by measured_angle (ascending)

    Returns:
        Interpolated/extrapolated readout angle
    """
    # Find bracketing points
    for i in range(len(sorted_points) - 1):
        p1 = sorted_points[i]
        p2 = sorted_points[i + 1]

        if p1.measured_angle <= target <= p2.measured_angle:
            # Target is between p1 and p2 - interpolate
            return _linear_interpolate(
                target,
                p1.measured_angle,
                p1.readout_angle,
                p2.measured_angle,
                p2.readout_angle,
            )

    # Target is outside the data range - extrapolate
    if target < sorted_points[0].measured_angle:
        # Extrapolate below using first two points
        p1 = sorted_points[0]
        p2 = sorted_points[1]
    else:
        # Extrapolate above using last two points
        p1 = sorted_points[-2]
        p2 = sorted_points[-1]

    return _linear_interpolate(
        target,
        p1.measured_angle,
        p1.readout_angle,
        p2.measured_angle,
        p2.readout_angle,
    )


def _linear_interpolate(
    x: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """
    Standard linear interpolation formula.

    Given two points (x1, y1) and (x2, y2), find y for a given x.

    Args:
        x: The x value to interpolate for
        x1, y1: First point
        x2, y2: Second point

    Returns:
        Interpolated y value
    """
    if abs(x2 - x1) < 1e-10:
        # Points have same x value (shouldn't happen with valid data)
        return y1

    # y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
    slope = (y2 - y1) / (x2 - x1)
    return y1 + (x - x1) * slope


def get_compensation_factor(data_points: list[CompensationDataPoint]) -> float:
    """
    Get the average compensation factor from data points.

    Useful for displaying a single summary factor to the user.

    Args:
        data_points: List of compensation data points

    Returns:
        Average of all individual compensation factors

    Raises:
        ValueError: If data_points is empty
    """
    if not data_points:
        raise ValueError("data_points cannot be empty")

    total = sum(p.compensation_factor for p in data_points)
    return total / len(data_points)


def has_sufficient_data(data_points: list[CompensationDataPoint]) -> bool:
    """
    Check if there's sufficient data for accurate compensation.

    At least 2 data points at different angles provides interpolation.
    A single point only provides a constant factor (less accurate).

    Args:
        data_points: List of compensation data points

    Returns:
        True if 2+ data points exist
    """
    return len(data_points) >= 2


def get_data_range(
    data_points: list[CompensationDataPoint],
) -> tuple[float, float] | None:
    """
    Get the range of measured angles covered by the data.

    Useful for warning users when their target angle is outside
    the recorded data range.

    Args:
        data_points: List of compensation data points

    Returns:
        Tuple of (min_angle, max_angle) or None if no data
    """
    if not data_points:
        return None

    measured_angles = [p.measured_angle for p in data_points]
    return (min(measured_angles), max(measured_angles))
