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
from ...core.compensation import calculate_compensated_angle
from ...models import (
    UnitConfig,
    BendSheetData,
    ToolingInfo,
    GeometrySpecs,
    PathData,
    MaterialInfo,
    SheetWarnings,
)

if TYPE_CHECKING:
    from ...core import PathElement
    from ...core.grip_tail import MaterialCalculation
    from ...models import StraightSection, BendData, MarkPosition, PathSegment
    from .input_parser import BendSheetParams
    from ...storage.tubes import TubeManager


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

    def __init__(
        self,
        units: UnitConfig,
        tube_manager: "TubeManager | None" = None,
    ) -> None:
        """
        Initialize the generator.

        Args:
            units: Unit configuration for the design
            tube_manager: Optional tube manager for compensation lookup
        """
        self._units = units
        self._tube_manager = tube_manager

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
        # Extract line endpoints and arcs from ordered path
        line_endpoints = [
            e.endpoints
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
        try:
            straights, bends = calculate_straights_and_bends(
                line_endpoints, arcs, start_point, clr, self._units,
                starts_with_arc=starts_with_arc,
                ends_with_arc=ends_with_arc,
            )
        except ValueError as e:
            return GenerationResult(
                success=False,
                error=f"Path geometry error: {e}",
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

        # Apply bender compensation if enabled
        compensation_warnings = self._apply_compensation(mark_positions, params)

        # Calculate totals and build sheet data
        total_centerline, total_cut_length, tail_cut_position = (
            self._calculate_totals(straights, bends, material)
        )

        sheet_data = self._build_sheet_data(
            params=params,
            component_name=component_name,
            clr=clr,
            clr_mismatch=clr_mismatch,
            clr_values=clr_values,
            straights=straights,
            bends=bends,
            segments=segments,
            mark_positions=mark_positions,
            total_centerline=total_centerline,
            total_cut_length=total_cut_length,
            travel_direction=travel_direction,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
            material=material,
            tail_cut_position=tail_cut_position,
            spring_back_warning=spring_back_warning,
            compensation_warnings=compensation_warnings,
        )

        return GenerationResult(success=True, data=sheet_data)

    def generate_from_data(
        self,
        straights: list["StraightSection"],
        bends: list["BendData"],
        clr: float,
        clr_mismatch: bool,
        clr_values: list[float],
        params: "BendSheetParams",
        component_name: str,
        travel_direction: str,
        opposite_direction: str,
        starts_with_arc: bool,
        ends_with_arc: bool,
    ) -> GenerationResult:
        """Generate bend sheet from pre-computed straights and bends.

        Skips geometry extraction (steps 1-3) and runs the calculation
        pipeline (steps 4-9) directly. Used by the body-based
        tubeFabrication command.

        Args:
            straights: Pre-computed straight sections (display units).
            bends: Pre-computed bend data.
            clr: Center line radius in display units.
            clr_mismatch: Whether CLR values are inconsistent.
            clr_values: List of all CLR values found (display units).
            params: Parsed input parameters.
            component_name: Name of the component.
            travel_direction: Direction of travel label.
            opposite_direction: Opposite direction label.
            starts_with_arc: Whether path starts with an arc.
            ends_with_arc: Whether path ends with an arc.

        Returns:
            GenerationResult with success status and data or error.
        """
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

        spring_back_warning = (
            material.has_tail_extension and
            material.effective_end_allowance == 0
        )

        segments, mark_positions = build_segments_and_marks(
            straights, bends, material.extra_material, params.die_offset
        )

        compensation_warnings = self._apply_compensation(mark_positions, params)

        total_centerline, total_cut_length, tail_cut_position = (
            self._calculate_totals(straights, bends, material)
        )

        sheet_data = self._build_sheet_data(
            params=params,
            component_name=component_name,
            clr=clr,
            clr_mismatch=clr_mismatch,
            clr_values=clr_values,
            straights=straights,
            bends=bends,
            segments=segments,
            mark_positions=mark_positions,
            total_centerline=total_centerline,
            total_cut_length=total_cut_length,
            travel_direction=travel_direction,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
            material=material,
            tail_cut_position=tail_cut_position,
            spring_back_warning=spring_back_warning,
            compensation_warnings=compensation_warnings,
        )

        return GenerationResult(success=True, data=sheet_data)

    def _apply_compensation(
        self,
        mark_positions: list["MarkPosition"],
        params: "BendSheetParams",
    ) -> list[str]:
        """Apply bender compensation to mark positions.

        Args:
            mark_positions: Mark positions to update with compensated angles
            params: Parameters containing compensation settings

        Returns:
            List of unique compensation warnings
        """
        warnings: list[str] = []
        if not (
            params.apply_compensation
            and params.tube_id
            and params.die_id
            and self._tube_manager
        ):
            return warnings

        compensation_data = self._tube_manager.get_compensation(
            params.die_id, params.tube_id
        )
        if compensation_data and compensation_data.data_points:
            for mark in mark_positions:
                result = calculate_compensated_angle(
                    mark.bend_angle, compensation_data.data_points
                )
                mark.compensated_angle = result.compensated_angle
                if result.warning and result.warning not in warnings:
                    warnings.append(result.warning)

        return warnings

    def _calculate_totals(
        self,
        straights: list["StraightSection"],
        bends: list["BendData"],
        material: "MaterialCalculation",
    ) -> tuple[float, float, float | None]:
        """Calculate centerline length, cut length, and tail cut position.

        Args:
            straights: Straight sections of the path
            bends: Bend data for the path
            material: Material calculation results

        Returns:
            Tuple of (total_centerline, total_cut_length, tail_cut_position)
        """
        total_straights: float = sum(s.length for s in straights)
        total_arcs: float = sum(b.arc_length for b in bends)
        total_centerline: float = total_straights + total_arcs

        total_cut_length: float = (
            total_centerline
            + material.extra_material
            + material.extra_tail_material
            + material.synthetic_tail_material
            + material.effective_start_allowance
            + material.effective_end_allowance
        )

        # Tail cut position for post-bend trimming
        tail_cut_position: float | None = None
        if material.has_synthetic_tail or material.has_tail_extension:
            tail_cut_position = (
                total_centerline
                + material.extra_material
                + material.effective_start_allowance
            )

        return total_centerline, total_cut_length, tail_cut_position

    def _build_sheet_data(
        self,
        *,
        params: "BendSheetParams",
        component_name: str,
        clr: float,
        clr_mismatch: bool,
        clr_values: list[float],
        straights: list["StraightSection"],
        bends: list["BendData"],
        segments: list["PathSegment"],
        mark_positions: list["MarkPosition"],
        total_centerline: float,
        total_cut_length: float,
        travel_direction: str,
        starts_with_arc: bool,
        ends_with_arc: bool,
        material: "MaterialCalculation",
        tail_cut_position: float | None,
        spring_back_warning: bool,
        compensation_warnings: list[str],
    ) -> BendSheetData:
        """Construct BendSheetData from sub-groups.

        Args:
            params: Parsed input parameters
            component_name: Name of the component
            clr: Center line radius
            clr_mismatch: Whether CLR values are inconsistent
            clr_values: List of all CLR values found
            straights: Straight sections
            bends: Bend data
            segments: Path segments for table
            mark_positions: Mark positions for bender
            total_centerline: Total centerline length
            total_cut_length: Total cut length including extensions
            travel_direction: Direction of travel label
            starts_with_arc: Whether path starts with arc
            ends_with_arc: Whether path ends with arc
            material: Material calculation results
            tail_cut_position: Position to cut tail (or None)
            spring_back_warning: Whether spring back warning applies
            compensation_warnings: List of compensation warnings

        Returns:
            Complete BendSheetData
        """
        tooling = ToolingInfo(
            component_name=component_name,
            bender_name=params.bender_name,
            die_name=params.die_name,
            bender_notes=params.bender_notes,
            die_notes=params.die_notes,
            tube_name=params.tube_name,
            wall_thickness=params.wall_thickness,
            material_type=params.material_type,
            apply_compensation=params.apply_compensation,
        )
        geometry = GeometrySpecs(
            tube_od=params.tube_od,
            clr=clr,
            die_offset=params.die_offset,
            precision=params.precision,
            units=self._units,
            clr_mismatch=clr_mismatch,
            clr_values=clr_values,
        )
        path_data = PathData(
            straights=straights,
            bends=bends,
            segments=segments,
            mark_positions=mark_positions,
            total_centerline=total_centerline,
            total_cut_length=total_cut_length,
            travel_direction=travel_direction,
            starts_with_arc=starts_with_arc,
            ends_with_arc=ends_with_arc,
            continuity_errors=[],
        )
        material_info = MaterialInfo(
            min_grip=params.min_grip,
            extra_material=material.extra_material,
            min_tail=params.min_tail,
            grip_violations=material.grip_violations,
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
        )
        sheet_warnings = SheetWarnings(
            spring_back_warning=spring_back_warning,
            compensation_warnings=compensation_warnings,
        )
        return BendSheetData.from_groups(
            tooling, geometry, path_data, material_info, sheet_warnings,
        )
