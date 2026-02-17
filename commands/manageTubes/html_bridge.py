"""Python-JavaScript bridge for BrowserCommandInput communication.

This module provides type-safe handling of messages between the Python
add-in and the HTML tube tree view component.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    import adsk.core

from ...lib import fusionAddInUtils as futil
from ...models import UnitConfig
from ...models.tube import Tube


# Action types for incoming messages (JS -> Python)
IncomingAction = Literal[
    'requestTubes',
    'addTube',
    'editTube',
    'deleteTube',
    'manageCompensation',
]

# Action types for outgoing messages (Python -> JS)
OutgoingAction = Literal[
    'loadTubes',
    'updateTube',
    'addTubeToList',
    'removeTube',
]


class TubeDisplayDict(TypedDict):
    """Type-safe dict for tube display data sent to HTML."""

    id: str
    name: str
    tube_od: float
    wall_thickness: float
    wall_thickness_display: str
    material_type: str
    batch: str
    notes: str
    tube_od_display: str  # Formatted display string with units


@dataclass(slots=True)
class HTMLMessage:
    """Parsed message from JavaScript."""

    action: str
    tube_id: str | None = None
    die_id: str | None = None

    def __repr__(self) -> str:
        parts = [f"action={self.action!r}"]
        if self.tube_id:
            parts.append(f"tube_id={self.tube_id!r}")
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
            tube_id=data.get('tube_id'),
            die_id=data.get('die_id'),
        )

    def _format_value(self, value_cm: float) -> str:
        """Format a value from cm to display units with symbol."""
        if self._units is None:
            return f"{value_cm:.2f}"
        display_value = value_cm * self._units.cm_to_unit
        return f"{display_value:.4f}{self._units.unit_symbol}"

    def _format_tube_for_display(self, tube: Tube) -> TubeDisplayDict:
        """
        Format a tube for HTML display with converted units.

        Args:
            tube: The tube to format

        Returns:
            Type-safe dict with tube data plus formatted display strings
        """
        wall_display = ""
        if tube.wall_thickness > 0:
            wall_display = self._format_value(tube.wall_thickness)

        return TubeDisplayDict(
            id=tube.id,
            name=tube.name,
            tube_od=tube.tube_od,
            wall_thickness=tube.wall_thickness,
            wall_thickness_display=wall_display,
            material_type=tube.material_type,
            batch=tube.batch,
            notes=tube.notes,
            tube_od_display=self._format_value(tube.tube_od),
        )

    def send_tubes(self, tubes: list[Tube]) -> None:
        """
        Send the full tube list to the HTML view.

        Args:
            tubes: List of all tubes to display
        """
        formatted = [self._format_tube_for_display(t) for t in tubes]
        data = json.dumps(formatted)
        self._browser_input.sendInfoToHTML('loadTubes', data)

    def send_tube_added(self, tube: Tube) -> None:
        """
        Notify HTML that a new tube was added.

        Args:
            tube: The newly created tube
        """
        data = json.dumps(self._format_tube_for_display(tube))
        self._browser_input.sendInfoToHTML('addTubeToList', data)

    def send_tube_update(self, tube: Tube) -> None:
        """
        Send a single tube update to the HTML view.

        Args:
            tube: The updated tube
        """
        data = json.dumps(self._format_tube_for_display(tube))
        self._browser_input.sendInfoToHTML('updateTube', data)

    def send_tube_removed(self, tube_id: str) -> None:
        """
        Notify HTML that a tube was removed.

        Args:
            tube_id: ID of the removed tube
        """
        self._browser_input.sendInfoToHTML('removeTube', tube_id)
