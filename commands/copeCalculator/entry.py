"""Cope Calculator command — calculates notcher settings and generates SVG wrap templates.

This command analyzes selected solid tube bodies to calculate cope angles,
rotation marks, and generates printable 1:1 scale SVG templates for tube
coping operations at multi-tube nodes.
"""

from __future__ import annotations

import os
import time

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ... import config
from ...models import UnitConfig
from ...models.cope_data import CopeResult, ReceivingTube

from ...core.cope_math import calculate_cope
from ...core.cope_template import generate_cope_svg

from .body_extraction import extract_bend_reference, extract_cylinder_axis, identify_cope_end
from .build_order import validate_receiving_bodies
from .dialog_builder import build_dialog
from .results_display import format_results_html

app: adsk.core.Application = adsk.core.Application.get()
ui: adsk.core.UserInterface = app.userInterface

# Command identity
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_copeCalculator'
CMD_NAME = 'Cope Calculator'
CMD_DESCRIPTION = 'Calculate cope angles and generate wrap templates for tube coping'
IS_PROMOTED = True

# UI placement
WORKSPACE_ID = config.WORKSPACE_ID
PANEL_ID = config.PANEL_ID

# Resource location for command icons
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Handler list for lifetime management
local_handlers: list[futil.FusionHandler] = []


def start() -> None:
    """Initialize and register the command."""
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )

    futil.add_handler(cmd_def.commandCreated, command_created)

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
    global local_handlers

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

    local_handlers = []


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Set up the command dialog when the command is created."""
    global local_handlers
    local_handlers = []
    futil.log(f'{CMD_NAME} Command Created Event')

    cmd = args.command

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox('No active design. Please open a design first.', 'Error')
        return

    # Build dialog inputs
    build_dialog(cmd.commandInputs)

    # Dialog settings
    cmd.setDialogInitialSize(450, 500)
    cmd.isOKButtonVisible = True
    cmd.okButtonText = 'Calculate & Generate Template'

    # Connect handlers
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    """Handle input changes — update validation status."""
    try:
        inputs = args.inputs

        incoming_sel = adsk.core.SelectionCommandInput.cast(inputs.itemById('incoming_tube'))
        receiving_sel = adsk.core.SelectionCommandInput.cast(inputs.itemById('receiving_tubes'))
        status_text = adsk.core.TextBoxCommandInput.cast(inputs.itemById('validation_status'))

        if not incoming_sel or not receiving_sel or not status_text:
            return

        incoming_count = incoming_sel.selectionCount
        receiving_count = receiving_sel.selectionCount

        if incoming_count == 0:
            status_text.text = 'Select the incoming tube body'
        elif receiving_count == 0:
            status_text.text = 'Select one or more receiving tube bodies'
        else:
            # Validate receiving bodies
            incoming_body = adsk.fusion.BRepBody.cast(incoming_sel.selection(0).entity)
            receiving_bodies = []
            for i in range(receiving_count):
                body = adsk.fusion.BRepBody.cast(receiving_sel.selection(i).entity)
                if body:
                    receiving_bodies.append(body)

            if incoming_body and receiving_bodies:
                results = validate_receiving_bodies(incoming_body, receiving_bodies)
                all_valid = all(r.is_valid for r in results)

                if all_valid:
                    status_text.text = f'Ready — {len(receiving_bodies)} receiving tube(s) validated'
                else:
                    warnings = [r.message for r in results if not r.is_valid]
                    status_text.text = '<br/>'.join(warnings)
            else:
                status_text.text = 'Invalid selection'

    except:
        futil.handle_error('command_input_changed')


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Execute the cope calculation and generate SVG template."""
    try:
        futil.log(f'{CMD_NAME} Command Execute Event')

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('No active design.', 'Error')
            return

        try:
            units = UnitConfig.from_design(design)
        except ValueError as e:
            ui.messageBox(str(e), 'Unsupported Units')
            return

        incoming_body, receiving_bodies, node_label = _extract_selections(args.command.commandInputs)
        if incoming_body is None or not receiving_bodies:
            return

        _validate_build_order(incoming_body, receiving_bodies)

        result, od1, has_bends = _compute_cope(incoming_body, receiving_bodies, units)

        svg_path = _generate_and_save_template(result, od1, incoming_body.name, node_label, has_bends)

        results_html = format_results_html(result)
        results_html += f'<br/>Template saved to:<br/>{svg_path}'
        ui.messageBox(results_html, f'Cope Calculator — {incoming_body.name}')

    except ValueError as e:
        ui.messageBox(str(e), 'Cope Calculator Error')
    except:
        futil.handle_error('command_execute')


