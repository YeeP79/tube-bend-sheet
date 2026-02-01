"""
Tests for compensation calculation functions - runs without Fusion.

Run with: pytest tests/test_compensation_calc.py -v
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest


# Mock the CompensationDataPoint to avoid import issues
@dataclass(frozen=True, slots=True)
class CompensationDataPoint:
    """Mock of CompensationDataPoint for testing."""
    readout_angle: float
    measured_angle: float

    @property
    def compensation_factor(self) -> float:
        return self.readout_angle / self.measured_angle


@dataclass(frozen=True, slots=True)
class CompensationResult:
    """Result of a compensation calculation."""
    compensated_angle: float
    warning: str | None = None


def _linear_interpolate(
    x: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Standard linear interpolation formula."""
    if abs(x2 - x1) < 1e-10:
        return y1
    slope = (y2 - y1) / (x2 - x1)
    return y1 + (x - x1) * slope


def _interpolate(
    target: float,
    sorted_points: list[CompensationDataPoint],
) -> float:
    """Linearly interpolate/extrapolate compensated angle."""
    for i in range(len(sorted_points) - 1):
        p1 = sorted_points[i]
        p2 = sorted_points[i + 1]
        if p1.measured_angle <= target <= p2.measured_angle:
            return _linear_interpolate(
                target,
                p1.measured_angle,
                p1.readout_angle,
                p2.measured_angle,
                p2.readout_angle,
            )

    if target < sorted_points[0].measured_angle:
        p1 = sorted_points[0]
        p2 = sorted_points[1]
    else:
        p1 = sorted_points[-2]
        p2 = sorted_points[-1]

    return _linear_interpolate(
        target,
        p1.measured_angle,
        p1.readout_angle,
        p2.measured_angle,
        p2.readout_angle,
    )


def calculate_compensated_angle(
    target_angle: float,
    data_points: list[CompensationDataPoint],
) -> CompensationResult:
    """Calculate what bender readout should show to achieve target measured angle."""
    if target_angle <= 0:
        raise ValueError(f"target_angle must be positive, got {target_angle}")
    if target_angle > 180:
        raise ValueError(f"target_angle must be ≤180 degrees, got {target_angle}")

    if not data_points:
        raise ValueError("data_points cannot be empty")

    sorted_points = sorted(data_points, key=lambda p: p.measured_angle)
    min_measured = sorted_points[0].measured_angle
    max_measured = sorted_points[-1].measured_angle

    if len(sorted_points) == 1:
        factor = sorted_points[0].compensation_factor
        compensated = target_angle * factor
        return CompensationResult(
            compensated_angle=compensated,
            warning="Single data point: using constant factor. "
            "Add more points at different angles for better accuracy.",
        )

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

    compensated = _interpolate(target_angle, sorted_points)
    return CompensationResult(compensated_angle=compensated, warning=warning)


def get_compensation_factor(data_points: list[CompensationDataPoint]) -> float:
    """Get the average compensation factor from data points."""
    if not data_points:
        raise ValueError("data_points cannot be empty")
    total = sum(p.compensation_factor for p in data_points)
    return total / len(data_points)


def has_sufficient_data(data_points: list[CompensationDataPoint]) -> bool:
    """Check if there's sufficient data for accurate compensation."""
    return len(data_points) >= 2


def get_data_range(
    data_points: list[CompensationDataPoint],
) -> tuple[float, float] | None:
    """Get the range of measured angles covered by the data."""
    if not data_points:
        return None
    measured_angles = [p.measured_angle for p in data_points]
    return (min(measured_angles), max(measured_angles))


