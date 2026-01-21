"""Create Bend Sheet command - generates printable bend sheets from selected tube paths.

This command analyzes selected sketch geometry (lines and arcs) to calculate
bend angles, rotations, and straight lengths, then generates an HTML bend sheet
for printing.
"""

from __future__ import annotations

import os

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config
from ...models import UnitConfig
from ...storage import ProfileManager, AttributeManager
from ...storage.attributes import TubeSettings

from .dialog_builder import BendSheetDialogBuilder
from .input_parser import InputParser
from .selection_validator import SelectionValidator
from .bend_sheet_generator import BendSheetGenerator
from .bend_sheet_display import BendSheetDisplay

app: adsk.core.Application = adsk.core.Application.get()
ui: adsk.core.UserInterface = app.userInterface

# Command identity
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_createBendSheet'
CMD_NAME = 'Create Bend Sheet'
CMD_DESCRIPTION = 'Generate a printable bend sheet from selected tube path'
IS_PROMOTED = True

# UI placement
WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID

# Resource location for command icons
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Handler list stores Fusion event handlers for lifetime management.
# FusionHandler Protocol ensures type-safe handler storage.
local_handlers: list[futil.FusionHandler] = []

# Module-level profile manager (initialized in start)
_profile_manager: ProfileManager | None = None


def start() -> None:
    """Initialize and register the command."""
    global _profile_manager

    # Initialize profile manager
    addin_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _profile_manager = ProfileManager(addin_path)

    # Create command definition
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )

    # Connect command created handler
    futil.add_handler(cmd_def.commandCreated, command_created)

    # Get workspace and panel
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if workspace:
        toolbar_tabs = workspace.toolbarTabs
        tools_tab = toolbar_tabs.itemById(config.TAB_ID)

        if tools_tab:
            panel = tools_tab.toolbarPanels.itemById(PANEL_ID)
            if not panel:
                panel = tools_tab.toolbarPanels.add(PANEL_ID, config.PANEL_NAME, config.TAB_ID, False)

            control = panel.controls.itemById(CMD_ID)
            if not control:
                control = panel.controls.addCommand(cmd_def)
                control.isPromoted = IS_PROMOTED


