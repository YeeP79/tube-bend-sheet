"""Selection validation orchestrator for Create Bend Sheet command.

This module orchestrates the validation workflow by delegating to specialized
classes for geometry extraction, path building, and direction normalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import adsk.core
import adsk.fusion

from ...core import PathElement
from ...models import UnitConfig
from .selection_extractor import extract_geometry
from .path_builder import build_path_from_geometry
from .path_direction import normalize_path_direction


@dataclass(slots=True)
class SelectionResult:
    """Result of validating and analyzing user selection.

    Contains all extracted geometry data needed for bend sheet generation.
    """

    is_valid: bool
    error_message: str | None = None

    # Raw geometry
    lines: list[adsk.fusion.SketchLine] = field(default_factory=list)
    arcs: list[adsk.fusion.SketchArc] = field(default_factory=list)

    # Ordered path
    ordered_path: list[PathElement] = field(default_factory=list)

    # Path properties
    first_entity: adsk.fusion.SketchEntity | None = None
    detected_clr: float = 0.0
    component_name: str = ""
    starts_with_arc: bool = False
    ends_with_arc: bool = False

    # Direction info
    start_point: tuple[float, float, float] | None = None
    end_point: tuple[float, float, float] | None = None
    primary_axis: str = ""
    travel_direction: str = ""
    opposite_direction: str = ""


class SelectionValidator:
    """Orchestrate selection validation for bend sheet generation.

    Coordinates the workflow between specialized components:
    - SelectionExtractor: Extracts lines and arcs from selections
    - PathBuilder: Builds and validates ordered path
    - PathDirectionNormalizer: Determines and normalizes travel direction
    """

    MIN_SELECTION_COUNT: int = 3

    def __init__(self, units: UnitConfig) -> None:
        """Initialize the validator.

        Args:
            units: Unit configuration for the design
        """
        self._units = units

    def validate_for_dialog(
        self,
        selections: adsk.core.Selections,
    ) -> SelectionResult:
        """Validate selection and extract geometry for dialog creation.

        Orchestrates the complete validation workflow:
        1. Check minimum selection count
        2. Extract geometry from selections
        3. Build ordered path from geometry
        4. Normalize path direction for consistent UI

        Args:
            selections: Active selections from the UI

        Returns:
            SelectionResult with validation status and geometry data
        """
        # 1. Check minimum selection count
        if selections.count < self.MIN_SELECTION_COUNT:
            return SelectionResult(
                is_valid=False,
                error_message=(
                    "Please select the tube path elements first:\n\n"
                    "Select all straight sections (lines) AND bends (arcs).\n"
                    "You can select them in any order."
                ),
            )

        # 2. Extract geometry from selections
        geometry = extract_geometry(selections)

        # Detect CLR from first arc
        detected_clr: float = 0.0
        if geometry.arcs:
            detected_clr = geometry.arcs[0].radius * self._units.cm_to_unit

        # 3. Build ordered path from geometry
        path_result = build_path_from_geometry(geometry.lines, geometry.arcs)
        if not path_result.success:
            return SelectionResult(
                is_valid=False,
                error_message=path_result.error_message,
                lines=geometry.lines,
                arcs=geometry.arcs,
                first_entity=geometry.first_entity,
                detected_clr=detected_clr,
            )

        # Guard: path_result.ordered_path is guaranteed non-None when success=True
        assert path_result.ordered_path is not None

        # 4. Normalize path direction for consistent UI
        direction = normalize_path_direction(
            path_result.ordered_path,
            path_result.starts_with_arc,
            path_result.ends_with_arc,
        )

        return SelectionResult(
            is_valid=True,
            lines=geometry.lines,
            arcs=geometry.arcs,
            ordered_path=direction.ordered_path,
            first_entity=geometry.first_entity,
            detected_clr=detected_clr,
            component_name=direction.component_name,
            starts_with_arc=direction.starts_with_arc,
            ends_with_arc=direction.ends_with_arc,
            start_point=direction.start_point,
            end_point=direction.end_point,
            primary_axis=direction.primary_axis,
            travel_direction=direction.travel_direction,
            opposite_direction=direction.opposite_direction,
        )

    def validate_for_execution(
        self,
        selections: adsk.core.Selections,
    ) -> SelectionResult:
        """Validate for command execution.

        This is equivalent to validate_for_dialog() since that method
        performs all necessary validation and geometry extraction.

        Args:
            selections: Active selections from the UI

        Returns:
            SelectionResult with full validation and geometry data
        """
        return self.validate_for_dialog(selections)