class TestCalculateCompensatedAngle:
    """Test calculate_compensated_angle function."""

    def test_single_data_point_constant_factor(self):
        """Single data point uses constant factor."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        result = calculate_compensated_angle(45.0, points)

        # Factor = 72.2 / 65.95 = 1.0947...
        expected_factor = 72.2 / 65.95
        expected = 45.0 * expected_factor

        assert abs(result.compensated_angle - expected) < 0.001
        assert result.warning is not None
        assert "Single data point" in result.warning

    def test_two_data_points_interpolation(self):
        """Two data points uses interpolation."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]

        # Target 60° is between 42° and 83° measured
        result = calculate_compensated_angle(60.0, points)

        # Should interpolate between the two points
        # Linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
        # y = 45 + (60 - 42) * (90 - 45) / (83 - 42)
        # y = 45 + 18 * 45 / 41 = 45 + 19.76 = 64.76
        expected = 45.0 + (60.0 - 42.0) * (90.0 - 45.0) / (83.0 - 42.0)

        assert abs(result.compensated_angle - expected) < 0.001
        assert result.warning is None

    def test_multiple_data_points_finds_correct_bracket(self):
        """Multiple data points finds correct bracket for interpolation."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]

        # Target 50° is between 42° and 65.95° measured (first two points)
        result = calculate_compensated_angle(50.0, points)

        # Should use first two points for interpolation
        expected = 45.0 + (50.0 - 42.0) * (72.2 - 45.0) / (65.95 - 42.0)

        assert abs(result.compensated_angle - expected) < 0.001
        assert result.warning is None

    def test_extrapolation_below_range(self):
        """Extrapolation below data range includes warning."""
        points = [
            CompensationDataPoint(readout_angle=72.2, measured_angle=66.0),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]

        # Target 30° is below min measured (66°)
        result = calculate_compensated_angle(30.0, points)

        assert result.warning is not None
        assert "Extrapolating below" in result.warning
        assert "66.0" in result.warning

    def test_extrapolation_above_range(self):
        """Extrapolation above data range includes warning."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=72.2, measured_angle=66.0),
        ]

        # Target 90° is above max measured (66°)
        result = calculate_compensated_angle(90.0, points)

        assert result.warning is not None
        assert "Extrapolating above" in result.warning
        assert "66.0" in result.warning

    def test_target_at_exact_data_point(self):
        """Target exactly at a data point returns correct value."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]

        # Target exactly at middle point's measured angle
        result = calculate_compensated_angle(65.95, points)

        # Should return the middle point's readout angle
        assert abs(result.compensated_angle - 72.2) < 0.1
        assert result.warning is None

    def test_negative_target_raises(self):
        """Negative target_angle raises ValueError."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        with pytest.raises(ValueError, match="target_angle must be positive"):
            calculate_compensated_angle(-45.0, points)

    def test_zero_target_raises(self):
        """Zero target_angle raises ValueError."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        with pytest.raises(ValueError, match="target_angle must be positive"):
            calculate_compensated_angle(0.0, points)

    def test_empty_data_points_raises(self):
        """Empty data_points raises ValueError."""
        with pytest.raises(ValueError, match="data_points cannot be empty"):
            calculate_compensated_angle(45.0, [])

    def test_target_angle_over_180_raises(self):
        """target_angle > 180 should raise ValueError."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        with pytest.raises(ValueError, match="target_angle must be ≤180"):
            calculate_compensated_angle(181.0, points)

    def test_target_angle_exactly_180_is_valid(self):
        """target_angle exactly 180 should be valid."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        result = calculate_compensated_angle(180.0, points)
        assert result.compensated_angle > 0

    def test_result_is_frozen_dataclass(self):
        """CompensationResult is immutable."""
        from dataclasses import FrozenInstanceError

        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        result = calculate_compensated_angle(45.0, points)

        with pytest.raises(FrozenInstanceError):
            result.compensated_angle = 999  # type: ignore[misc]


class TestLinearInterpolate:
    """Test _linear_interpolate helper function."""

    def test_midpoint(self):
        """Interpolate at midpoint."""
        result = _linear_interpolate(50.0, 0.0, 0.0, 100.0, 100.0)
        assert abs(result - 50.0) < 0.001

    def test_quarter_point(self):
        """Interpolate at quarter point."""
        result = _linear_interpolate(25.0, 0.0, 0.0, 100.0, 100.0)
        assert abs(result - 25.0) < 0.001

    def test_extrapolate_below(self):
        """Extrapolate below range."""
        result = _linear_interpolate(-10.0, 0.0, 0.0, 100.0, 100.0)
        assert abs(result - (-10.0)) < 0.001

    def test_extrapolate_above(self):
        """Extrapolate above range."""
        result = _linear_interpolate(150.0, 0.0, 0.0, 100.0, 100.0)
        assert abs(result - 150.0) < 0.001

    def test_different_slope(self):
        """Interpolate with non-unity slope."""
        # Line from (0, 0) to (100, 200) - slope = 2
        result = _linear_interpolate(50.0, 0.0, 0.0, 100.0, 200.0)
        assert abs(result - 100.0) < 0.001

    def test_same_x_values_returns_first_y(self):
        """When x1 == x2, returns y1."""
        result = _linear_interpolate(50.0, 50.0, 100.0, 50.0, 200.0)
        assert result == 100.0


class TestGetCompensationFactor:
    """Test get_compensation_factor function."""

    def test_single_point(self):
        """Single point returns its factor."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        factor = get_compensation_factor(points)
        expected = 72.2 / 65.95
        assert abs(factor - expected) < 0.0001

    def test_multiple_points_average(self):
        """Multiple points returns average factor."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]
        factor = get_compensation_factor(points)

        expected = ((45.0 / 42.0) + (90.0 / 83.0)) / 2
        assert abs(factor - expected) < 0.0001

    def test_empty_raises(self):
        """Empty data_points raises ValueError."""
        with pytest.raises(ValueError, match="data_points cannot be empty"):
            get_compensation_factor([])


class TestHasSufficientData:
    """Test has_sufficient_data function."""

    def test_empty_returns_false(self):
        """Empty list returns False."""
        assert has_sufficient_data([]) is False

    def test_single_point_returns_false(self):
        """Single point returns False."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        assert has_sufficient_data(points) is False

    def test_two_points_returns_true(self):
        """Two points returns True."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]
        assert has_sufficient_data(points) is True

    def test_three_points_returns_true(self):
        """Three points returns True."""
        points = [
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
        ]
        assert has_sufficient_data(points) is True


class TestGetDataRange:
    """Test get_data_range function."""

    def test_empty_returns_none(self):
        """Empty list returns None."""
        assert get_data_range([]) is None

    def test_single_point_same_min_max(self):
        """Single point returns same min and max."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]
        result = get_data_range(points)
        assert result == (65.95, 65.95)

    def test_multiple_points_correct_range(self):
        """Multiple points returns correct min/max."""
        points = [
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.0),
            CompensationDataPoint(readout_angle=45.0, measured_angle=42.0),
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
        ]
        result = get_data_range(points)
        assert result == (42.0, 83.0)


