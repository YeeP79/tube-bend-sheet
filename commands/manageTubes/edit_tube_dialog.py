"""Edit Tube dialog command.

A hidden Fusion command that displays a form dialog for adding/editing tubes.
This command is not added to any toolbar - it's launched programmatically.
"""

from __future__ import annotations

from collections.abc import Callable

import adsk.core

from ...lib import fusionAddInUtils as futil
from ... import config
from ...models import UnitConfig
from ...models.tube import MATERIAL_TYPES
from .dialog_contexts import EditTubeContext
from .dialog_relaunch import request_relaunch
from .input_dialogs import TubeInput

# Command identity - hidden from toolbar
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_editTubeDialog'
CMD_NAME = 'Edit Tube'

# Handler list for lifetime management
local_handlers: list[futil.FusionHandler] = []

# Module-level state for passing context between functions
_context: EditTubeContext | None = None
_units: UnitConfig | None = None
_on_complete: Callable[[TubeInput | None], None] | None = None


def set_context(
    context: EditTubeContext,
    units: UnitConfig,
    on_complete: Callable[[TubeInput | None], None],
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
    cmd.setDialogInitialSize(400, 350)

    # Name field
    name_input = inputs.addStringValueInput(
        'tube_name',
        'Name',
        _context.current_name,
    )
    name_input.tooltip = (  # type: ignore[attr-defined]
        'Display name for this tube (e.g., "DOM 1020 1.75x0.120")'
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
        'you want to use with this tube for compensation data.'
    )

    # Wall thickness field
    wall_input = inputs.addValueInput(
        'wall_thickness',
        f'Wall Thickness ({_units.unit_symbol})',
        _units.unit_name,
        adsk.core.ValueInput.createByReal(_context.current_wall_thickness),
    )
    wall_input.tooltip = (
        'Wall thickness of the tube. Leave at 0 if not specified.'
    )

    # Material type dropdown
    mat_type_dropdown = inputs.addDropDownCommandInput(
        'material_type',
        'Material Type',
        adsk.core.DropDownStyles.TextListDropDownStyle,
    )
    items = mat_type_dropdown.listItems
    for mat_type in MATERIAL_TYPES:
        display = mat_type if mat_type else "(Not specified)"
        is_selected = mat_type == _context.current_material_type
        items.add(display, is_selected)

    # Batch field
    batch_input = inputs.addStringValueInput(
        'batch',
        'Batch/Lot (optional)',
        _context.current_batch,
    )
    batch_input.tooltip = (  # type: ignore[attr-defined]
        'Optional batch or lot number for tracking tube batches with '
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
        'Optional notes about this tube (supplier, specifications, etc.)'
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
    name_input = adsk.core.StringValueCommandInput.cast(inputs.itemById('tube_name'))
    tube_od_input = adsk.core.ValueCommandInput.cast(inputs.itemById('tube_od'))
    wall_input = adsk.core.ValueCommandInput.cast(inputs.itemById('wall_thickness'))
    mat_type_dropdown = adsk.core.DropDownCommandInput.cast(inputs.itemById('material_type'))
    batch_input = adsk.core.StringValueCommandInput.cast(inputs.itemById('batch'))
    notes_input = adsk.core.TextBoxCommandInput.cast(  # type: ignore[attr-defined]
        inputs.itemById('notes')
    )

    if not name_input or not tube_od_input or not batch_input or not notes_input:
        return

    name = name_input.value.strip()
    tube_od = tube_od_input.value  # Already in cm from ValueInput
    wall_thickness = wall_input.value if wall_input else 0.0

    # Extract material type from dropdown
    material_type = ""
    if mat_type_dropdown and mat_type_dropdown.selectedItem:
        selected_name = mat_type_dropdown.selectedItem.name
        if selected_name != "(Not specified)":
            material_type = selected_name

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

    if wall_thickness < 0:
        ui.messageBox('Wall thickness must be non-negative.', 'Invalid Input')
        args.isValidResult = False  # type: ignore[attr-defined]
        return

    # Create result and call callback
    result = TubeInput(
        name=name,
        tube_od=tube_od,
        wall_thickness=wall_thickness,
        material_type=material_type,
        batch=batch,
        notes=notes,
    )

    if _on_complete:
        _on_complete(result)

    # Request Manage Tubes dialog to reopen after this dialog closes
    request_relaunch()


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when dialog closes."""
    global local_handlers, _context, _on_complete

    local_handlers = []
    _context = None
    _on_complete = None
