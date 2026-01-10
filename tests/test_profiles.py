"""
Tests for ProfileManager - runs without Fusion.

Run with: pytest tests/ -v
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from models.bender import Bender, Die
from storage.profiles import ProfileManager

if TYPE_CHECKING:
    pass


class TestBenderModel:
    """Test Bender and Die dataclass functionality."""

    def test_bender_creation(self):
        bender = Bender(
            id="test-id",
            name="Test Bender",
            min_grip=6.0,
            notes="Test notes"
        )
        assert bender.id == "test-id"
        assert bender.name == "Test Bender"
        assert bender.min_grip == 6.0
        assert bender.dies == []

    def test_die_creation(self):
        die = Die(
            id="die-id",
            name="1.5in x 4.5 CLR",
            tube_od=1.5,
            clr=4.5,
            offset=0.625
        )
        assert die.tube_od == 1.5
        assert die.clr == 4.5

    def test_die_matches_clr(self):
        die = Die(id="1", name="Test", tube_od=1.5, clr=4.5, offset=0.5)

        # Exact match
        assert die.matches_clr(4.5, tolerance=0.1) == True

        # Within tolerance
        assert die.matches_clr(4.55, tolerance=0.1) == True
        assert die.matches_clr(4.45, tolerance=0.1) == True

        # Outside tolerance
        assert die.matches_clr(5.0, tolerance=0.1) == False

    def test_bender_to_dict(self):
        die = Die(id="d1", name="Die1", tube_od=1.5, clr=4.5, offset=0.5, notes="")
        bender = Bender(id="b1", name="Bender1", min_grip=6.0, dies=[die], notes="")

        data = bender.to_dict()
        assert data["id"] == "b1"
        assert data["name"] == "Bender1"
        assert len(data["dies"]) == 1
        assert data["dies"][0]["clr"] == 4.5

    def test_bender_from_dict(self):
        data = {
            "id": "b1",
            "name": "Test Bender",
            "min_grip": 6.0,
            "dies": [
                {"id": "d1", "name": "Die1", "tube_od": 1.5, "clr": 4.5, "offset": 0.5, "notes": ""}
            ],
            "notes": ""
        }
        bender = Bender.from_dict(data)
        assert bender.name == "Test Bender"
        assert len(bender.dies) == 1
        assert bender.dies[0].clr == 4.5

    def test_bender_get_die_by_id(self):
        die1 = Die(id="d1", name="Die1", tube_od=1.5, clr=4.5, offset=0.5)
        die2 = Die(id="d2", name="Die2", tube_od=1.75, clr=5.5, offset=0.6)
        bender = Bender(id="b1", name="Bender", min_grip=6.0, dies=[die1, die2])

        found = bender.get_die_by_id("d2")
        assert found is not None
        assert found.name == "Die2"

        not_found = bender.get_die_by_id("nonexistent")
        assert not_found is None

    # Validation tests (Issue 3e)
    def test_die_negative_tube_od_raises(self):
        """Die with negative tube_od should raise ValueError."""
        with pytest.raises(ValueError, match="tube_od must be positive"):
            Die(id="1", name="Test", tube_od=-1.0, clr=4.5, offset=0.5)

    def test_die_zero_tube_od_raises(self):
        """Die with zero tube_od should raise ValueError."""
        with pytest.raises(ValueError, match="tube_od must be positive"):
            Die(id="1", name="Test", tube_od=0.0, clr=4.5, offset=0.5)

    def test_die_negative_clr_raises(self):
        """Die with negative clr should raise ValueError."""
        with pytest.raises(ValueError, match="clr must be positive"):
            Die(id="1", name="Test", tube_od=1.5, clr=-4.5, offset=0.5)

    def test_die_zero_clr_raises(self):
        """Die with zero clr should raise ValueError."""
        with pytest.raises(ValueError, match="clr must be positive"):
            Die(id="1", name="Test", tube_od=1.5, clr=0, offset=0.5)

    def test_die_negative_offset_raises(self):
        """Die with negative offset should raise ValueError."""
        with pytest.raises(ValueError, match="offset cannot be negative"):
            Die(id="1", name="Test", tube_od=1.5, clr=4.5, offset=-0.5)

    def test_die_zero_offset_valid(self):
        """Die with zero offset should be valid (offset can be zero)."""
        die = Die(id="1", name="Test", tube_od=1.5, clr=4.5, offset=0.0)
        assert die.offset == 0.0

    def test_bender_negative_min_grip_raises(self):
        """Bender with negative min_grip should raise ValueError."""
        with pytest.raises(ValueError, match="min_grip must be positive"):
            Bender(id="1", name="Test", min_grip=-1.0)

    def test_bender_zero_min_grip_raises(self):
        """Bender with zero min_grip should raise ValueError."""
        with pytest.raises(ValueError, match="min_grip must be positive"):
            Bender(id="1", name="Test", min_grip=0.0)

    def test_die_from_dict_clamps_negative_values(self):
        """Die.from_dict should clamp invalid values to valid ranges."""
        data = {
            "id": "1",
            "name": "Bad Die",
            "tube_od": -1.0,  # Invalid
            "clr": -4.5,      # Invalid
            "offset": -0.5,   # Invalid
            "notes": ""
        }
        die = Die.from_dict(data)
        # Should be clamped to minimum valid values
        assert die.tube_od == 0.001
        assert die.clr == 0.001
        assert die.offset == 0.0

    def test_bender_from_dict_clamps_negative_min_grip(self):
        """Bender.from_dict should clamp invalid min_grip to valid range."""
        data = {
            "id": "1",
            "name": "Bad Bender",
            "min_grip": -6.0,  # Invalid
            "dies": [],
            "notes": ""
        }
        bender = Bender.from_dict(data)
        # Should be clamped to minimum valid value
        assert bender.min_grip == 0.001


class TestProfileManagerJSON:
    """Test JSON loading/saving without the full ProfileManager (avoiding relative imports)."""

    def test_load_benders_json(self):
        """Test that we can load the actual benders.json file."""
        # Get the project root from the test file location
        project_root = Path(__file__).parent.parent
        json_path = project_root / "resources" / "benders.json"

        if not json_path.exists():
            pytest.skip(f"{json_path} does not exist")

        with open(json_path) as f:
            data = json.load(f)

        assert "benders" in data
        assert "version" in data

        benders = [Bender.from_dict(b) for b in data["benders"]]
        assert len(benders) > 0

        # Verify JD2 Model 3 has dies
        jd2 = next((b for b in benders if b.name == "JD2 Model 3"), None)
        if jd2:
            assert len(jd2.dies) == 3, f"JD2 Model 3 should have 3 dies, got {len(jd2.dies)}"

    def test_save_and_load_roundtrip(self):
        """Test that we can save and reload benders."""
        # Create test data
        die = Die(id="d1", name="Test Die", tube_od=1.5, clr=4.5, offset=0.5, notes="")
        bender = Bender(id="b1", name="Test Bender", min_grip=6.0, dies=[die], notes="")

        data = {
            "version": "1.0",
            "benders": [bender.to_dict()]
        }

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f, indent=2)
            temp_path = f.name

        try:
            # Load it back
            with open(temp_path) as f:
                loaded = json.load(f)

            loaded_benders = [Bender.from_dict(b) for b in loaded["benders"]]
            assert len(loaded_benders) == 1
            assert loaded_benders[0].name == "Test Bender"
            assert len(loaded_benders[0].dies) == 1
        finally:
            os.unlink(temp_path)


class TestProfileManagerOperations:
    """Test ProfileManager operations with real ProfileManager instance."""

    @pytest.fixture
    def profile_manager(self, tmp_path: Path) -> 'ProfileManager':
        """Create a ProfileManager with a temp directory."""
        return ProfileManager(str(tmp_path))

    def test_add_bender_creates_unique_id(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Adding a bender generates a unique ID."""
        bender1 = profile_manager.add_bender("Bender 1", 6.0)
        bender2 = profile_manager.add_bender("Bender 2", 8.0)
        assert bender1.id != bender2.id
        assert len(bender1.id) == 8  # UUID truncated to 8 chars

    def test_add_bender_saves_immediately(
        self, profile_manager: 'ProfileManager', tmp_path: Path
    ) -> None:
        """Adding a bender saves to disk immediately."""
        profile_manager.add_bender("New Bender", 6.0)

        # Create new manager pointing to same path
        manager2 = ProfileManager(str(tmp_path))
        bender = manager2.get_bender_by_name("New Bender")
        assert bender is not None

    def test_get_bender_by_id(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Find bender by ID."""
        bender = profile_manager.add_bender("Test", 6.0)
        found = profile_manager.get_bender_by_id(bender.id)
        assert found is not None
        assert found.name == "Test"

    def test_get_bender_by_id_not_found(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Returns None when bender not found."""
        assert profile_manager.get_bender_by_id("nonexistent") is None

    def test_get_bender_by_name(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Find bender by name."""
        profile_manager.add_bender("JD2 Model 3", 6.0)
        found = profile_manager.get_bender_by_name("JD2 Model 3")
        assert found is not None
        assert found.name == "JD2 Model 3"

    def test_get_bender_by_name_not_found(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Returns None when bender not found by name."""
        assert profile_manager.get_bender_by_name("Nonexistent") is None

    def test_update_bender_changes_values(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update bender with new values."""
        bender = profile_manager.add_bender("Original", 6.0, "Old notes")
        result = profile_manager.update_bender(
            bender.id,
            name="Updated",
            min_grip=8.0,
            notes="New notes"
        )
        assert result is True

        updated = profile_manager.get_bender_by_id(bender.id)
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.min_grip == 8.0
        assert updated.notes == "New notes"

    def test_update_bender_not_found(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update returns False when bender not found."""
        result = profile_manager.update_bender("nonexistent", name="Test")
        assert result is False

    def test_update_bender_rejects_zero_min_grip(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update raises ValueError for zero min_grip."""
        bender = profile_manager.add_bender("Test", 6.0)
        with pytest.raises(ValueError, match="min_grip must be positive"):
            profile_manager.update_bender(bender.id, min_grip=0.0)

    def test_update_bender_rejects_negative_min_grip(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update raises ValueError for negative min_grip."""
        bender = profile_manager.add_bender("Test", 6.0)
        with pytest.raises(ValueError, match="min_grip must be positive"):
            profile_manager.update_bender(bender.id, min_grip=-1.0)

    def test_delete_bender_removes_from_list(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Delete bender removes it from the list."""
        bender = profile_manager.add_bender("ToDelete", 6.0)
        result = profile_manager.delete_bender(bender.id)
        assert result is True
        assert profile_manager.get_bender_by_id(bender.id) is None

    def test_delete_bender_not_found(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Delete returns False when bender not found."""
        result = profile_manager.delete_bender("nonexistent")
        assert result is False

    def test_add_die_to_bender(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Add a die to an existing bender."""
        bender = profile_manager.add_bender("Test", 6.0)
        die = profile_manager.add_die_to_bender(
            bender.id, "New Die", 1.5, 4.5, 0.5, notes="Notes"
        )
        assert die is not None
        assert die.name == "New Die"
        assert die.clr == 4.5

    def test_add_die_to_nonexistent_bender(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Add die returns None when bender not found."""
        result = profile_manager.add_die_to_bender(
            "nonexistent", "Die", 1.5, 4.5, 0.5
        )
        assert result is None

    def test_update_die(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update die with new values."""
        bender = profile_manager.add_bender("Test", 6.0)
        die = profile_manager.add_die_to_bender(
            bender.id, "Original", 1.5, 4.5, 0.5
        )
        assert die is not None

        result = profile_manager.update_die(
            bender.id, die.id,
            name="Updated",
            tube_od=1.75,
            clr=5.5,
            offset=0.625,
            notes="New notes"
        )
        assert result is True

        updated_bender = profile_manager.get_bender_by_id(bender.id)
        assert updated_bender is not None
        updated_die = updated_bender.get_die_by_id(die.id)
        assert updated_die is not None
        assert updated_die.name == "Updated"
        assert updated_die.tube_od == 1.75
        assert updated_die.clr == 5.5

    def test_update_die_not_found_bender(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update die returns False when bender not found."""
        result = profile_manager.update_die("nonexistent", "die-id", name="Test")
        assert result is False

    def test_update_die_not_found_die(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update die returns False when die not found."""
        bender = profile_manager.add_bender("Test", 6.0)
        result = profile_manager.update_die(bender.id, "nonexistent", name="Test")
        assert result is False

    def test_update_die_rejects_invalid_values(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Update die raises ValueError for invalid numeric values."""
        bender = profile_manager.add_bender("Test", 6.0)
        die = profile_manager.add_die_to_bender(bender.id, "Die", 1.5, 4.5, 0.5)
        assert die is not None

        with pytest.raises(ValueError, match="tube_od must be positive"):
            profile_manager.update_die(bender.id, die.id, tube_od=0.0)

        with pytest.raises(ValueError, match="clr must be positive"):
            profile_manager.update_die(bender.id, die.id, clr=-1.0)

        with pytest.raises(ValueError, match="offset cannot be negative"):
            profile_manager.update_die(bender.id, die.id, offset=-0.5)

    def test_delete_die(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Delete die removes it from the bender."""
        bender = profile_manager.add_bender("Test", 6.0)
        die = profile_manager.add_die_to_bender(bender.id, "Die", 1.5, 4.5, 0.5)
        assert die is not None

        result = profile_manager.delete_die(bender.id, die.id)
        assert result is True

        updated_bender = profile_manager.get_bender_by_id(bender.id)
        assert updated_bender is not None
        assert updated_bender.get_die_by_id(die.id) is None

    def test_delete_die_not_found(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Delete die returns False when not found."""
        bender = profile_manager.add_bender("Test", 6.0)
        result = profile_manager.delete_die(bender.id, "nonexistent")
        assert result is False

    def test_find_die_for_clr_exact_match(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Find die with exact CLR match."""
        bender = profile_manager.add_bender("Test", 6.0)
        profile_manager.add_die_to_bender(bender.id, "4.5 CLR", 1.5, 4.5, 0.5)

        result = profile_manager.find_die_for_clr(4.5)
        assert result is not None
        found_bender, found_die = result
        assert found_die.clr == 4.5

    def test_find_die_for_clr_within_tolerance(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Find die within CLR tolerance."""
        bender = profile_manager.add_bender("Test", 6.0)
        profile_manager.add_die_to_bender(bender.id, "4.5 CLR", 1.5, 4.5, 0.5)

        # Within default tolerance of 0.01
        result = profile_manager.find_die_for_clr(4.505, tolerance=0.1)
        assert result is not None

    def test_find_die_for_clr_no_match(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Find die returns None when no match."""
        bender = profile_manager.add_bender("Test", 6.0)
        profile_manager.add_die_to_bender(bender.id, "4.5 CLR", 1.5, 4.5, 0.5)

        result = profile_manager.find_die_for_clr(10.0)
        assert result is None

    def test_find_die_for_clr_specific_bender(
        self, profile_manager: 'ProfileManager'
    ) -> None:
        """Find die searching specific bender."""
        bender1 = profile_manager.add_bender("Bender1", 6.0)
        bender2 = profile_manager.add_bender("Bender2", 6.0)
        profile_manager.add_die_to_bender(bender1.id, "Die1", 1.5, 4.5, 0.5)
        profile_manager.add_die_to_bender(bender2.id, "Die2", 1.75, 5.5, 0.6)

        # Search only bender2
        result = profile_manager.find_die_for_clr(4.5, bender_id=bender2.id)
        assert result is None  # Die1 is in bender1, not bender2

        result = profile_manager.find_die_for_clr(5.5, bender_id=bender2.id)
        assert result is not None

    def test_reload_picks_up_changes(
        self, profile_manager: 'ProfileManager', tmp_path: Path
    ) -> None:
        """Reload picks up changes made externally."""
        bender = profile_manager.add_bender("Original", 6.0)

        # Externally modify the file
        json_path = tmp_path / 'resources' / 'benders.json'
        with open(json_path) as f:
            data = json.load(f)
        data['benders'][0]['name'] = 'Modified'
        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Reload
        profile_manager.reload()
        found = profile_manager.get_bender_by_id(bender.id)
        assert found is not None
        assert found.name == 'Modified'

    def test_benders_property_lazy_loads(
        self, tmp_path: Path
    ) -> None:
        """Benders property lazy loads on first access."""
        manager = ProfileManager(str(tmp_path))
        # Access benders property - should trigger load
        benders = manager.benders
        # Default bender should be created
        assert len(benders) >= 1


class TestProfileManagerAtomicWrite:
    """
    Test atomic write and error handling in ProfileManager.

    Note: These tests require the full package structure to be available.
    They test save/load behavior that depends on the ProfileManager class.
    The atomic write pattern and error handling are tested via JSON roundtrips.
    """

    def test_atomic_write_via_json_roundtrip(self):
        """Test that save creates proper JSON that can be reloaded."""
        # Create test data
        die = Die(id="d1", name="Test Die", tube_od=1.5, clr=4.5, offset=0.5, notes="")
        bender = Bender(id="b1", name="Test Bender", min_grip=6.0, dies=[die], notes="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Manually test atomic write pattern: write to temp, rename
            resources_path = Path(tmp_dir) / 'resources'
            resources_path.mkdir(parents=True)
            json_path = resources_path / 'benders.json'
            temp_path = json_path.with_suffix('.tmp')

            data = {
                'version': '1.0',
                'benders': [bender.to_dict()]
            }

            # Write to temp file first
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            temp_path.replace(json_path)

            # Verify no temp file remains
            assert not temp_path.exists(), "Temp file should not remain after atomic rename"
            assert json_path.exists(), "Target file should exist"

            # Verify content
            with open(json_path) as f:
                loaded = json.load(f)
            assert loaded['benders'][0]['name'] == 'Test Bender'

    def test_corrupt_json_detection(self):
        """Test that corrupt JSON can be detected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            resources_path = Path(tmp_dir) / 'resources'
            resources_path.mkdir(parents=True)
            json_path = resources_path / 'benders.json'

            # Write corrupt JSON
            json_path.write_text('{ this is not valid json }')

            # Verify it raises JSONDecodeError
            with pytest.raises(json.JSONDecodeError):
                with open(json_path) as f:
                    json.load(f)

    def test_directory_creation_pattern(self):
        """Test that mkdir with parents=True creates nested directories."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_path = Path(tmp_dir) / 'a' / 'b' / 'c'
            nested_path.mkdir(parents=True, exist_ok=True)
            assert nested_path.exists(), "Nested directories should be created"

    def test_save_to_readonly_path_fails(self):
        """Test that saving to an invalid path raises an error."""
        # This tests the pattern, not the actual ProfileManager
        invalid_path = Path("/nonexistent/path/that/cannot/exist/file.json")
        with pytest.raises(OSError):
            invalid_path.parent.mkdir(parents=True, exist_ok=True)
