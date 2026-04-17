"""Unified Tube Fabrication command — select body → bend sheet + cope templates.

One toolbar button. Select a tube body, auto-extract everything,
minimal dialog, combined printable output.
"""

from __future__ import annotations

import os
import tempfile
import webbrowser

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config
from ...models import UnitConfig
from ...storage import ProfileManager
from ...storage.tubes import TubeManager
from ...core import format_length
from ...core.combined_output import generate_combined_document

from ..createBendSheet.bend_sheet_generator import BendSheetGenerator
from ..createBendSheet.input_parser import InputParser

from .body_analyzer import analyze_body, build_cope_pages, BodyAnalysisResult
from .dialog_builder import TubeFabDialogBuilder

app: adsk.core.Application = adsk.core.Application.get()
ui: adsk.core.UserInterface = app.userInterface

# Command identity
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_tubeFabrication"
CMD_NAME = "Tube Fabrication"
CMD_DESCRIPTION = "Select a tube body to auto-generate a bend sheet and cope templates"
IS_PROMOTED = True

# UI placement
WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID

# Resource location for command icons
ICON_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", ""
)

# Handler list for lifetime management
local_handlers: list[futil.FusionHandler] = []

# Module-level state
_profile_manager: ProfileManager | None = None
_tube_manager: TubeManager | None = None
_dialog_builder: TubeFabDialogBuilder | None = None
_analysis: BodyAnalysisResult | None = None


def start() -> None:
    """Initialize and register the command."""
    global _profile_manager, _tube_manager

    addin_path = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    _profile_manager = ProfileManager(addin_path)
    _tube_manager = TubeManager(addin_path)

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER,
    )

    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if workspace:
        toolbar_tabs = workspace.toolbarTabs
        tools_tab = toolbar_tabs.itemById(config.TAB_ID)

        if tools_tab:
            panel = tools_tab.toolbarPanels.itemById(PANEL_ID)
            if not panel:
                panel = tools_tab.toolbarPanels.add(
                    PANEL_ID, config.PANEL_NAME, config.TAB_ID, False,
                )

            control = panel.controls.itemById(CMD_ID)
            if not control:
                control = panel.controls.addCommand(cmd_def)
                control.isPromoted = IS_PROMOTED


