"""Edit Die dialog command.

A hidden Fusion command that displays a form dialog for adding/editing dies.
This command is not added to any toolbar - it's launched programmatically.
"""

from __future__ import annotations

from collections.abc import Callable

import adsk.core

from ...lib import fusionAddInUtils as futil
from ... import config
from ...models import UnitConfig
from ...models.bender import validate_die_values
from .dialog_contexts import EditDieContext
from .dialog_relaunch import request_relaunch
from .input_dialogs import DieInput

# Command identity - hidden from toolbar
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_editDieDialog'
CMD_NAME = 'Edit Die'

# Handler list for lifetime management
local_handlers: list[futil.FusionHandler] = []

# Module-level state for passing context between functions
_context: EditDieContext | None = None
_units: UnitConfig | None = None
_on_complete: Callable[[DieInput | None], None] | None = None


def set_context(
    context: EditDieContext,
    units: UnitConfig,
    on_complete: Callable[[DieInput | None], None],
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
    cmd.setDialogInitialSize(400, 400)

    # Name field
    name_input = inputs.addStringValueInput(
        'die_name',
        'Name',
        _context.current_name,
    )
    name_input.tooltip = "Display name for this die (e.g., '1.75 x 5.5 CLR')"  # type: ignore[attr-defined]

    # Tube OD field - context value is already in cm (internal units)
    # Fusion handles display conversion automatically based on unit_name
    tube_od_input = inputs.addValueInput(
        'tube_od',
        f'Tube OD ({_units.unit_symbol})',
        _units.unit_name,
        adsk.core.ValueInput.createByReal(_context.current_tube_od),
    )
    tube_od_input.tooltip = (
        'Outer diameter of the tube this die accepts. '
        'Must match the actual tube being bent.'
    )

    # CLR field - context value is already in cm
    clr_input = inputs.addValueInput(
        'clr',
        f'CLR ({_units.unit_symbol})',
        _units.unit_name,
        adsk.core.ValueInput.createByReal(_context.current_clr),
    )
    clr_input.tooltip = (
        'Center Line Radius - distance from tube centerline to center of bend arc. '
        'This is fixed by the die\'s physical construction. Smaller CLR = tighter bend.'
    )

    # Die offset field - context value is already in cm
    offset_input = inputs.addValueInput(
        'die_offset',
        f'Die Offset ({_units.unit_symbol})',
        _units.unit_name,
        adsk.core.ValueInput.createByReal(_context.current_offset),
    )
    offset_input.tooltip = (
        'Distance from the leading edge of the die to the bend tangent point. '
        'Compensates for die shape in bend placement calculations.'
    )

    # Min tail field - context value is already in cm
    min_tail_input = inputs.addValueInput(
        'min_tail',
        f'Min Tail ({_units.unit_symbol})',
        _units.unit_name,
        adsk.core.ValueInput.createByReal(_context.current_min_tail),
    )
    min_tail_input.tooltip = (
        'For JD2-style benders, start with the length of the shoe '
        '(makes tangential line to arc after bend). '
        'This is the minimum straight section required after the last bend.'
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
        'Optional notes about this die (material compatibility, special instructions, etc.)'
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
    name_input = adsk.core.StringValueCommandInput.cast(inputs.itemById('die_name'))
    tube_od_input = adsk.core.ValueCommandInput.cast(inputs.itemById('tube_od'))
    clr_input = adsk.core.ValueCommandInput.cast(inputs.itemById('clr'))
    offset_input = adsk.core.ValueCommandInput.cast(inputs.itemById('die_offset'))
    min_tail_input = adsk.core.ValueCommandInput.cast(inputs.itemById('min_tail'))
    notes_input = adsk.core.TextBoxCommandInput.cast(  # type: ignore[attr-defined]
        inputs.itemById('notes')
    )

    if (
        not name_input
        or not tube_od_input
        or not clr_input
        or not offset_input
        or not min_tail_input
        or not notes_input
    ):
        return

    name = name_input.value.strip()
    tube_od = tube_od_input.value  # Already in cm from ValueInput
    clr = clr_input.value
    offset = offset_input.value
    min_tail = min_tail_input.value
    notes = notes_input.text

    # Validate
    app = adsk.core.Application.get()
    ui = app.userInterface

    if not name:
        ui.messageBox('Name cannot be empty.', 'Invalid Input')
        args.isValidResult = False  # type: ignore[attr-defined]
        return

    try:
        validate_die_values(tube_od=tube_od, clr=clr, offset=offset, min_tail=min_tail)
    except ValueError as e:
        ui.messageBox(str(e), 'Invalid Input')
        args.isValidResult = False  # type: ignore[attr-defined]
        return

    # Create result and call callback
    result = DieInput(
        name=name,
        tube_od=tube_od,
        clr=clr,
        offset=offset,
        min_tail=min_tail,
        notes=notes,
    )

    if _on_complete:
        _on_complete(result)

    # Request Manage Benders dialog to reopen after this dialog closes
    request_relaunch()


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when dialog closes."""
    global local_handlers, _context, _on_complete

    local_handlers = []
    _context = None
    _on_complete = None