def stop() -> None:
    """Clean up the command."""
    global _profile_manager, local_handlers

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
    local_handlers = []


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Set up the command dialog when the command is created."""
    global _profile_manager, local_handlers
    local_handlers = []
    futil.log(f'{CMD_NAME} Command Created Event')

    # Create fresh profile manager to pick up any changes made via Manage Benders
    addin_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _profile_manager = ProfileManager(addin_path)

    cmd = args.command

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('No active design. Please open a design first.', 'Error')
        return

    try:
        units = UnitConfig.from_design(design)
    except ValueError as e:
        ui.messageBox(str(e), 'Unsupported Units')
        return

    # Validate selection
    validator = SelectionValidator(units)
    result = validator.validate_for_dialog(ui.activeSelections)

    if not result.is_valid:
        ui.messageBox(result.error_message or 'Invalid selection', 'Create Bend Sheet')
        return

    # Try to load saved settings
    saved_settings: TubeSettings | None = None
    if result.first_entity:
        saved_settings = AttributeManager.load_settings(result.first_entity)

    # Build dialog using dialog builder
    builder = BendSheetDialogBuilder(cmd.commandInputs, _profile_manager, units)
    builder.build_all(
        detected_clr=result.detected_clr,
        saved_settings=saved_settings,
        primary_axis=result.primary_axis,
        current_direction=result.travel_direction,
        opposite_direction=result.opposite_direction,
    )

    # Dialog settings
    cmd.setDialogInitialSize(400, 500)
    cmd.isOKButtonVisible = True
    cmd.okButtonText = 'Create Bend Sheet'

    # Connect event handlers
    if config.DEBUG:
        futil.log(f'{CMD_NAME}: Connecting handlers...')
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)
    if config.DEBUG:
        futil.log(f'{CMD_NAME}: Handlers connected, count = {len(local_handlers)}')


def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    """Handle input changes - updates die list when bender changes."""
    try:
        if config.DEBUG:
            futil.log(f'{CMD_NAME}: input_changed - {args.input.id}')

        changed_input = args.input
        inputs = args.inputs

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return

        try:
            units = UnitConfig.from_design(design)
        except ValueError:
            return  # Silently skip update if units unsupported

        # Use dialog builder for dropdown updates
        builder = BendSheetDialogBuilder(inputs, _profile_manager, units)

        if changed_input.id == 'bender':
            bender_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById('bender')
            )
            if bender_dropdown and bender_dropdown.selectedItem:
                builder.update_die_dropdown_for_bender(bender_dropdown.selectedItem.name)

        elif changed_input.id == 'die':
            bender_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById('bender')
            )
            die_dropdown = adsk.core.DropDownCommandInput.cast(
                inputs.itemById('die')
            )
            if (
                bender_dropdown
                and bender_dropdown.selectedItem
                and die_dropdown
                and die_dropdown.selectedItem
            ):
                builder.update_values_for_die(
                    bender_dropdown.selectedItem.name,
                    die_dropdown.selectedItem.name,
                )

    except:
        futil.handle_error('command_input_changed')


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Execute the command - generate the bend sheet."""
    futil.log(f'{CMD_NAME} Command Execute Event')

    inputs = args.command.commandInputs

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('No active design.', 'Error')
        return

    try:
        units = UnitConfig.from_design(design)
    except ValueError as e:
        ui.messageBox(str(e), 'Unsupported Units')
        return

    # Validate and analyze selection
    validator = SelectionValidator(units)
    selection_result = validator.validate_for_execution(ui.activeSelections)

    if not selection_result.is_valid:
        ui.messageBox(selection_result.error_message or 'Invalid selection', 'Error')
        return

    # Guard: valid result must have start_point and end_point
    if selection_result.start_point is None or selection_result.end_point is None:
        ui.messageBox('Invalid path: could not determine start/end points', 'Error')
        return

    # Parse input values
    parser = InputParser(inputs, units)
    params = parser.parse(_profile_manager)

    # Get path info, handling direction reversal
    ordered_path = selection_result.ordered_path
    starts_with_arc = selection_result.starts_with_arc
    ends_with_arc = selection_result.ends_with_arc
    start_point = selection_result.start_point

    if params.travel_reversed:
        ordered_path = ordered_path[::-1]
        start_point = selection_result.end_point
        starts_with_arc, ends_with_arc = ends_with_arc, starts_with_arc
        # Full label: "Front to Back" (current to opposite)
        travel_direction = (
            f"{selection_result.travel_direction} to "
            f"{selection_result.opposite_direction}"
        )
        opposite_direction = (
            f"{selection_result.opposite_direction} to "
            f"{selection_result.travel_direction}"
        )
    else:
        # Full label: "Back to Front" (opposite to current)
        travel_direction = (
            f"{selection_result.opposite_direction} to "
            f"{selection_result.travel_direction}"
        )
        opposite_direction = (
            f"{selection_result.travel_direction} to "
            f"{selection_result.opposite_direction}"
        )

    # Generate bend sheet data
    generator = BendSheetGenerator(units)
    result = generator.generate(
        ordered_path=ordered_path,
        start_point=start_point,
        params=params,
        component_name=selection_result.component_name,
        travel_direction=travel_direction,
        opposite_direction=opposite_direction,
        starts_with_arc=starts_with_arc,
        ends_with_arc=ends_with_arc,
    )

    if not result.success:
        error_msg = result.error
        if result.suggestion:
            error_msg += f"\n\nSuggestion: {result.suggestion}"
        ui.messageBox(error_msg, 'Error')
        return

    # Save settings to document
    if selection_result.first_entity:
        settings = TubeSettings(
            bender_id=params.bender_id,
            die_id=params.die_id,
            tube_od=params.tube_od,
            precision=params.precision,
            travel_reversed=params.travel_reversed,
        )
        AttributeManager.save_settings(selection_result.first_entity, settings)

    # Guard: successful result must have data
    if result.data is None:
        ui.messageBox('Internal error: No bend sheet data generated', 'Error')
        return

    # Display result
    display = BendSheetDisplay(ui)
    display.show(result.data)


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when the command dialog is closed."""
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers
    local_handlers = []
