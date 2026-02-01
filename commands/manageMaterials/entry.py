"""Manage Materials command - add, edit, and delete material profiles.

This command provides a dialog with an HTML tree view for managing tube
materials and their associated bender compensation data.
"""

from __future__ import annotations

import os

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config
from ...storage import ProfileManager
from ...storage.materials import MaterialManager
from ...models import UnitConfig
from ...models.material import Material
from .html_bridge import HTMLBridge
from .input_dialogs import (
    MaterialInput,
    confirm_delete,
    get_compensation_point_input,
    confirm_clear_compensation,
)
from .dialog_contexts import EditMaterialContext
from .dialog_launcher import (
    launch_material_dialog,
    register_dialog_commands,
    unregister_dialog_commands,
)
from .dialog_relaunch import (
    start as start_relaunch,
    stop as stop_relaunch,
)

app: adsk.core.Application = adsk.core.Application.get()
ui: adsk.core.UserInterface = app.userInterface

# Command identity
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_manageMaterials'
CMD_NAME = 'Manage Materials'
CMD_DESCRIPTION = 'Add, edit, or remove tube materials and bender compensation data'
IS_PROMOTED = False

# UI placement
WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID

# Resource location for command icons and HTML
RESOURCE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')
ICON_FOLDER = RESOURCE_FOLDER

# Handler list stores Fusion event handlers for lifetime management.
local_handlers: list[futil.FusionHandler] = []

# Module-level state
_material_manager: MaterialManager | None = None
_profile_manager: ProfileManager | None = None
_html_bridge: HTMLBridge | None = None
_units: UnitConfig | None = None


