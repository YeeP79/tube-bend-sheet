"""Die filtering and CLR matching logic.

This module handles die filtering, bender/die lookup, and name cleaning.
Follows SRP by separating filtering logic from UI concerns.
"""

from __future__ import annotations

from ...core.tolerances import CLR_MATCH_DISPLAY
from ...models.bender import Bender, Die
from ...storage import ProfileManager


class DieFilter:
    """Filter and format dies for dropdown display.

    Provides methods for:
    - Looking up benders and dies by name
    - Cleaning die names (removing CLR match indicators)
    - Detecting manual entry selections
    """

    CLR_MATCH_TOLERANCE: float = CLR_MATCH_DISPLAY
    CLR_MATCH_INDICATOR: str = " \u2713"  # Checkmark

    MANUAL_ENTRY_BENDER: str = "(None - Manual Entry)"
    MANUAL_ENTRY_DIE: str = "(Manual Entry)"

    def __init__(self, profile_manager: ProfileManager | None) -> None:
        """Initialize the die filter.

        Args:
            profile_manager: Profile manager for bender/die data, or None
        """
        self._profile_manager = profile_manager

    def get_bender_by_name(self, name: str) -> Bender | None:
        """Get bender by name, refreshing from disk first.

        Args:
            name: Name of the bender to find

        Returns:
            The Bender if found, None otherwise
        """
        if not self._profile_manager:
            return None

        self._profile_manager.load()
        return self._profile_manager.get_bender_by_name(name)

    def get_die_by_name(self, bender_name: str, die_name: str) -> Die | None:
        """Get die by name from a specific bender.

        Handles CLR match indicator in die name by cleaning it first.

        Args:
            bender_name: Name of the bender containing the die
            die_name: Name of the die (may include CLR match indicator)

        Returns:
            The Die if found, None otherwise
        """
        if not self._profile_manager:
            return None

        bender = self._profile_manager.get_bender_by_name(bender_name)
        if not bender:
            return None

        clean_name = self.clean_die_name(die_name)
        for die in bender.dies:
            if die.name == clean_name:
                return die

        return None

    @staticmethod
    def clean_die_name(die_name: str) -> str:
        """Remove CLR match indicator from die name.

        Args:
            die_name: Die name potentially containing the indicator

        Returns:
            Clean die name without the indicator
        """
        return die_name.replace(DieFilter.CLR_MATCH_INDICATOR, "")

    @staticmethod
    def is_manual_entry_bender(bender_name: str) -> bool:
        """Check if bender name indicates manual entry mode.

        Args:
            bender_name: Name to check

        Returns:
            True if this is the manual entry option
        """
        return bender_name == DieFilter.MANUAL_ENTRY_BENDER

    @staticmethod
    def is_manual_entry_die(die_name: str) -> bool:
        """Check if die name indicates manual entry mode.

        Args:
            die_name: Name to check (CLR indicator is cleaned first)

        Returns:
            True if this is the manual entry option
        """
        clean_name = DieFilter.clean_die_name(die_name)
        return clean_name == DieFilter.MANUAL_ENTRY_DIE

    def format_die_name_with_clr_match(
        self, die: Die, detected_clr: float
    ) -> str:
        """Format die name with CLR match indicator if applicable.

        Args:
            die: Die to format name for
            detected_clr: CLR detected from geometry for matching

        Returns:
            Die name with checkmark if CLR matches, plain name otherwise
        """
        if die.matches_clr(detected_clr, self.CLR_MATCH_TOLERANCE):
            return f"{die.name}{self.CLR_MATCH_INDICATOR}"
        return die.name
