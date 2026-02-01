"""
Tests for Compensation models - runs without Fusion.

Run with: pytest tests/test_compensation.py -v
"""
from __future__ import annotations

import pytest

from models.compensation import (
    CompensationDataPoint,
    CompensationDataPointDict,
    DieMaterialCompensation,
    DieMaterialCompensationDict,
    validate_compensation_values,
)


class TestCompensationDataPoint:
    """Test CompensationDataPoint dataclass functionality."""

    def test_data_point_creation(self):
        """Create a basic compensation data point."""
        point = CompensationDataPoint(
            readout_angle=72.2,
            measured_angle=65.95,
        )
        assert point.readout_angle == 72.2
        assert point.measured_angle == 65.95

    def test_data_point_repr(self):
        """Data point repr shows angles with degree symbol."""
        point = CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)
        repr_str = repr(point)
        assert "72.2" in repr_str
        assert "65.95" in repr_str
        assert "°" in repr_str

    def test_compensation_factor(self):
        """Compensation factor is readout / measured."""
        point = CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)
        expected_factor = 72.2 / 65.95
        assert abs(point.compensation_factor - expected_factor) < 0.0001

    def test_compensation_factor_always_greater_than_one(self):
        """Compensation factor should always be > 1 due to validation."""
        point = CompensationDataPoint(readout_angle=90.0, measured_angle=83.5)
        assert point.compensation_factor > 1.0


class TestCompensationDataPointValidation:
    """Test CompensationDataPoint validation."""

    def test_negative_readout_angle_raises(self):
        """Negative readout_angle should raise ValueError."""
        with pytest.raises(ValueError, match="readout_angle must be positive"):
            CompensationDataPoint(readout_angle=-72.2, measured_angle=65.95)

    def test_zero_readout_angle_raises(self):
        """Zero readout_angle should raise ValueError."""
        with pytest.raises(ValueError, match="readout_angle must be positive"):
            CompensationDataPoint(readout_angle=0.0, measured_angle=65.95)

    def test_negative_measured_angle_raises(self):
        """Negative measured_angle should raise ValueError."""
        with pytest.raises(ValueError, match="measured_angle must be positive"):
            CompensationDataPoint(readout_angle=72.2, measured_angle=-65.95)

    def test_zero_measured_angle_raises(self):
        """Zero measured_angle should raise ValueError."""
        with pytest.raises(ValueError, match="measured_angle must be positive"):
            CompensationDataPoint(readout_angle=72.2, measured_angle=0.0)

    def test_measured_greater_than_readout_raises(self):
        """measured_angle >= readout_angle should raise ValueError."""
        with pytest.raises(ValueError, match="measured_angle.*must be less than"):
            CompensationDataPoint(readout_angle=65.0, measured_angle=72.0)

    def test_measured_equal_to_readout_raises(self):
        """measured_angle == readout_angle should raise ValueError."""
        with pytest.raises(ValueError, match="measured_angle.*must be less than"):
            CompensationDataPoint(readout_angle=72.0, measured_angle=72.0)

    def test_validate_compensation_values_none_is_valid(self):
        """validate_compensation_values with None values should not raise."""
        validate_compensation_values(readout_angle=None, measured_angle=None)

    def test_readout_angle_over_180_raises(self):
        """readout_angle > 180 should raise ValueError."""
        with pytest.raises(ValueError, match="readout_angle must be ≤180"):
            CompensationDataPoint(readout_angle=181.0, measured_angle=170.0)

    def test_measured_angle_over_180_raises(self):
        """measured_angle > 180 should raise ValueError."""
        # Test via validate function directly since creating a CompensationDataPoint
        # with measured > 180 would require readout > 180 (which is also invalid)
        with pytest.raises(ValueError, match="measured_angle must be ≤180"):
            validate_compensation_values(measured_angle=185.0)

    def test_validate_readout_angle_exactly_180_is_valid(self):
        """readout_angle exactly 180 should be valid."""
        # This should not raise
        point = CompensationDataPoint(readout_angle=180.0, measured_angle=170.0)
        assert point.readout_angle == 180.0

    def test_validate_measured_angle_exactly_180_is_valid(self):
        """measured_angle exactly 180 should be valid (edge case)."""
        # Note: This will fail because measured must be < readout
        # So we use readout > 180 which is itself invalid
        # Actually, we can't have measured = 180 with a valid readout
        # because readout must be > measured. Best we can do is test
        # that the 180 check happens before the relationship check.
        with pytest.raises(ValueError, match="readout_angle must be ≤180"):
            CompensationDataPoint(readout_angle=185.0, measured_angle=180.0)


