"""
Tests for Tube model - runs without Fusion.

Run with: pytest tests/test_tube.py -v
"""
from __future__ import annotations

import pytest

from models.tube import Tube, TubeDict, MATERIAL_TYPES, validate_tube_values


class TestTubeModel:
    """Test Tube dataclass functionality."""

    def test_tube_creation(self):
        """Create a basic tube."""
        tube = Tube(
            id="tube-001",
            name="DOM 1020 1.75x0.120",
            tube_od=4.445,
            wall_thickness=0.3048,
            material_type="DOM",
            batch="B-2024-0542",
            notes="Standard mild steel"
        )
        assert tube.id == "tube-001"
        assert tube.name == "DOM 1020 1.75x0.120"
        assert tube.tube_od == 4.445
        assert tube.wall_thickness == 0.3048
        assert tube.material_type == "DOM"
        assert tube.batch == "B-2024-0542"
        assert tube.notes == "Standard mild steel"

    def test_tube_creation_minimal(self):
        """Create a tube with only required fields."""
        tube = Tube(
            id="tube-001",
            name="DOM 1020",
            tube_od=4.445,
        )
        assert tube.wall_thickness == 0.0
        assert tube.material_type == ""
        assert tube.batch == ""
        assert tube.notes == ""

    def test_tube_repr(self):
        """Tube repr shows name and tube_od."""
        tube = Tube(id="1", name="DOM 1020", tube_od=4.445)
        repr_str = repr(tube)
        assert "DOM 1020" in repr_str
        assert "4.445" in repr_str

    def test_tube_repr_with_material_type(self):
        """Tube repr shows material_type when present."""
        tube = Tube(id="1", name="DOM 1020", tube_od=4.445, material_type="DOM")
        repr_str = repr(tube)
        assert "DOM" in repr_str


class TestTubeValidation:
    """Test Tube validation."""

    def test_negative_tube_od_raises(self):
        """Tube with negative tube_od should raise ValueError."""
        with pytest.raises(ValueError, match="tube_od must be positive"):
            Tube(id="1", name="Test", tube_od=-1.0)

    def test_zero_tube_od_raises(self):
        """Tube with zero tube_od should raise ValueError."""
        with pytest.raises(ValueError, match="tube_od must be positive"):
            Tube(id="1", name="Test", tube_od=0.0)

    def test_positive_tube_od_valid(self):
        """Tube with positive tube_od should be valid."""
        tube = Tube(id="1", name="Test", tube_od=0.001)
        assert tube.tube_od == 0.001

    def test_negative_wall_thickness_raises(self):
        """Tube with negative wall_thickness should raise ValueError."""
        with pytest.raises(ValueError, match="wall_thickness must be non-negative"):
            Tube(id="1", name="Test", tube_od=4.445, wall_thickness=-0.1)

    def test_zero_wall_thickness_valid(self):
        """Tube with zero wall_thickness should be valid (not specified)."""
        tube = Tube(id="1", name="Test", tube_od=4.445, wall_thickness=0.0)
        assert tube.wall_thickness == 0.0

    def test_positive_wall_thickness_valid(self):
        """Tube with positive wall_thickness should be valid."""
        tube = Tube(id="1", name="Test", tube_od=4.445, wall_thickness=0.3048)
        assert tube.wall_thickness == 0.3048

    def test_validate_tube_values_none_is_valid(self):
        """validate_tube_values with None values should not raise."""
        validate_tube_values(tube_od=None, wall_thickness=None)  # Should not raise


class TestTubeMatchesTubeOd:
    """Test Tube.matches_tube_od method."""

    def test_exact_match(self):
        """Exact match returns True."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(4.445, tolerance=0.01) is True

    def test_within_tolerance(self):
        """Value within tolerance returns True."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(4.45, tolerance=0.01) is True
        assert tube.matches_tube_od(4.44, tolerance=0.01) is True

    def test_at_tolerance_boundary(self):
        """Value exactly at tolerance boundary returns True."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(4.455, tolerance=0.01) is True

    def test_outside_tolerance(self):
        """Value outside tolerance returns False."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(4.5, tolerance=0.01) is False
        assert tube.matches_tube_od(4.4, tolerance=0.01) is False

    def test_negative_tube_od_returns_false(self):
        """Negative tube_od argument returns False."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(-4.445, tolerance=0.01) is False

    def test_zero_tube_od_returns_false(self):
        """Zero tube_od argument returns False."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(0, tolerance=0.01) is False

    def test_negative_tolerance_returns_false(self):
        """Negative tolerance returns False."""
        tube = Tube(id="1", name="Test", tube_od=4.445)
        assert tube.matches_tube_od(4.445, tolerance=-0.01) is False


