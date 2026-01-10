"""Input handling for Manage Benders command.

This module provides safe access to command inputs with null checks,
and manages visibility state based on selected action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import adsk.core

from ...models import UnitConfig
from ...storage import ProfileManager


class BenderAction(Enum):
    """Available actions in the Manage Benders dialog."""

    ADD_BENDER = "Add Bender"
    EDIT_BENDER = "Edit Bender"
    DELETE_BENDER = "Delete Bender"
    ADD_DIE = "Add Die to Bender"
    EDIT_DIE = "Edit Die"
    DELETE_DIE = "Delete Die"


@dataclass(slots=True)
class VisibilityState:
    """Visibility configuration for dialog elements."""

    show_bender_select: bool
    show_die_select: bool
    show_bender_fields: bool
    show_die_fields: bool

    @classmethod
    def for_action(cls, action: BenderAction) -> VisibilityState:
        """
        Create visibility state for a given action.

        Args:
            action: The selected action

        Returns:
            VisibilityState configured for the action
        """
        return cls(
            show_bender_select=action
            in [
                BenderAction.EDIT_BENDER,
                BenderAction.DELETE_BENDER,
                BenderAction.ADD_DIE,
                BenderAction.EDIT_DIE,
                BenderAction.DELETE_DIE,
            ],
            show_die_select=action
            in [
                BenderAction.EDIT_DIE,
                BenderAction.DELETE_DIE,
            ],
            show_bender_fields=action
            in [
                BenderAction.ADD_BENDER,
                BenderAction.EDIT_BENDER,
            ],
            show_die_fields=action
            in [
                BenderAction.ADD_DIE,
                BenderAction.EDIT_DIE,
            ],
        )


@dataclass(slots=True)
class BenderFormData:
    """Data from the bender form fields."""

    name: str
    min_grip: float  # In display units
    notes: str


@dataclass(slots=True)
class DieFormData:
    """Data from the die form fields."""

    name: str
    tube_od: float  # In display units
    clr: float  # In display units
    offset: float  # In display units
    min_tail: float  # In display units
    notes: str


class InputHandler:
    """Safe input handling for Manage Benders dialog.

    Provides:
    - Null-safe dropdown access
    - Visibility state management
    - Form data extraction with unit conversion
    """

    def __init__(self, inputs: adsk.core.CommandInputs, units: UnitConfig) -> None:
        """
        Initialize the input handler.

        Args:
            inputs: Command inputs from the dialog
            units: Unit configuration for value conversion
        """
        self._inputs = inputs
        self._units = units

    def get_selected_action(self) -> BenderAction | None:
        """
        Get the currently selected action.

        Returns:
            BenderAction enum value, or None if not available
        """
        dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById("action")
        )
        if not dropdown or not dropdown.selectedItem:
            return None

        name = dropdown.selectedItem.name
        try:
            return BenderAction(name)
        except ValueError:
            return None

    def get_selected_bender_name(self) -> str | None:
        """
        Get the selected bender name from dropdown.

        Returns:
            Bender name, or None if not available
        """
        dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById("bender")
        )
        if not dropdown or dropdown.listItems.count == 0 or not dropdown.selectedItem:
            return None
        return dropdown.selectedItem.name

    def get_selected_die_name(self) -> str | None:
        """
        Get the selected die name from dropdown.

        Returns:
            Die name, or None if not available
        """
        dropdown = adsk.core.DropDownCommandInput.cast(self._inputs.itemById("die"))
        if not dropdown or dropdown.listItems.count == 0 or not dropdown.selectedItem:
            return None
        return dropdown.selectedItem.name

    def apply_visibility(self, state: VisibilityState) -> None:
        """
        Apply visibility state to dialog elements.

        Args:
            state: Visibility configuration to apply
        """
        bender_dropdown = self._inputs.itemById("bender")
        die_dropdown = self._inputs.itemById("die")
        bender_group = self._inputs.itemById("bender_group")
        die_group = self._inputs.itemById("die_group")

        if bender_dropdown:
            bender_dropdown.isVisible = state.show_bender_select
        if die_dropdown:
            die_dropdown.isVisible = state.show_die_select
        if bender_group:
            bender_group.isVisible = state.show_bender_fields
        if die_group:
            die_group.isVisible = state.show_die_fields

    def populate_die_dropdown(self, profile_manager: ProfileManager) -> None:
        """
        Populate die dropdown based on selected bender.

        Args:
            profile_manager: Profile manager to get dies from
        """
        die_dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById("die")
        )
        if not die_dropdown:
            return

        # Clear existing items
        while die_dropdown.listItems.count > 0:
            die_dropdown.listItems.item(0).deleteMe()

        # Get selected bender
        bender_name = self.get_selected_bender_name()
        if not bender_name:
            return

        bender = profile_manager.get_bender_by_name(bender_name)
        if bender:
            for die in bender.dies:
                die_dropdown.listItems.add(die.name, False)
            if die_dropdown.listItems.count > 0:
                die_dropdown.listItems.item(0).isSelected = True

    def get_bender_form_data(self) -> BenderFormData:
        """
        Extract bender form data.

        Returns:
            BenderFormData with values in display units
        """
        name_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("bender_name")
        )
        min_grip_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("min_grip")
        )
        notes_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("bender_notes")
        )

        return BenderFormData(
            name=name_input.value if name_input else "",
            min_grip=(
                min_grip_input.value * self._units.cm_to_unit if min_grip_input else 0.0
            ),
            notes=notes_input.value if notes_input else "",
        )

    def get_die_form_data(self) -> DieFormData:
        """
        Extract die form data.

        Returns:
            DieFormData with values in display units
        """
        name_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("die_name")
        )
        tube_od_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("tube_od")
        )
        clr_input = adsk.core.ValueCommandInput.cast(self._inputs.itemById("clr"))
        offset_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("die_offset")
        )
        min_tail_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("min_tail")
        )
        notes_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("die_notes")
        )

        return DieFormData(
            name=name_input.value if name_input else "",
            tube_od=(
                tube_od_input.value * self._units.cm_to_unit if tube_od_input else 0.0
            ),
            clr=clr_input.value * self._units.cm_to_unit if clr_input else 0.0,
            offset=offset_input.value * self._units.cm_to_unit if offset_input else 0.0,
            min_tail=min_tail_input.value * self._units.cm_to_unit if min_tail_input else 0.0,
            notes=notes_input.value if notes_input else "",
        )

    def set_bender_form_data(self, name: str, min_grip: float, notes: str) -> None:
        """
        Set bender form fields.

        Args:
            name: Bender name
            min_grip: Min grip in display units
            notes: Notes text
        """
        name_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("bender_name")
        )
        min_grip_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("min_grip")
        )
        notes_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("bender_notes")
        )

        if name_input:
            name_input.value = name
        if min_grip_input:
            min_grip_input.value = min_grip / self._units.cm_to_unit
        if notes_input:
            notes_input.value = notes

    def set_die_form_data(
        self, name: str, tube_od: float, clr: float, offset: float, min_tail: float, notes: str
    ) -> None:
        """
        Set die form fields.

        Args:
            name: Die name
            tube_od: Tube OD in display units
            clr: CLR in display units
            offset: Die offset in display units
            min_tail: Min tail in display units
            notes: Notes text
        """
        name_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("die_name")
        )
        tube_od_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("tube_od")
        )
        clr_input = adsk.core.ValueCommandInput.cast(self._inputs.itemById("clr"))
        offset_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("die_offset")
        )
        min_tail_input = adsk.core.ValueCommandInput.cast(
            self._inputs.itemById("min_tail")
        )
        notes_input = adsk.core.StringValueCommandInput.cast(
            self._inputs.itemById("die_notes")
        )

        if name_input:
            name_input.value = name
        if tube_od_input:
            tube_od_input.value = tube_od / self._units.cm_to_unit
        if clr_input:
            clr_input.value = clr / self._units.cm_to_unit
        if offset_input:
            offset_input.value = offset / self._units.cm_to_unit
        if min_tail_input:
            min_tail_input.value = min_tail / self._units.cm_to_unit
        if notes_input:
            notes_input.value = notes