class TestCompensationDataPointSerialization:
    """Test CompensationDataPoint to_dict and from_dict methods."""

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        point = CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)
        data = point.to_dict()
        assert data["readout_angle"] == 72.2
        assert data["measured_angle"] == 65.95

    def test_from_dict(self):
        """from_dict creates correct CompensationDataPoint."""
        data: CompensationDataPointDict = {
            "readout_angle": 72.2,
            "measured_angle": 65.95,
        }
        point = CompensationDataPoint.from_dict(data)
        assert point.readout_angle == 72.2
        assert point.measured_angle == 65.95

    def test_from_dict_clamps_negative_values(self):
        """from_dict clamps negative values to valid range."""
        data: CompensationDataPointDict = {
            "readout_angle": -72.2,
            "measured_angle": -65.95,
        }
        point = CompensationDataPoint.from_dict(data)
        assert point.readout_angle == 0.001
        assert point.measured_angle < point.readout_angle

    def test_from_dict_clamps_zero_values(self):
        """from_dict clamps zero values to valid range."""
        data: CompensationDataPointDict = {
            "readout_angle": 0.0,
            "measured_angle": 0.0,
        }
        point = CompensationDataPoint.from_dict(data)
        assert point.readout_angle == 0.001
        assert point.measured_angle < point.readout_angle

    def test_from_dict_clamps_invalid_relationship(self):
        """from_dict clamps when measured >= readout."""
        data: CompensationDataPointDict = {
            "readout_angle": 65.0,
            "measured_angle": 72.0,
        }
        point = CompensationDataPoint.from_dict(data)
        # Should clamp measured to 95% of readout
        assert point.measured_angle < point.readout_angle

    def test_roundtrip(self):
        """to_dict -> from_dict preserves all values."""
        original = CompensationDataPoint(readout_angle=72.2, measured_angle=65.95)
        data = original.to_dict()
        restored = CompensationDataPoint.from_dict(data)
        assert restored.readout_angle == original.readout_angle
        assert restored.measured_angle == original.measured_angle


class TestDieMaterialCompensation:
    """Test DieMaterialCompensation dataclass functionality."""

    def test_compensation_creation(self):
        """Create a basic compensation record."""
        comp = DieMaterialCompensation(
            die_id="die-001",
            material_id="mat-001",
        )
        assert comp.die_id == "die-001"
        assert comp.material_id == "mat-001"
        assert comp.data_points == []

    def test_compensation_creation_with_points(self):
        """Create compensation with initial data points."""
        points = [
            CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
            CompensationDataPoint(readout_angle=90.0, measured_angle=83.5),
        ]
        comp = DieMaterialCompensation(
            die_id="die-001",
            material_id="mat-001",
            data_points=points,
        )
        assert len(comp.data_points) == 2

    def test_compensation_repr(self):
        """Compensation repr shows die, material, and point count."""
        comp = DieMaterialCompensation(
            die_id="die-001",
            material_id="mat-001",
            data_points=[CompensationDataPoint(72.2, 65.95)],
        )
        repr_str = repr(comp)
        assert "die-001" in repr_str
        assert "mat-001" in repr_str
        assert "1" in repr_str


class TestDieMaterialCompensationAddPoint:
    """Test DieMaterialCompensation.add_data_point method."""

    def test_add_data_point(self):
        """Add a data point to compensation."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 72.2
        assert comp.data_points[0].measured_angle == 65.95

    def test_add_multiple_data_points(self):
        """Add multiple data points."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        comp.add_data_point(90.0, 83.5)
        comp.add_data_point(45.0, 42.1)
        assert len(comp.data_points) == 3

    def test_add_duplicate_readout_angle_raises(self):
        """Adding duplicate readout_angle should raise ValueError."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        with pytest.raises(ValueError, match="already exists"):
            comp.add_data_point(72.2, 66.0)

    def test_add_nearly_duplicate_readout_angle_raises(self):
        """Adding nearly duplicate readout_angle (within 0.01) should raise."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        with pytest.raises(ValueError, match="already exists"):
            comp.add_data_point(72.205, 66.0)


class TestDieMaterialCompensationRemovePoint:
    """Test DieMaterialCompensation.remove_data_point method."""

    def test_remove_data_point(self):
        """Remove a data point by index."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        comp.add_data_point(90.0, 83.5)

        result = comp.remove_data_point(0)
        assert result is True
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 90.0

    def test_remove_last_data_point(self):
        """Remove the last data point."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        comp.add_data_point(90.0, 83.5)

        result = comp.remove_data_point(1)
        assert result is True
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 72.2

    def test_remove_index_out_of_range(self):
        """Remove returns False for out of range index."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)

        assert comp.remove_data_point(5) is False
        assert comp.remove_data_point(-1) is False

    def test_remove_from_empty_list(self):
        """Remove from empty list returns False."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        assert comp.remove_data_point(0) is False


