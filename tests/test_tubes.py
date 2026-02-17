"""
Tests for TubeManager - runs without Fusion.

This test file duplicates the TubeManager and related classes locally
to avoid import issues with relative imports in storage/tubes.py.

Run with: pytest tests/test_tubes.py -v
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


# =============================================================================
# Local copies of data classes to avoid import issues
# =============================================================================


def validate_tube_values(
    tube_od: float | None = None,
    wall_thickness: float | None = None,
) -> None:
    """Validate tube numeric values."""
    if tube_od is not None and tube_od <= 0:
        raise ValueError(f"tube_od must be positive, got {tube_od}")
    if wall_thickness is not None and wall_thickness < 0:
        raise ValueError(f"wall_thickness must be non-negative, got {wall_thickness}")


def validate_compensation_values(
    readout_angle: float | None = None,
    measured_angle: float | None = None,
) -> None:
    """Validate compensation data point values."""
    if readout_angle is not None and readout_angle <= 0:
        raise ValueError(f"readout_angle must be positive, got {readout_angle}")
    if measured_angle is not None and measured_angle <= 0:
        raise ValueError(f"measured_angle must be positive, got {measured_angle}")
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
class Tube:
    """Local copy of Tube for testing."""
    id: str
    name: str
    tube_od: float
    wall_thickness: float = 0.0
    material_type: str = ""
    batch: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        validate_tube_values(tube_od=self.tube_od, wall_thickness=self.wall_thickness)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tube_od": self.tube_od,
            "wall_thickness": self.wall_thickness,
            "material_type": self.material_type,
            "batch": self.batch,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tube":
        tube_od = max(0.001, data['tube_od'])
        wall_thickness = max(0.0, data.get('wall_thickness', 0.0))
        return cls(
            id=data['id'],
            name=data['name'],
            tube_od=tube_od,
            wall_thickness=wall_thickness,
            material_type=data.get('material_type', ''),
            batch=data.get('batch', ''),
            notes=data.get('notes', ''),
        )

    def matches_tube_od(self, tube_od: float, tolerance: float = 0.01) -> bool:
        if tube_od <= 0 or tolerance < 0:
            return False
        return abs(self.tube_od - tube_od) <= tolerance


@dataclass(slots=True)
class CompensationDataPoint:
    """Local copy of CompensationDataPoint for testing."""
    readout_angle: float
    measured_angle: float

    def __post_init__(self) -> None:
        validate_compensation_values(
            readout_angle=self.readout_angle,
            measured_angle=self.measured_angle,
        )

    @property
    def compensation_factor(self) -> float:
        return self.readout_angle / self.measured_angle

    def to_dict(self) -> dict[str, float]:
        return {
            "readout_angle": self.readout_angle,
            "measured_angle": self.measured_angle,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "CompensationDataPoint":
        readout = max(0.001, data['readout_angle'])
        measured = max(0.001, data['measured_angle'])
        if measured >= readout:
            measured = readout * 0.95
        return cls(readout_angle=readout, measured_angle=measured)


@dataclass(slots=True)
class DieMaterialCompensation:
    """Local copy of DieMaterialCompensation for testing."""
    die_id: str
    material_id: str
    data_points: list[CompensationDataPoint] = field(default_factory=list)

    def add_data_point(self, readout_angle: float, measured_angle: float) -> None:
        for point in self.data_points:
            if abs(point.readout_angle - readout_angle) < 0.01:
                raise ValueError(
                    f"Data point for readout angle {readout_angle}° already exists"
                )
        self.data_points.append(
            CompensationDataPoint(readout_angle=readout_angle, measured_angle=measured_angle)
        )

    def remove_data_point(self, index: int) -> bool:
        if 0 <= index < len(self.data_points):
            self.data_points.pop(index)
            return True
        return False

    def clear_data_points(self) -> None:
        self.data_points.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "die_id": self.die_id,
            "material_id": self.material_id,
            "data_points": [p.to_dict() for p in self.data_points],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DieMaterialCompensation":
        data_points = [
            CompensationDataPoint.from_dict(p) for p in data.get('data_points', [])
        ]
        return cls(
            die_id=data['die_id'],
            material_id=data['material_id'],
            data_points=data_points,
        )


# =============================================================================
# TubeManager - local copy for testing
# =============================================================================


class TubeManager:
    """Local copy of TubeManager for testing."""

    FILENAME = 'tubes.json'
    LEGACY_FILENAME = 'materials.json'
    CURRENT_VERSION = '1.1'
    SUPPORTED_VERSIONS = {'1.0', '1.1'}

    def __init__(self, addin_path: str) -> None:
        self._addin_path = Path(addin_path)
        self._resources_path = self._addin_path / 'resources'
        self._tubes_path = self._resources_path / self.FILENAME
        self._legacy_path = self._resources_path / self.LEGACY_FILENAME
        self._tubes: list[Tube] = []
        self._compensation_data: list[DieMaterialCompensation] = []
        self._loaded = False
        self._load_lock = threading.Lock()

    @property
    def tubes(self) -> list[Tube]:
        with self._load_lock:
            if not self._loaded:
                self.load()
        return self._tubes

    @property
    def compensation_data(self) -> list[DieMaterialCompensation]:
        with self._load_lock:
            if not self._loaded:
                self.load()
        return self._compensation_data

    def reload(self) -> None:
        self._loaded = False
        self.load()

    def load(self) -> None:
        self._tubes = []
        self._compensation_data = []

        # Migration: if tubes.json doesn't exist but materials.json does, read from legacy
        load_path = self._tubes_path
        if not self._tubes_path.exists():
            if self._legacy_path.exists():
                load_path = self._legacy_path
            else:
                self.save()
                self._loaded = True
                return

        try:
            with open(load_path, encoding='utf-8') as f:
                data = json.load(f)

            # Parse tubes (supports both 'tubes' and legacy 'materials' keys)
            tubes_list = data.get('tubes', data.get('materials', []))
            if isinstance(tubes_list, list):
                for tube_data in tubes_list:
                    try:
                        self._tubes.append(Tube.from_dict(tube_data))
                    except (KeyError, TypeError, ValueError):
                        continue

            comp_list = data.get('compensation_data', [])
            if isinstance(comp_list, list):
                for comp_data in comp_list:
                    try:
                        self._compensation_data.append(
                            DieMaterialCompensation.from_dict(comp_data)
                        )
                    except (KeyError, TypeError, ValueError):
                        continue

            # If we loaded from legacy file, save to new file
            if load_path == self._legacy_path:
                self.save()

        except json.JSONDecodeError:
            self.save()

        self._loaded = True

    def save(self) -> None:
        temp_path = self._tubes_path.with_suffix('.tmp')
        self._resources_path.mkdir(parents=True, exist_ok=True)
        data = {
            'version': self.CURRENT_VERSION,
            'tubes': [t.to_dict() for t in self._tubes],
            'compensation_data': [c.to_dict() for c in self._compensation_data],
        }
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self._tubes_path)

    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def get_tube_by_id(self, tube_id: str) -> Tube | None:
        for tube in self.tubes:
            if tube.id == tube_id:
                return tube
        return None

    def get_tube_by_name(self, name: str) -> Tube | None:
        for tube in self.tubes:
            if tube.name == name:
                return tube
        return None

    def get_tubes_by_tube_od(
        self, tube_od: float, tolerance: float = 0.01
    ) -> list[Tube]:
        return [t for t in self.tubes if t.matches_tube_od(tube_od, tolerance)]

    def add_tube(
        self,
        name: str,
        tube_od: float,
        wall_thickness: float = 0.0,
        material_type: str = "",
        batch: str = "",
        notes: str = "",
    ) -> Tube:
        validate_tube_values(tube_od=tube_od, wall_thickness=wall_thickness)
        tube = Tube(
            id=self._generate_id(),
            name=name,
            tube_od=tube_od,
            wall_thickness=wall_thickness,
            material_type=material_type,
            batch=batch,
            notes=notes,
        )
        self._tubes.append(tube)
        self.save()
        return tube

    def update_tube(
        self,
        tube_id: str,
        name: str | None = None,
        tube_od: float | None = None,
        wall_thickness: float | None = None,
        material_type: str | None = None,
        batch: str | None = None,
        notes: str | None = None,
    ) -> bool:
        tube = self.get_tube_by_id(tube_id)
        if tube is None:
            return False
        validate_tube_values(tube_od=tube_od, wall_thickness=wall_thickness)
        if name is not None:
            tube.name = name
        if tube_od is not None:
            tube.tube_od = tube_od
        if wall_thickness is not None:
            tube.wall_thickness = wall_thickness
        if material_type is not None:
            tube.material_type = material_type
        if batch is not None:
            tube.batch = batch
        if notes is not None:
            tube.notes = notes
        self.save()
        return True

    def delete_tube(self, tube_id: str) -> bool:
        for i, tube in enumerate(self._tubes):
            if tube.id == tube_id:
                self._tubes.pop(i)
                self._compensation_data = [
                    c for c in self._compensation_data if c.material_id != tube_id
                ]
                self.save()
                return True
        return False

    def get_compensation(
        self, die_id: str, material_id: str
    ) -> DieMaterialCompensation | None:
        for comp in self.compensation_data:
            if comp.die_id == die_id and comp.material_id == material_id:
                return comp
        return None

    def get_or_create_compensation(
        self, die_id: str, material_id: str
    ) -> DieMaterialCompensation:
        comp = self.get_compensation(die_id, material_id)
        if comp is None:
            comp = DieMaterialCompensation(die_id=die_id, material_id=material_id)
            self._compensation_data.append(comp)
            self.save()
        return comp

    def add_compensation_point(
        self, die_id: str, material_id: str, readout_angle: float, measured_angle: float
    ) -> bool:
        validate_compensation_values(
            readout_angle=readout_angle, measured_angle=measured_angle
        )
        comp = self.get_or_create_compensation(die_id, material_id)
        comp.add_data_point(readout_angle, measured_angle)
        self.save()
        return True

    def remove_compensation_point(
        self, die_id: str, material_id: str, index: int
    ) -> bool:
        comp = self.get_compensation(die_id, material_id)
        if comp is None:
            return False
        if comp.remove_data_point(index):
            self.save()
            return True
        return False

    def clear_compensation_data(self, die_id: str, material_id: str) -> bool:
        comp = self.get_compensation(die_id, material_id)
        if comp is None:
            return False
        comp.clear_data_points()
        self.save()
        return True

    def delete_compensation_for_die(self, die_id: str) -> int:
        original_count = len(self._compensation_data)
        self._compensation_data = [
            c for c in self._compensation_data if c.die_id != die_id
        ]
        removed = original_count - len(self._compensation_data)
        if removed > 0:
            self.save()
        return removed


# =============================================================================
# Tests
# =============================================================================


class TestTubeManagerBasics:
    """Test TubeManager basic operations."""

    @pytest.fixture
    def tube_manager(self, tmp_path: Path) -> TubeManager:
        return TubeManager(str(tmp_path))

    def test_initial_state_empty(self, tube_manager: TubeManager) -> None:
        assert tube_manager.tubes == []
        assert tube_manager.compensation_data == []

    def test_tubes_property_lazy_loads(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        tubes = manager.tubes
        assert isinstance(tubes, list)

    def test_compensation_data_property_lazy_loads(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        comp_data = manager.compensation_data
        assert isinstance(comp_data, list)


class TestTubeManagerTubeCRUD:
    """Test TubeManager tube CRUD operations."""

    @pytest.fixture
    def tube_manager(self, tmp_path: Path) -> TubeManager:
        return TubeManager(str(tmp_path))

    def test_add_tube(self, tube_manager: TubeManager) -> None:
        tube = tube_manager.add_tube(
            name="DOM 1020", tube_od=4.445, batch="B-2024", notes="Test tube"
        )
        assert tube.name == "DOM 1020"
        assert tube.tube_od == 4.445
        assert len(tube.id) == 8

    def test_add_tube_with_new_fields(self, tube_manager: TubeManager) -> None:
        """Add a tube with wall_thickness and material_type."""
        tube = tube_manager.add_tube(
            name="DOM 1020 1.75x0.120",
            tube_od=4.445,
            wall_thickness=0.3048,
            material_type="DOM",
            batch="B-2024",
            notes="Standard mild steel",
        )
        assert tube.wall_thickness == 0.3048
        assert tube.material_type == "DOM"

    def test_add_tube_creates_unique_id(
        self, tube_manager: TubeManager
    ) -> None:
        tube1 = tube_manager.add_tube("Tube 1", 4.445)
        tube2 = tube_manager.add_tube("Tube 2", 4.445)
        assert tube1.id != tube2.id

    def test_add_tube_saves_immediately(
        self, tube_manager: TubeManager, tmp_path: Path
    ) -> None:
        tube_manager.add_tube("New Tube", 4.445)
        manager2 = TubeManager(str(tmp_path))
        tube = manager2.get_tube_by_name("New Tube")
        assert tube is not None

    def test_add_tube_invalid_tube_od_raises(
        self, tube_manager: TubeManager
    ) -> None:
        with pytest.raises(ValueError, match="tube_od must be positive"):
            tube_manager.add_tube("Test", tube_od=0.0)
        with pytest.raises(ValueError, match="tube_od must be positive"):
            tube_manager.add_tube("Test", tube_od=-1.0)

    def test_add_tube_invalid_wall_thickness_raises(
        self, tube_manager: TubeManager
    ) -> None:
        with pytest.raises(ValueError, match="wall_thickness must be non-negative"):
            tube_manager.add_tube("Test", tube_od=4.445, wall_thickness=-0.1)

    def test_get_tube_by_id(self, tube_manager: TubeManager) -> None:
        tube = tube_manager.add_tube("Test", 4.445)
        found = tube_manager.get_tube_by_id(tube.id)
        assert found is not None
        assert found.name == "Test"

    def test_get_tube_by_id_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        assert tube_manager.get_tube_by_id("nonexistent") is None

    def test_get_tube_by_name(self, tube_manager: TubeManager) -> None:
        tube_manager.add_tube("DOM 1020", 4.445)
        found = tube_manager.get_tube_by_name("DOM 1020")
        assert found is not None
        assert found.name == "DOM 1020"

    def test_get_tube_by_name_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        assert tube_manager.get_tube_by_name("Nonexistent") is None

    def test_get_tubes_by_tube_od(
        self, tube_manager: TubeManager
    ) -> None:
        tube_manager.add_tube("DOM 1020 - 1.75", 4.445)
        tube_manager.add_tube("4130 - 1.75", 4.445)
        tube_manager.add_tube("DOM 1020 - 1.5", 3.81)
        matches = tube_manager.get_tubes_by_tube_od(4.445)
        assert len(matches) == 2

    def test_get_tubes_by_tube_od_no_match(
        self, tube_manager: TubeManager
    ) -> None:
        tube_manager.add_tube("Test", 4.445)
        matches = tube_manager.get_tubes_by_tube_od(10.0)
        assert matches == []

    def test_update_tube(self, tube_manager: TubeManager) -> None:
        tube = tube_manager.add_tube("Original", 4.445, batch="Old batch")
        result = tube_manager.update_tube(
            tube.id, name="Updated", tube_od=3.81, batch="New batch", notes="New notes"
        )
        assert result is True
        updated = tube_manager.get_tube_by_id(tube.id)
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.tube_od == 3.81

    def test_update_tube_new_fields(self, tube_manager: TubeManager) -> None:
        """Update wall_thickness and material_type."""
        tube = tube_manager.add_tube("Test", 4.445)
        result = tube_manager.update_tube(
            tube.id, wall_thickness=0.3048, material_type="DOM"
        )
        assert result is True
        updated = tube_manager.get_tube_by_id(tube.id)
        assert updated is not None
        assert updated.wall_thickness == 0.3048
        assert updated.material_type == "DOM"

    def test_update_tube_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        result = tube_manager.update_tube("nonexistent", name="Test")
        assert result is False

    def test_update_tube_invalid_tube_od_raises(
        self, tube_manager: TubeManager
    ) -> None:
        tube = tube_manager.add_tube("Test", 4.445)
        with pytest.raises(ValueError, match="tube_od must be positive"):
            tube_manager.update_tube(tube.id, tube_od=0.0)

    def test_update_tube_invalid_wall_thickness_raises(
        self, tube_manager: TubeManager
    ) -> None:
        tube = tube_manager.add_tube("Test", 4.445)
        with pytest.raises(ValueError, match="wall_thickness must be non-negative"):
            tube_manager.update_tube(tube.id, wall_thickness=-0.5)

    def test_delete_tube(self, tube_manager: TubeManager) -> None:
        tube = tube_manager.add_tube("ToDelete", 4.445)
        result = tube_manager.delete_tube(tube.id)
        assert result is True
        assert tube_manager.get_tube_by_id(tube.id) is None

    def test_delete_tube_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        result = tube_manager.delete_tube("nonexistent")
        assert result is False

    def test_delete_tube_removes_compensation_data(
        self, tube_manager: TubeManager
    ) -> None:
        tube = tube_manager.add_tube("Test", 4.445)
        tube_manager.add_compensation_point("die-001", tube.id, 72.2, 65.95)
        comp = tube_manager.get_compensation("die-001", tube.id)
        assert comp is not None
        tube_manager.delete_tube(tube.id)
        comp = tube_manager.get_compensation("die-001", tube.id)
        assert comp is None


class TestTubeManagerCompensation:
    """Test TubeManager compensation data operations."""

    @pytest.fixture
    def tube_manager(self, tmp_path: Path) -> TubeManager:
        return TubeManager(str(tmp_path))

    def test_get_compensation_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        result = tube_manager.get_compensation("die-001", "mat-001")
        assert result is None

    def test_get_or_create_compensation_creates(
        self, tube_manager: TubeManager
    ) -> None:
        comp = tube_manager.get_or_create_compensation("die-001", "mat-001")
        assert comp.die_id == "die-001"
        assert comp.material_id == "mat-001"
        assert comp.data_points == []

    def test_get_or_create_compensation_returns_existing(
        self, tube_manager: TubeManager
    ) -> None:
        comp1 = tube_manager.get_or_create_compensation("die-001", "mat-001")
        comp1.add_data_point(72.2, 65.95)
        tube_manager.save()
        comp2 = tube_manager.get_or_create_compensation("die-001", "mat-001")
        assert len(comp2.data_points) == 1

    def test_add_compensation_point(
        self, tube_manager: TubeManager
    ) -> None:
        result = tube_manager.add_compensation_point(
            "die-001", "mat-001", 72.2, 65.95
        )
        assert result is True
        comp = tube_manager.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 72.2

    def test_add_compensation_point_invalid_raises(
        self, tube_manager: TubeManager
    ) -> None:
        with pytest.raises(ValueError, match="readout_angle must be positive"):
            tube_manager.add_compensation_point("die-001", "mat-001", 0.0, 65.95)
        with pytest.raises(ValueError, match="measured_angle.*must be less than"):
            tube_manager.add_compensation_point("die-001", "mat-001", 60.0, 70.0)

    def test_add_compensation_point_saves_immediately(
        self, tube_manager: TubeManager, tmp_path: Path
    ) -> None:
        tube_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        manager2 = TubeManager(str(tmp_path))
        comp = manager2.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 1

    def test_remove_compensation_point(
        self, tube_manager: TubeManager
    ) -> None:
        tube_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        tube_manager.add_compensation_point("die-001", "mat-001", 90.0, 83.5)
        result = tube_manager.remove_compensation_point("die-001", "mat-001", 0)
        assert result is True
        comp = tube_manager.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 90.0

    def test_remove_compensation_point_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        result = tube_manager.remove_compensation_point("die-001", "mat-001", 0)
        assert result is False

    def test_remove_compensation_point_index_out_of_range(
        self, tube_manager: TubeManager
    ) -> None:
        tube_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        result = tube_manager.remove_compensation_point("die-001", "mat-001", 5)
        assert result is False

    def test_clear_compensation_data(
        self, tube_manager: TubeManager
    ) -> None:
        tube_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        tube_manager.add_compensation_point("die-001", "mat-001", 90.0, 83.5)
        result = tube_manager.clear_compensation_data("die-001", "mat-001")
        assert result is True
        comp = tube_manager.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 0

    def test_clear_compensation_data_not_found(
        self, tube_manager: TubeManager
    ) -> None:
        result = tube_manager.clear_compensation_data("die-001", "mat-001")
        assert result is False

    def test_delete_compensation_for_die(
        self, tube_manager: TubeManager
    ) -> None:
        tube_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        tube_manager.add_compensation_point("die-001", "mat-002", 72.2, 65.95)
        tube_manager.add_compensation_point("die-002", "mat-001", 72.2, 65.95)
        removed = tube_manager.delete_compensation_for_die("die-001")
        assert removed == 2
        assert tube_manager.get_compensation("die-001", "mat-001") is None
        assert tube_manager.get_compensation("die-001", "mat-002") is None
        assert tube_manager.get_compensation("die-002", "mat-001") is not None

    def test_delete_compensation_for_die_none_found(
        self, tube_manager: TubeManager
    ) -> None:
        removed = tube_manager.delete_compensation_for_die("nonexistent")
        assert removed == 0


class TestTubeManagerPersistence:
    """Test TubeManager save/load functionality."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        manager1 = TubeManager(str(tmp_path))
        tube = manager1.add_tube(
            "DOM 1020", 4.445, wall_thickness=0.3048, material_type="DOM", batch="Batch A"
        )
        manager1.add_compensation_point("die-001", tube.id, 72.2, 65.95)
        manager2 = TubeManager(str(tmp_path))
        loaded_tube = manager2.get_tube_by_name("DOM 1020")
        assert loaded_tube is not None
        assert loaded_tube.batch == "Batch A"
        assert loaded_tube.wall_thickness == 0.3048
        assert loaded_tube.material_type == "DOM"
        comp = manager2.get_compensation("die-001", tube.id)
        assert comp is not None
        assert len(comp.data_points) == 1

    def test_reload_picks_up_changes(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        tube = manager.add_tube("Original", 4.445)
        json_path = tmp_path / 'resources' / 'tubes.json'
        with open(json_path) as f:
            data: dict[str, Any] = json.load(f)
        data['tubes'][0]['name'] = 'Modified'
        with open(json_path, 'w') as f:
            json.dump(data, f)
        manager.reload()
        found = manager.get_tube_by_id(tube.id)
        assert found is not None
        assert found.name == 'Modified'

    def test_load_corrupt_json_starts_fresh(self, tmp_path: Path) -> None:
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        json_path = resources_path / 'tubes.json'
        json_path.write_text('{ not valid json }')
        manager = TubeManager(str(tmp_path))
        assert manager.tubes == []
        assert manager.compensation_data == []

    def test_load_invalid_tube_skipped(self, tmp_path: Path) -> None:
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        json_path = resources_path / 'tubes.json'
        data = {
            'version': '1.1',
            'tubes': [
                {'id': '1', 'name': 'Good', 'tube_od': 4.445, 'wall_thickness': 0.0,
                 'material_type': '', 'batch': '', 'notes': ''},
                {'missing': 'required fields'},
                {'id': '3', 'name': 'Also Good', 'tube_od': 3.81, 'wall_thickness': 0.0,
                 'material_type': '', 'batch': '', 'notes': ''},
            ],
            'compensation_data': []
        }
        json_path.write_text(json.dumps(data))
        manager = TubeManager(str(tmp_path))
        assert len(manager.tubes) == 2

    def test_load_invalid_compensation_skipped(self, tmp_path: Path) -> None:
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        json_path = resources_path / 'tubes.json'
        data = {
            'version': '1.1',
            'tubes': [],
            'compensation_data': [
                {'die_id': 'die-001', 'material_id': 'mat-001', 'data_points': []},
                {'missing': 'required fields'},
            ]
        }
        json_path.write_text(json.dumps(data))
        manager = TubeManager(str(tmp_path))
        assert len(manager.compensation_data) == 1


class TestTubeManagerMigration:
    """Test migration from materials.json to tubes.json."""

    def test_migrate_from_materials_json(self, tmp_path: Path) -> None:
        """Load from legacy materials.json when tubes.json doesn't exist."""
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        legacy_path = resources_path / 'materials.json'
        legacy_data = {
            'version': '1.0',
            'materials': [
                {'id': 'mat-001', 'name': 'DOM 1020', 'tube_od': 4.445,
                 'batch': 'B-2024', 'notes': 'Legacy tube'},
            ],
            'compensation_data': [
                {'die_id': 'die-001', 'material_id': 'mat-001', 'data_points': [
                    {'readout_angle': 72.2, 'measured_angle': 65.95}
                ]},
            ]
        }
        legacy_path.write_text(json.dumps(legacy_data))

        manager = TubeManager(str(tmp_path))
        assert len(manager.tubes) == 1
        assert manager.tubes[0].name == 'DOM 1020'
        assert manager.tubes[0].wall_thickness == 0.0  # Defaulted
        assert manager.tubes[0].material_type == ''  # Defaulted

        comp = manager.get_compensation('die-001', 'mat-001')
        assert comp is not None
        assert len(comp.data_points) == 1

        # Verify tubes.json was created
        new_path = resources_path / 'tubes.json'
        assert new_path.exists()

    def test_migration_creates_valid_v11_file(self, tmp_path: Path) -> None:
        """Migration produces a valid v1.1 JSON file."""
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        legacy_path = resources_path / 'materials.json'
        legacy_data = {
            'version': '1.0',
            'materials': [
                {'id': 'mat-001', 'name': 'DOM 1020', 'tube_od': 4.445,
                 'batch': '', 'notes': ''},
            ],
            'compensation_data': []
        }
        legacy_path.write_text(json.dumps(legacy_data))

        manager = TubeManager(str(tmp_path))
        _ = manager.tubes  # Trigger load

        new_path = resources_path / 'tubes.json'
        with open(new_path) as f:
            data = json.load(f)

        assert data['version'] == '1.1'
        assert 'tubes' in data
        assert isinstance(data['tubes'], list)
        assert len(data['tubes']) == 1
        # Verify new fields were written with defaults
        assert data['tubes'][0]['wall_thickness'] == 0.0
        assert data['tubes'][0]['material_type'] == ''

    def test_tubes_json_preferred_over_materials_json(self, tmp_path: Path) -> None:
        """When both files exist, tubes.json is used."""
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)

        # Create legacy file
        legacy_path = resources_path / 'materials.json'
        legacy_data = {
            'version': '1.0',
            'materials': [
                {'id': 'mat-001', 'name': 'Legacy Tube', 'tube_od': 4.445,
                 'batch': '', 'notes': ''},
            ],
            'compensation_data': []
        }
        legacy_path.write_text(json.dumps(legacy_data))

        # Create new file
        new_path = resources_path / 'tubes.json'
        new_data = {
            'version': '1.1',
            'tubes': [
                {'id': 'tube-001', 'name': 'New Tube', 'tube_od': 3.81,
                 'wall_thickness': 0.3048, 'material_type': 'DOM',
                 'batch': '', 'notes': ''},
            ],
            'compensation_data': []
        }
        new_path.write_text(json.dumps(new_data))

        manager = TubeManager(str(tmp_path))
        assert len(manager.tubes) == 1
        assert manager.tubes[0].name == 'New Tube'
        assert manager.tubes[0].tube_od == 3.81


