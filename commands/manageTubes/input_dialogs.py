"""Input dialog helpers for tube management.

This module provides reusable functions for collecting tube
data from the user via Fusion's input dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass

import adsk.core

from ...models import UnitConfig


@dataclass(slots=True)
class TubeInput:
    """Data collected from tube input dialogs."""

    name: str
    tube_od: float  # In internal units (cm)
    wall_thickness: float = 0.0  # In internal units (cm)
    material_type: str = ""
    batch: str = ""
    notes: str = ""


@dataclass(slots=True)
class CompensationPointInput:
    """Data collected for a compensation data point."""

    readout_angle: float  # Degrees
    measured_angle: float  # Degrees


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


def _get_angle_input(
    ui: adsk.core.UserInterface,
    prompt: str,
    title: str,
    default: str,
) -> tuple[float, bool]:
    """
    Show input dialog for an angle value in degrees.

    Args:
        ui: Fusion UserInterface
        prompt: Dialog prompt text
        title: Dialog title
        default: Default value string

    Returns:
        Tuple of (angle in degrees, cancelled flag)
    """
    ret_value, cancelled = ui.inputBox(prompt, title, default)
    if cancelled:
        return 0.0, True

    try:
        angle = float(ret_value)
        return angle, False
    except ValueError:
        return 0.0, True


def get_tube_input(
    ui: adsk.core.UserInterface,
    units: UnitConfig,
    current_name: str = "New Tube",
    current_tube_od: float | None = None,
    current_batch: str = "",
    current_notes: str = "",
) -> TubeInput | None:
    """
    Show input dialogs to collect tube data.

    Args:
        ui: Fusion UserInterface
        units: Unit configuration for display/conversion
        current_name: Default name (for editing)
        current_tube_od: Current tube OD in cm (for editing), None for new
        current_batch: Current batch number (for editing)
        current_notes: Current notes (for editing)

    Returns:
        TubeInput with collected data, or None if cancelled
    """
    # Get tube name
    ret_value, cancelled = ui.inputBox(
        "Enter tube name (e.g., 'DOM 1020 1.75x0.120'):",
        "Tube Name",
        current_name,
    )
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

    # Get batch number (optional)
    ret_value, cancelled = ui.inputBox(
        "Enter batch/lot number (optional):",
        "Batch Number",
        current_batch,
    )
    if cancelled:
        return None
    batch = ret_value.strip()

    return TubeInput(name=name, tube_od=tube_od, batch=batch, notes=current_notes)


def get_compensation_point_input(
    ui: adsk.core.UserInterface,
) -> CompensationPointInput | None:
    """
    Show input dialogs to collect a compensation data point.

    Asks for:
    1. Readout angle - what bender readout showed when you stopped
    2. Measured angle - actual angle measured after removing from bender

    Returns:
        CompensationPointInput with collected data, or None if cancelled
    """
    # Get readout angle
    readout_angle, cancelled = _get_angle_input(
        ui,
        "Enter readout angle (what bender showed when you stopped):",
        "Readout Angle (degrees)",
        "90.0",
    )
    if cancelled:
        return None

    if readout_angle <= 0:
        ui.messageBox("Readout angle must be positive.", "Invalid Input")
        return None

    # Get measured angle
    measured_angle, cancelled = _get_angle_input(
        ui,
        "Enter measured angle (actual angle after removing from bender):",
        "Measured Angle (degrees)",
        str(readout_angle - 5.0),  # Suggest slightly less than readout
    )
    if cancelled:
        return None

    if measured_angle <= 0:
        ui.messageBox("Measured angle must be positive.", "Invalid Input")
        return None

    if measured_angle >= readout_angle:
        ui.messageBox(
            "Measured angle must be less than readout angle.\n\n"
            "The tube springs back after bending, so the actual measured angle "
            "is always less than what the bender readout showed.",
            "Invalid Input",
        )
        return None

    return CompensationPointInput(readout_angle=readout_angle, measured_angle=measured_angle)


def confirm_delete(
    ui: adsk.core.UserInterface,
    item_type: str,
    item_name: str,
    include_children: bool = False,
    custom_message: str | None = None,
) -> bool:
    """
    Show a confirmation dialog for deletion.

    Args:
        ui: Fusion UserInterface
        item_type: Type of item being deleted (e.g., "tube", "compensation data")
        item_name: Name of item being deleted
        include_children: Whether to mention child items in message
        custom_message: Optional custom message to display instead of default

    Returns:
        True if user confirmed deletion, False otherwise
    """
    if custom_message:
        message = custom_message
    elif include_children:
        message = f'Delete {item_type} "{item_name}" and all its compensation data?'
    else:
        message = f'Delete {item_type} "{item_name}"?'

    result = ui.messageBox(
        message,
        "Confirm Delete",
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
    )

    return result == adsk.core.DialogResults.DialogYes


def confirm_clear_compensation(
    ui: adsk.core.UserInterface,
    die_name: str,
    tube_name: str,
) -> bool:
    """
    Show a confirmation dialog for clearing all compensation data.

    Args:
        ui: Fusion UserInterface
        die_name: Name of the die
        tube_name: Name of the tube

    Returns:
        True if user confirmed, False otherwise
    """
    message = (
        f"Clear all compensation data for:\n"
        f"  Die: {die_name}\n"
        f"  Tube: {tube_name}\n\n"
        f"This will remove all recorded bend measurements.\n\n"
        f"You should do this if you've recalibrated your bender's "
        f"angle readout, as previous data is no longer valid.\n\n"
        f"This cannot be undone."
    )

    result = ui.messageBox(
        message,
        "Clear Compensation Data",
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
    )

    return result == adsk.core.DialogResults.DialogYes
