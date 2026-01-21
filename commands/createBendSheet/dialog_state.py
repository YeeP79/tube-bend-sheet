"""Dialog state management for Create Bend Sheet command.

This module handles setting values and enabled/disabled states
for dialog inputs. Follows SRP by separating state management from UI building.
"""

from __future__ import annotations

import adsk.core

from ...models.bender import Bender, Die


class DialogState:
    """Manage dialog input values and enabled states.

    Provides methods to:
    - Set individual input values and enabled states
    - Apply bender values (min_grip, disabled)
    - Apply die values (offset, tube_od, min_tail, all disabled)
    - Enable inputs for manual entry mode
    """

    def __init__(self, inputs: adsk.core.CommandInputs) -> None:
        """Initialize the dialog state manager.

        Args:
            inputs: Command inputs container to manage
        """
        self._inputs = inputs

    def _get_value_input(self, input_id: str) -> adsk.core.ValueCommandInput | None:
        """Get a value input by ID, safely cast.

        Args:
            input_id: ID of the input to retrieve

        Returns:
            The ValueCommandInput if found, None otherwise
        """
        return adsk.core.ValueCommandInput.cast(self._inputs.itemById(input_id))

    def set_min_grip(self, value: float, enabled: bool) -> None:
        """Set min grip value and enabled state.

        Args:
            value: Value in internal units (cm)
            enabled: Whether the input should be editable
        """
        input_field = self._get_value_input("min_grip")
        if input_field:
            input_field.value = value
            input_field.isEnabled = enabled

    def set_die_offset(self, value: float, enabled: bool) -> None:
        """Set die offset value and enabled state.

        Args:
            value: Value in internal units (cm)
            enabled: Whether the input should be editable
        """
        input_field = self._get_value_input("die_offset")
        if input_field:
            input_field.value = value
            input_field.isEnabled = enabled

    def set_tube_od(self, value: float, enabled: bool) -> None:
        """Set tube OD value and enabled state.

        Args:
            value: Value in internal units (cm)
            enabled: Whether the input should be editable
        """
        input_field = self._get_value_input("tube_od")
        if input_field:
            input_field.value = value
            input_field.isEnabled = enabled

    def set_min_tail(self, value: float, enabled: bool) -> None:
        """Set min tail value and enabled state.

        Args:
            value: Value in internal units (cm)
            enabled: Whether the input should be editable
        """
        input_field = self._get_value_input("min_tail")
        if input_field:
            input_field.value = value
            input_field.isEnabled = enabled

    def apply_bender_values(self, bender: Bender) -> None:
        """Apply values from a bender profile.

        Sets min_grip from bender (disabled) and enables die-related fields
        since no die is selected yet.

        Args:
            bender: Bender to apply values from
        """
        self.set_min_grip(bender.min_grip, enabled=False)
        # Die-related fields enabled (no die selected yet)
        self._set_die_fields_enabled(True)

    def apply_die_values(self, die: Die) -> None:
        """Apply values from a die profile.

        Sets die_offset, tube_od, and min_tail from die (all disabled).

        Args:
            die: Die to apply values from
        """
        self.set_die_offset(die.offset, enabled=False)
        self.set_tube_od(die.tube_od, enabled=False)
        self.set_min_tail(die.min_tail, enabled=False)

    def enable_manual_entry(self) -> None:
        """Enable all inputs for manual entry mode.

        Called when user selects "(None - Manual Entry)" for bender.
        """
        self._set_min_grip_enabled(True)
        self._set_die_fields_enabled(True)

    def enable_die_inputs(self) -> None:
        """Enable only die-related inputs for manual entry.

        Called when die is "(Manual Entry)" but a bender is selected.
        Min grip stays disabled (from bender), but die fields are editable.
        """
        self._set_die_fields_enabled(True)

    def _set_min_grip_enabled(self, enabled: bool) -> None:
        """Set min grip enabled state without changing value.

        Args:
            enabled: Whether the input should be editable
        """
        input_field = self._get_value_input("min_grip")
        if input_field:
            input_field.isEnabled = enabled

    def _set_die_fields_enabled(self, enabled: bool) -> None:
        """Set all die-related fields enabled state without changing values.

        Args:
            enabled: Whether the inputs should be editable
        """
        for input_id in ("die_offset", "tube_od", "min_tail"):
            input_field = self._get_value_input(input_id)
            if input_field:
                input_field.isEnabled = enabled