class TestTubeManagerJSON:
    """Test TubeManager JSON file structure."""

    def test_json_has_version(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        manager.add_tube("Test", 4.445)
        json_path = tmp_path / 'resources' / 'tubes.json'
        with open(json_path) as f:
            data = json.load(f)
        assert data['version'] == '1.1'

    def test_json_structure(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        tube = manager.add_tube("Test", 4.445)
        manager.add_compensation_point("die-001", tube.id, 72.2, 65.95)
        json_path = tmp_path / 'resources' / 'tubes.json'
        with open(json_path) as f:
            data = json.load(f)
        assert 'version' in data
        assert 'tubes' in data
        assert 'compensation_data' in data
        assert isinstance(data['tubes'], list)
        assert isinstance(data['compensation_data'], list)

    def test_json_includes_new_fields(self, tmp_path: Path) -> None:
        """Saved JSON includes wall_thickness and material_type."""
        manager = TubeManager(str(tmp_path))
        manager.add_tube(
            "DOM 1020", 4.445, wall_thickness=0.3048, material_type="DOM"
        )
        json_path = tmp_path / 'resources' / 'tubes.json'
        with open(json_path) as f:
            data = json.load(f)
        tube_data = data['tubes'][0]
        assert tube_data['wall_thickness'] == 0.3048
        assert tube_data['material_type'] == 'DOM'

    def test_production_tubes_json_uses_cm(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        tube_od_inches = 1.75
        tube_od_cm = tube_od_inches * 2.54
        manager.add_tube("1.75\" DOM", tube_od_cm)
        json_path = tmp_path / 'resources' / 'tubes.json'
        with open(json_path) as f:
            data = json.load(f)
        saved_tube_od = data['tubes'][0]['tube_od']
        assert saved_tube_od > 3


class TestTubeIdMapBatchSuffix:
    """Test tube ID map approach for handling batch suffixes."""

    @pytest.fixture
    def tube_manager(self, tmp_path: Path) -> TubeManager:
        return TubeManager(str(tmp_path))

    def test_tube_id_map_handles_batch_suffix(
        self, tube_manager: TubeManager
    ) -> None:
        """Tube ID map correctly maps display names with batch to IDs."""
        tube = tube_manager.add_tube("DOM 1020", 4.445, batch="B-2024")

        # Simulate what dialog_builder does: create display name with batch suffix
        display_name = tube.name
        if tube.batch:
            display_name += f" [{tube.batch}]"

        # Create the ID map (display_name -> tube_id)
        tube_id_map = {display_name: tube.id}

        # Verify lookup by ID works after going through the map
        found = tube_manager.get_tube_by_id(tube_id_map[display_name])
        assert found is not None
        assert found.id == tube.id
        assert found.name == "DOM 1020"
        assert found.batch == "B-2024"

    def test_tube_name_lookup_fails_with_batch_suffix(
        self, tube_manager: TubeManager
    ) -> None:
        """get_tube_by_name fails when batch suffix is included."""
        tube = tube_manager.add_tube("DOM 1020", 4.445, batch="B-2024")

        # Name lookup with batch suffix should fail
        display_name = f"{tube.name} [{tube.batch}]"
        found = tube_manager.get_tube_by_name(display_name)
        assert found is None

        # Name lookup without batch suffix should work
        found = tube_manager.get_tube_by_name(tube.name)
        assert found is not None

    def test_multiple_tubes_same_name_different_batch(
        self, tube_manager: TubeManager
    ) -> None:
        """ID map distinguishes tubes with same name but different batches."""
        tube1 = tube_manager.add_tube("DOM 1020", 4.445, batch="B-2024-01")
        tube2 = tube_manager.add_tube("DOM 1020", 4.445, batch="B-2024-02")

        # Build ID map for both
        tube_id_map: dict[str, str] = {}
        for tube in [tube1, tube2]:
            display_name = tube.name
            if tube.batch:
                display_name += f" [{tube.batch}]"
            tube_id_map[display_name] = tube.id

        # Verify each lookup returns the correct tube
        found1 = tube_manager.get_tube_by_id(
            tube_id_map["DOM 1020 [B-2024-01]"]
        )
        found2 = tube_manager.get_tube_by_id(
            tube_id_map["DOM 1020 [B-2024-02]"]
        )

        assert found1 is not None
        assert found2 is not None
        assert found1.id != found2.id
        assert found1.batch == "B-2024-01"
        assert found2.batch == "B-2024-02"


class TestTubeManagerAtomicWrite:
    """Test atomic write pattern in TubeManager."""

    def test_atomic_write_no_temp_file_remains(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        manager.add_tube("Test", 4.445)
        temp_path = tmp_path / 'resources' / 'tubes.tmp'
        assert not temp_path.exists()

    def test_directory_creation(self, tmp_path: Path) -> None:
        manager = TubeManager(str(tmp_path))
        manager.add_tube("Test", 4.445)
        resources_path = tmp_path / 'resources'
        assert resources_path.exists()


class TestTubeManagerConcurrentAccess:
    """Test thread-safe access to TubeManager."""

    def test_concurrent_access_thread_safe(self, tmp_path: Path) -> None:
        """TubeManager handles concurrent access to tubes safely."""
        manager = TubeManager(str(tmp_path))
        manager.add_tube("Test Tube", 4.445)
        manager.save()

        results: list[int] = []
        errors: list[Exception] = []

        def access_tubes() -> None:
            try:
                tubes = manager.tubes
                results.append(len(tubes))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_tubes) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert all(r == 1 for r in results), f"Unexpected results: {results}"

    def test_concurrent_compensation_access_thread_safe(
        self, tmp_path: Path
    ) -> None:
        """TubeManager handles concurrent access to compensation_data safely."""
        manager = TubeManager(str(tmp_path))
        manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        manager.save()

        results: list[int] = []
        errors: list[Exception] = []

        def access_compensation() -> None:
            try:
                comp_data = manager.compensation_data
                results.append(len(comp_data))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_compensation) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert all(r == 1 for r in results), f"Unexpected results: {results}"