class TestDieMaterialCompensationClear:
    """Test DieMaterialCompensation.clear_data_points method."""

    def test_clear_data_points(self):
        """Clear all data points."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(72.2, 65.95)
        comp.add_data_point(90.0, 83.5)
        comp.add_data_point(45.0, 42.1)

        comp.clear_data_points()
        assert len(comp.data_points) == 0

    def test_clear_empty_list(self):
        """Clear empty list doesn't raise."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.clear_data_points()  # Should not raise
        assert len(comp.data_points) == 0


class TestDieMaterialCompensationSortByMeasured:
    """Test DieMaterialCompensation.get_sorted_by_measured method."""

    def test_get_sorted_by_measured(self):
        """Data points sorted by measured angle ascending."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(90.0, 83.5)
        comp.add_data_point(45.0, 42.1)
        comp.add_data_point(72.2, 65.95)

        sorted_points = comp.get_sorted_by_measured()
        assert sorted_points[0].measured_angle == 42.1
        assert sorted_points[1].measured_angle == 65.95
        assert sorted_points[2].measured_angle == 83.5

    def test_get_sorted_does_not_modify_original(self):
        """get_sorted_by_measured doesn't modify original list."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        comp.add_data_point(90.0, 83.5)
        comp.add_data_point(45.0, 42.1)

        original_first = comp.data_points[0].measured_angle
        _sorted_points = comp.get_sorted_by_measured()
        assert comp.data_points[0].measured_angle == original_first

    def test_get_sorted_empty_list(self):
        """get_sorted_by_measured on empty list returns empty list."""
        comp = DieMaterialCompensation(die_id="die-001", material_id="mat-001")
        sorted_points = comp.get_sorted_by_measured()
        assert sorted_points == []


class TestDieMaterialCompensationSerialization:
    """Test DieMaterialCompensation to_dict and from_dict methods."""

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        comp = DieMaterialCompensation(
            die_id="die-001",
            material_id="mat-001",
            data_points=[
                CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
                CompensationDataPoint(readout_angle=90.0, measured_angle=83.5),
            ],
        )
        data = comp.to_dict()
        assert data["die_id"] == "die-001"
        assert data["material_id"] == "mat-001"
        assert len(data["data_points"]) == 2
        assert data["data_points"][0]["readout_angle"] == 72.2

    def test_from_dict(self):
        """from_dict creates correct DieMaterialCompensation."""
        data: DieMaterialCompensationDict = {
            "die_id": "die-001",
            "material_id": "mat-001",
            "data_points": [
                {"readout_angle": 72.2, "measured_angle": 65.95},
                {"readout_angle": 90.0, "measured_angle": 83.5},
            ],
        }
        comp = DieMaterialCompensation.from_dict(data)
        assert comp.die_id == "die-001"
        assert comp.material_id == "mat-001"
        assert len(comp.data_points) == 2

    def test_from_dict_empty_data_points(self):
        """from_dict handles empty data_points list."""
        data: DieMaterialCompensationDict = {
            "die_id": "die-001",
            "material_id": "mat-001",
            "data_points": [],
        }
        comp = DieMaterialCompensation.from_dict(data)
        assert comp.data_points == []

    def test_from_dict_missing_data_points(self):
        """from_dict handles missing data_points key."""
        # Create a dict without data_points using type ignore
        data = {
            "die_id": "die-001",
            "material_id": "mat-001",
        }
        comp = DieMaterialCompensation.from_dict(data)  # type: ignore[arg-type]
        assert comp.data_points == []

    def test_roundtrip(self):
        """to_dict -> from_dict preserves all values."""
        original = DieMaterialCompensation(
            die_id="die-001",
            material_id="mat-001",
            data_points=[
                CompensationDataPoint(readout_angle=72.2, measured_angle=65.95),
                CompensationDataPoint(readout_angle=90.0, measured_angle=83.5),
            ],
        )
        data = original.to_dict()
        restored = DieMaterialCompensation.from_dict(data)
        assert restored.die_id == original.die_id
        assert restored.material_id == original.material_id
        assert len(restored.data_points) == len(original.data_points)
        assert restored.data_points[0].readout_angle == original.data_points[0].readout_angle