def start() -> None:
    """Initialize and register the command."""
    global _material_manager, _profile_manager

    # Initialize managers
    addin_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _material_manager = MaterialManager(addin_path)
    _profile_manager = ProfileManager(addin_path)

    # Register hidden dialog commands for material editing
    register_dialog_commands()

    # Register relaunch event for dialog reopening
    start_relaunch(CMD_ID)

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
    global _material_manager, _profile_manager, _html_bridge, _units, local_handlers

    # Unregister relaunch event first
    stop_relaunch()

    # Unregister hidden dialog commands
    unregister_dialog_commands()

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

    _material_manager = None
    _profile_manager = None
    _html_bridge = None
    _units = None
    local_handlers = []


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Set up the command dialog when the command is created."""
    global _html_bridge, _units

    futil.log(f'{CMD_NAME} Command Created Event')

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('No active design.', 'Error')
        return

    try:
        _units = UnitConfig.from_design(design)
    except ValueError as e:
        ui.messageBox(str(e), 'Unsupported Units')
        return

    cmd = args.command
    inputs = cmd.commandInputs

    # Add HTML tree view for material management
    html_url = os.path.join(RESOURCE_FOLDER, 'material_tree.html')
    browser_input = inputs.addBrowserCommandInput(
        'materialTree', '', html_url, 300, 450
    )

    # Initialize HTML bridge for communication (with units for value formatting)
    _html_bridge = HTMLBridge(browser_input, _units)

    # Configure dialog
    cmd.setDialogInitialSize(450, 380)
    cmd.isOKButtonVisible = True
    cmd.okButtonText = 'Close'

    # Connect event handlers
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.incomingFromHTML, command_incoming_from_html, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    # Send initial material data to HTML
    if _material_manager:
        futil.log(f'{CMD_NAME}: Pushing {len(_material_manager.materials)} materials to HTML on startup')
        _html_bridge.send_materials(_material_manager.materials)


def command_incoming_from_html(args: adsk.core.HTMLEventArgs) -> None:
    """Handle incoming messages from the HTML tree view."""
    global _html_bridge, _material_manager, _units

    futil.log(f'{CMD_NAME} HTML Event received: action={args.action}')

    if not _html_bridge or not _material_manager or not _units:
        futil.log(f'{CMD_NAME} HTML Event: bridge/manager/units not ready')
        return

    message = _html_bridge.parse_message(args)
    futil.log(f'{CMD_NAME} HTML Event: {message}')

    try:
        if message.action == 'requestMaterials':
            # Send all materials to the HTML view
            futil.log(f'{CMD_NAME}: Sending {len(_material_manager.materials)} materials to HTML')
            _html_bridge.send_materials(_material_manager.materials)

        elif message.action == 'addMaterial':
            _handle_add_material()

        elif message.action == 'editMaterial':
            if message.material_id:
                _handle_edit_material(message.material_id)

        elif message.action == 'deleteMaterial':
            if message.material_id:
                _handle_delete_material(message.material_id)

        elif message.action == 'manageCompensation':
            if message.material_id:
                _handle_manage_compensation(message.material_id)

    except Exception:
        futil.handle_error('command_incoming_from_html')


def _handle_add_material() -> None:
    """Handle adding a new material via form dialog."""
    if not _material_manager or not _units:
        return

    context = EditMaterialContext(
        material_id=None,
        current_name="New Material",
        current_tube_od=config.DEFAULT_TUBE_OD_CM,
        current_batch="",
        current_notes="",
    )

    def on_complete(result: MaterialInput | None) -> None:
        if result is None or not _material_manager:
            return
        new_material = _material_manager.add_material(
            result.name, result.tube_od, result.batch, result.notes
        )
        if _html_bridge:
            _html_bridge.send_material_added(new_material)

    launch_material_dialog(context, _units, on_complete)


def _handle_edit_material(material_id: str) -> None:
    """Handle editing an existing material via form dialog."""
    if not _material_manager or not _html_bridge or not _units:
        return

    material = _material_manager.get_material_by_id(material_id)
    if not material:
        return

    context = EditMaterialContext(
        material_id=material_id,
        current_name=material.name,
        current_tube_od=material.tube_od,
        current_batch=material.batch,
        current_notes=material.notes,
    )

    def on_complete(result: MaterialInput | None) -> None:
        if result is None or not _material_manager:
            return
        success = _material_manager.update_material(
            material_id, result.name, result.tube_od, result.batch, result.notes
        )
        if success and _html_bridge:
            updated_material = _material_manager.get_material_by_id(material_id)
            if updated_material:
                _html_bridge.send_material_update(updated_material)

    launch_material_dialog(context, _units, on_complete)


def _handle_delete_material(material_id: str) -> None:
    """Handle deleting a material."""
    if not _material_manager or not _html_bridge:
        return

    material = _material_manager.get_material_by_id(material_id)
    if not material:
        return

    if confirm_delete(ui, "material", material.name, include_children=True):
        _material_manager.delete_material(material_id)
        _html_bridge.send_material_removed(material_id)


def _handle_manage_compensation(material_id: str) -> None:
    """Handle managing compensation data for a material.

    Shows a dialog to select a compatible die, then allows managing
    compensation data points for that die-material pair.
    """
    if not _material_manager or not _profile_manager or not _units:
        return

    material = _material_manager.get_material_by_id(material_id)
    if not material:
        return

    # Find compatible dies (matching tube OD)
    compatible_dies: list[tuple[str, str, str]] = []  # (bender_name, die_id, die_name)
    for bender in _profile_manager.benders:
        for die in bender.dies:
            if abs(die.tube_od - material.tube_od) < 0.01:  # 0.01cm tolerance
                compatible_dies.append((bender.name, die.id, die.name))

    if not compatible_dies:
        ui.messageBox(
            f'No compatible dies found for material "{material.name}".\n\n'
            f'To create compensation data, you need a die with matching '
            f'tube OD ({material.tube_od * _units.cm_to_unit:.4f}{_units.unit_symbol}).\n\n'
            f'Use "Manage Benders" to create dies with this tube OD.',
            'No Compatible Dies'
        )
        return

    # If only one compatible die, use it directly
    if len(compatible_dies) == 1:
        bender_name, die_id, die_name = compatible_dies[0]
        _show_compensation_dialog(material, die_id, f"{bender_name} - {die_name}")
        return

    # Multiple dies - let user select
    die_names = [f"{b} - {d}" for b, _, d in compatible_dies]
    selected_index = _show_die_selection_dialog(die_names)

    if selected_index is not None and 0 <= selected_index < len(compatible_dies):
        bender_name, die_id, die_name = compatible_dies[selected_index]
        _show_compensation_dialog(material, die_id, f"{bender_name} - {die_name}")


def _show_die_selection_dialog(die_names: list[str]) -> int | None:
    """Show a simple selection dialog for choosing a die.

    Returns the selected index, or None if cancelled.
    """
    # Create a simple numbered list for selection
    options = "\n".join(f"{i+1}. {name}" for i, name in enumerate(die_names))
    prompt = f"Select a die for compensation data:\n\n{options}\n\nEnter number (1-{len(die_names)}):"

    ret_value, cancelled = ui.inputBox(prompt, "Select Die", "1")
    if cancelled:
        return None

    try:
        index = int(ret_value.strip()) - 1
        if 0 <= index < len(die_names):
            return index
    except ValueError:
        pass

    ui.messageBox("Invalid selection.", "Error")
    return None


def _show_compensation_dialog(
    material: Material,
    die_id: str,
    die_display_name: str,
) -> None:
    """Show the compensation data management dialog.

    This uses a simple menu-based approach for managing data points.
    """
    if not _material_manager:
        return

    while True:
        # Get current compensation data
        comp = _material_manager.get_or_create_compensation(die_id, material.id)
        points = comp.data_points

        # Build status message
        if points:
            points_text = "\n".join(
                f"  {i+1}. Readout: {p.readout_angle:.1f}° → Measured: {p.measured_angle:.1f}°"
                for i, p in enumerate(points)
            )
            status = f"Current data points ({len(points)}):\n{points_text}"
        else:
            status = "No compensation data points recorded yet."

        # Show menu
        message = (
            f"Bender Compensation Data\n"
            f"{'='*40}\n"
            f"Material: {material.name}\n"
            f"Die: {die_display_name}\n\n"
            f"{status}\n\n"
            f"Options:\n"
            f"  1. Add data point\n"
            f"  2. Remove data point\n"
            f"  3. Clear all data\n"
            f"  4. Done\n\n"
            f"Enter option (1-4):"
        )

        ret_value, cancelled = ui.inputBox(message, "Compensation Data", "4")
        if cancelled:
            return

        option = ret_value.strip()

        if option == "1":
            _add_compensation_point(die_id, material.id)
        elif option == "2":
            _remove_compensation_point(die_id, material.id, len(points))
        elif option == "3":
            _clear_compensation_data(die_id, material, die_display_name)
        elif option == "4":
            return
        else:
            ui.messageBox("Invalid option. Please enter 1-4.", "Error")


def _add_compensation_point(die_id: str, material_id: str) -> None:
    """Add a compensation data point."""
    if not _material_manager:
        return

    point = get_compensation_point_input(ui)
    if point:
        try:
            _material_manager.add_compensation_point(
                die_id, material_id, point.readout_angle, point.measured_angle
            )
            ui.messageBox(
                f"Added compensation point:\n"
                f"Readout: {point.readout_angle:.1f}°\n"
                f"Measured: {point.measured_angle:.1f}°",
                "Point Added"
            )
        except ValueError as e:
            ui.messageBox(str(e), "Error")


def _remove_compensation_point(die_id: str, material_id: str, count: int) -> None:
    """Remove a compensation data point by index."""
    if not _material_manager or count == 0:
        ui.messageBox("No data points to remove.", "Error")
        return

    ret_value, cancelled = ui.inputBox(
        f"Enter point number to remove (1-{count}):",
        "Remove Point",
        "1"
    )
    if cancelled:
        return

    try:
        index = int(ret_value.strip()) - 1
        if 0 <= index < count:
            if _material_manager.remove_compensation_point(die_id, material_id, index):
                ui.messageBox("Point removed.", "Success")
            else:
                ui.messageBox("Failed to remove point.", "Error")
        else:
            ui.messageBox(f"Invalid index. Enter 1-{count}.", "Error")
    except ValueError:
        ui.messageBox("Invalid number.", "Error")


def _clear_compensation_data(
    die_id: str,
    material: Material,
    die_display_name: str,
) -> None:
    """Clear all compensation data for a die-material pair."""
    if not _material_manager:
        return

    if confirm_clear_compensation(ui, die_display_name, material.name):
        _material_manager.clear_compensation_data(die_id, material.id)
        ui.messageBox("All compensation data cleared.", "Cleared")


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Execute the command - dialog closed with OK."""
    futil.log(f'{CMD_NAME} Command Execute Event')
    # Nothing to do - changes are saved as they're made


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when the command dialog is closed."""
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers, _html_bridge, _units
    local_handlers = []
    _html_bridge = None
    _units = None
