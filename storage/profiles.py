"""Bender profile storage and management."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from ..models.bender import (
    Bender,
    Die,
    validate_bender_values,
    validate_die_values,
)


class ProfileSaveError(IOError):
    """Raised when saving bender profiles fails."""

    pass


class ProfileLoadError(IOError):
    """Raised when loading bender profiles fails due to I/O errors."""

    pass


class ProfileManager:
    """
    Manages bender profiles stored in JSON.

    Profiles are stored in a benders.json file in the add-in's resources folder.

    Schema Version History:
        1.0 - Initial schema with benders and dies
    """

    FILENAME = 'benders.json'
    CURRENT_VERSION = '1.0'
    SUPPORTED_VERSIONS = {'1.0'}
    
    def __init__(self, addin_path: str) -> None:
        """
        Initialize the profile manager.

        Args:
            addin_path: Path to the add-in root directory
        """
        self._addin_path = Path(addin_path)
        self._resources_path = self._addin_path / 'resources'
        self._profiles_path = self._resources_path / self.FILENAME
        self._benders: list[Bender] = []
        self._loaded = False
        self._load_lock = threading.Lock()
    
    @property
    def benders(self) -> list[Bender]:
        """Get all bender profiles.

        Thread-safe lazy loading using a lock to prevent race conditions
        when multiple threads access benders simultaneously.
        """
        with self._load_lock:
            if not self._loaded:
                self.load()
        return self._benders

    def reload(self) -> None:
        """
        Force reload profiles from disk.

        Use this when the profile file may have been modified externally
        and you need to pick up the latest changes.
        """
        self._loaded = False
        self.load()

    def load(self) -> None:
        """
        Load profiles from disk.

        If no profile file exists, creates default profiles.
        If file is corrupted (invalid JSON), creates fresh defaults.
        Invalid individual benders are skipped with a warning.

        Raises:
            ProfileLoadError: If file exists but cannot be read due to I/O errors
        """
        self._benders = []

        if not self._profiles_path.exists():
            # Create default profile if none exists
            self._create_default_profiles()
            self.save()
        else:
            try:
                with open(self._profiles_path, encoding='utf-8') as f:
                    data = json.load(f)

                # Validate top-level structure
                if not isinstance(data, dict):
                    raise ProfileLoadError(
                        "Invalid profile format: expected JSON object at root"
                    )

                if 'benders' not in data:
                    raise ProfileLoadError(
                        "Invalid profile format: missing 'benders' key"
                    )

                # Check schema version
                file_version = data.get('version', '1.0')  # Default to 1.0 for legacy files
                if file_version not in self.SUPPORTED_VERSIONS:
                    raise ProfileLoadError(
                        f"Unsupported profile schema version: {file_version}. "
                        f"Supported versions: {', '.join(sorted(self.SUPPORTED_VERSIONS))}"
                    )

                benders_list = data['benders']
                if not isinstance(benders_list, list):
                    raise ProfileLoadError(
                        "Invalid profile format: 'benders' must be a list"
                    )

                # Parse each bender, skipping invalid ones
                for i, bender_data in enumerate(benders_list):
                    try:
                        self._benders.append(Bender.from_dict(bender_data))
                    except (KeyError, TypeError, ValueError) as e:
                        # Skip invalid bender but continue loading others
                        print(f"Warning: Skipping invalid bender at index {i}: {e}")
                        continue

            except json.JSONDecodeError as e:
                # If file is corrupted JSON, start fresh with defaults
                print(f"Error loading profiles (invalid JSON): {e}")
                self._create_default_profiles()
                self.save()

            except OSError as e:
                # I/O errors are not recoverable - raise to caller
                raise ProfileLoadError(f"Failed to load bender profiles: {e}") from e

        self._loaded = True
    
    def save(self) -> None:
        """
        Save profiles to disk using atomic write pattern.

        Writes to a temporary file first, then atomically renames to target.
        This prevents data corruption from interrupted writes.

        Raises:
            ProfileSaveError: If file cannot be written
        """
        temp_path = self._profiles_path.with_suffix('.tmp')

        try:
            # Ensure resources directory exists
            self._resources_path.mkdir(parents=True, exist_ok=True)

            data = {
                'version': self.CURRENT_VERSION,
                'benders': [b.to_dict() for b in self._benders]
            }

            # Write to temp file first
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Atomic rename to target (overwrites existing)
            temp_path.replace(self._profiles_path)

        except (OSError, TypeError) as e:
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass  # Best effort cleanup

            raise ProfileSaveError(f"Failed to save bender profiles: {e}") from e
    
    def _create_default_profiles(self) -> None:
        """Create default bender profiles.

        All values are stored in internal units (centimeters) per Fusion convention.
        """
        # Example: JD2 Model 3 with common dies
        # Values converted from inches: 1" = 2.54 cm
        jd2 = Bender(
            id=self._generate_id(),
            name='JD2 Model 3',
            min_grip=15.24,  # 6"
            dies=[
                Die(
                    id=self._generate_id(),
                    name='1.5" x 4.5" CLR',
                    tube_od=3.81,    # 1.5"
                    clr=11.43,       # 4.5"
                    offset=1.5875,   # 0.625"
                    notes='Standard 1.5" die'
                ),
                Die(
                    id=self._generate_id(),
                    name='1.75" x 5.5" CLR',
                    tube_od=4.445,   # 1.75"
                    clr=13.97,       # 5.5"
                    offset=1.74625,  # 0.6875"
                    notes='Standard 1.75" die'
                ),
            ],
            notes='Default bender profile'
        )
        self._benders = [jd2]
    
    def _generate_id(self) -> str:
        """Generate a unique ID."""
        return str(uuid.uuid4())[:8]
    
    def get_bender_by_id(self, bender_id: str) -> Bender | None:
        """Find a bender by ID."""
        for bender in self.benders:
            if bender.id == bender_id:
                return bender
        return None
    
    def get_bender_by_name(self, name: str) -> Bender | None:
        """Find a bender by name."""
        for bender in self.benders:
            if bender.name == name:
                return bender
        return None
    
    def add_bender(self, name: str, min_grip: float, notes: str = "") -> Bender:
        """
        Add a new bender profile.
        
        Args:
            name: Display name for the bender
            min_grip: Minimum grip length
            notes: Optional notes
            
        Returns:
            The created Bender
        """
        bender = Bender(
            id=self._generate_id(),
            name=name,
            min_grip=min_grip,
            notes=notes
        )
        self._benders.append(bender)
        self.save()
        return bender
    
    def update_bender(self, bender_id: str, name: str | None = None,
                      min_grip: float | None = None, notes: str | None = None) -> bool:
        """
        Update an existing bender.

        Args:
            bender_id: ID of bender to update
            name: New name (optional)
            min_grip: New min grip value - must be positive (optional)
            notes: New notes (optional)

        Returns:
            True if bender was found and updated

        Raises:
            ValueError: If min_grip is not positive
        """
        bender = self.get_bender_by_id(bender_id)
        if bender is None:
            return False

        # Validate min_grip before updating
        validate_bender_values(min_grip=min_grip)

        if name is not None:
            bender.name = name
        if min_grip is not None:
            bender.min_grip = min_grip
        if notes is not None:
            bender.notes = notes

        self.save()
        return True
    
    def delete_bender(self, bender_id: str) -> bool:
        """
        Delete a bender profile.
        
        Returns:
            True if bender was found and deleted
        """
        for i, bender in enumerate(self._benders):
            if bender.id == bender_id:
                self._benders.pop(i)
                self.save()
                return True
        return False
    
    def add_die_to_bender(self, bender_id: str, name: str, tube_od: float,
                          clr: float, offset: float, min_tail: float = 0.0,
                          notes: str = "") -> Die | None:
        """
        Add a die to a bender.

        Returns:
            The created Die, or None if bender not found
        """
        bender = self.get_bender_by_id(bender_id)
        if bender is None:
            return None

        die = Die(
            id=self._generate_id(),
            name=name,
            tube_od=tube_od,
            clr=clr,
            offset=offset,
            min_tail=min_tail,
            notes=notes
        )
        bender.add_die(die)
        self.save()
        return die
    
    def update_die(self, bender_id: str, die_id: str, name: str | None = None,
                   tube_od: float | None = None, clr: float | None = None,
                   offset: float | None = None, min_tail: float | None = None,
                   notes: str | None = None) -> bool:
        """
        Update an existing die.

        Args:
            bender_id: ID of bender containing the die
            die_id: ID of die to update
            name: New name (optional)
            tube_od: New tube OD - must be positive (optional)
            clr: New CLR - must be positive (optional)
            offset: New offset - must be non-negative (optional)
            min_tail: New min tail - must be non-negative (optional)
            notes: New notes (optional)

        Returns:
            True if die was found and updated

        Raises:
            ValueError: If numeric values are invalid
        """
        bender = self.get_bender_by_id(bender_id)
        if bender is None:
            return False

        die = bender.get_die_by_id(die_id)
        if die is None:
            return False

        # Validate numeric values before updating
        validate_die_values(
            tube_od=tube_od,
            clr=clr,
            offset=offset,
            min_tail=min_tail,
        )

        if name is not None:
            die.name = name
        if tube_od is not None:
            die.tube_od = tube_od
        if clr is not None:
            die.clr = clr
        if offset is not None:
            die.offset = offset
        if min_tail is not None:
            die.min_tail = min_tail
        if notes is not None:
            die.notes = notes

        self.save()
        return True
    
    def delete_die(self, bender_id: str, die_id: str) -> bool:
        """
        Delete a die from a bender.
        
        Returns:
            True if die was found and deleted
        """
        bender = self.get_bender_by_id(bender_id)
        if bender is None:
            return False
        
        if bender.remove_die(die_id):
            self.save()
            return True
        return False
    
    def find_die_for_clr(self, clr: float, bender_id: str | None = None,
                         tolerance: float = 0.01) -> tuple[Bender, Die] | None:
        """
        Find a die that matches the given CLR.
        
        Args:
            clr: Center line radius to match
            bender_id: Optional bender to search in (searches all if None)
            tolerance: CLR matching tolerance
            
        Returns:
            Tuple of (Bender, Die) if found, None otherwise
        """
        benders_to_search = (
            [self.get_bender_by_id(bender_id)] if bender_id 
            else self.benders
        )
        
        for bender in benders_to_search:
            if bender is None:
                continue
            die = bender.find_die_for_clr(clr, tolerance)
            if die:
                return (bender, die)
        
        return None
