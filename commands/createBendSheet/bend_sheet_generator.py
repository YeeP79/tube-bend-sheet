"""Orchestrates bend sheet calculation and data building.

This module coordinates the calculation pipeline to generate complete
bend sheet data from geometry and parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import adsk.fusion

from ...core import (
    validate_clr_consistency,
    calculate_straights_and_bends,
    build_segments_and_marks,
    validate_direction_aware,
    calculate_material_requirements,
)
from ...models import UnitConfig, BendSheetData

if TYPE_CHECKING:
    from ...core import PathElement
    from .input_parser import BendSheetParams


@dataclass(slots=True)
class GenerationResult:
    """Result of bend sheet generation."""

    success: bool
    data: BendSheetData | None = None
    error: str = ""
    suggestion: str = ""  # Suggestion for user (e.g., "try reversed direction")


class BendSheetGenerator:
    """Generates bend sheet data from geometry and parameters.

    Responsible for:
    - Validating CLR consistency
    - Calculating straights and bends
    - Building segments and mark positions
    - Handling paths that start/end with bends (synthetic grip/tail)
    - Constructing complete BendSheetData
    """

    def __init__(self, units: UnitConfig) -> None:
        """
        Initialize the generator.

        Args:
            units: Unit configuration for the design
        """
        self._units = units

    def generate(
        self,
        ordered_path: list["PathElement"],
        start_point: tuple[float, float, float],
        params: "BendSheetParams",
        component_name: str,
        travel_direction: str,
        opposite_direction: str,
        starts_with_arc: bool,
        ends_with_arc: bool,
    ) -> GenerationResult:
        """
        Generate complete bend sheet data.

        Args:
            ordered_path: Ordered list of path elements (lines and arcs)
            start_point: Starting point of the path
            params: Parsed input parameters
            component_name: Name of the component
            travel_direction: Direction of travel along path (e.g., "Back to Front")
            opposite_direction: Opposite direction label (e.g., "Front to Back")
            starts_with_arc: Whether path starts with an arc
            ends_with_arc: Whether path ends with an arc

        Returns:
            GenerationResult with success status and data or error
        """
        # Extract lines and arcs from ordered path
        lines: list[adsk.fusion.SketchLine] = [
            cast(adsk.fusion.SketchLine, e.entity)
            for e in ordered_path if e.element_type == "line"
        ]
        arcs: list[adsk.fusion.SketchArc] = [
            cast(adsk.fusion.SketchArc, e.entity)
            for e in ordered_path if e.element_type == "arc"
        ]

        # Validate CLR consistency
        clr, clr_mismatch, clr_values = validate_clr_consistency(arcs, self._units)

        # Validate CLR is usable for calculations (avoid NaN in arc length)
        if clr <= 0 and arcs:
            return GenerationResult(
                success=False,
                error="Invalid CLR detected (zero or negative). Check that arcs have valid radii.",
            )

        # Calculate straights and bends
        straights, bends = calculate_straights_and_bends(
            lines, arcs, start_point, clr, self._units,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
        )

        # Validate we have geometry to work with (straights or bends)
        if not straights and not bends:
            return GenerationResult(
                success=False,
                error="No geometry found in path. Cannot generate bend sheet.",
            )

        # Direction-aware validation for middle straights
        if params.min_grip > 0 and len(straights) > 2:
            direction_result = validate_direction_aware(
                straights,
                params.min_grip,
                params.min_tail,
                travel_direction,
                opposite_direction,
            )
            if not direction_result.current_direction_valid:
                return GenerationResult(
                    success=False,
                    error=direction_result.error_message,
                    suggestion=direction_result.suggestion,
                )

        # Calculate grip/tail material requirements
        material = calculate_material_requirements(
            straights=straights,
            min_grip=params.min_grip,
            min_tail=params.min_tail,
            die_offset=params.die_offset,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
            start_allowance=params.start_allowance,
            end_allowance=params.end_allowance,
            add_allowance_with_grip_extension=params.add_allowance_with_grip_extension,
            add_allowance_with_tail_extension=params.add_allowance_with_tail_extension,
        )

        # Determine if spring back warning is needed
        # This occurs when tail is extended but effective end allowance is 0
        spring_back_warning = (
            material.has_tail_extension and
            material.effective_end_allowance == 0
        )

        # Build segments and mark positions
        segments, mark_positions = build_segments_and_marks(
            straights, bends, material.extra_material, params.die_offset
        )

        # Calculate totals
        total_straights: float = sum(s.length for s in straights)
        total_arcs: float = sum(b.arc_length for b in bends)
        total_centerline: float = total_straights + total_arcs

        # Calculate total cut length:
        # - Base centerline length
        # - Grip extension at start (extra_material) if needed
        # - Tail extension at end (extra_tail_material) if last straight < min_tail
        # - Synthetic tail material if path ends with arc
        # - Effective allowances at each end (may be 0 if extensions were added)
        total_cut_length: float = (
            total_centerline
            + material.extra_material
            + material.extra_tail_material
            + material.synthetic_tail_material
            + material.effective_start_allowance
            + material.effective_end_allowance
        )

        # Calculate tail cut position for post-bend trimming
        # Cut position is at the end of original centerline + grip extension + start allowance
        # (any tail extension material and end allowance are beyond this point, to be trimmed)
        tail_cut_position: float | None = None
        if material.has_synthetic_tail or material.has_tail_extension:
            tail_cut_position = (
                total_centerline
                + material.extra_material
                + material.effective_start_allowance
            )

        # Build sheet data
        sheet_data = BendSheetData(
            component_name=component_name,
            tube_od=params.tube_od,
            clr=clr,
            die_offset=params.die_offset,
            precision=params.precision,
            min_grip=params.min_grip,
            travel_direction=travel_direction,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
            clr_mismatch=clr_mismatch,
            clr_values=clr_values,
            continuity_errors=[],
            straights=straights,
            bends=bends,
            segments=segments,
            mark_positions=mark_positions,
            extra_material=material.extra_material,
            total_centerline=total_centerline,
            total_cut_length=total_cut_length,
            units=self._units,
            bender_name=params.bender_name,
            die_name=params.die_name,
            bender_notes=params.bender_notes,
            die_notes=params.die_notes,
            grip_violations=material.grip_violations,
            min_tail=params.min_tail,
            tail_violation=material.tail_violation,
            has_synthetic_grip=material.has_synthetic_grip,
            has_synthetic_tail=material.has_synthetic_tail,
            grip_cut_position=material.grip_cut_position,
            tail_cut_position=tail_cut_position,
            start_allowance=params.start_allowance,
            end_allowance=params.end_allowance,
            extra_tail_material=material.extra_tail_material,
            has_tail_extension=material.has_tail_extension,
            effective_start_allowance=material.effective_start_allowance,
            effective_end_allowance=material.effective_end_allowance,
            spring_back_warning=spring_back_warning,
        )

        return GenerationResult(success=True, data=sheet_data)
