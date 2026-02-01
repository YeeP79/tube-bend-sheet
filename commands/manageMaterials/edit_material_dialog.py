"""Edit Material dialog command.

A hidden Fusion command that displays a form dialog for adding/editing materials.
This command is not added to any toolbar - it's launched programmatically.
"""

from __future__ import annotations

from collections.abc import Callable

import adsk.core

from ...lib import fusionAddInUtils as futil
from ... import config
from ...models import UnitConfig
from .dialog_contexts import EditMaterialContext
from .dialog_relaunch import request_relaunch
from .input_dialogs import MaterialInput

# Command identity - hidden from toolbar
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_editMaterialDialog'
CMD_NAME = 'Edit Material'

# Handler list for lifetime management
local_handlers: list[futil.FusionHandler] = []

# Module-level state for passing context between functions
_context: EditMaterialContext | None = None
_units: UnitConfig | None = None
_on_complete: Callable[[MaterialInput | None], None] | None = None


def set_context(
    context: EditMaterialContext,
    units: UnitConfig,
    on_complete: Callable[[MaterialInput | None], None],
) -> None:
    """Set context before launching the dialog.

    Args:
        context: Pre-populated values for the form
        units: Unit configuration for display
        on_complete: Callback with result (None if cancelled)
    """
    global _context, _units, _on_complete
    _context = context
    _units = units
    _on_complete = on_complete


def register_command() -> None:
    """Register the hidden command definition."""
    app = adsk.core.Application.get()
    ui = app.userInterface

    # Remove existing definition if present
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    # Create command definition (no icon folder = no toolbar button)
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, '')
    futil.add_handler(cmd_def.commandCreated, command_created)


def unregister_command() -> None:
    """Unregister the command definition."""
    app = adsk.core.Application.get()
    ui = app.userInterface

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def launch() -> None:
    """Execute the command to show the dialog."""
    app = adsk.core.Application.get()
    ui = app.userInterface

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.execute()  # type: ignore[attr-defined]


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Set up the command dialog when created."""
    global local_handlers

    if not _context or not _units:
        futil.log(f'{CMD_NAME}: No context set')
        return

    cmd = args.command
    inputs = cmd.commandInputs

    # Set dialog size
    cmd.setDialogInitialSize(400, 300)

    # Name field
    name_input = inputs.addStringValueInput(
        'material_name',
        'Name',
        _context.current_name,
    )
    name_input.tooltip = (  # type: ignore[attr-defined]
        'Display name for this material (e.g., "DOM 1020", "4130 Chromoly")'
    )

    # Tube OD field - context value is already in cm (internal units)
    tube_od_input = inputs.addValueInput(
        'tube_od',
        f'Tube OD ({_units.unit_symbol})',
        _units.unit_name,
        adsk.core.ValueInput.createByReal(_context.current_tube_od),
    )
    tube_od_input.tooltip = (
        'Tube outer diameter. This must match the tube OD of dies '
        'you want to use with this material for compensation data.'
    )

    # Batch field
    batch_input = inputs.addStringValueInput(
        'batch',
        'Batch/Lot (optional)',
        _context.current_batch,
    )
    batch_input.tooltip = (  # type: ignore[attr-defined]
        'Optional batch or lot number for tracking material batches with '
        'different properties.'
    )

    # Notes field (multi-line)
    notes_input = inputs.addTextBoxCommandInput(
        'notes',
        'Notes',
        _context.current_notes,
        3,  # Number of rows
        False,  # Not read-only
    )
    notes_input.tooltip = (  # type: ignore[attr-defined]
        'Optional notes about this material (supplier, specifications, etc.)'
    )

    # Connect event handlers
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Handle OK button - validate and return data."""
    global _on_complete, _units

    if not _units:
        return

    inputs = args.command.commandInputs

    # Extract values
    name_input = adsk.core.StringValueCommandInput.cast(inputs.itemById('material_name'))
    tube_od_input = adsk.core.ValueCommandInput.cast(inputs.itemById('tube_od'))
    batch_input = adsk.core.StringValueCommandInput.cast(inputs.itemById('batch'))
    notes_input = adsk.core.TextBoxCommandInput.cast(  # type: ignore[attr-defined]
        inputs.itemById('notes')
    )

    if not name_input or not tube_od_input or not batch_input or not notes_input:
        return

    name = name_input.value.strip()
    tube_od = tube_od_input.value  # Already in cm from ValueInput
    batch = batch_input.value.strip()
    notes = notes_input.text

    # Validate
    app = adsk.core.Application.get()
    ui = app.userInterface

    if not name:
        ui.messageBox('Name cannot be empty.', 'Invalid Input')
        args.isValidResult = False  # type: ignore[attr-defined]
        return

    if tube_od <= 0:
        ui.messageBox('Tube OD must be a positive value.', 'Invalid Input')
        args.isValidResult = False  # type: ignore[attr-defined]
        return

    # Create result and call callback
    result = MaterialInput(name=name, tube_od=tube_od, batch=batch, notes=notes)

    if _on_complete:
        _on_complete(result)

    # Request Manage Materials dialog to reopen after this dialog closes
    request_relaunch()


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when dialog closes."""
    global local_handlers, _context, _on_complete

    local_handlers = []
    _context = None
    _on_complete = None
