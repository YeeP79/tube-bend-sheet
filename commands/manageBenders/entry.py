"""Manage Benders command - add, edit, and delete bender profiles and dies.

This command provides a dialog with an HTML tree view for managing bender
profiles and their associated die configurations.
"""

from __future__ import annotations

import os

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config
from ...storage import ProfileManager
from ...models import UnitConfig
from .html_bridge import HTMLBridge
from .input_dialogs import get_bender_input, get_die_input, confirm_delete

app: adsk.core.Application = adsk.core.Application.get()
ui: adsk.core.UserInterface = app.userInterface

# Command identity
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_manageBenders'
CMD_NAME = 'Manage Benders'
CMD_DESCRIPTION = 'Add, edit, or remove bender profiles and dies'
IS_PROMOTED = False

# UI placement
WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID

# Resource location for command icons and HTML
RESOURCE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')
ICON_FOLDER = RESOURCE_FOLDER

# Handler list stores Fusion event handlers for lifetime management.
# FusionHandler Protocol ensures type-safe handler storage.
local_handlers: list[futil.FusionHandler] = []

# Module-level state
_profile_manager: ProfileManager | None = None
_html_bridge: HTMLBridge | None = None
_units: UnitConfig | None = None


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
    global _profile_manager, _html_bridge, _units, local_handlers

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

    # Add HTML tree view for bender management
    html_url = os.path.join(RESOURCE_FOLDER, 'bender_tree.html')
    browser_input = inputs.addBrowserCommandInput(
        'benderTree', '', html_url, 300, 500
    )

    # Initialize HTML bridge for communication (with units for value formatting)
    _html_bridge = HTMLBridge(browser_input, _units)

    # Configure dialog
    cmd.setDialogInitialSize(500, 400)
    cmd.isOKButtonVisible = True
    cmd.okButtonText = 'Close'

    # Connect event handlers
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.incomingFromHTML, command_incoming_from_html, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    # Send initial bender data to HTML (don't wait for request due to timing issues)
    if _profile_manager:
        futil.log(f'{CMD_NAME}: Pushing {len(_profile_manager.benders)} benders to HTML on startup')
        _html_bridge.send_benders(_profile_manager.benders)


def command_incoming_from_html(args: adsk.core.HTMLEventArgs) -> None:
    """Handle incoming messages from the HTML tree view."""
    global _html_bridge, _profile_manager, _units

    futil.log(f'{CMD_NAME} HTML Event received: action={args.action}')

    if not _html_bridge or not _profile_manager or not _units:
        futil.log(f'{CMD_NAME} HTML Event: bridge/manager/units not ready')
        return

    message = _html_bridge.parse_message(args)
    futil.log(f'{CMD_NAME} HTML Event: {message}')

    try:
        if message.action == 'requestBenders':
            # Send all benders to the HTML view
            futil.log(f'{CMD_NAME}: Sending {len(_profile_manager.benders)} benders to HTML')
            _html_bridge.send_benders(_profile_manager.benders)

        elif message.action == 'addBender':
            _handle_add_bender()

        elif message.action == 'editBender':
            if message.bender_id:
                _handle_edit_bender(message.bender_id)

        elif message.action == 'deleteBender':
            if message.bender_id:
                _handle_delete_bender(message.bender_id)

        elif message.action == 'addDie':
            if message.bender_id:
                _handle_add_die(message.bender_id)

        elif message.action == 'editDie':
            if message.bender_id and message.die_id:
                _handle_edit_die(message.bender_id, message.die_id)

        elif message.action == 'deleteDie':
            if message.bender_id and message.die_id:
                _handle_delete_die(message.bender_id, message.die_id)

    except Exception:
        futil.handle_error('command_incoming_from_html')


def _handle_add_bender() -> None:
    """Handle adding a new bender via input dialogs."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender_input = get_bender_input(ui, _units)
    if bender_input is None:
        return

    bender = _profile_manager.add_bender(bender_input.name, bender_input.min_grip, "")
    _html_bridge.send_bender_added(bender)


def _handle_edit_bender(bender_id: str) -> None:
    """Handle editing an existing bender."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    bender_input = get_bender_input(
        ui, _units, current_name=bender.name, current_min_grip=bender.min_grip
    )
    if bender_input is None:
        return

    _profile_manager.update_bender(
        bender_id, bender_input.name, bender_input.min_grip, bender.notes
    )

    updated_bender = _profile_manager.get_bender_by_id(bender_id)
    if updated_bender:
        _html_bridge.send_bender_update(updated_bender)


def _handle_delete_bender(bender_id: str) -> None:
    """Handle deleting a bender."""
    if not _profile_manager or not _html_bridge:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    if confirm_delete(ui, "bender", bender.name, include_children=True):
        _profile_manager.delete_bender(bender_id)
        _html_bridge.send_bender_removed(bender_id)


def _handle_add_die(bender_id: str) -> None:
    """Handle adding a new die to a bender."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    die_input = get_die_input(ui, _units)
    if die_input is None:
        return

    _profile_manager.add_die_to_bender(
        bender_id, die_input.name, die_input.tube_od, die_input.clr,
        die_input.offset, die_input.min_tail, ""
    )

    updated_bender = _profile_manager.get_bender_by_id(bender_id)
    if updated_bender:
        _html_bridge.send_bender_update(updated_bender)


def _handle_edit_die(bender_id: str, die_id: str) -> None:
    """Handle editing an existing die."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    die = bender.get_die_by_id(die_id)
    if not die:
        return

    die_input = get_die_input(
        ui,
        _units,
        current_name=die.name,
        current_tube_od=die.tube_od,
        current_clr=die.clr,
        current_offset=die.offset,
        current_min_tail=die.min_tail,
    )
    if die_input is None:
        return

    _profile_manager.update_die(
        bender_id,
        die_id,
        die_input.name,
        die_input.tube_od,
        die_input.clr,
        die_input.offset,
        die_input.min_tail,
        die.notes,
    )

    updated_bender = _profile_manager.get_bender_by_id(bender_id)
    if updated_bender:
        _html_bridge.send_bender_update(updated_bender)


def _handle_delete_die(bender_id: str, die_id: str) -> None:
    """Handle deleting a die."""
    if not _profile_manager or not _html_bridge:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    die = bender.get_die_by_id(die_id)
    if not die:
        return

    if confirm_delete(ui, "die", die.name):
        _profile_manager.delete_die(bender_id, die_id)
        _html_bridge.send_die_removed(bender_id, die_id)


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
