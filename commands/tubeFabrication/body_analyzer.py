"""Orchestrates body extraction → bend sheet + cope computation.

Bridges the Fusion body_path_extractor with the Fusion-free core modules
to produce a complete analysis result from a single BRepBody selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import adsk.fusion

from ...models.types import Point3D, Vector3D
from ...models.body_path_data import BodyPathResult
from ...models.cope_data import ReceivingTube
from ...core.body_path import body_path_to_straights_and_bends, detect_path_direction
from ...core.cope_path import compute_end_reference
from ...core.cope_math import calculate_cope, _compute_inclination_angle
from ...core.combined_output import CopePageData
from ...core.geometry import normalize, dot_product, cross_product, magnitude
from ...lib import fusionAddInUtils as futil
from ..shared.body_path_extractor import extract_body_path, detect_receiving_tubes_assembly

if TYPE_CHECKING:
    from ...models.bend_data import StraightSection, BendData
    from ...models.cope_data import CopeResult
    from ...models.units import UnitConfig


@dataclass(slots=True)
class BodyAnalysisResult:
    """Complete analysis of a tube body for fabrication.

    Attributes:
        body_name: Name of the analysed body.
        body_path: Raw extraction result from face topology.
        straights: Straight sections in display units.
        bends: Bend data with angles, rotations, arc lengths.
        clr: Primary CLR in display units.
        od: Tube outer diameter in display units.
        wall_thickness: Wall thickness in display units (None if unknown).
        primary_axis: Detected primary travel axis name (X/Y/Z).
        travel_direction: Endpoint direction label (e.g. "Back").
        opposite_direction: Opposite endpoint label (e.g. "Front").
        starts_with_bend: Whether the ordered path starts with a bend.
        ends_with_bend: Whether the ordered path ends with a bend.
        start_is_coped: Whether the start end has cope geometry.
        end_is_coped: Whether the end end has cope geometry.
        start_point: Center point of path start (cm).
        end_point: Center point of path end (cm).
        clr_mismatch: Whether CLR values are inconsistent.
        clr_values_display: CLR values in display units.
        start_receiving: Receiving tubes detected at start.
        end_receiving: Receiving tubes detected at end.
    """
    body_name: str
    body_path: BodyPathResult
    straights: list["StraightSection"]
    bends: list["BendData"]
    clr: float
    od: float
    wall_thickness: float | None
    primary_axis: str
    travel_direction: str
    opposite_direction: str
    starts_with_bend: bool
    ends_with_bend: bool
    start_is_coped: bool
    end_is_coped: bool
    start_point: Point3D
    end_point: Point3D
    clr_mismatch: bool
    clr_values_display: list[float]
    start_receiving: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]] = field(
        default_factory=list
    )
    end_receiving: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]] = field(
        default_factory=list
    )


def analyze_body(
    body: adsk.fusion.BRepBody,
    units: "UnitConfig",
    component: adsk.fusion.Component | None = None,
    design: adsk.fusion.Design | None = None,
) -> BodyAnalysisResult | None:
    """Perform complete analysis of a tube body.

    Args:
        body: The BRepBody to analyse (proxy or native).
        units: Unit configuration for display conversion.
        component: Deprecated — kept for compatibility.
        design: The active Fusion design (for assembly-wide receiving
            tube detection across all components/occurrences).

    Returns:
        BodyAnalysisResult or None if extraction fails.
    """
    # Use the body as-is (proxy or native). Proxy bodies have geometry
    # in assembly coordinates, which is consistent with proxy bodies from
    # other occurrences when searching for receiving tubes.
    try:
        path = extract_body_path(body)
    except Exception as e:
        futil.log(f"analyze_body: extract_body_path raised {type(e).__name__}: {e}")
        return None
    if path is None:
        futil.log("analyze_body: extract_body_path returned None")
        return None
    futil.log(f"analyze_body: path extracted — {len(path.segments)} segments")

    straights, bends, clr = body_path_to_straights_and_bends(path, units)
    primary_axis, travel_direction, opposite_direction = detect_path_direction(path)

    # Tube dimensions in display units
    od_display = 2.0 * path.od_radius * units.cm_to_unit
    wall_display: float | None = None
    if path.id_radius is not None:
        wall_display = (path.od_radius - path.id_radius) * units.cm_to_unit

    # CLR mismatch and display values
    clr_mismatch = not path.clr_consistent
    clr_values_display = [c * units.cm_to_unit for c in path.clr_values]

    # Detect starts/ends with bend
    starts_with_bend = bool(
        path.segments and path.segments[0].face_type == "bend"
    )
    ends_with_bend = bool(
        path.segments and path.segments[-1].face_type == "bend"
    )

    # Detect receiving tubes
    start_receiving: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]] = []
    end_receiving: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]] = []

    futil.log(
        f"analyze_body: straights={len(straights)}, bends={len(bends)}, "
        f"start_coped={path.start_is_coped}, end_coped={path.end_is_coped}"
    )

    # Search for receiving tubes at both endpoints regardless of whether
    # the body already has cope geometry. Templates are needed before
    # cutting, so the tube won't have cope cuts yet in the typical workflow.
    if design is not None:
        start_receiving = detect_receiving_tubes_assembly(
            body, path.start_point, design,
            incoming_od_r=path.od_radius,
        )
        end_receiving = detect_receiving_tubes_assembly(
            body, path.end_point, design,
            incoming_od_r=path.od_radius,
        )
        futil.log(
            f"analyze_body: receivers — start={len(start_receiving)}, "
            f"end={len(end_receiving)}"
        )

    return BodyAnalysisResult(
        body_name=body.name,
        body_path=path,
        straights=straights,
        bends=bends,
        clr=clr,
        od=od_display,
        wall_thickness=wall_display,
        primary_axis=primary_axis,
        travel_direction=travel_direction,
        opposite_direction=opposite_direction,
        starts_with_bend=starts_with_bend,
        ends_with_bend=ends_with_bend,
        start_is_coped=path.start_is_coped,
        end_is_coped=path.end_is_coped,
        start_point=path.start_point,
        end_point=path.end_point,
        clr_mismatch=clr_mismatch,
        clr_values_display=clr_values_display,
        start_receiving=start_receiving,
        end_receiving=end_receiving,
    )


def build_cope_pages(
    analysis: BodyAnalysisResult,
    units: "UnitConfig",
    waste_side: Literal["top", "bottom"] = "top",
) -> list[CopePageData]:
    """Build cope template pages for coped ends of the analysed tube.

    Args:
        analysis: Complete body analysis result.
        units: Unit configuration.
        waste_side: Template layout — "top" for flush, "bottom" for setback.

    Returns:
        List of CopePageData, one per end with nearby receiving tubes.
    """
    pages: list[CopePageData] = []

    if not analysis.straights:
        return pages

    has_bends = len(analysis.bends) > 0

    # Process start end — generate template if receiving tubes are nearby
    if analysis.start_receiving:
        try:
            ref = compute_end_reference(analysis.straights, analysis.bends, "start")
            receiving = _build_receiving_list(
                analysis.start_receiving, units,
            )
            _log_cope_diagnostics(
                "Start", ref.tube_direction, analysis.start_point,
                analysis.start_receiving, receiving, units,
            )
            if receiving:
                result = calculate_cope(
                    v1=ref.tube_direction,
                    od1=analysis.od,
                    receiving_tubes=receiving,
                    reference_vector=ref.extrados_direction,
                    unit_label=units.unit_symbol,
                )
                max_z = max(result.z_profile) if result.z_profile else 0.0
                _log_cope_summary(
                    "Start", analysis.od, receiving, result, max_z, units,
                )
                pages.append(CopePageData(
                    end_label=f"{analysis.opposite_direction} End",
                    cope_result=result,
                    od1=analysis.od,
                    tube_name=analysis.body_name,
                    has_bends=has_bends,
                    waste_side=waste_side,
                ))
        except ValueError:
            pass  # Skip if end reference cannot be computed

    # Process end end
    if analysis.end_receiving:
        try:
            ref = compute_end_reference(analysis.straights, analysis.bends, "end")
            receiving = _build_receiving_list(
                analysis.end_receiving, units,
            )
            _log_cope_diagnostics(
                "End", ref.tube_direction, analysis.end_point,
                analysis.end_receiving, receiving, units,
            )
            if receiving:
                result = calculate_cope(
                    v1=ref.tube_direction,
                    od1=analysis.od,
                    receiving_tubes=receiving,
                    reference_vector=ref.extrados_direction,
                    unit_label=units.unit_symbol,
                )
                max_z = max(result.z_profile) if result.z_profile else 0.0
                _log_cope_summary(
                    "End", analysis.od, receiving, result, max_z, units,
                )
                pages.append(CopePageData(
                    end_label=f"{analysis.travel_direction} End",
                    cope_result=result,
                    od1=analysis.od,
                    tube_name=analysis.body_name,
                    has_bends=has_bends,
                    waste_side=waste_side,
                ))
        except ValueError:
            pass

    return pages


def _build_receiving_list(
    receiving: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]],
    units: "UnitConfig",
) -> list[ReceivingTube]:
    """Convert extractor results into ReceivingTube model objects.

    Args:
        receiving: List of (body, axis, od_radius_cm, axis_origin_cm)
            from extractor.
        units: Unit configuration for OD conversion.

    Returns:
        List of ReceivingTube with OD in display units.
    """
    result: list[ReceivingTube] = []
    for body, axis, od_radius, _origin in receiving:
        try:
            norm_axis = normalize(axis)
        except ValueError:
            continue
        od_display = 2.0 * od_radius * units.cm_to_unit
        result.append(ReceivingTube(
            vector=norm_axis,
            od=od_display,
            name=body.name,
        ))
    return result


def _compute_skew_distance(
    p1: Point3D, d1: Vector3D,
    p2: Point3D, d2: Vector3D,
) -> float:
    """Compute minimum distance between two lines in 3D.

    Uses the scalar triple product formula:
        distance = |((p2 - p1) · (d1 × d2))| / |d1 × d2|

    For intersecting lines (coplanar), this returns 0.
    For skew lines, this returns the perpendicular offset.

    Args:
        p1: Point on line 1.
        d1: Direction of line 1 (does not need to be normalized).
        p2: Point on line 2.
        d2: Direction of line 2 (does not need to be normalized).

    Returns:
        Distance in the same units as p1/p2. Returns 0.0 if lines
        are parallel (cross product is zero).
    """
    cross = cross_product(d1, d2)
    cross_mag = magnitude(cross)
    if cross_mag < 1e-10:
        return 0.0  # Parallel lines — offset is point-to-line distance
    dp = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    return abs(dot_product(dp, cross)) / cross_mag


def _log_cope_diagnostics(
    end_label: str,
    tube_direction: Vector3D,
    cope_point: Point3D,
    raw_receiving: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]],
    receiving_tubes: list[ReceivingTube],
    units: "UnitConfig",
) -> None:
    """Log diagnostic info about cope geometry for debugging."""
    futil.log(f"  --- Cope diagnostics: {end_label} end ---")
    futil.log(
        f"  incoming tube dir: ({tube_direction[0]:.4f}, "
        f"{tube_direction[1]:.4f}, {tube_direction[2]:.4f})"
    )
    futil.log(
        f"  cope point (cm): ({cope_point[0]:.3f}, "
        f"{cope_point[1]:.3f}, {cope_point[2]:.3f})"
    )

    for i, (body, axis, od_r, origin) in enumerate(raw_receiving):
        try:
            norm_axis = normalize(axis)
        except ValueError:
            continue

        # Inclination angle (included angle between axes)
        incl = _compute_inclination_angle(tube_direction, norm_axis)
        notcher_setting = 90.0 - incl

        # Skew distance (minimum distance between the two axis lines)
        skew = _compute_skew_distance(
            cope_point, tube_direction, origin, norm_axis,
        )
        skew_display = skew * units.cm_to_unit

        futil.log(
            f"  receiver {i+1}: {body.name}"
        )
        futil.log(
            f"    axis: ({norm_axis[0]:.4f}, {norm_axis[1]:.4f}, "
            f"{norm_axis[2]:.4f})"
        )
        futil.log(
            f"    origin (cm): ({origin[0]:.3f}, {origin[1]:.3f}, "
            f"{origin[2]:.3f})"
        )
        futil.log(
            f"    OD: {2.0 * od_r * units.cm_to_unit:.3f}{units.unit_symbol}"
        )
        futil.log(
            f"    inclination: {incl:.1f}°, notcher setting: "
            f"{notcher_setting:.1f}°"
        )
        futil.log(
            f"    axis skew distance: {skew_display:.4f}{units.unit_symbol} "
            f"(0 = axes intersect/coplanar)"
        )


def _log_cope_summary(
    end_label: str,
    od1: float,
    receiving: list[ReceivingTube],
    result: "CopeResult",
    max_z: float,
    units: "UnitConfig",
) -> None:
    """Log a concise cope calculation summary for debugging."""
    futil.log(f"  === COPE SUMMARY: {end_label} end ===")
    futil.log(f"  incoming OD: {od1:.3f}{units.unit_symbol}")
    for i, rt in enumerate(receiving):
        name = rt.name or f"tube {i + 1}"
        futil.log(f"  receiver {i+1}: {name}, OD={rt.od:.3f}{units.unit_symbol}")
    futil.log(
        f"  method={result.method}, desc={result.method_description}"
    )
    for i, p in enumerate(result.passes):
        futil.log(
            f"  pass {i+1}: notcher={p.notcher_angle:.1f}°, "
            f"rotation={p.rotation_mark:.1f}°, "
            f"depth={p.plunge_depth:.3f}{units.unit_symbol}, "
            f"passthrough={p.is_pass_through}"
        )
    futil.log(f"  max z-profile (cope depth): {max_z:.3f}{units.unit_symbol}")
    if max_z > od1 * 2:
        futil.log(
            f"  WARNING: cope depth {max_z:.3f}{units.unit_symbol} is >"
            f"2x tube OD ({od1:.3f}{units.unit_symbol}) — "
            f"check receiver detection"
        )
