"""Dialog launcher for bender/die edit dialogs.

This module provides convenience functions to launch the form dialogs
with context and callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

from ...models import UnitConfig
from .dialog_contexts import EditBenderContext, EditDieContext
from .input_dialogs import BenderInput, DieInput
from . import edit_bender_dialog, edit_die_dialog


def launch_bender_dialog(
    context: EditBenderContext,
    units: UnitConfig,
    on_complete: Callable[[BenderInput | None], None],
) -> None:
    """Launch the bender edit dialog.

    Args:
        context: Pre-populated values for the form
        units: Unit configuration for display
        on_complete: Callback with result (None if cancelled)
    """
    edit_bender_dialog.set_context(context, units, on_complete)
    edit_bender_dialog.launch()


def launch_die_dialog(
    context: EditDieContext,
    units: UnitConfig,
    on_complete: Callable[[DieInput | None], None],
) -> None:
    """Launch the die edit dialog.

    Args:
        context: Pre-populated values for the form
        units: Unit configuration for display
        on_complete: Callback with result (None if cancelled)
    """
    edit_die_dialog.set_context(context, units, on_complete)
    edit_die_dialog.launch()


def register_dialog_commands() -> None:
    """Register hidden dialog commands. Call from main entry start()."""
    edit_bender_dialog.register_command()
    edit_die_dialog.register_command()


def unregister_dialog_commands() -> None:
    """Unregister dialog commands. Call from main entry stop()."""
    edit_bender_dialog.unregister_command()
    edit_die_dialog.unregister_command()
