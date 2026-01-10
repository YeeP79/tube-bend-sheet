"""Python-JavaScript bridge for BrowserCommandInput communication.

This module provides type-safe handling of messages between the Python
add-in and the HTML tree view component.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import adsk.core

from ...lib import fusionAddInUtils as futil
from ...models import Bender, UnitConfig


# Action types for incoming messages (JS -> Python)
IncomingAction = Literal[
    'requestBenders',
    'addBender',
    'editBender',
    'deleteBender',
    'addDie',
    'editDie',
    'deleteDie',
]

# Action types for outgoing messages (Python -> JS)
OutgoingAction = Literal[
    'loadBenders',
    'updateBender',
    'addBenderToList',
    'removeBender',
    'removeDie',
]


@dataclass(slots=True)
class HTMLMessage:
    """Parsed message from JavaScript."""

    action: str
    bender_id: str | None = None
    die_id: str | None = None

    def __repr__(self) -> str:
        parts = [f"action={self.action!r}"]
        if self.bender_id:
            parts.append(f"bender_id={self.bender_id!r}")
        if self.die_id:
            parts.append(f"die_id={self.die_id!r}")
        return f"HTMLMessage({', '.join(parts)})"


class HTMLBridge:
    """Handles Python-JavaScript communication for BrowserCommandInput.

    This class provides type-safe methods for:
    - Parsing incoming messages from JavaScript
    - Sending data updates to the HTML tree view
    - Formatting values with proper unit conversion
    """

    def __init__(
        self,
        browser_input: 'adsk.core.BrowserCommandInput',
        units: UnitConfig | None = None
    ) -> None:
        """
        Initialize the bridge.

        Args:
            browser_input: The BrowserCommandInput to communicate with
            units: Unit configuration for formatting display values
        """
        self._browser_input = browser_input
        self._units = units

    def set_units(self, units: UnitConfig) -> None:
        """Update the unit configuration."""
        self._units = units

    def parse_message(self, args: 'adsk.core.HTMLEventArgs') -> HTMLMessage:
        """
        Parse an incoming HTML event into a typed message.

        Args:
            args: The HTMLEventArgs from the incomingFromHTML event

        Returns:
            Parsed HTMLMessage with action and optional IDs
        """
        action = args.action
        data: dict[str, str] = {}

        if args.data:
            try:
                parsed = json.loads(args.data)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    futil.log(
                        f'HTMLBridge: Expected dict, got {type(parsed).__name__}'
                    )
            except json.JSONDecodeError as e:
                futil.log(f'HTMLBridge: JSON decode error: {e}')

        return HTMLMessage(
            action=action,
            bender_id=data.get('bender_id'),
            die_id=data.get('die_id'),
        )

    def _format_value(self, value_cm: float) -> str:
        """Format a value from cm to display units with symbol."""
        if self._units is None:
            return f"{value_cm:.2f}"
        display_value = value_cm * self._units.cm_to_unit
        return f"{display_value:.2f}{self._units.unit_symbol}"

    def _format_bender_for_display(self, bender: Bender) -> dict[str, Any]:
        """
        Format a bender for HTML display with converted units.

        Args:
            bender: The bender to format

        Returns:
            Dict with bender data plus formatted display strings
        """
        # Convert TypedDict to regular dict so we can add display fields
        bender_dict = bender.to_dict()
        data: dict[str, Any] = dict(bender_dict)
        # Add formatted display values
        data['min_grip_display'] = self._format_value(bender.min_grip)

        # Format each die - convert TypedDicts to regular dicts
        formatted_dies: list[dict[str, Any]] = []
        for i, die in enumerate(bender.dies):
            die_data: dict[str, Any] = dict(bender_dict['dies'][i])
            die_data['clr_display'] = self._format_value(die.clr)
            die_data['tube_od_display'] = self._format_value(die.tube_od)
            die_data['offset_display'] = self._format_value(die.offset)
            die_data['min_tail_display'] = self._format_value(die.min_tail)
            formatted_dies.append(die_data)
        data['dies'] = formatted_dies

        return data

    def send_benders(self, benders: list[Bender]) -> None:
        """
        Send the full bender list to the HTML view.

        Args:
            benders: List of all benders to display
        """
        formatted = [self._format_bender_for_display(b) for b in benders]
        data = json.dumps(formatted)
        self._browser_input.sendInfoToHTML('loadBenders', data)

    def send_bender_added(self, bender: Bender) -> None:
        """
        Notify HTML that a new bender was added.

        Args:
            bender: The newly created bender
        """
        data = json.dumps(self._format_bender_for_display(bender))
        self._browser_input.sendInfoToHTML('addBenderToList', data)

    def send_bender_update(self, bender: Bender) -> None:
        """
        Send a single bender update to the HTML view.

        Args:
            bender: The updated bender
        """
        data = json.dumps(self._format_bender_for_display(bender))
        self._browser_input.sendInfoToHTML('updateBender', data)

    def send_bender_removed(self, bender_id: str) -> None:
        """
        Notify HTML that a bender was removed.

        Args:
            bender_id: ID of the removed bender
        """
        self._browser_input.sendInfoToHTML('removeBender', bender_id)

    def send_die_removed(self, bender_id: str, die_id: str) -> None:
        """
        Notify HTML that a die was removed.

        Args:
            bender_id: ID of the bender containing the die
            die_id: ID of the removed die
        """
        data = json.dumps({'bender_id': bender_id, 'die_id': die_id})
        self._browser_input.sendInfoToHTML('removeDie', data)
