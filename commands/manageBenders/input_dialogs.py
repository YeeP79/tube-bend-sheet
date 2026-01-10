"""Input dialog helpers for bender/die management.

This module provides reusable functions for collecting bender and die
data from the user via Fusion's input dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass

import adsk.core

from ...models import UnitConfig


@dataclass(slots=True)
class BenderInput:
    """Data collected from bender input dialogs."""

    name: str
    min_grip: float  # In internal units (cm)


@dataclass(slots=True)
class DieInput:
    """Data collected from die input dialogs."""

    name: str
    tube_od: float  # In internal units (cm)
    clr: float  # In internal units (cm)
    offset: float  # In internal units (cm)
    min_tail: float  # In internal units (cm)


def _get_float_input(
    ui: adsk.core.UserInterface,
    prompt: str,
    title: str,
    default: str,
    units: UnitConfig,
) -> tuple[float, bool]:
    """
    Show input dialog for a float value and convert from display to internal units.

    Args:
        ui: Fusion UserInterface
        prompt: Dialog prompt text
        title: Dialog title
        default: Default value string
        units: Unit configuration for conversion

    Returns:
        Tuple of (value in cm, cancelled flag)
    """
    ret_value, cancelled = ui.inputBox(prompt, title, default)
    if cancelled:
        return 0.0, True

    try:
        display_value = float(ret_value)
        internal_value = display_value / units.cm_to_unit
        return internal_value, False
    except ValueError:
        return 0.0, True


def get_bender_input(
    ui: adsk.core.UserInterface,
    units: UnitConfig,
    current_name: str = "New Bender",
    current_min_grip: float | None = None,
) -> BenderInput | None:
    """
    Show input dialogs to collect bender data.

    Args:
        ui: Fusion UserInterface
        units: Unit configuration for display/conversion
        current_name: Default name (for editing)
        current_min_grip: Current min grip in cm (for editing), None for new

    Returns:
        BenderInput with collected data, or None if cancelled
    """
    # Get bender name
    ret_value, cancelled = ui.inputBox("Enter bender name:", "Bender Name", current_name)
    if cancelled or not ret_value.strip():
        return None
    name = ret_value.strip()

    # Get min grip
    default_grip = "6.0"
    if current_min_grip is not None:
        default_grip = f"{current_min_grip * units.cm_to_unit:.2f}"

    min_grip, cancelled = _get_float_input(
        ui,
        f"Enter minimum grip length ({units.unit_symbol}):",
        "Minimum Grip",
        default_grip,
        units,
    )
    if cancelled:
        return None

    if min_grip <= 0:
        ui.messageBox("Minimum grip must be a positive value.", "Invalid Input")
        return None

    return BenderInput(name=name, min_grip=min_grip)


def get_die_input(
    ui: adsk.core.UserInterface,
    units: UnitConfig,
    current_name: str = "New Die",
    current_tube_od: float | None = None,
    current_clr: float | None = None,
    current_offset: float | None = None,
    current_min_tail: float | None = None,
) -> DieInput | None:
    """
    Show input dialogs to collect die data.

    Args:
        ui: Fusion UserInterface
        units: Unit configuration for display/conversion
        current_name: Default name (for editing)
        current_tube_od: Current tube OD in cm (for editing), None for new
        current_clr: Current CLR in cm (for editing), None for new
        current_offset: Current offset in cm (for editing), None for new
        current_min_tail: Current min tail in cm (for editing), None for new

    Returns:
        DieInput with collected data, or None if cancelled
    """
    # Get die name
    ret_value, cancelled = ui.inputBox("Enter die name:", "Die Name", current_name)
    if cancelled or not ret_value.strip():
        return None
    name = ret_value.strip()

    # Get tube OD
    default_od = "1.75" if current_tube_od is None else f"{current_tube_od * units.cm_to_unit:.4f}"
    tube_od, cancelled = _get_float_input(
        ui,
        f"Enter tube OD ({units.unit_symbol}):",
        "Tube OD",
        default_od,
        units,
    )
    if cancelled:
        return None

    if tube_od <= 0:
        ui.messageBox("Tube OD must be a positive value.", "Invalid Input")
        return None

    # Get CLR
    default_clr = "5.5" if current_clr is None else f"{current_clr * units.cm_to_unit:.4f}"
    clr, cancelled = _get_float_input(
        ui,
        f"Enter CLR ({units.unit_symbol}):",
        "CLR",
        default_clr,
        units,
    )
    if cancelled:
        return None

    if clr <= 0:
        ui.messageBox("CLR must be a positive value.", "Invalid Input")
        return None

    # Get die offset
    default_offset = "0.6875" if current_offset is None else f"{current_offset * units.cm_to_unit:.4f}"
    offset, cancelled = _get_float_input(
        ui,
        f"Enter die offset ({units.unit_symbol}):",
        "Die Offset",
        default_offset,
        units,
    )
    if cancelled:
        return None

    if offset < 0:
        ui.messageBox("Die offset cannot be negative.", "Invalid Input")
        return None

    # Get minimum tail length
    default_min_tail = "2.0" if current_min_tail is None else f"{current_min_tail * units.cm_to_unit:.4f}"
    min_tail, cancelled = _get_float_input(
        ui,
        f"Enter minimum tail length ({units.unit_symbol}):",
        "Minimum Tail",
        default_min_tail,
        units,
    )
    if cancelled:
        return None

    if min_tail < 0:
        ui.messageBox("Minimum tail length cannot be negative.", "Invalid Input")
        return None

    return DieInput(name=name, tube_od=tube_od, clr=clr, offset=offset, min_tail=min_tail)


def confirm_delete(
    ui: adsk.core.UserInterface,
    item_type: str,
    item_name: str,
    include_children: bool = False,
) -> bool:
    """
    Show a confirmation dialog for deletion.

    Args:
        ui: Fusion UserInterface
        item_type: Type of item being deleted (e.g., "bender", "die")
        item_name: Name of item being deleted
        include_children: Whether to mention child items in message

    Returns:
        True if user confirmed deletion, False otherwise
    """
    if include_children:
        message = f'Delete {item_type} "{item_name}" and all its dies?'
    else:
        message = f'Delete {item_type} "{item_name}"?'

    result = ui.messageBox(
        message,
        "Confirm Delete",
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
    )

    return result == adsk.core.DialogResults.DialogYes
