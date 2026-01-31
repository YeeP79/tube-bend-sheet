"""Dialog relaunch service for Manage Benders command.

Wraps CustomEventService for the specific use case of reopening
the Manage Benders dialog after an edit dialog closes.
"""

from __future__ import annotations

import adsk.core

from ...lib.custom_events import CustomEventService
from ... import config

# Event identity
RELAUNCH_EVENT_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_relaunchManageBenders'

# Module state
_event_service: CustomEventService | None = None
_target_command_id: str | None = None


def _execute_relaunch() -> None:
    """Callback invoked when relaunch event fires."""
    if not _target_command_id:
        return

    app = adsk.core.Application.get()
    ui = app.userInterface

    cmd_def = ui.commandDefinitions.itemById(_target_command_id)
    if cmd_def:
        cmd_def.execute()  # type: ignore[attr-defined]


def start(target_command_id: str) -> None:
    """Register the relaunch event. Call from entry.start().

    Args:
        target_command_id: The command ID to relaunch (Manage Benders CMD_ID)
    """
    global _event_service, _target_command_id

    _target_command_id = target_command_id
    _event_service = CustomEventService()
    _event_service.register(RELAUNCH_EVENT_ID, callback=_execute_relaunch)


def stop() -> None:
    """Cleanup the event service. Call from entry.stop()."""
    global _event_service, _target_command_id

    if _event_service:
        _event_service.stop()

    _event_service = None
    _target_command_id = None


def request_relaunch() -> None:
    """Request the Manage Benders dialog to reopen.

    Call from edit dialog's command_execute handler.
    The event fires asynchronously after the command completes.
    """
    if _event_service:
        _event_service.fire(RELAUNCH_EVENT_ID)
