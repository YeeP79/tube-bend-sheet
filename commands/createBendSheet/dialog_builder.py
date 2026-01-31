"""Dialog builder for Create Bend Sheet command.

This module handles the creation and population of UI components,
following SRP by separating UI building from business logic.
"""

from __future__ import annotations

import adsk.core

from ...models import UnitConfig
from ...storage import ProfileManager
from ...storage.attributes import TubeSettings
from ...core import format_length
from .dialog_state import DialogState
from .die_filter import DieFilter


class BendSheetDialogBuilder:
    """Build and populate the Create Bend Sheet command dialog.

    Responsible for:
    - Creating dropdown inputs
    - Populating dropdowns with bender/die options
    - Setting up value inputs with defaults
    - Configuring dialog appearance

    Delegates to:
    - DialogState: Value and enabled state management
    - DieFilter: Die filtering and CLR matching
    """

    def __init__(
        self,
        inputs: adsk.core.CommandInputs,
        profile_manager: ProfileManager | None,
        units: UnitConfig,
    ) -> None:
        """Initialize the dialog builder.

        Args:
            inputs: Command inputs container
            profile_manager: Profile manager for bender/die data
            units: Unit configuration for the design
        """
        self._inputs = inputs
        self._profile_manager = profile_manager
        self._units = units
        self._state = DialogState(inputs)
        self._die_filter = DieFilter(profile_manager)

    def build_bender_dropdown(
        self,
        saved_settings: TubeSettings | None,
    ) -> tuple[adsk.core.DropDownCommandInput, int]:
        """Create and populate the bender selection dropdown.

        Args:
            saved_settings: Previously saved settings to restore selection

        Returns:
            Tuple of (dropdown input, selected bender index)
        """
        dropdown = self._inputs.addDropDownCommandInput(
            'bender',
            'Bender',
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        items.add(DieFilter.MANUAL_ENTRY_BENDER, True)

        selected_idx: int = 0

        if self._profile_manager:
            for i, bender in enumerate(self._profile_manager.benders):
                is_selected = bool(
                    saved_settings and saved_settings.bender_id == bender.id
                )
                items.add(bender.name, is_selected)
                if is_selected:
                    selected_idx = i + 1

        # Ensure correct selection state
        if selected_idx > 0:
            items.item(0).isSelected = False
            items.item(selected_idx).isSelected = True

        return dropdown, selected_idx

    def build_die_dropdown(
        self,
        selected_bender_idx: int,
        detected_clr: float,
        saved_settings: TubeSettings | None,
    ) -> adsk.core.DropDownCommandInput:
        """Create and populate the die selection dropdown.

        Args:
            selected_bender_idx: Index of selected bender (0 = none)
            detected_clr: CLR detected from geometry for matching
            saved_settings: Previously saved settings to restore selection

        Returns:
            The created dropdown input
        """
        dropdown = self._inputs.addDropDownCommandInput(
            'die',
            'Die',
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        items.add(DieFilter.MANUAL_ENTRY_DIE, True)

        if selected_bender_idx > 0 and self._profile_manager:
            bender = self._profile_manager.benders[selected_bender_idx - 1]
            selected_die_idx: int = 0

            for i, die in enumerate(bender.dies):
                is_selected = bool(
                    saved_settings and saved_settings.die_id == die.id
                )
                # Add CLR match indicator using DieFilter
                display_name = self._die_filter.format_die_name_with_clr_match(
                    die, detected_clr
                )
                items.add(display_name, is_selected)
                if is_selected:
                    selected_die_idx = i + 1

            if selected_die_idx > 0:
                items.item(0).isSelected = False
                items.item(selected_die_idx).isSelected = True

        return dropdown

    def build_precision_dropdown(
        self,
        saved_settings: TubeSettings | None,
    ) -> adsk.core.DropDownCommandInput:
        """Create and populate the precision dropdown.

        Args:
            saved_settings: Previously saved settings to restore selection

        Returns:
            The created dropdown input
        """
        dropdown = self._inputs.addDropDownCommandInput(
            'precision',
            'Precision',
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems

        saved_precision = (
            saved_settings.precision if saved_settings else self._units.default_precision
        )

        if self._units.is_metric:
            items.add('Auto', saved_precision == 0)
            items.add('0.1mm', saved_precision == 1)
            items.add('0.01mm', saved_precision == 2)
        else:
            items.add('1/4"', saved_precision == 4)
            items.add('1/8"', saved_precision == 8)
            items.add('1/16"', saved_precision == 16)
            items.add('1/32"', saved_precision == 32)
            items.add('Exact', saved_precision == 0)

        return dropdown

    def build_value_inputs(
        self,
        detected_clr: float,
        saved_settings: TubeSettings | None,
    ) -> None:
        """Create the value input fields (tube OD, die offset, min grip).

        Args:
            detected_clr: CLR detected from geometry
            saved_settings: Previously saved settings to restore values
        """
        # Separator
        self._inputs.addTextBoxCommandInput('sep1', '', '<hr>', 1, True)

        # Detected CLR (read-only info)
        clr_text = (
            f"Detected CLR from model: "
            f"{format_length(detected_clr, self._units.default_precision, self._units)}"
        )
        self._inputs.addTextBoxCommandInput('detected_clr', '', clr_text, 1, True)

        # Tube OD
        default_od = (
            saved_settings.tube_od
            if saved_settings and saved_settings.tube_od > 0
            else float(self._units.default_tube_od)
        )
        self._inputs.addValueInput(
            'tube_od',
            f'Tube OD ({self._units.unit_symbol})',
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(default_od / self._units.cm_to_unit),
        )

        # Die offset
        self._inputs.addValueInput(
            'die_offset',
            f'Die Offset ({self._units.unit_symbol})',
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )

        # Min grip
        self._inputs.addValueInput(
            'min_grip',
            f'Min Grip ({self._units.unit_symbol})',
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )

        # Min tail
        self._inputs.addValueInput(
            'min_tail',
            f'Min Tail ({self._units.unit_symbol})',
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )

        # Start Allowance - extra material at grip end
        start_allowance_input = self._inputs.addValueInput(
            'start_allowance',
            f'Start Allowance ({self._units.unit_symbol})',
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )
        start_allowance_input.tooltip = (
            "Additional material at the START of the tube (grip end). "
            "This is extra material beyond what's needed for grip extension."
        )

        # End Allowance - extra material at tail end
        end_allowance_input = self._inputs.addValueInput(
            'end_allowance',
            f'End Allowance ({self._units.unit_symbol})',
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )
        end_allowance_input.tooltip = (
            "Additional material at the END of the tube (tail end). "
            "Recommended when tail extension is added to account for spring back."
        )

        # Checkbox: Add allowance even when grip is extended
        grip_allowance_checkbox = self._inputs.addBoolValueInput(
            'add_allowance_with_grip',
            'Add allowance with grip extension',
            True,  # checkbox style
            '',  # no resource folder
            False,  # default unchecked
        )
        # Fusion API stubs don't expose the 'tooltip' attribute for BoolValueCommandInput,
        # but it exists at runtime. Suppress pyright error for this known limitation.
        grip_allowance_checkbox.tooltip = (  # type: ignore[attr-defined]
            "When grip extension is added (first straight shorter than min grip), "
            "the START allowance is normally skipped (since there's already extra "
            "material to cut off). Check this to add the Start Allowance anyway."
        )

        # Checkbox: Add allowance even when tail is extended
        tail_allowance_checkbox = self._inputs.addBoolValueInput(
            'add_allowance_with_tail',
            'Add allowance with tail extension',
            True,  # checkbox style
            '',  # no resource folder
            False,  # default unchecked
        )
        # Fusion API stubs don't expose the 'tooltip' attribute for BoolValueCommandInput,
        # but it exists at runtime. Suppress pyright error for this known limitation.
        tail_allowance_checkbox.tooltip = (  # type: ignore[attr-defined]
            "When tail extension is added (last straight shorter than min tail), "
            "the END allowance is normally skipped (since there's already extra "
            "material to cut off). Check this to add the End Allowance anyway."
        )

    def build_direction_selector(
        self,
        primary_axis: str,
        current_direction: str,
        opposite_direction: str,
        saved_reversed: bool = False,
    ) -> None:
        """Create direction info text and radio button selector.

        Args:
            primary_axis: The detected primary axis (X, Y, or Z)
            current_direction: The natural travel direction (e.g., "+Z")
            opposite_direction: The reversed travel direction (e.g., "-Z")
            saved_reversed: Whether the saved settings had direction reversed
        """
        # Add text showing detected axis (read-only)
        axis_text = f"Path detected along {primary_axis} axis"
        self._inputs.addTextBoxCommandInput('axis_info', '', axis_text, 1, True)

        # Add radio button group for direction selection
        radio_group = self._inputs.addRadioButtonGroupCommandInput(
            'travel_direction',
            'Travel Direction'
        )
        items = radio_group.listItems

        # Build labels in "-Z to +Z" format
        # Label shows "from → to" format based on travel direction
        natural_label = f"{opposite_direction} to {current_direction}"
        reversed_label = f"{current_direction} to {opposite_direction}"

        # Select based on saved settings
        items.add(natural_label, not saved_reversed)
        items.add(reversed_label, saved_reversed)

    def build_all(
        self,
        detected_clr: float,
        saved_settings: TubeSettings | None,
        primary_axis: str,
        current_direction: str,
        opposite_direction: str,
    ) -> None:
        """Build all dialog components.

        Args:
            detected_clr: CLR detected from geometry
            saved_settings: Previously saved settings to restore state
            primary_axis: The detected primary axis (X, Y, or Z)
            current_direction: The natural travel direction (e.g., "+Z")
            opposite_direction: The reversed travel direction (e.g., "-Z")
        """
        # Bender dropdown
        _, selected_bender_idx = self.build_bender_dropdown(saved_settings)

        # Die dropdown (populated based on bender selection)
        self.build_die_dropdown(selected_bender_idx, detected_clr, saved_settings)

        # Value inputs
        self.build_value_inputs(detected_clr, saved_settings)

        # Precision dropdown
        self.build_precision_dropdown(saved_settings)

        # Direction selector (axis info + radio buttons)
        saved_reversed = saved_settings.travel_reversed if saved_settings else False
        self.build_direction_selector(
            primary_axis,
            current_direction,
            opposite_direction,
            saved_reversed,
        )

        # Populate values from pre-selected bender/die (when restoring saved settings)
        if selected_bender_idx > 0 and self._profile_manager:
            bender = self._profile_manager.benders[selected_bender_idx - 1]
            self._state.apply_bender_values(bender)

            # Set die values if a die is pre-selected
            if saved_settings and saved_settings.die_id:
                die = bender.get_die_by_id(saved_settings.die_id)
                if die:
                    self._state.apply_die_values(die)

    def update_die_dropdown_for_bender(
        self,
        bender_name: str,
    ) -> None:
        """Update die dropdown when bender selection changes.

        Clears existing dies and populates with dies from selected bender.

        Args:
            bender_name: Name of selected bender
        """
        die_dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById("die")
        )

        if not die_dropdown:
            return

        # Clear existing items (from end to avoid index issues)
        items = die_dropdown.listItems
        for i in range(items.count - 1, -1, -1):
            items.item(i).deleteMe()

        # Add default option
        items.add(DieFilter.MANUAL_ENTRY_DIE, True)

        # If manual entry bender, enable all inputs for manual entry
        if DieFilter.is_manual_entry_bender(bender_name) or not self._profile_manager:
            self._state.enable_manual_entry()
            return

        # Load fresh data and find bender
        bender = self._die_filter.get_bender_by_name(bender_name)
        if not bender:
            return

        # Apply bender values (min_grip disabled, die fields enabled)
        self._state.apply_bender_values(bender)

        # Add dies
        for die in bender.dies:
            items.add(die.name, False)

    def update_values_for_die(
        self,
        bender_name: str,
        die_name: str,
    ) -> None:
        """Update value inputs when die selection changes.

        Args:
            bender_name: Name of selected bender
            die_name: Name of selected die (may include match indicator)
        """
        # If manual entry die, enable die-related inputs for user editing
        if DieFilter.is_manual_entry_die(die_name) or not self._profile_manager:
            self._state.enable_die_inputs()
            return

        if DieFilter.is_manual_entry_bender(bender_name):
            return

        die = self._die_filter.get_die_by_name(bender_name, die_name)
        if die:
            self._state.apply_die_values(die)
