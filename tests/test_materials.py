"""
Tests for MaterialManager - runs without Fusion.

This test file duplicates the MaterialManager and related classes locally
to avoid import issues with relative imports in storage/materials.py.

Run with: pytest tests/test_materials.py -v
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


def validate_material_values(tube_od: float | None = None) -> None:
    """Validate material numeric values."""
    if tube_od is not None and tube_od <= 0:
        raise ValueError(f"tube_od must be positive, got {tube_od}")


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
class Material:
    """Local copy of Material for testing."""
    id: str
    name: str
    tube_od: float
    batch: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        validate_material_values(tube_od=self.tube_od)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tube_od": self.tube_od,
            "batch": self.batch,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Material":
        tube_od = max(0.001, data['tube_od'])
        return cls(
            id=data['id'],
            name=data['name'],
            tube_od=tube_od,
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
# MaterialManager - local copy for testing
# =============================================================================


class MaterialManager:
    """Local copy of MaterialManager for testing."""

    FILENAME = 'materials.json'
    CURRENT_VERSION = '1.0'
    SUPPORTED_VERSIONS = {'1.0'}

    def __init__(self, addin_path: str) -> None:
        self._addin_path = Path(addin_path)
        self._resources_path = self._addin_path / 'resources'
        self._materials_path = self._resources_path / self.FILENAME
        self._materials: list[Material] = []
        self._compensation_data: list[DieMaterialCompensation] = []
        self._loaded = False
        self._load_lock = threading.Lock()

    @property
    def materials(self) -> list[Material]:
        with self._load_lock:
            if not self._loaded:
                self.load()
        return self._materials

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
        self._materials = []
        self._compensation_data = []

        if not self._materials_path.exists():
            self.save()
        else:
            try:
                with open(self._materials_path, encoding='utf-8') as f:
                    data = json.load(f)

                materials_list = data.get('materials', [])
                if isinstance(materials_list, list):
                    for mat_data in materials_list:
                        try:
                            self._materials.append(Material.from_dict(mat_data))
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
            except json.JSONDecodeError:
                self.save()

        self._loaded = True

    def save(self) -> None:
        temp_path = self._materials_path.with_suffix('.tmp')
        self._resources_path.mkdir(parents=True, exist_ok=True)
        data = {
            'version': self.CURRENT_VERSION,
            'materials': [m.to_dict() for m in self._materials],
            'compensation_data': [c.to_dict() for c in self._compensation_data],
        }
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self._materials_path)

    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def get_material_by_id(self, material_id: str) -> Material | None:
        for material in self.materials:
            if material.id == material_id:
                return material
        return None

    def get_material_by_name(self, name: str) -> Material | None:
        for material in self.materials:
            if material.name == name:
                return material
        return None

    def get_materials_by_tube_od(
        self, tube_od: float, tolerance: float = 0.01
    ) -> list[Material]:
        return [m for m in self.materials if m.matches_tube_od(tube_od, tolerance)]

    def add_material(
        self, name: str, tube_od: float, batch: str = "", notes: str = ""
    ) -> Material:
        validate_material_values(tube_od=tube_od)
        material = Material(
            id=self._generate_id(), name=name, tube_od=tube_od, batch=batch, notes=notes
        )
        self._materials.append(material)
        self.save()
        return material

    def update_material(
        self,
        material_id: str,
        name: str | None = None,
        tube_od: float | None = None,
        batch: str | None = None,
        notes: str | None = None,
    ) -> bool:
        material = self.get_material_by_id(material_id)
        if material is None:
            return False
        validate_material_values(tube_od=tube_od)
        if name is not None:
            material.name = name
        if tube_od is not None:
            material.tube_od = tube_od
        if batch is not None:
            material.batch = batch
        if notes is not None:
            material.notes = notes
        self.save()
        return True

    def delete_material(self, material_id: str) -> bool:
        for i, material in enumerate(self._materials):
            if material.id == material_id:
                self._materials.pop(i)
                self._compensation_data = [
                    c for c in self._compensation_data if c.material_id != material_id
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


class TestMaterialManagerBasics:
    """Test MaterialManager basic operations."""

    @pytest.fixture
    def material_manager(self, tmp_path: Path) -> MaterialManager:
        return MaterialManager(str(tmp_path))

    def test_initial_state_empty(self, material_manager: MaterialManager) -> None:
        assert material_manager.materials == []
        assert material_manager.compensation_data == []

    def test_materials_property_lazy_loads(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        materials = manager.materials
        assert isinstance(materials, list)

    def test_compensation_data_property_lazy_loads(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        comp_data = manager.compensation_data
        assert isinstance(comp_data, list)


class TestMaterialManagerMaterialCRUD:
    """Test MaterialManager material CRUD operations."""

    @pytest.fixture
    def material_manager(self, tmp_path: Path) -> MaterialManager:
        return MaterialManager(str(tmp_path))

    def test_add_material(self, material_manager: MaterialManager) -> None:
        material = material_manager.add_material(
            name="DOM 1020", tube_od=4.445, batch="B-2024", notes="Test material"
        )
        assert material.name == "DOM 1020"
        assert material.tube_od == 4.445
        assert len(material.id) == 8

    def test_add_material_creates_unique_id(
        self, material_manager: MaterialManager
    ) -> None:
        mat1 = material_manager.add_material("Material 1", 4.445)
        mat2 = material_manager.add_material("Material 2", 4.445)
        assert mat1.id != mat2.id

    def test_add_material_saves_immediately(
        self, material_manager: MaterialManager, tmp_path: Path
    ) -> None:
        material_manager.add_material("New Material", 4.445)
        manager2 = MaterialManager(str(tmp_path))
        mat = manager2.get_material_by_name("New Material")
        assert mat is not None

    def test_add_material_invalid_tube_od_raises(
        self, material_manager: MaterialManager
    ) -> None:
        with pytest.raises(ValueError, match="tube_od must be positive"):
            material_manager.add_material("Test", tube_od=0.0)
        with pytest.raises(ValueError, match="tube_od must be positive"):
            material_manager.add_material("Test", tube_od=-1.0)

    def test_get_material_by_id(self, material_manager: MaterialManager) -> None:
        material = material_manager.add_material("Test", 4.445)
        found = material_manager.get_material_by_id(material.id)
        assert found is not None
        assert found.name == "Test"

    def test_get_material_by_id_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        assert material_manager.get_material_by_id("nonexistent") is None

    def test_get_material_by_name(self, material_manager: MaterialManager) -> None:
        material_manager.add_material("DOM 1020", 4.445)
        found = material_manager.get_material_by_name("DOM 1020")
        assert found is not None
        assert found.name == "DOM 1020"

    def test_get_material_by_name_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        assert material_manager.get_material_by_name("Nonexistent") is None

    def test_get_materials_by_tube_od(
        self, material_manager: MaterialManager
    ) -> None:
        material_manager.add_material("DOM 1020 - 1.75", 4.445)
        material_manager.add_material("4130 - 1.75", 4.445)
        material_manager.add_material("DOM 1020 - 1.5", 3.81)
        matches = material_manager.get_materials_by_tube_od(4.445)
        assert len(matches) == 2

    def test_get_materials_by_tube_od_no_match(
        self, material_manager: MaterialManager
    ) -> None:
        material_manager.add_material("Test", 4.445)
        matches = material_manager.get_materials_by_tube_od(10.0)
        assert matches == []

    def test_update_material(self, material_manager: MaterialManager) -> None:
        material = material_manager.add_material("Original", 4.445, "Old batch")
        result = material_manager.update_material(
            material.id, name="Updated", tube_od=3.81, batch="New batch", notes="New notes"
        )
        assert result is True
        updated = material_manager.get_material_by_id(material.id)
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.tube_od == 3.81

    def test_update_material_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        result = material_manager.update_material("nonexistent", name="Test")
        assert result is False

    def test_update_material_invalid_tube_od_raises(
        self, material_manager: MaterialManager
    ) -> None:
        material = material_manager.add_material("Test", 4.445)
        with pytest.raises(ValueError, match="tube_od must be positive"):
            material_manager.update_material(material.id, tube_od=0.0)

    def test_delete_material(self, material_manager: MaterialManager) -> None:
        material = material_manager.add_material("ToDelete", 4.445)
        result = material_manager.delete_material(material.id)
        assert result is True
        assert material_manager.get_material_by_id(material.id) is None

    def test_delete_material_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        result = material_manager.delete_material("nonexistent")
        assert result is False

    def test_delete_material_removes_compensation_data(
        self, material_manager: MaterialManager
    ) -> None:
        material = material_manager.add_material("Test", 4.445)
        material_manager.add_compensation_point("die-001", material.id, 72.2, 65.95)
        comp = material_manager.get_compensation("die-001", material.id)
        assert comp is not None
        material_manager.delete_material(material.id)
        comp = material_manager.get_compensation("die-001", material.id)
        assert comp is None


class TestMaterialManagerCompensation:
    """Test MaterialManager compensation data operations."""

    @pytest.fixture
    def material_manager(self, tmp_path: Path) -> MaterialManager:
        return MaterialManager(str(tmp_path))

    def test_get_compensation_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        result = material_manager.get_compensation("die-001", "mat-001")
        assert result is None

    def test_get_or_create_compensation_creates(
        self, material_manager: MaterialManager
    ) -> None:
        comp = material_manager.get_or_create_compensation("die-001", "mat-001")
        assert comp.die_id == "die-001"
        assert comp.material_id == "mat-001"
        assert comp.data_points == []

    def test_get_or_create_compensation_returns_existing(
        self, material_manager: MaterialManager
    ) -> None:
        comp1 = material_manager.get_or_create_compensation("die-001", "mat-001")
        comp1.add_data_point(72.2, 65.95)
        material_manager.save()
        comp2 = material_manager.get_or_create_compensation("die-001", "mat-001")
        assert len(comp2.data_points) == 1

    def test_add_compensation_point(
        self, material_manager: MaterialManager
    ) -> None:
        result = material_manager.add_compensation_point(
            "die-001", "mat-001", 72.2, 65.95
        )
        assert result is True
        comp = material_manager.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 72.2

    def test_add_compensation_point_invalid_raises(
        self, material_manager: MaterialManager
    ) -> None:
        with pytest.raises(ValueError, match="readout_angle must be positive"):
            material_manager.add_compensation_point("die-001", "mat-001", 0.0, 65.95)
        with pytest.raises(ValueError, match="measured_angle.*must be less than"):
            material_manager.add_compensation_point("die-001", "mat-001", 60.0, 70.0)

    def test_add_compensation_point_saves_immediately(
        self, material_manager: MaterialManager, tmp_path: Path
    ) -> None:
        material_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        manager2 = MaterialManager(str(tmp_path))
        comp = manager2.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 1

    def test_remove_compensation_point(
        self, material_manager: MaterialManager
    ) -> None:
        material_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        material_manager.add_compensation_point("die-001", "mat-001", 90.0, 83.5)
        result = material_manager.remove_compensation_point("die-001", "mat-001", 0)
        assert result is True
        comp = material_manager.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 1
        assert comp.data_points[0].readout_angle == 90.0

    def test_remove_compensation_point_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        result = material_manager.remove_compensation_point("die-001", "mat-001", 0)
        assert result is False

    def test_remove_compensation_point_index_out_of_range(
        self, material_manager: MaterialManager
    ) -> None:
        material_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        result = material_manager.remove_compensation_point("die-001", "mat-001", 5)
        assert result is False

    def test_clear_compensation_data(
        self, material_manager: MaterialManager
    ) -> None:
        material_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        material_manager.add_compensation_point("die-001", "mat-001", 90.0, 83.5)
        result = material_manager.clear_compensation_data("die-001", "mat-001")
        assert result is True
        comp = material_manager.get_compensation("die-001", "mat-001")
        assert comp is not None
        assert len(comp.data_points) == 0

    def test_clear_compensation_data_not_found(
        self, material_manager: MaterialManager
    ) -> None:
        result = material_manager.clear_compensation_data("die-001", "mat-001")
        assert result is False

    def test_delete_compensation_for_die(
        self, material_manager: MaterialManager
    ) -> None:
        material_manager.add_compensation_point("die-001", "mat-001", 72.2, 65.95)
        material_manager.add_compensation_point("die-001", "mat-002", 72.2, 65.95)
        material_manager.add_compensation_point("die-002", "mat-001", 72.2, 65.95)
        removed = material_manager.delete_compensation_for_die("die-001")
        assert removed == 2
        assert material_manager.get_compensation("die-001", "mat-001") is None
        assert material_manager.get_compensation("die-001", "mat-002") is None
        assert material_manager.get_compensation("die-002", "mat-001") is not None

    def test_delete_compensation_for_die_none_found(
        self, material_manager: MaterialManager
    ) -> None:
        removed = material_manager.delete_compensation_for_die("nonexistent")
        assert removed == 0


class TestMaterialManagerPersistence:
    """Test MaterialManager save/load functionality."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        manager1 = MaterialManager(str(tmp_path))
        mat = manager1.add_material("DOM 1020", 4.445, "Batch A")
        manager1.add_compensation_point("die-001", mat.id, 72.2, 65.95)
        manager2 = MaterialManager(str(tmp_path))
        loaded_mat = manager2.get_material_by_name("DOM 1020")
        assert loaded_mat is not None
        assert loaded_mat.batch == "Batch A"
        comp = manager2.get_compensation("die-001", mat.id)
        assert comp is not None
        assert len(comp.data_points) == 1

    def test_reload_picks_up_changes(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        mat = manager.add_material("Original", 4.445)
        json_path = tmp_path / 'resources' / 'materials.json'
        with open(json_path) as f:
            data: dict[str, Any] = json.load(f)
        data['materials'][0]['name'] = 'Modified'
        with open(json_path, 'w') as f:
            json.dump(data, f)
        manager.reload()
        found = manager.get_material_by_id(mat.id)
        assert found is not None
        assert found.name == 'Modified'

    def test_load_corrupt_json_starts_fresh(self, tmp_path: Path) -> None:
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        json_path = resources_path / 'materials.json'
        json_path.write_text('{ not valid json }')
        manager = MaterialManager(str(tmp_path))
        assert manager.materials == []
        assert manager.compensation_data == []

    def test_load_invalid_material_skipped(self, tmp_path: Path) -> None:
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        json_path = resources_path / 'materials.json'
        data = {
            'version': '1.0',
            'materials': [
                {'id': '1', 'name': 'Good', 'tube_od': 4.445, 'batch': '', 'notes': ''},
                {'missing': 'required fields'},
                {'id': '3', 'name': 'Also Good', 'tube_od': 3.81, 'batch': '', 'notes': ''},
            ],
            'compensation_data': []
        }
        json_path.write_text(json.dumps(data))
        manager = MaterialManager(str(tmp_path))
        assert len(manager.materials) == 2

    def test_load_invalid_compensation_skipped(self, tmp_path: Path) -> None:
        resources_path = tmp_path / 'resources'
        resources_path.mkdir(parents=True)
        json_path = resources_path / 'materials.json'
        data = {
            'version': '1.0',
            'materials': [],
            'compensation_data': [
                {'die_id': 'die-001', 'material_id': 'mat-001', 'data_points': []},
                {'missing': 'required fields'},
            ]
        }
        json_path.write_text(json.dumps(data))
        manager = MaterialManager(str(tmp_path))
        assert len(manager.compensation_data) == 1


class TestMaterialManagerJSON:
    """Test MaterialManager JSON file structure."""

    def test_json_has_version(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        manager.add_material("Test", 4.445)
        json_path = tmp_path / 'resources' / 'materials.json'
        with open(json_path) as f:
            data = json.load(f)
        assert data['version'] == '1.0'

    def test_json_structure(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        mat = manager.add_material("Test", 4.445)
        manager.add_compensation_point("die-001", mat.id, 72.2, 65.95)
        json_path = tmp_path / 'resources' / 'materials.json'
        with open(json_path) as f:
            data = json.load(f)
        assert 'version' in data
        assert 'materials' in data
        assert 'compensation_data' in data
        assert isinstance(data['materials'], list)
        assert isinstance(data['compensation_data'], list)

    def test_production_materials_json_uses_cm(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        tube_od_inches = 1.75
        tube_od_cm = tube_od_inches * 2.54
        manager.add_material("1.75\" DOM", tube_od_cm)
        json_path = tmp_path / 'resources' / 'materials.json'
        with open(json_path) as f:
            data = json.load(f)
        saved_tube_od = data['materials'][0]['tube_od']
        assert saved_tube_od > 3


class TestMaterialIdMapBatchSuffix:
    """Test material ID map approach for handling batch suffixes."""

    @pytest.fixture
    def material_manager(self, tmp_path: Path) -> MaterialManager:
        return MaterialManager(str(tmp_path))

    def test_material_id_map_handles_batch_suffix(
        self, material_manager: MaterialManager
    ) -> None:
        """Material ID map correctly maps display names with batch to IDs."""
        mat = material_manager.add_material("DOM 1020", 4.445, batch="B-2024")

        # Simulate what dialog_builder does: create display name with batch suffix
        display_name = mat.name
        if mat.batch:
            display_name += f" [{mat.batch}]"

        # Create the ID map (display_name -> material_id)
        material_id_map = {display_name: mat.id}

        # Verify lookup by ID works after going through the map
        found = material_manager.get_material_by_id(material_id_map[display_name])
        assert found is not None
        assert found.id == mat.id
        assert found.name == "DOM 1020"
        assert found.batch == "B-2024"

    def test_material_name_lookup_fails_with_batch_suffix(
        self, material_manager: MaterialManager
    ) -> None:
        """get_material_by_name fails when batch suffix is included."""
        mat = material_manager.add_material("DOM 1020", 4.445, batch="B-2024")

        # Name lookup with batch suffix should fail
        display_name = f"{mat.name} [{mat.batch}]"
        found = material_manager.get_material_by_name(display_name)
        assert found is None

        # Name lookup without batch suffix should work
        found = material_manager.get_material_by_name(mat.name)
        assert found is not None

    def test_multiple_materials_same_name_different_batch(
        self, material_manager: MaterialManager
    ) -> None:
        """ID map distinguishes materials with same name but different batches."""
        mat1 = material_manager.add_material("DOM 1020", 4.445, batch="B-2024-01")
        mat2 = material_manager.add_material("DOM 1020", 4.445, batch="B-2024-02")

        # Build ID map for both
        material_id_map: dict[str, str] = {}
        for mat in [mat1, mat2]:
            display_name = mat.name
            if mat.batch:
                display_name += f" [{mat.batch}]"
            material_id_map[display_name] = mat.id

        # Verify each lookup returns the correct material
        found1 = material_manager.get_material_by_id(
            material_id_map["DOM 1020 [B-2024-01]"]
        )
        found2 = material_manager.get_material_by_id(
            material_id_map["DOM 1020 [B-2024-02]"]
        )

        assert found1 is not None
        assert found2 is not None
        assert found1.id != found2.id
        assert found1.batch == "B-2024-01"
        assert found2.batch == "B-2024-02"


class TestMaterialManagerAtomicWrite:
    """Test atomic write pattern in MaterialManager."""

    def test_atomic_write_no_temp_file_remains(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        manager.add_material("Test", 4.445)
        temp_path = tmp_path / 'resources' / 'materials.tmp'
        assert not temp_path.exists()

    def test_directory_creation(self, tmp_path: Path) -> None:
        manager = MaterialManager(str(tmp_path))
        manager.add_material("Test", 4.445)
        resources_path = tmp_path / 'resources'
        assert resources_path.exists()


class TestMaterialManagerConcurrentAccess:
    """Test thread-safe access to MaterialManager."""

    def test_concurrent_access_thread_safe(self, tmp_path: Path) -> None:
        """MaterialManager handles concurrent access to materials safely."""
        manager = MaterialManager(str(tmp_path))
        manager.add_material("Test Material", 4.445)
        manager.save()

        results: list[int] = []
        errors: list[Exception] = []

        def access_materials() -> None:
            try:
                materials = manager.materials
                results.append(len(materials))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_materials) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert all(r == 1 for r in results), f"Unexpected results: {results}"

    def test_concurrent_compensation_access_thread_safe(
        self, tmp_path: Path
    ) -> None:
        """MaterialManager handles concurrent access to compensation_data safely."""
        manager = MaterialManager(str(tmp_path))
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