def stop() -> None:
    """Clean up the command."""
    global _profile_manager, _tube_manager, _dialog_builder, _analysis, local_handlers

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if workspace:
        toolbar_tabs = workspace.toolbarTabs
        tools_tab = toolbar_tabs.itemById(config.TAB_ID)

        if tools_tab:
            panel = tools_tab.toolbarPanels.itemById(PANEL_ID)
            if panel:
                control = panel.controls.itemById(CMD_ID)
                if control:
                    control.deleteMe()

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    _profile_manager = None
    _tube_manager = None
    _dialog_builder = None
    _analysis = None
    local_handlers = []


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Set up the command dialog when the command is created."""
    global _dialog_builder, _analysis, local_handlers
    local_handlers = []

    futil.log(f"{CMD_NAME} Command Created Event (v2 — coaxial merge)")

    if _profile_manager:
        _profile_manager.reload()
    if _tube_manager:
        _tube_manager.reload()

    if not _profile_manager or not _tube_manager:
        ui.messageBox(
            "Add-in not fully initialized. Please restart Fusion 360.", "Error"
        )
        return

    cmd = args.command
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("No active design. Please open a design first.", "Error")
        return

    try:
        units = UnitConfig.from_design(design)
    except ValueError as e:
        ui.messageBox(str(e), "Unsupported Units")
        return

    # Validate selection — must have exactly one body selected
    body = _get_selected_body()
    if body is None:
        ui.messageBox(
            "Please select a tube body before running this command.",
            "Tube Fabrication",
        )
        return

    # Analyse the body
    try:
        analysis = analyze_body(body, units, design=design)
    except Exception:
        import traceback
        ui.messageBox(
            f"Error analyzing body:\n{traceback.format_exc()}",
            "Tube Fabrication — Debug",
        )
        return
    if analysis is None:
        ui.messageBox(
            "Could not extract tube path from the selected body.\n"
            "The body must have cylindrical (straight) and/or torus (bend) faces.",
            "Tube Fabrication",
        )
        return

    _analysis = analysis

    # Build dialog
    _dialog_builder = TubeFabDialogBuilder(
        cmd.commandInputs, _profile_manager, units, _tube_manager,
    )
    _dialog_builder.build_all(analysis)

    # Dialog settings
    cmd.setDialogInitialSize(400, 550)
    cmd.isOKButtonVisible = True
    cmd.okButtonText = "Generate"

    # Connect event handlers
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers,
    )
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    """Handle input changes — update die/tube lists when bender changes."""
    try:
        changed = args.input
        inputs = args.inputs

        if not _dialog_builder:
            return

        if changed.id == "bender":
            bender_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById("bender")
            )
            if bender_dropdown and bender_dropdown.selectedItem:
                bender_name = bender_dropdown.selectedItem.name
                _dialog_builder.update_die_dropdown_for_bender(bender_name)
                _dialog_builder.update_bender_values(bender_name)

        elif changed.id == "die":
            bender_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById("bender")
            )
            die_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById("die")
            )
            if (
                bender_dropdown
                and bender_dropdown.selectedItem
                and die_dropdown
                and die_dropdown.selectedItem
            ):
                _dialog_builder.update_values_for_die(
                    bender_dropdown.selectedItem.name,
                    die_dropdown.selectedItem.name,
                )

        elif changed.id == "tube":
            tube_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById("tube")
            )
            comp_checkbox = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById("apply_compensation")
            )
            if tube_dropdown and comp_checkbox:
                has_tube = (
                    tube_dropdown.selectedItem
                    and tube_dropdown.selectedItem.name != "(None)"
                )
                comp_checkbox.isEnabled = has_tube  # type: ignore[attr-defined]
                if not has_tube:
                    comp_checkbox.value = False  # type: ignore[attr-defined]

    except:
        futil.handle_error("command_input_changed")


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Execute — generate bend sheet + cope templates."""
    try:
        futil.log(f"{CMD_NAME} Command Execute Event")

        if _analysis is None:
            ui.messageBox("No body analysis available.", "Error")
            return

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("No active design.", "Error")
            return

        try:
            units = UnitConfig.from_design(design)
        except ValueError as e:
            ui.messageBox(str(e), "Unsupported Units")
            return

        inputs = args.command.commandInputs

        # Parse input values
        parser = InputParser(inputs, units)
        tube_id_map = _dialog_builder.get_tube_id_map() if _dialog_builder else None
        params = parser.parse(_profile_manager, _tube_manager, tube_id_map)

        # Get direction (index 0 = natural, index 1 = reversed)
        travel_reversed = params.travel_reversed

        straights = _analysis.straights
        bends = _analysis.bends
        starts_with_arc = _analysis.starts_with_bend
        ends_with_arc = _analysis.ends_with_bend

        if travel_reversed:
            straights = straights[::-1]
            bends = bends[::-1]
            starts_with_arc, ends_with_arc = ends_with_arc, starts_with_arc
            travel_direction = (
                f"{_analysis.travel_direction} to {_analysis.opposite_direction}"
            )
            opposite_direction = (
                f"{_analysis.opposite_direction} to {_analysis.travel_direction}"
            )
        else:
            travel_direction = (
                f"{_analysis.opposite_direction} to {_analysis.travel_direction}"
            )
            opposite_direction = (
                f"{_analysis.travel_direction} to {_analysis.opposite_direction}"
            )

        # Generate bend sheet data
        generator = BendSheetGenerator(units, _tube_manager)
        result = generator.generate_from_data(
            straights=straights,
            bends=bends,
            clr=_analysis.clr,
            clr_mismatch=_analysis.clr_mismatch,
            clr_values=_analysis.clr_values_display,
            params=params,
            component_name=_analysis.body_name,
            travel_direction=travel_direction,
            opposite_direction=opposite_direction,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
        )

        if not result.success:
            error_msg = result.error
            if result.suggestion:
                error_msg += f"\n\nSuggestion: {result.suggestion}"
            ui.messageBox(error_msg, "Error")
            return

        if result.data is None:
            ui.messageBox("Internal error: No bend sheet data generated", "Error")
            return

        # Read template layout dropdown
        layout_input = adsk.core.DropDownCommandInput.cast(
            inputs.itemById("template_layout")
        )
        if layout_input and layout_input.selectedItem:
            waste_side = "bottom" if "Setback" in layout_input.selectedItem.name else "top"
        else:
            waste_side = "top"

        # Build cope pages for coped ends
        cope_pages = build_cope_pages(_analysis, units, waste_side=waste_side)

        # Generate combined HTML
        html = generate_combined_document(result.data, cope_pages)

        # Save and display
        safe_name = _sanitize_filename(_analysis.body_name)
        temp_dir = tempfile.gettempdir()
        html_path = os.path.join(temp_dir, f"{safe_name}.html")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Build summary
        cut_length_str = format_length(
            result.data.total_cut_length,
            result.data.precision,
            result.data.units,
        )
        bend_count = len(result.data.bends)
        cope_count = len(cope_pages)

        message = (
            f"Tube fabrication output created!\n\n"
            f"Body: {_analysis.body_name}\n"
            f"Cut Length: {cut_length_str}\n"
            f"Bends: {bend_count}\n"
        )
        if cope_count > 0:
            message += f"Cope Templates: {cope_count}\n"

        message += "\nOpen in browser for printing?"

        msg_result = ui.messageBox(
            message,
            "Tube Fabrication",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType,
        )

        if msg_result == adsk.core.DialogResults.DialogYes:
            webbrowser.open(f"file://{html_path}")

    except:
        futil.handle_error("command_execute")


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when command dialog is closed."""
    futil.log(f"{CMD_NAME} Command Destroy Event")
    global local_handlers
    local_handlers = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_selected_body() -> adsk.fusion.BRepBody | None:
    """Get the first selected BRepBody (or body from selected face/edge)."""
    sel = ui.activeSelections
    if sel.count == 0:
        return None

    entity = sel.item(0).entity

    if isinstance(entity, adsk.fusion.BRepBody):
        return entity
    if isinstance(entity, (adsk.fusion.BRepFace, adsk.fusion.BRepEdge)):
        return entity.body
    if isinstance(entity, adsk.fusion.Occurrence):
        comp = entity.component
        if comp.bRepBodies.count > 0:
            return comp.bRepBodies.item(0)
    return None


def _sanitize_filename(name: str | None) -> str:
    """Create a safe filename from body name."""
    if not name:
        return "tube_fabrication"

    name = "".join(c for c in name if c.isprintable())
    if not name:
        return "tube_fabrication"

    result = (
        name.replace(" ", "_")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace("*", "-")
        .replace("?", "-")
        .replace('"', "-")
        .replace("<", "-")
        .replace(">", "-")
        .replace("|", "-")
    )
    return result[:100]
