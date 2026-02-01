"""Dialog launcher for material/compensation edit dialogs.

This module provides convenience functions to launch the form dialogs
with context and callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

from ...models import UnitConfig
from .dialog_contexts import EditMaterialContext
from .input_dialogs import MaterialInput
from . import edit_material_dialog


def launch_material_dialog(
    context: EditMaterialContext,
    units: UnitConfig,
    on_complete: Callable[[MaterialInput | None], None],
) -> None:
    """Launch the material edit dialog.

    Args:
        context: Pre-populated values for the form
        units: Unit configuration for display
        on_complete: Callback with result (None if cancelled)
    """
    edit_material_dialog.set_context(context, units, on_complete)
    edit_material_dialog.launch()


def register_dialog_commands() -> None:
    """Register hidden dialog commands. Call from main entry start()."""
    edit_material_dialog.register_command()


def unregister_dialog_commands() -> None:
    """Unregister dialog commands. Call from main entry stop()."""
    edit_material_dialog.unregister_command()
