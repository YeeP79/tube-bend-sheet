"""Python-JavaScript bridge for BrowserCommandInput communication.

This module provides type-safe handling of messages between the Python
add-in and the HTML material tree view component.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    import adsk.core

from ...lib import fusionAddInUtils as futil
from ...models import UnitConfig
from ...models.material import Material


# Action types for incoming messages (JS -> Python)
IncomingAction = Literal[
    'requestMaterials',
    'addMaterial',
    'editMaterial',
    'deleteMaterial',
    'manageCompensation',
]

# Action types for outgoing messages (Python -> JS)
OutgoingAction = Literal[
    'loadMaterials',
    'updateMaterial',
    'addMaterialToList',
    'removeMaterial',
]


class MaterialDisplayDict(TypedDict):
    """Type-safe dict for material display data sent to HTML."""

    id: str
    name: str
    tube_od: float
    batch: str
    notes: str
    tube_od_display: str  # Formatted display string with units


@dataclass(slots=True)
class HTMLMessage:
    """Parsed message from JavaScript."""

    action: str
    material_id: str | None = None
    die_id: str | None = None

    def __repr__(self) -> str:
        parts = [f"action={self.action!r}"]
        if self.material_id:
            parts.append(f"material_id={self.material_id!r}")
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
            material_id=data.get('material_id'),
            die_id=data.get('die_id'),
        )

    def _format_value(self, value_cm: float) -> str:
        """Format a value from cm to display units with symbol."""
        if self._units is None:
            return f"{value_cm:.2f}"
        display_value = value_cm * self._units.cm_to_unit
        return f"{display_value:.4f}{self._units.unit_symbol}"

    def _format_material_for_display(self, material: Material) -> MaterialDisplayDict:
        """
        Format a material for HTML display with converted units.

        Args:
            material: The material to format

        Returns:
            Type-safe dict with material data plus formatted display strings
        """
        return MaterialDisplayDict(
            id=material.id,
            name=material.name,
            tube_od=material.tube_od,
            batch=material.batch,
            notes=material.notes,
            tube_od_display=self._format_value(material.tube_od),
        )

    def send_materials(self, materials: list[Material]) -> None:
        """
        Send the full material list to the HTML view.

        Args:
            materials: List of all materials to display
        """
        formatted = [self._format_material_for_display(m) for m in materials]
        data = json.dumps(formatted)
        self._browser_input.sendInfoToHTML('loadMaterials', data)

    def send_material_added(self, material: Material) -> None:
        """
        Notify HTML that a new material was added.

        Args:
            material: The newly created material
        """
        data = json.dumps(self._format_material_for_display(material))
        self._browser_input.sendInfoToHTML('addMaterialToList', data)

    def send_material_update(self, material: Material) -> None:
        """
        Send a single material update to the HTML view.

        Args:
            material: The updated material
        """
        data = json.dumps(self._format_material_for_display(material))
        self._browser_input.sendInfoToHTML('updateMaterial', data)

    def send_material_removed(self, material_id: str) -> None:
        """
        Notify HTML that a material was removed.

        Args:
            material_id: ID of the removed material
        """
        self._browser_input.sendInfoToHTML('removeMaterial', material_id)
