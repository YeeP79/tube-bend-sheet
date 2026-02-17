"""Dialog launcher for tube/compensation edit dialogs.

This module provides convenience functions to launch the form dialogs
with context and callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

from ...models import UnitConfig
from .dialog_contexts import EditTubeContext
from .input_dialogs import TubeInput
from . import edit_tube_dialog


def launch_tube_dialog(
    context: EditTubeContext,
    units: UnitConfig,
    on_complete: Callable[[TubeInput | None], None],
) -> None:
    """Launch the tube edit dialog.

    Args:
        context: Pre-populated values for the form
        units: Unit configuration for display
        on_complete: Callback with result (None if cancelled)
    """
    edit_tube_dialog.set_context(context, units, on_complete)
    edit_tube_dialog.launch()


def register_dialog_commands() -> None:
    """Register hidden dialog commands. Call from main entry start()."""
    edit_tube_dialog.register_command()


def unregister_dialog_commands() -> None:
    """Unregister dialog commands. Call from main entry stop()."""
    edit_tube_dialog.unregister_command()