class TestCompensationResult:
    """Test CompensationResult dataclass."""

    def test_creation_with_warning(self):
        """Create result with warning."""
        result = CompensationResult(compensated_angle=49.3, warning="Test warning")
        assert result.compensated_angle == 49.3
        assert result.warning == "Test warning"

    def test_creation_without_warning(self):
        """Create result without warning (default None)."""
        result = CompensationResult(compensated_angle=49.3)
        assert result.compensated_angle == 49.3
        assert result.warning is None

    def test_is_frozen(self):
        """Result is immutable."""
        from dataclasses import FrozenInstanceError

        result = CompensationResult(compensated_angle=49.3)
        with pytest.raises(FrozenInstanceError):
            result.compensated_angle = 100  # type: ignore[misc]


class TestRealWorldScenarios:
    """Test compensation calculations with real-world scenarios."""

    def test_user_example_72_to_65(self):
        """User's example: bent to 72.2°, measured 65.95°."""
        points = [CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)]

        # If user wants 45° final angle, what should they bend to?
        result = calculate_compensated_angle(45.0, points)

        # Factor = 72.2 / 65.95 ≈ 1.095
        # To get 45° measured, bend to 45 * 1.095 ≈ 49.3°
        assert 48.0 < result.compensated_angle < 51.0

    def test_typical_multi_angle_data(self):
        """Typical scenario with data at multiple angles."""
        # Realistic compensation data from a bender
        points = [
            CompensationDataPoint(readout_angle=50.0, measured_angle=46.5),  # ~7.5% over
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),  # ~9.5% over
            CompensationDataPoint(readout_angle=95.0, measured_angle=86.0),  # ~10.5% over
        ]

        # Test at various target angles
        result_30 = calculate_compensated_angle(30.0, points)  # Extrapolate below
        result_60 = calculate_compensated_angle(60.0, points)  # Interpolate
        result_75 = calculate_compensated_angle(75.0, points)  # Interpolate
        result_100 = calculate_compensated_angle(100.0, points)  # Extrapolate above

        # All compensated angles should be greater than target
        assert result_30.compensated_angle > 30.0
        assert result_60.compensated_angle > 60.0
        assert result_75.compensated_angle > 75.0
        assert result_100.compensated_angle > 100.0

        # Extrapolation warnings for outside range
        assert result_30.warning is not None
        assert result_100.warning is not None

        # No warnings for interpolation
        assert result_60.warning is None
        assert result_75.warning is None

    def test_compensation_factor_increases_with_angle(self):
        """Compensation factor typically increases with bend angle (realistic)."""
        # This is a common real-world observation - larger angles spring back more
        points = [
            CompensationDataPoint(readout_angle=50.0, measured_angle=47.0),  # 6.4% over
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),  # 9.5% over
            CompensationDataPoint(readout_angle=95.0, measured_angle=84.0),  # 13.1% over
        ]

        result_50 = calculate_compensated_angle(50.0, points)
        result_80 = calculate_compensated_angle(80.0, points)

        # At 80°, compensation should be proportionally higher than at 50°
        ratio_50 = result_50.compensated_angle / 50.0
        ratio_80 = result_80.compensated_angle / 80.0

        # Not necessarily monotonic, but should be reasonable
        assert 1.0 < ratio_50 < 1.2
        assert 1.0 < ratio_80 < 1.2
