"""Dialog builder for the unified Tube Fabrication command.

Auto-populates fields from body analysis. Simpler than the sketch-based
dialog since most geometry data is extracted automatically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import adsk.core

from ...models import UnitConfig
from ...storage import ProfileManager
from ...core import format_length
from ...core.tolerances import TUBE_OD_MATCH_CM
from ..createBendSheet.die_filter import DieFilter

if TYPE_CHECKING:
    from ...storage.tubes import TubeManager
    from .body_analyzer import BodyAnalysisResult


class TubeFabDialogBuilder:
    """Build and populate the Tube Fabrication command dialog.

    Auto-populates read-only fields from body analysis and provides
    bender/die/tube dropdowns with auto-matching.
    """

    def __init__(
        self,
        inputs: adsk.core.CommandInputs,
        profile_manager: ProfileManager | None,
        units: UnitConfig,
        tube_manager: "TubeManager | None" = None,
    ) -> None:
        self._inputs = inputs
        self._profile_manager = profile_manager
        self._units = units
        self._tube_manager = tube_manager
        self._die_filter = DieFilter(profile_manager)
        self._tube_id_map: dict[str, str] = {}

    def build_all(self, analysis: "BodyAnalysisResult") -> None:
        """Build all dialog components from body analysis.

        Args:
            analysis: Complete body analysis result.
        """
        # Read-only info section
        self._build_info_section(analysis)

        # Bender/die dropdowns
        self._build_bender_dropdown(analysis)
        self._build_die_dropdown(analysis)

        # Tube dropdown
        self._build_tube_dropdown()

        # Compensation checkbox
        self._build_compensation_checkbox()

        # Separator
        self._inputs.addTextBoxCommandInput("sep1", "", "<hr>", 1, True)

        # Value inputs
        self._build_value_inputs(analysis)

        # Precision
        self._build_precision_dropdown()

        # Template layout (for cope templates)
        self._build_template_layout_dropdown()

        # Direction selector
        self._build_direction_selector(analysis)

    def _build_info_section(self, analysis: "BodyAnalysisResult") -> None:
        """Add read-only info fields showing detected geometry."""
        info_lines: list[str] = []
        info_lines.append(f"Body: {analysis.body_name}")
        info_lines.append(
            f"OD: {format_length(analysis.od, self._units.default_precision, self._units)}"
        )
        if analysis.wall_thickness is not None:
            info_lines.append(
                f"Wall: {format_length(analysis.wall_thickness, self._units.default_precision, self._units)}"
            )
        if analysis.clr > 0:
            info_lines.append(
                f"CLR: {format_length(analysis.clr, self._units.default_precision, self._units)}"
            )
        info_lines.append(f"Bends: {len(analysis.bends)}")
        info_lines.append(f"Straights: {len(analysis.straights)}")

        if analysis.start_is_coped or analysis.end_is_coped:
            cope_ends: list[str] = []
            if analysis.start_is_coped:
                cope_ends.append("Start")
            if analysis.end_is_coped:
                cope_ends.append("End")
            info_lines.append(f"Coped: {', '.join(cope_ends)}")

        info_html = "<br>".join(info_lines)
        self._inputs.addTextBoxCommandInput(
            "body_info", "", info_html, len(info_lines), True,
        )

    def _build_bender_dropdown(self, analysis: "BodyAnalysisResult") -> None:
        """Create bender dropdown."""
        dropdown = self._inputs.addDropDownCommandInput(
            "bender",
            "Bender",
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        items.add(DieFilter.MANUAL_ENTRY_BENDER, True)

        if self._profile_manager:
            for bender in self._profile_manager.benders:
                items.add(bender.name, False)

    def _build_die_dropdown(self, analysis: "BodyAnalysisResult") -> None:
        """Create die dropdown."""
        dropdown = self._inputs.addDropDownCommandInput(
            "die",
            "Die",
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        items.add(DieFilter.MANUAL_ENTRY_DIE, True)

    def _build_tube_dropdown(self) -> None:
        """Create tube dropdown."""
        dropdown = self._inputs.addDropDownCommandInput(
            "tube",
            "Tube",
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        items.add("(None)", True)
        self._tube_id_map.clear()

    def _build_compensation_checkbox(self) -> None:
        """Create compensation checkbox (disabled until tube selected)."""
        checkbox = self._inputs.addBoolValueInput(
            "apply_compensation",
            "Apply bender compensation",
            True,
            "",
            False,
        )
        checkbox.tooltip = (  # type: ignore[attr-defined]
            "Apply recorded bender compensation data to bend angles."
        )
        checkbox.isEnabled = False  # type: ignore[attr-defined]

    def _build_value_inputs(self, analysis: "BodyAnalysisResult") -> None:
        """Create value inputs, auto-populated from analysis."""
        # Tube OD (pre-filled from detected OD)
        self._inputs.addValueInput(
            "tube_od",
            f"Tube OD ({self._units.unit_symbol})",
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(
                analysis.od / self._units.cm_to_unit
            ),
        )

        # Die offset
        self._inputs.addValueInput(
            "die_offset",
            f"Die Offset ({self._units.unit_symbol})",
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )

        # Min grip
        self._inputs.addValueInput(
            "min_grip",
            f"Min Grip ({self._units.unit_symbol})",
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )

        # Min tail
        self._inputs.addValueInput(
            "min_tail",
            f"Min Tail ({self._units.unit_symbol})",
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )

        # Start Allowance
        start_allowance = self._inputs.addValueInput(
            "start_allowance",
            f"Start Allowance ({self._units.unit_symbol})",
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )
        start_allowance.tooltip = (
            "Additional material at the START of the tube (grip end)."
        )

        # End Allowance
        end_allowance = self._inputs.addValueInput(
            "end_allowance",
            f"End Allowance ({self._units.unit_symbol})",
            self._units.unit_name,
            adsk.core.ValueInput.createByReal(0),
        )
        end_allowance.tooltip = (
            "Additional material at the END of the tube (tail end)."
        )

        # Grip/tail allowance checkboxes
        grip_cb = self._inputs.addBoolValueInput(
            "add_allowance_with_grip",
            "Add allowance with grip extension",
            True, "", False,
        )
        grip_cb.tooltip = (  # type: ignore[attr-defined]
            "Add Start Allowance even when grip is extended."
        )

        tail_cb = self._inputs.addBoolValueInput(
            "add_allowance_with_tail",
            "Add allowance with tail extension",
            True, "", False,
        )
        tail_cb.tooltip = (  # type: ignore[attr-defined]
            "Add End Allowance even when tail is extended."
        )

    def _build_precision_dropdown(self) -> None:
        """Create precision dropdown."""
        dropdown = self._inputs.addDropDownCommandInput(
            "precision",
            "Precision",
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        default = self._units.default_precision

        if self._units.is_metric:
            items.add("Auto", default == 0)
            items.add("0.1mm", default == 1)
            items.add("0.01mm", default == 2)
        else:
            items.add('1/4"', default == 4)
            items.add('1/8"', default == 8)
            items.add('1/16"', default == 16)
            items.add('1/32"', default == 32)
            items.add("Exact", default == 0)

    def _build_template_layout_dropdown(self) -> None:
        """Create template layout dropdown for cope templates."""
        dropdown = self._inputs.addDropDownCommandInput(
            "template_layout",
            "Template Layout",
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        items = dropdown.listItems
        items.add("Flush with tube end", True, "")
        items.add("Setback from cut (reusable)", False, "")

    def _build_direction_selector(self, analysis: "BodyAnalysisResult") -> None:
        """Create direction radio buttons from detected path direction."""
        axis_text = f"Path detected along {analysis.primary_axis} axis"
        self._inputs.addTextBoxCommandInput("axis_info", "", axis_text, 1, True)

        radio_group = self._inputs.addRadioButtonGroupCommandInput(
            "travel_direction",
            "Travel Direction",
        )
        items = radio_group.listItems

        natural_label = f"{analysis.opposite_direction} to {analysis.travel_direction}"
        reversed_label = f"{analysis.travel_direction} to {analysis.opposite_direction}"

        items.add(natural_label, True)
        items.add(reversed_label, False)

    # --- Update methods for input_changed handler ---

    def update_die_dropdown_for_bender(self, bender_name: str) -> None:
        """Update die dropdown when bender changes."""
        die_dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById("die")
        )
        if not die_dropdown:
            return

        items = die_dropdown.listItems
        for i in range(items.count - 1, -1, -1):
            items.item(i).deleteMe()

        items.add(DieFilter.MANUAL_ENTRY_DIE, True)

        if DieFilter.is_manual_entry_bender(bender_name) or not self._profile_manager:
            return

        bender = self._die_filter.get_bender_by_name(bender_name)
        if not bender:
            return

        for die in bender.dies:
            items.add(die.name, False)

    def update_values_for_die(
        self,
        bender_name: str,
        die_name: str,
    ) -> None:
        """Update value inputs when die changes."""
        if DieFilter.is_manual_entry_die(die_name) or not self._profile_manager:
            return

        die = self._die_filter.get_die_by_name(bender_name, die_name)
        if not die:
            return

        # Update tube OD
        od_input = adsk.core.ValueCommandInput.cast(self._inputs.itemById("tube_od"))
        if od_input:
            od_input.value = die.tube_od  # type: ignore[attr-defined]

        # Update die offset
        offset_input = adsk.core.ValueCommandInput.cast(self._inputs.itemById("die_offset"))
        if offset_input:
            offset_input.value = die.offset  # type: ignore[attr-defined]

        # Update tube dropdown for matching OD
        self._update_tube_dropdown_for_od(die.tube_od)

    def _update_tube_dropdown_for_od(self, tube_od_cm: float | None) -> None:
        """Update tube dropdown to show tubes matching given OD."""
        tube_dropdown = adsk.core.DropDownCommandInput.cast(
            self._inputs.itemById("tube")
        )
        comp_checkbox = adsk.core.BoolValueCommandInput.cast(
            self._inputs.itemById("apply_compensation")
        )

        if not tube_dropdown:
            return

        items = tube_dropdown.listItems
        for i in range(items.count - 1, -1, -1):
            items.item(i).deleteMe()
        self._tube_id_map.clear()

        items.add("(None)", True)

        if self._tube_manager and tube_od_cm is not None:
            matching = self._tube_manager.get_tubes_by_tube_od(
                tube_od_cm, tolerance=TUBE_OD_MATCH_CM,
            )
            for tube in matching:
                display_name = tube.name
                if tube.batch:
                    display_name += f" [{tube.batch}]"
                items.add(display_name, False)
                self._tube_id_map[display_name] = tube.id

        if comp_checkbox:
            comp_checkbox.value = False  # type: ignore[attr-defined]
            comp_checkbox.isEnabled = False  # type: ignore[attr-defined]

    def update_bender_values(self, bender_name: str) -> None:
        """Update min_grip from bender profile."""
        if DieFilter.is_manual_entry_bender(bender_name) or not self._profile_manager:
            return

        bender = self._profile_manager.get_bender_by_name(bender_name)
        if not bender:
            return

        grip_input = adsk.core.ValueCommandInput.cast(self._inputs.itemById("min_grip"))
        if grip_input:
            grip_input.value = bender.min_grip  # type: ignore[attr-defined]

    def get_tube_id_map(self) -> dict[str, str]:
        """Get tube display name → ID mapping."""
        return self._tube_id_map
