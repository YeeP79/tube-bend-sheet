"""Material and compensation data storage and management."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from ..models.material import Material, validate_material_values
from ..models.compensation import (
    DieMaterialCompensation,
    validate_compensation_values,
)
from ..lib import fusionAddInUtils as futil


class MaterialSaveError(IOError):
    """Raised when saving materials fails."""

    pass


class MaterialLoadError(IOError):
    """Raised when loading materials fails due to I/O errors."""

    pass


class MaterialManager:
    """
    Manages materials and compensation data stored in JSON.

    Materials and compensation data are stored in a materials.json file
    in the add-in's resources folder.

    Schema Version History:
        1.0 - Initial schema with materials and compensation_data
    """

    FILENAME = 'materials.json'
    CURRENT_VERSION = '1.0'
    SUPPORTED_VERSIONS = {'1.0'}

    def __init__(self, addin_path: str) -> None:
        """
        Initialize the material manager.

        Args:
            addin_path: Path to the add-in root directory
        """
        self._addin_path = Path(addin_path)
        self._resources_path = self._addin_path / 'resources'
        self._materials_path = self._resources_path / self.FILENAME
        self._materials: list[Material] = []
        self._compensation_data: list[DieMaterialCompensation] = []
        self._loaded = False
        self._load_lock = threading.Lock()

    @property
    def materials(self) -> list[Material]:
        """Get all materials.

        Thread-safe lazy loading using a lock to prevent race conditions
        when multiple threads access materials simultaneously.
        """
        with self._load_lock:
            if not self._loaded:
                self.load()
        return self._materials

    @property
    def compensation_data(self) -> list[DieMaterialCompensation]:
        """Get all compensation data.

        Thread-safe lazy loading using a lock to prevent race conditions.
        """
        with self._load_lock:
            if not self._loaded:
                self.load()
        return self._compensation_data

    def reload(self) -> None:
        """
        Force reload data from disk.

        Use this when the file may have been modified externally
        and you need to pick up the latest changes.
        """
        self._loaded = False
        self.load()

    def load(self) -> None:
        """
        Load materials and compensation data from disk.

        If no file exists, creates empty defaults.
        If file is corrupted (invalid JSON), creates fresh defaults.
        Invalid individual entries are skipped with a warning.

        Raises:
            MaterialLoadError: If file exists but cannot be read due to I/O errors
        """
        self._materials = []
        self._compensation_data = []

        if not self._materials_path.exists():
            # Create empty file if none exists
            self.save()
        else:
            try:
                with open(self._materials_path, encoding='utf-8') as f:
                    data = json.load(f)

                # Validate top-level structure
                if not isinstance(data, dict):
                    raise MaterialLoadError(
                        "Invalid materials format: expected JSON object at root"
                    )

                # Check schema version
                file_version = data.get('version', '1.0')
                if file_version not in self.SUPPORTED_VERSIONS:
                    raise MaterialLoadError(
                        f"Unsupported materials schema version: {file_version}. "
                        f"Supported versions: {', '.join(sorted(self.SUPPORTED_VERSIONS))}"
                    )

                # Parse materials
                materials_list = data.get('materials', [])
                if isinstance(materials_list, list):
                    for i, mat_data in enumerate(materials_list):
                        try:
                            self._materials.append(Material.from_dict(mat_data))
                        except (KeyError, TypeError, ValueError) as e:
                            futil.log(f"Warning: Skipping invalid material at index {i}: {e}")
                            continue

                # Parse compensation data
                comp_list = data.get('compensation_data', [])
                if isinstance(comp_list, list):
                    for i, comp_data in enumerate(comp_list):
                        try:
                            self._compensation_data.append(
                                DieMaterialCompensation.from_dict(comp_data)
                            )
                        except (KeyError, TypeError, ValueError) as e:
                            futil.log(
                                f"Warning: Skipping invalid compensation data at index {i}: {e}"
                            )
                            continue

            except json.JSONDecodeError as e:
                # If file is corrupted JSON, start fresh
                futil.log(f"Error loading materials (invalid JSON): {e}")
                self.save()

            except OSError as e:
                # I/O errors are not recoverable - raise to caller
                raise MaterialLoadError(f"Failed to load materials: {e}") from e

        self._loaded = True

    def save(self) -> None:
        """
        Save materials and compensation data to disk using atomic write pattern.

        Writes to a temporary file first, then atomically renames to target.
        This prevents data corruption from interrupted writes.

        Raises:
            MaterialSaveError: If file cannot be written
        """
        temp_path = self._materials_path.with_suffix('.tmp')

        try:
            # Ensure resources directory exists
            self._resources_path.mkdir(parents=True, exist_ok=True)

            data = {
                'version': self.CURRENT_VERSION,
                'materials': [m.to_dict() for m in self._materials],
                'compensation_data': [c.to_dict() for c in self._compensation_data],
            }

            # Write to temp file first
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Atomic rename to target (overwrites existing)
            temp_path.replace(self._materials_path)

        except (OSError, TypeError) as e:
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass  # Best effort cleanup

            raise MaterialSaveError(f"Failed to save materials: {e}") from e

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        return str(uuid.uuid4())[:8]

    # -------------------------------------------------------------------------
    # Material CRUD Operations
    # -------------------------------------------------------------------------

    def get_material_by_id(self, material_id: str) -> Material | None:
        """Find a material by ID."""
        for material in self.materials:
            if material.id == material_id:
                return material
        return None

    def get_material_by_name(self, name: str) -> Material | None:
        """Find a material by name."""
        for material in self.materials:
            if material.name == name:
                return material
        return None

    def get_materials_by_tube_od(
        self, tube_od: float, tolerance: float = 0.01
    ) -> list[Material]:
        """
        Get all materials that match a given tube OD.

        Args:
            tube_od: Tube outer diameter to match (in cm)
            tolerance: Matching tolerance (default 0.01 cm)

        Returns:
            List of matching materials
        """
        return [m for m in self.materials if m.matches_tube_od(tube_od, tolerance)]

    def add_material(
        self,
        name: str,
        tube_od: float,
        batch: str = "",
        notes: str = "",
    ) -> Material:
        """
        Add a new material.

        Args:
            name: Display name for the material
            tube_od: Tube outer diameter (must be positive)
            batch: Optional batch/lot number
            notes: Optional notes

        Returns:
            The created Material

        Raises:
            ValueError: If tube_od is not positive
        """
        validate_material_values(tube_od=tube_od)

        material = Material(
            id=self._generate_id(),
            name=name,
            tube_od=tube_od,
            batch=batch,
            notes=notes,
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
        """
        Update an existing material.

        Args:
            material_id: ID of material to update
            name: New name (optional)
            tube_od: New tube OD - must be positive (optional)
            batch: New batch number (optional)
            notes: New notes (optional)

        Returns:
            True if material was found and updated

        Raises:
            ValueError: If tube_od is not positive
        """
        material = self.get_material_by_id(material_id)
        if material is None:
            return False

        # Validate tube_od before updating
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
        """
        Delete a material and its associated compensation data.

        Returns:
            True if material was found and deleted
        """
        for i, material in enumerate(self._materials):
            if material.id == material_id:
                self._materials.pop(i)
                # Also remove any compensation data for this material
                self._compensation_data = [
                    c for c in self._compensation_data if c.material_id != material_id
                ]
                self.save()
                return True
        return False

    # -------------------------------------------------------------------------
    # Compensation Data Operations
    # -------------------------------------------------------------------------

    def get_compensation(
        self, die_id: str, material_id: str
    ) -> DieMaterialCompensation | None:
        """
        Get compensation data for a specific die-material pair.

        Args:
            die_id: ID of the die
            material_id: ID of the material

        Returns:
            DieMaterialCompensation if found, None otherwise
        """
        for comp in self.compensation_data:
            if comp.die_id == die_id and comp.material_id == material_id:
                return comp
        return None

    def get_or_create_compensation(
        self, die_id: str, material_id: str
    ) -> DieMaterialCompensation:
        """
        Get existing compensation data or create new empty entry.

        Args:
            die_id: ID of the die
            material_id: ID of the material

        Returns:
            DieMaterialCompensation (existing or newly created)
        """
        comp = self.get_compensation(die_id, material_id)
        if comp is None:
            comp = DieMaterialCompensation(
                die_id=die_id,
                material_id=material_id,
                data_points=[],
            )
            self._compensation_data.append(comp)
            self.save()
        return comp

    def add_compensation_point(
        self,
        die_id: str,
        material_id: str,
        readout_angle: float,
        measured_angle: float,
    ) -> bool:
        """
        Add a compensation data point for a die-material pair.

        Args:
            die_id: ID of the die
            material_id: ID of the material
            readout_angle: What bender readout showed (degrees)
            measured_angle: Actual measured angle (degrees)

        Returns:
            True if added successfully

        Raises:
            ValueError: If values are invalid or duplicate readout_angle exists
        """
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
        """
        Remove a compensation data point by index.

        Args:
            die_id: ID of the die
            material_id: ID of the material
            index: Index of data point to remove

        Returns:
            True if removed, False if not found or index out of range
        """
        comp = self.get_compensation(die_id, material_id)
        if comp is None:
            return False

        if comp.remove_data_point(index):
            self.save()
            return True
        return False

    def clear_compensation_data(self, die_id: str, material_id: str) -> bool:
        """
        Clear all compensation data points for a die-material pair.

        Use this when the bender is recalibrated and all previous
        data becomes invalid.

        Args:
            die_id: ID of the die
            material_id: ID of the material

        Returns:
            True if cleared, False if no data found
        """
        comp = self.get_compensation(die_id, material_id)
        if comp is None:
            return False

        comp.clear_data_points()
        self.save()
        return True

    def delete_compensation_for_die(self, die_id: str) -> int:
        """
        Delete all compensation data associated with a die.

        Call this when a die is deleted.

        Args:
            die_id: ID of the die

        Returns:
            Number of compensation entries removed
        """
        original_count = len(self._compensation_data)
        self._compensation_data = [
            c for c in self._compensation_data if c.die_id != die_id
        ]
        removed = original_count - len(self._compensation_data)
        if removed > 0:
            self.save()
        return removed
