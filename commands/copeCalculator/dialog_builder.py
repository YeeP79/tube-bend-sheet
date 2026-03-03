"""Dialog builder for cope calculator command.

Creates the command dialog inputs for selecting tube bodies and
configuring the cope calculation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import adsk.core
    import adsk.fusion


def build_dialog(inputs: adsk.core.CommandInputs) -> None:
    """
    Build the cope calculator command dialog.

    Args:
        inputs: The command's input collection
    """
    # Selection input: incoming tube body
    incoming_sel = inputs.addSelectionInput(
        'incoming_tube', 'Incoming Tube',
        'Select the tube body to be coped'
    )
    incoming_sel.addSelectionFilter('SolidBodies')
    incoming_sel.setSelectionLimits(1, 1)

    # Selection input: receiving tube bodies
    receiving_sel = inputs.addSelectionInput(
        'receiving_tubes', 'Receiving Tubes',
        'Select tube bodies at the target node'
    )
    receiving_sel.addSelectionFilter('SolidBodies')
    receiving_sel.setSelectionLimits(1, 0)  # 1 minimum, unlimited maximum

    # Node label (optional)
    inputs.addStringValueInput('node_label', 'Node Label', '')

    # Validation status (read-only text)
    validation_text = inputs.addTextBoxCommandInput(
        'validation_status', 'Status',
        'Select tubes to begin', 1, True
    )
    validation_text.isFullWidth = True
