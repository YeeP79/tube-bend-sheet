"""Tube and compensation data storage and management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models.tube import Tube, validate_tube_values
from ..models.compensation import (
    DieMaterialCompensation,
    validate_compensation_values,
)
from ..lib import fusionAddInUtils as futil
from .json_store import JsonFileStore


class TubeSaveError(IOError):
    """Raised when saving tubes fails."""

    pass


class TubeLoadError(IOError):
    """Raised when loading tubes fails due to I/O errors."""

    pass


class TubeManager(JsonFileStore):
    """
    Manages tubes and compensation data stored in JSON.

    Tubes and compensation data are stored in a tubes.json file
    in the add-in's resources folder.

    Schema Version History:
        1.0 - Initial schema with materials and compensation_data
        1.1 - Renamed to tubes.json, added wall_thickness and material_type
    """

    FILENAME = 'tubes.json'
    LEGACY_FILENAME = 'materials.json'
    CURRENT_VERSION = '1.1'
    SUPPORTED_VERSIONS = {'1.0', '1.1'}

    def __init__(self, addin_path: str) -> None:
        """
        Initialize the tube manager.

        Args:
            addin_path: Path to the add-in root directory
        """
        resources_path = Path(addin_path) / 'resources'
        super().__init__(resources_path, self.FILENAME)
        self._legacy_path = resources_path / self.LEGACY_FILENAME
        self._tubes: list[Tube] = []
        self._compensation_data: list[DieMaterialCompensation] = []

    @property
    def tubes(self) -> list[Tube]:
        """Get all tubes.

        Thread-safe lazy loading using a lock to prevent race conditions
        when multiple threads access tubes simultaneously.
        """
        self._ensure_loaded()
        return self._tubes

    @property
    def compensation_data(self) -> list[DieMaterialCompensation]:
        """Get all compensation data.

        Thread-safe lazy loading using a lock to prevent race conditions.
        """
        self._ensure_loaded()
        return self._compensation_data

    def load(self) -> None:
        """
        Load tubes and compensation data from disk.

        If no file exists, checks for legacy materials.json and migrates.
        If neither exists, creates empty defaults.
        If file is corrupted (invalid JSON), creates fresh defaults.
        Invalid individual entries are skipped with a warning.

        Raises:
            TubeLoadError: If file exists but cannot be read due to I/O errors
        """
        self._tubes = []
        self._compensation_data = []

        # Migration: if tubes.json doesn't exist but materials.json does, read from legacy
        load_path = self._file_path
        if not self._file_path.exists():
            if self._legacy_path.exists():
                load_path = self._legacy_path
                futil.log(f"TubeManager: Migrating from {self.LEGACY_FILENAME} to {self.FILENAME}")
            else:
                # No file exists - create empty
                self.save()
                self._loaded = True
                return

        try:
            with open(load_path, encoding='utf-8') as f:
                data = json.load(f)

            # Validate top-level structure
            if not isinstance(data, dict):
                raise TubeLoadError(
                    "Invalid tubes format: expected JSON object at root"
                )

            # Check schema version
            file_version = data.get('version', '1.0')
            if file_version not in self.SUPPORTED_VERSIONS:
                raise TubeLoadError(
                    f"Unsupported tubes schema version: {file_version}. "
                    f"Supported versions: {', '.join(sorted(self.SUPPORTED_VERSIONS))}"
                )

            # Parse tubes (supports both 'tubes' and legacy 'materials' keys)
            tubes_list = data.get('tubes', data.get('materials', []))
            if isinstance(tubes_list, list):
                for i, tube_data in enumerate(tubes_list):
                    try:
                        self._tubes.append(Tube.from_dict(tube_data))
                    except (KeyError, TypeError, ValueError) as e:
                        futil.log(f"Warning: Skipping invalid tube at index {i}: {e}")
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

            # If we loaded from legacy file, save to new file
            if load_path == self._legacy_path:
                self.save()
                futil.log(f"TubeManager: Migration complete - saved to {self.FILENAME}")

        except json.JSONDecodeError as e:
            # If file is corrupted JSON, start fresh
            futil.log(f"Error loading tubes (invalid JSON): {e}")
            self.save()

        except OSError as e:
            # I/O errors are not recoverable - raise to caller
            raise TubeLoadError(f"Failed to load tubes: {e}") from e

        self._loaded = True

    def save(self) -> None:
        """
        Save tubes and compensation data to disk using atomic write pattern.

        Raises:
            TubeSaveError: If file cannot be written
        """
        try:
            super().save()
        except OSError as e:
            raise TubeSaveError(f"Failed to save tubes: {e}") from e

    def _get_save_data(self) -> dict[str, Any]:
        """Return the JSON-serializable dict for tubes and compensation."""
        return {
            'version': self.CURRENT_VERSION,
            'tubes': [t.to_dict() for t in self._tubes],
            'compensation_data': [c.to_dict() for c in self._compensation_data],
        }

    # -------------------------------------------------------------------------
    # Tube CRUD Operations
    # -------------------------------------------------------------------------

    def get_tube_by_id(self, tube_id: str) -> Tube | None:
        """Find a tube by ID."""
        for tube in self.tubes:
            if tube.id == tube_id:
                return tube
        return None

    def get_tube_by_name(self, name: str) -> Tube | None:
        """Find a tube by name."""
        for tube in self.tubes:
            if tube.name == name:
                return tube
        return None

    def get_tubes_by_tube_od(
        self, tube_od: float, tolerance: float = 0.01
    ) -> list[Tube]:
        """
        Get all tubes that match a given tube OD.

        Args:
            tube_od: Tube outer diameter to match (in cm)
            tolerance: Matching tolerance (default 0.01 cm)

        Returns:
            List of matching tubes
        """
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
        """
        Add a new tube.

        Args:
            name: Display name for the tube
            tube_od: Tube outer diameter (must be positive)
            wall_thickness: Wall thickness (must be non-negative)
            material_type: Material type (from MATERIAL_TYPES)
            batch: Optional batch/lot number
            notes: Optional notes

        Returns:
            The created Tube

        Raises:
            ValueError: If tube_od is not positive or wall_thickness is negative
        """
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
        """
        Update an existing tube.

        Args:
            tube_id: ID of tube to update
            name: New name (optional)
            tube_od: New tube OD - must be positive (optional)
            wall_thickness: New wall thickness - must be non-negative (optional)
            material_type: New material type (optional)
            batch: New batch number (optional)
            notes: New notes (optional)

        Returns:
            True if tube was found and updated

        Raises:
            ValueError: If tube_od is not positive or wall_thickness is negative
        """
        tube = self.get_tube_by_id(tube_id)
        if tube is None:
            return False

        # Validate before updating
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
        """
        Delete a tube and its associated compensation data.

        Returns:
            True if tube was found and deleted
        """
        for i, tube in enumerate(self._tubes):
            if tube.id == tube_id:
                self._tubes.pop(i)
                # Also remove any compensation data for this tube
                self._compensation_data = [
                    c for c in self._compensation_data if c.material_id != tube_id
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
        Get compensation data for a specific die-tube pair.

        Args:
            die_id: ID of the die
            material_id: ID of the tube

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
            material_id: ID of the tube

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
        Add a compensation data point for a die-tube pair.

        Args:
            die_id: ID of the die
            material_id: ID of the tube
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
            material_id: ID of the tube
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
        Clear all compensation data points for a die-tube pair.

        Use this when the bender is recalibrated and all previous
        data becomes invalid.

        Args:
            die_id: ID of the die
            material_id: ID of the tube

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
