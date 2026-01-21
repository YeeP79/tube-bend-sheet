"""Safe input parsing for Create Bend Sheet command.

This module provides type-safe extraction of command inputs with null checks,
following CLAUDE.md guidelines for defensive programming.
"""

from __future__ import annotations

from dataclasses import dataclass

import adsk.core

from ...models import UnitConfig
from ...storage import ProfileManager
from .die_filter import DieFilter


@dataclass(slots=True)
class BendSheetParams:
    """Parsed parameters for bend sheet generation."""

    bender_name: str
    die_name: str
    bender_id: str
    die_id: str
    tube_od: float  # In display units
    die_offset: float  # In display units
    min_grip: float  # In display units
    min_tail: float  # In display units
    extra_allowance: float  # In display units - extra material at each end
    precision: int
    travel_reversed: bool


class InputParser:
    """Safely parse command inputs with null checks.

    Provides defensive access to dropdown and value inputs, returning
    None or default values when inputs are unavailable.
    """

    # Precision label to value mapping
    PRECISION_MAP: dict[str, int] = {
        '1/4"': 4,
        '1/8"': 8,
        '1/16"': 16,
        '1/32"': 32,
        'Exact': 0,
        'Auto': 0,
        '0.1mm': 1,
        '0.01mm': 2,
    }

    def __init__(self, inputs: adsk.core.CommandInputs, units: UnitConfig) -> None:
        """
        Initialize the parser.

        Args:
            inputs: Command inputs from the dialog
            units: Unit configuration for value conversion
        """
        self._inputs = inputs
        self._units = units

    def get_dropdown_value(self, input_id: str) -> str | None:
        """
        Safely get selected item name from a dropdown.

        Args:
            input_id: The input ID to look up

        Returns:
            Selected item name, or None if not available
        """
        dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById(input_id)
        )
        if not dropdown or not dropdown.selectedItem:
            return None
        return dropdown.selectedItem.name

    def get_value_input(self, input_id: str) -> float:
        """
        Get value from a ValueCommandInput in display units.

        Args:
            input_id: The input ID to look up

        Returns:
            Value converted to display units, or 0.0 if not available
        """
        value_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById(input_id)
        )
        if not value_input:
            return 0.0
        # Convert from internal (cm) to display units
        return value_input.value * self._units.cm_to_unit

    def get_bool_value(self, input_id: str) -> bool:
        """
        Get value from a BoolValueCommandInput.

        Args:
            input_id: The input ID to look up

        Returns:
            Boolean value, or False if not available
        """
        bool_input = adsk.core.BoolValueCommandInput.cast(
            self._inputs.itemById(input_id)
        )
        if not bool_input:
            return False
        return bool_input.value

    def get_radio_button_index(self, input_id: str) -> int:
        """
        Get the selected index from a radio button group.

        Args:
            input_id: The input ID to look up

        Returns:
            Selected item index (0-based), or 0 if not available
        """
        radio_group = adsk.core.RadioButtonGroupCommandInput.cast(
            self._inputs.itemById(input_id)
        )
        if not radio_group:
            return 0
        # Find index of selected item
        for i in range(radio_group.listItems.count):
            if radio_group.listItems.item(i).isSelected:
                return i
        return 0

    def parse_precision(self) -> int:
        """
        Parse precision from the precision dropdown.

        Returns:
            Precision value (fraction denominator or decimal places)
        """
        prec_text = self.get_dropdown_value('precision')
        if prec_text is None:
            return self._units.default_precision
        return self.PRECISION_MAP.get(prec_text, self._units.default_precision)

    def parse(self, profile_manager: ProfileManager | None) -> BendSheetParams:
        """
        Parse all inputs into a typed BendSheetParams object.

        Args:
            profile_manager: Optional profile manager for bender/die lookup

        Returns:
            BendSheetParams with all values extracted
        """
        # Get dropdown selections
        bender_selection = self.get_dropdown_value('bender')
        die_selection = self.get_dropdown_value('die')

        # Look up bender/die details
        bender_name = ""
        die_name = ""
        bender_id = ""
        die_id = ""

        if (
            bender_selection
            and bender_selection != DieFilter.MANUAL_ENTRY_BENDER
            and profile_manager
        ):
            bender = profile_manager.get_bender_by_name(bender_selection)
            if bender:
                bender_name = bender.name
                bender_id = bender.id

                if die_selection and die_selection != DieFilter.MANUAL_ENTRY_DIE:
                    # Remove CLR match indicator if present
                    clean_die_name = DieFilter.clean_die_name(die_selection)
                    for die in bender.dies:
                        if die.name == clean_die_name:
                            die_name = die.name
                            die_id = die.id
                            break

        # Index 0 = natural direction, Index 1 = reversed
        travel_reversed = self.get_radio_button_index('travel_direction') == 1

        return BendSheetParams(
            bender_name=bender_name,
            die_name=die_name,
            bender_id=bender_id,
            die_id=die_id,
            tube_od=self.get_value_input('tube_od'),
            die_offset=self.get_value_input('die_offset'),
            min_grip=self.get_value_input('min_grip'),
            min_tail=self.get_value_input('min_tail'),
            extra_allowance=self.get_value_input('extra_allowance'),
            precision=self.parse_precision(),
            travel_reversed=travel_reversed,
        )