class TestTubeSerialization:
    """Test Tube to_dict and from_dict methods."""

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        tube = Tube(
            id="tube-001",
            name="DOM 1020",
            tube_od=4.445,
            wall_thickness=0.3048,
            material_type="DOM",
            batch="B-2024",
            notes="Test notes"
        )
        data = tube.to_dict()
        assert data["id"] == "tube-001"
        assert data["name"] == "DOM 1020"
        assert data["tube_od"] == 4.445
        assert data["wall_thickness"] == 0.3048
        assert data["material_type"] == "DOM"
        assert data["batch"] == "B-2024"
        assert data["notes"] == "Test notes"

    def test_from_dict(self):
        """from_dict creates correct Tube."""
        data: TubeDict = {
            "id": "tube-001",
            "name": "DOM 1020",
            "tube_od": 4.445,
            "wall_thickness": 0.3048,
            "material_type": "DOM",
            "batch": "B-2024",
            "notes": "Test notes"
        }
        tube = Tube.from_dict(data)
        assert tube.id == "tube-001"
        assert tube.name == "DOM 1020"
        assert tube.tube_od == 4.445
        assert tube.wall_thickness == 0.3048
        assert tube.material_type == "DOM"
        assert tube.batch == "B-2024"
        assert tube.notes == "Test notes"

    def test_from_dict_missing_optional_fields(self):
        """from_dict handles missing optional fields (backward compat)."""
        data: TubeDict = {
            "id": "tube-001",
            "name": "DOM 1020",
            "tube_od": 4.445,
            "wall_thickness": 0.0,
            "material_type": "",
            "batch": "",
            "notes": ""
        }
        tube = Tube.from_dict(data)
        assert tube.wall_thickness == 0.0
        assert tube.material_type == ""
        assert tube.batch == ""
        assert tube.notes == ""

    def test_from_dict_backward_compat_no_new_fields(self):
        """from_dict defaults correctly when new fields are missing (v1.0 data)."""
        # Simulate v1.0 data without wall_thickness/material_type
        data = {
            "id": "mat-001",
            "name": "DOM 1020",
            "tube_od": 4.445,
            "batch": "B-2024",
            "notes": "Old data"
        }
        tube = Tube.from_dict(data)  # type: ignore[arg-type]
        assert tube.wall_thickness == 0.0
        assert tube.material_type == ""

    def test_from_dict_clamps_negative_tube_od(self):
        """from_dict clamps negative tube_od to valid range."""
        data: TubeDict = {
            "id": "1",
            "name": "Bad Tube",
            "tube_od": -1.0,
            "wall_thickness": 0.0,
            "material_type": "",
            "batch": "",
            "notes": ""
        }
        tube = Tube.from_dict(data)
        assert tube.tube_od == 0.001

    def test_from_dict_clamps_zero_tube_od(self):
        """from_dict clamps zero tube_od to valid range."""
        data: TubeDict = {
            "id": "1",
            "name": "Bad Tube",
            "tube_od": 0.0,
            "wall_thickness": 0.0,
            "material_type": "",
            "batch": "",
            "notes": ""
        }
        tube = Tube.from_dict(data)
        assert tube.tube_od == 0.001

    def test_from_dict_clamps_negative_wall_thickness(self):
        """from_dict clamps negative wall_thickness to 0."""
        data = {
            "id": "1",
            "name": "Bad Tube",
            "tube_od": 4.445,
            "wall_thickness": -0.5,
            "material_type": "",
            "batch": "",
            "notes": ""
        }
        tube = Tube.from_dict(data)  # type: ignore[arg-type]
        assert tube.wall_thickness == 0.0

    def test_roundtrip(self):
        """to_dict -> from_dict preserves all values."""
        original = Tube(
            id="tube-001",
            name="DOM 1020",
            tube_od=4.445,
            wall_thickness=0.3048,
            material_type="DOM",
            batch="B-2024",
            notes="Test notes"
        )
        data = original.to_dict()
        restored = Tube.from_dict(data)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.tube_od == original.tube_od
        assert restored.wall_thickness == original.wall_thickness
        assert restored.material_type == original.material_type
        assert restored.batch == original.batch
        assert restored.notes == original.notes


class TestMaterialTypes:
    """Test MATERIAL_TYPES constant."""

    def test_material_types_contains_empty(self):
        """MATERIAL_TYPES starts with empty string (not specified)."""
        assert MATERIAL_TYPES[0] == ""

    def test_material_types_contains_dom(self):
        """MATERIAL_TYPES contains DOM."""
        assert "DOM" in MATERIAL_TYPES

    def test_material_types_contains_hrew(self):
        """MATERIAL_TYPES contains HREW."""
        assert "HREW" in MATERIAL_TYPES

    def test_material_types_is_tuple(self):
        """MATERIAL_TYPES is immutable tuple."""
        assert isinstance(MATERIAL_TYPES, tuple)


class TestTubeValuesStoredInCentimeters:
    """Test that tube values are stored in cm (Fusion's internal unit).

    CRITICAL: All numeric values in tubes.json are stored in centimeters.
    Conversion reference:
    - 1 inch = 2.54 cm
    - Example: 1.75" tube = 4.445 cm
    """

    def test_tube_od_is_in_centimeters(self):
        """Verify that tube_od values should be in cm."""
        # A 1.75" OD tube stored in cm
        tube_od_inches = 1.75
        tube_od_cm = tube_od_inches * 2.54  # 4.445 cm

        tube = Tube(
            id="test",
            name="1.75\" DOM",
            tube_od=tube_od_cm,
        )

        assert abs(tube.tube_od - 4.445) < 0.001

    def test_roundtrip_preserves_exact_values(self):
        """Ensure serialization doesn't apply any conversion."""
        original = Tube(
            id="tube-001",
            name="Test",
            tube_od=4.445,  # cm
            wall_thickness=0.3048,  # cm (0.120")
        )

        data = original.to_dict()
        restored = Tube.from_dict(data)

        assert restored.tube_od == original.tube_od
        assert restored.wall_thickness == original.wall_thickness
