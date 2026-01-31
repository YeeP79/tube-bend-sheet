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
from .input_dialogs import BenderInput, DieInput, confirm_delete
from .dialog_contexts import EditBenderContext, EditDieContext
from .dialog_launcher import (
    launch_bender_dialog,
    launch_die_dialog,
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

    # Register hidden dialog commands for bender/die editing
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
    global _profile_manager, _html_bridge, _units, local_handlers

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
    """Handle adding a new bender via form dialog."""
    if not _profile_manager or not _units:
        return

    context = EditBenderContext(
        bender_id=None,
        current_name="New Bender",
        current_min_grip=config.DEFAULT_MIN_GRIP_CM,
        current_notes="",
    )

    def on_complete(result: BenderInput | None) -> None:
        if result is None or not _profile_manager:
            return
        new_bender = _profile_manager.add_bender(result.name, result.min_grip, result.notes)
        if _html_bridge:
            _html_bridge.send_bender_added(new_bender)

    launch_bender_dialog(context, _units, on_complete)


def _handle_edit_bender(bender_id: str) -> None:
    """Handle editing an existing bender via form dialog."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    context = EditBenderContext(
        bender_id=bender_id,
        current_name=bender.name,
        current_min_grip=bender.min_grip,
        current_notes=bender.notes,
    )

    def on_complete(result: BenderInput | None) -> None:
        if result is None or not _profile_manager:
            return
        success = _profile_manager.update_bender(
            bender_id, result.name, result.min_grip, result.notes
        )
        if success and _html_bridge:
            updated_bender = _profile_manager.get_bender_by_id(bender_id)
            if updated_bender:
                _html_bridge.send_bender_update(updated_bender)

    launch_bender_dialog(context, _units, on_complete)


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
    """Handle adding a new die to a bender via form dialog."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    context = EditDieContext(
        bender_id=bender_id,
        die_id=None,
        current_name="New Die",
        current_tube_od=config.DEFAULT_TUBE_OD_CM,
        current_clr=config.DEFAULT_CLR_CM,
        current_offset=config.DEFAULT_DIE_OFFSET_CM,
        current_min_tail=config.DEFAULT_MIN_TAIL_CM,
        current_notes="",
    )

    def on_complete(result: DieInput | None) -> None:
        if result is None or not _profile_manager:
            return
        new_die = _profile_manager.add_die_to_bender(
            bender_id,
            result.name,
            result.tube_od,
            result.clr,
            result.offset,
            result.min_tail,
            result.notes,
        )
        if new_die and _html_bridge:
            updated_bender = _profile_manager.get_bender_by_id(bender_id)
            if updated_bender:
                _html_bridge.send_bender_update(updated_bender)

    launch_die_dialog(context, _units, on_complete)


def _handle_edit_die(bender_id: str, die_id: str) -> None:
    """Handle editing an existing die via form dialog."""
    if not _profile_manager or not _html_bridge or not _units:
        return

    bender = _profile_manager.get_bender_by_id(bender_id)
    if not bender:
        return

    die = bender.get_die_by_id(die_id)
    if not die:
        return

    context = EditDieContext(
        bender_id=bender_id,
        die_id=die_id,
        current_name=die.name,
        current_tube_od=die.tube_od,
        current_clr=die.clr,
        current_offset=die.offset,
        current_min_tail=die.min_tail,
        current_notes=die.notes,
    )

    def on_complete(result: DieInput | None) -> None:
        if result is None or not _profile_manager:
            return
        success = _profile_manager.update_die(
            bender_id,
            die_id,
            result.name,
            result.tube_od,
            result.clr,
            result.offset,
            result.min_tail,
            result.notes,
        )
        if success and _html_bridge:
            updated_bender = _profile_manager.get_bender_by_id(bender_id)
            if updated_bender:
                _html_bridge.send_bender_update(updated_bender)

    launch_die_dialog(context, _units, on_complete)


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
