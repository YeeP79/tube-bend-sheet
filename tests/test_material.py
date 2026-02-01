"""
Tests for Material model - runs without Fusion.

Run with: pytest tests/test_material.py -v
"""
from __future__ import annotations

import pytest

from models.material import Material, MaterialDict, validate_material_values


class TestMaterialModel:
    """Test Material dataclass functionality."""

    def test_material_creation(self):
        """Create a basic material."""
        material = Material(
            id="mat-001",
            name="DOM 1020",
            tube_od=4.445,
            batch="B-2024-0542",
            notes="Standard mild steel"
        )
        assert material.id == "mat-001"
        assert material.name == "DOM 1020"
        assert material.tube_od == 4.445
        assert material.batch == "B-2024-0542"
        assert material.notes == "Standard mild steel"

    def test_material_creation_minimal(self):
        """Create a material with only required fields."""
        material = Material(
            id="mat-001",
            name="DOM 1020",
            tube_od=4.445,
        )
        assert material.batch == ""
        assert material.notes == ""

    def test_material_repr(self):
        """Material repr shows name and tube_od."""
        material = Material(id="1", name="DOM 1020", tube_od=4.445)
        repr_str = repr(material)
        assert "DOM 1020" in repr_str
        assert "4.445" in repr_str


class TestMaterialValidation:
    """Test Material validation."""

    def test_negative_tube_od_raises(self):
        """Material with negative tube_od should raise ValueError."""
        with pytest.raises(ValueError, match="tube_od must be positive"):
            Material(id="1", name="Test", tube_od=-1.0)

    def test_zero_tube_od_raises(self):
        """Material with zero tube_od should raise ValueError."""
        with pytest.raises(ValueError, match="tube_od must be positive"):
            Material(id="1", name="Test", tube_od=0.0)

    def test_positive_tube_od_valid(self):
        """Material with positive tube_od should be valid."""
        material = Material(id="1", name="Test", tube_od=0.001)
        assert material.tube_od == 0.001

    def test_validate_material_values_none_is_valid(self):
        """validate_material_values with None values should not raise."""
        validate_material_values(tube_od=None)  # Should not raise


class TestMaterialMatchesTubeOd:
    """Test Material.matches_tube_od method."""

    def test_exact_match(self):
        """Exact match returns True."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(4.445, tolerance=0.01) is True

    def test_within_tolerance(self):
        """Value within tolerance returns True."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(4.45, tolerance=0.01) is True
        assert material.matches_tube_od(4.44, tolerance=0.01) is True

    def test_at_tolerance_boundary(self):
        """Value exactly at tolerance boundary returns True."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(4.455, tolerance=0.01) is True

    def test_outside_tolerance(self):
        """Value outside tolerance returns False."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(4.5, tolerance=0.01) is False
        assert material.matches_tube_od(4.4, tolerance=0.01) is False

    def test_negative_tube_od_returns_false(self):
        """Negative tube_od argument returns False."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(-4.445, tolerance=0.01) is False

    def test_zero_tube_od_returns_false(self):
        """Zero tube_od argument returns False."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(0, tolerance=0.01) is False

    def test_negative_tolerance_returns_false(self):
        """Negative tolerance returns False."""
        material = Material(id="1", name="Test", tube_od=4.445)
        assert material.matches_tube_od(4.445, tolerance=-0.01) is False


class TestMaterialSerialization:
    """Test Material to_dict and from_dict methods."""

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        material = Material(
            id="mat-001",
            name="DOM 1020",
            tube_od=4.445,
            batch="B-2024",
            notes="Test notes"
        )
        data = material.to_dict()
        assert data["id"] == "mat-001"
        assert data["name"] == "DOM 1020"
        assert data["tube_od"] == 4.445
        assert data["batch"] == "B-2024"
        assert data["notes"] == "Test notes"

    def test_from_dict(self):
        """from_dict creates correct Material."""
        data: MaterialDict = {
            "id": "mat-001",
            "name": "DOM 1020",
            "tube_od": 4.445,
            "batch": "B-2024",
            "notes": "Test notes"
        }
        material = Material.from_dict(data)
        assert material.id == "mat-001"
        assert material.name == "DOM 1020"
        assert material.tube_od == 4.445
        assert material.batch == "B-2024"
        assert material.notes == "Test notes"

    def test_from_dict_missing_optional_fields(self):
        """from_dict handles missing optional fields."""
        data: MaterialDict = {
            "id": "mat-001",
            "name": "DOM 1020",
            "tube_od": 4.445,
            "batch": "",
            "notes": ""
        }
        material = Material.from_dict(data)
        assert material.batch == ""
        assert material.notes == ""

    def test_from_dict_clamps_negative_tube_od(self):
        """from_dict clamps negative tube_od to valid range."""
        data: MaterialDict = {
            "id": "1",
            "name": "Bad Material",
            "tube_od": -1.0,
            "batch": "",
            "notes": ""
        }
        material = Material.from_dict(data)
        assert material.tube_od == 0.001

    def test_from_dict_clamps_zero_tube_od(self):
        """from_dict clamps zero tube_od to valid range."""
        data: MaterialDict = {
            "id": "1",
            "name": "Bad Material",
            "tube_od": 0.0,
            "batch": "",
            "notes": ""
        }
        material = Material.from_dict(data)
        assert material.tube_od == 0.001

    def test_roundtrip(self):
        """to_dict -> from_dict preserves all values."""
        original = Material(
            id="mat-001",
            name="DOM 1020",
            tube_od=4.445,
            batch="B-2024",
            notes="Test notes"
        )
        data = original.to_dict()
        restored = Material.from_dict(data)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.tube_od == original.tube_od
        assert restored.batch == original.batch
        assert restored.notes == original.notes


class TestMaterialValuesStoredInCentimeters:
    """Test that material values are stored in cm (Fusion's internal unit).

    CRITICAL: All numeric values in materials.json are stored in centimeters.
    Conversion reference:
    - 1 inch = 2.54 cm
    - Example: 1.75" tube = 4.445 cm
    """

    def test_tube_od_is_in_centimeters(self):
        """Verify that tube_od values should be in cm."""
        # A 1.75" OD tube stored in cm
        tube_od_inches = 1.75
        tube_od_cm = tube_od_inches * 2.54  # 4.445 cm

        material = Material(
            id="test",
            name="1.75\" DOM",
            tube_od=tube_od_cm,
        )

        assert abs(material.tube_od - 4.445) < 0.001

    def test_roundtrip_preserves_exact_values(self):
        """Ensure serialization doesn't apply any conversion."""
        original = Material(
            id="mat-001",
            name="Test",
            tube_od=4.445,  # cm
        )

        data = original.to_dict()
        restored = Material.from_dict(data)

        assert restored.tube_od == original.tube_od