def _extract_selections(
    inputs: adsk.core.CommandInputs,
) -> tuple[adsk.fusion.BRepBody | None, list[adsk.fusion.BRepBody], str]:
    """Extract and validate body selections from command inputs.

    Returns:
        Tuple of (incoming_body, receiving_bodies, node_label).
        incoming_body is None if selection is invalid; an error message
        is shown to the user.
    """
    incoming_sel = adsk.core.SelectionCommandInput.cast(inputs.itemById('incoming_tube'))
    receiving_sel = adsk.core.SelectionCommandInput.cast(inputs.itemById('receiving_tubes'))
    node_label_input = adsk.core.StringValueCommandInput.cast(inputs.itemById('node_label'))

    if not incoming_sel or incoming_sel.selectionCount == 0:
        ui.messageBox('Please select the incoming tube body.', 'Error')
        return None, [], ''

    if not receiving_sel or receiving_sel.selectionCount == 0:
        ui.messageBox('Please select at least one receiving tube body.', 'Error')
        return None, [], ''

    incoming_body = adsk.fusion.BRepBody.cast(incoming_sel.selection(0).entity)
    if not incoming_body:
        ui.messageBox('Invalid incoming tube selection.', 'Error')
        return None, [], ''

    receiving_bodies: list[adsk.fusion.BRepBody] = []
    for i in range(receiving_sel.selectionCount):
        body = adsk.fusion.BRepBody.cast(receiving_sel.selection(i).entity)
        if body:
            receiving_bodies.append(body)

    if not receiving_bodies:
        ui.messageBox('No valid receiving tube bodies selected.', 'Error')
        return None, [], ''

    node_label = node_label_input.value if node_label_input else ''
    return incoming_body, receiving_bodies, node_label


def _validate_build_order(
    incoming_body: adsk.fusion.BRepBody,
    receiving_bodies: list[adsk.fusion.BRepBody],
) -> None:
    """Validate that receiving tubes are already coped.

    Raises:
        ValueError: If any receiving tube fails build order validation.
    """
    validation_results = validate_receiving_bodies(incoming_body, receiving_bodies)
    invalid = [r for r in validation_results if not r.is_valid]
    if invalid:
        msg = 'Build order validation failed:\n\n'
        msg += '\n'.join(f'• {r.message}' for r in invalid)
        msg += '\n\nCope the receiving tubes first.'
        raise ValueError(msg)


def _compute_cope(
    incoming_body: adsk.fusion.BRepBody,
    receiving_bodies: list[adsk.fusion.BRepBody],
    units: UnitConfig,
) -> tuple[CopeResult, float, bool]:
    """Extract geometry and run the cope calculation.

    Returns:
        Tuple of (result, od1_display_units, has_bends).
    """
    cm_to_unit = units.cm_to_unit

    v1, od1_cm = extract_cylinder_axis(incoming_body)
    od1 = od1_cm * cm_to_unit

    cope_end = identify_cope_end(incoming_body, receiving_bodies)
    ref_vector, _ref_desc = extract_bend_reference(incoming_body, cope_end)
    has_bends = ref_vector is not None

    receiving: list[ReceivingTube] = []
    for body in receiving_bodies:
        v_r, od_r_cm = extract_cylinder_axis(body)
        receiving.append(ReceivingTube(
            vector=v_r,
            od=od_r_cm * cm_to_unit,
            name=body.name,
        ))

    result = calculate_cope(
        v1=v1,
        od1=od1,
        receiving_tubes=receiving,
        reference_vector=ref_vector,
    )

    return result, od1, has_bends


def _generate_and_save_template(
    result: CopeResult,
    od1: float,
    tube_name: str,
    node_label: str,
    has_bends: bool,
) -> str:
    """Generate SVG template and save to desktop.

    Returns:
        Path to the saved SVG file.
    """
    svg_content = generate_cope_svg(
        result=result,
        od1=od1,
        tube_name=tube_name,
        node_label=node_label,
        has_bends=has_bends,
    )

    doc = app.activeDocument
    doc_name = doc.name if doc else 'untitled'
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    svg_filename = f'{doc_name}_cope_{tube_name}_{timestamp}.svg'

    save_dir = os.path.expanduser('~/Desktop')
    svg_path = os.path.join(save_dir, svg_filename)

    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)

    return svg_path


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Clean up when the command dialog is closed."""
    futil.log(f'{CMD_NAME} Command Destroy Event')
    global local_handlers
    local_handlers = []
