"""Orchestrates body extraction → bend sheet + cope computation.

Bridges the Fusion body_path_extractor with the Fusion-free core modules
to produce a complete analysis result from a single BRepBody selection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import adsk.core
import adsk.fusion

from ...models.types import Point3D, Vector3D
from ...models.body_path_data import BodyPathResult
from ...models.cope_data import ReceivingTube
from ...core.body_path import body_path_to_straights_and_bends, detect_path_direction
from ...core.cope_path import compute_end_reference, compute_long_point_adjustment
from ...core.tolerances import CONNECTIVITY_CM
from ...core.cope_math import calculate_cope, _compute_inclination_angle
from ...core.combined_output import CopePageData
from ...core.geometry import normalize, dot_product, cross_product, magnitude
from ...lib import fusionAddInUtils as futil
from ..shared.body_path_extractor import extract_body_path, detect_receiving_tubes_assembly

if TYPE_CHECKING:
    from ...models.bend_data import StraightSection, BendData
    from ...models.cope_data import CopeResult
    from ...models.units import UnitConfig


# (body, axis, od_radius_cm, axis_origin_cm) from detect_receiving_tubes_assembly
ReceiverHit = tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]

# Cut-length changes smaller than this (~1/32") are not called out on the page
_ADJUSTMENT_REPORT_THRESHOLD_CM: float = 0.08


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
        body: The original BRepBody (for diagnostic edge sampling).
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
    body: adsk.fusion.BRepBody | None = None
    start_receiving: list[ReceiverHit] = field(
        default_factory=list
    )
    end_receiving: list[ReceiverHit] = field(
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
    start_receiving: list[ReceiverHit] = []
    end_receiving: list[ReceiverHit] = []

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
        body=body,
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
        List of CopePageData, one per end with nearby receiving tubes,
        in path order (start end first).
    """
    pages: list[CopePageData] = []

    if not analysis.straights:
        return pages

    ends: list[tuple[Literal["start", "end"], str, Point3D, list[ReceiverHit], bool]] = [
        ("start", f"{analysis.opposite_direction} End", analysis.start_point,
         analysis.start_receiving, analysis.starts_with_bend),
        ("end", f"{analysis.travel_direction} End", analysis.end_point,
         analysis.end_receiving, analysis.ends_with_bend),
    ]
    for path_end, end_label, end_point, receivers, at_bend in ends:
        if not receivers:
            continue
        page = _build_end_page(
            analysis, units, waste_side, path_end, end_label,
            end_point, receivers, at_bend,
        )
        if page is not None:
            pages.append(page)

    return pages


def _build_end_page(
    analysis: BodyAnalysisResult,
    units: "UnitConfig",
    waste_side: Literal["top", "bottom"],
    path_end: Literal["start", "end"],
    end_label: str,
    end_point: Point3D,
    receivers: list[ReceiverHit],
    at_bend: bool,
) -> CopePageData | None:
    """Compute one end's cope and the cut-length change it needs.

    Returns None when the end reference or cope cannot be computed.
    """
    log_label = path_end.capitalize()
    try:
        ref = compute_end_reference(analysis.straights, analysis.bends, path_end)
    except ValueError:
        return None

    receiving = _build_receiving_list(receivers, units)
    _log_cope_diagnostics(
        log_label, ref.tube_direction, end_point, receivers, receiving, units,
    )
    if not receiving:
        return None

    try:
        result = calculate_cope(
            v1=ref.tube_direction,
            od1=analysis.od,
            receiving_tubes=receiving,
            reference_vector=ref.extrados_direction,
            unit_label=units.unit_symbol,
        )
    except ValueError as e:
        futil.log(f"  {log_label} end: cope not computed — {e}")
        return None

    max_z = max(result.z_profile) if result.z_profile else 0.0
    _log_cope_summary(log_label, analysis.od, receiving, result, max_z, units)
    # Diagnostic only: logs body-edge vs formula comparison.
    # The formula drives the template (verified against an
    # exact ray-cast); body-edge sampling is not reliable enough.
    _run_profile_comparison(
        log_label, analysis.body, ref.tube_direction,
        end_point, ref.extrados_direction,
        analysis.body_path.od_radius, result.z_profile, units,
    )

    adjustment: float | None = None
    notes: list[str] = []
    if at_bend:
        notes.append(
            "Cut length NOT adjusted for the cope: this end finishes in a bend. "
            "Check the fit before cutting."
        )
    else:
        adjustment = _long_point_adjustment(
            end_point, ref.tube_direction, receivers, result.z_profile,
            analysis.body_path.od_radius, units,
        )
        if adjustment is None:
            notes.append(
                "Cut length NOT adjusted for the cope: tube centerlines do not "
                "meet at this joint. Check the fit before cutting."
            )
        elif abs(adjustment) / units.cm_to_unit >= _ADJUSTMENT_REPORT_THRESHOLD_CM:
            change = "adds" if adjustment > 0 else "removes"
            notes.append(
                f"Cut length {change} {abs(adjustment):.3f}{units.unit_symbol} at this "
                f"end so the tube ends at the cope's long point (template TUBE END)."
            )
    futil.log(f"  {log_label} end: long-point length adjustment = {adjustment}")

    return CopePageData(
        end_label=end_label,
        cope_result=result,
        od1=analysis.od,
        tube_name=analysis.body_name,
        has_bends=len(analysis.bends) > 0,
        waste_side=waste_side,
        path_end=path_end,
        length_adjustment=adjustment,
        notes=notes,
    )


def _long_point_adjustment(
    end_point: Point3D,
    tube_direction: Vector3D,
    receivers: list[ReceiverHit],
    z_profile: list[float],
    od_radius_cm: float,
    units: "UnitConfig",
) -> float | None:
    """Display-unit length to add so this end finishes at the cope long point.

    Every receiver must agree on the crossing point (the formula assumes all
    centerlines meet at one node); otherwise None.
    """
    if not z_profile:
        return None
    z_min_cm = min(z_profile) / units.cm_to_unit
    values: list[float] = []
    for _body, axis, _od_r, origin in receivers:
        adj = compute_long_point_adjustment(
            end_point, tube_direction, origin, axis, z_min_cm, od_radius_cm,
        )
        if adj is None:
            return None
        values.append(adj)
    if max(values) - min(values) > CONNECTIVITY_CM:
        return None
    return values[0] * units.cm_to_unit


def _build_receiving_list(
    receiving: list[ReceiverHit],
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
    raw_receiving: list[ReceiverHit],
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


# ── Diagnostic: body edge sampling & formula comparison ──────────


def _run_profile_comparison(
    end_label: str,
    body: adsk.fusion.BRepBody | None,
    tube_direction: Vector3D,
    cope_point: Point3D,
    reference_direction: Vector3D | None,
    od_radius_cm: float,
    formula_z: list[float],
    units: "UnitConfig",
) -> list[float] | None:
    """Sample body cope edges and compare with formula z-profile.

    Logs diagnostic comparison data. Returns the sampled profile for
    overlay on the template SVG, or None if sampling fails.
    """
    if body is None:
        return None
    try:
        sampled = _sample_body_cope_profile(
            body, tube_direction, cope_point,
            reference_direction, od_radius_cm, units,
        )
        if sampled is not None:
            _log_profile_comparison(end_label, formula_z, sampled, units)
            return sampled
        else:
            futil.log(
                f"  DIAGNOSTIC ({end_label}): No cope edges found on body — "
                f"body may not be coped yet"
            )
            return None
    except Exception as e:
        futil.log(f"  DIAGNOSTIC ({end_label}): Edge sampling failed: {e}")
        return None


def _sample_body_cope_profile(
    body: adsk.fusion.BRepBody,
    tube_direction: Vector3D,
    cope_point: Point3D,
    reference_direction: Vector3D | None,
    od_radius_cm: float,
    units: "UnitConfig",
) -> list[float] | None:
    """Sample actual cope edge profile from BRepBody geometry.

    Collects non-circle edges from OD cylinder faces, samples points
    along each edge, converts to cylindrical coordinates aligned with
    the formula's reference system, and builds a 1-degree depth profile.

    Args:
        body: The tube BRepBody to sample.
        tube_direction: Tube centerline unit vector (outward from cope end).
        cope_point: Tube endpoint on the centerline (cm).
        reference_direction: Extrados (back-of-bend) direction, or None.
        od_radius_cm: Tube OD radius in cm.
        units: Unit configuration for conversion.

    Returns:
        360-element depth profile in display units, or None if no edges found.
    """
    axis_dir = adsk.core.Vector3D.create(
        tube_direction[0], tube_direction[1], tube_direction[2],
    )
    axis_dir.normalize()
    axis_origin = adsk.core.Point3D.create(
        cope_point[0], cope_point[1], cope_point[2],
    )

    # Build reference direction aligned with the formula's reference
    if reference_direction is not None:
        ref_dir = _project_ref_direction(reference_direction, tube_direction)
    else:
        ref_dir = _build_ref_dir_fusion(axis_dir)

    # Collect non-circle edges from OD cylinder faces
    edges = _collect_od_intersection_edges(body, od_radius_cm)
    if not edges:
        return None

    futil.log(f"  DIAGNOSTIC: found {len(edges)} intersection edges on OD faces")

    # Sample edge points and convert to cylindrical coordinates
    curve_types = {
        0: "Line", 1: "Arc", 2: "Circle", 3: "Ellipse",
        4: "EllArc", 5: "InfLine", 6: "NURBS",
    }
    all_points: list[tuple[float, float]] = []  # (azimuth_deg, z_cm)
    sampled_count = 0
    failed_count = 0
    for ei, edge in enumerate(edges):
        ct = edge.geometry.curveType
        ct_name = curve_types.get(ct, f"Unknown({ct})")
        try:
            evaluator = edge.evaluator
            ok_range, t_start, t_end = evaluator.getParameterExtents()
            if not ok_range:
                futil.log(
                    f"  DIAGNOSTIC: edge {ei} ({ct_name}) — "
                    f"getParameterExtents failed"
                )
                failed_count += 1
                continue
            edge_points = 0
            for i in range(101):
                t = t_start + (t_end - t_start) * i / 100
                ok, point = evaluator.getPointAtParameter(t)
                if not ok:
                    continue
                azimuth, z, r = _point_to_cylindrical_fusion(
                    point, axis_origin, axis_dir, ref_dir,
                )
                # Only keep points on the OD surface (within tolerance)
                if abs(r - od_radius_cm) < 0.05:
                    all_points.append((azimuth, z))
                    edge_points += 1
            sampled_count += 1
            futil.log(
                f"  DIAGNOSTIC: edge {ei} ({ct_name}) — "
                f"{edge_points} OD pts, len={edge.length:.3f} cm"
            )
        except Exception as e:
            failed_count += 1
            futil.log(
                f"  DIAGNOSTIC: edge {ei} ({ct_name}) — "
                f"evaluator error: {e}"
            )

    futil.log(
        f"  DIAGNOSTIC: {sampled_count} edges sampled, "
        f"{failed_count} failed, {len(all_points)} total OD points"
    )

    if not all_points:
        futil.log("  DIAGNOSTIC: no valid OD points sampled from edges")
        return None

    # Z-proximity filter: only keep points near THIS cope end.
    # The cope point is the cylindrical origin (z=0). Edges from the
    # other cope end will have large |z| (~tube length) and must be
    # excluded. The cope profile depth is at most a few OD diameters,
    # so |z| < 4×OD is a safe threshold.
    z_threshold = 4 * (2 * od_radius_cm)
    filtered = [(a, z) for a, z in all_points if abs(z) <= z_threshold]
    rejected = len(all_points) - len(filtered)
    futil.log(
        f"  DIAGNOSTIC: |z| threshold {z_threshold:.2f} cm (4×OD), "
        f"{len(filtered)} kept, {rejected} rejected (other end)"
    )

    if not filtered:
        return None

    # Build 1-degree depth profile using min-z per degree.
    # The cope_point may not be exactly at the tube end (it can be
    # offset by a few cm). Using min(z) per degree captures the deepest
    # edge point at each angle, then depth = z_max - z_at_deg gives
    # depth relative to the shallowest point (tube end), automatically
    # cancelling any cope_point offset.
    bins_min_z: dict[int, float] = {}
    for azimuth, z in filtered:
        deg = int(round(azimuth)) % 360
        if deg not in bins_min_z or z < bins_min_z[deg]:
            bins_min_z[deg] = z

    if not bins_min_z:
        return None

    # z_max = shallowest point across all degrees ≈ tube end
    z_tube_end = max(bins_min_z.values())
    futil.log(
        f"  DIAGNOSTIC: z_tube_end offset from cope_point: "
        f"{z_tube_end:.3f} cm ({z_tube_end * units.cm_to_unit:.4f}{units.unit_symbol})"
    )

    # Convert to depth relative to tube end, in display units
    profile: list[float] = [0.0] * 360
    for deg, z in bins_min_z.items():
        depth_cm = z_tube_end - z
        profile[deg] = depth_cm * units.cm_to_unit

    covered = sum(1 for z in profile if z > 0.001)
    futil.log(f"  DIAGNOSTIC: profile coverage {covered}/360 degrees")

    return profile


def _collect_od_intersection_edges(
    body: adsk.fusion.BRepBody,
    od_radius_cm: float,
) -> list[adsk.fusion.BRepEdge]:
    """Collect unique non-circle edges from OD cylinder faces."""
    edges: list[adsk.fusion.BRepEdge] = []
    seen: set[int] = set()
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType != 1:  # Not a cylinder
            continue
        if abs(face.geometry.radius - od_radius_cm) > 0.01:
            continue
        for j in range(face.edges.count):
            edge = face.edges.item(j)
            if edge.geometry.curveType == 2:  # Circle — skip
                continue
            eid = edge.tempId
            if eid in seen:
                continue
            seen.add(eid)
            edges.append(edge)
    return edges


def _point_to_cylindrical_fusion(
    point: adsk.core.Point3D,
    axis_origin: adsk.core.Point3D,
    axis_dir: adsk.core.Vector3D,
    ref_dir: adsk.core.Vector3D,
) -> tuple[float, float, float]:
    """Convert a 3D point to cylindrical coordinates (azimuth_deg, z, r).

    Uses the same angular convention as cope_math._compute_rotation_mark:
    azimuth increases CCW when viewed from the positive axis_dir direction.
    """
    dx = point.x - axis_origin.x
    dy = point.y - axis_origin.y
    dz = point.z - axis_origin.z
    # Axial component (signed distance along tube axis)
    z = dx * axis_dir.x + dy * axis_dir.y + dz * axis_dir.z
    # Radial component (perpendicular to axis)
    rx = dx - z * axis_dir.x
    ry = dy - z * axis_dir.y
    rz = dz - z * axis_dir.z
    r = math.sqrt(rx * rx + ry * ry + rz * rz)
    # Azimuth from reference direction
    cos_a = rx * ref_dir.x + ry * ref_dir.y + rz * ref_dir.z
    # Perpendicular direction in cross-section plane: axis × ref
    perp_x = axis_dir.y * ref_dir.z - axis_dir.z * ref_dir.y
    perp_y = axis_dir.z * ref_dir.x - axis_dir.x * ref_dir.z
    perp_z = axis_dir.x * ref_dir.y - axis_dir.y * ref_dir.x
    sin_a = rx * perp_x + ry * perp_y + rz * perp_z
    azimuth = math.degrees(math.atan2(sin_a, cos_a)) % 360
    return azimuth, z, r


def _project_ref_direction(
    reference_direction: Vector3D,
    tube_direction: Vector3D,
) -> adsk.core.Vector3D:
    """Project reference_direction onto the plane perpendicular to tube axis.

    Returns a Fusion Vector3D suitable for cylindrical coordinate conversion.
    Falls back to an arbitrary perpendicular if projection has zero magnitude.
    """
    dot_val = (
        reference_direction[0] * tube_direction[0]
        + reference_direction[1] * tube_direction[1]
        + reference_direction[2] * tube_direction[2]
    )
    proj = (
        reference_direction[0] - dot_val * tube_direction[0],
        reference_direction[1] - dot_val * tube_direction[1],
        reference_direction[2] - dot_val * tube_direction[2],
    )
    mag = math.sqrt(proj[0] ** 2 + proj[1] ** 2 + proj[2] ** 2)
    if mag > 1e-10:
        ref = adsk.core.Vector3D.create(
            proj[0] / mag, proj[1] / mag, proj[2] / mag,
        )
    else:
        axis = adsk.core.Vector3D.create(
            tube_direction[0], tube_direction[1], tube_direction[2],
        )
        ref = _build_ref_dir_fusion(axis)
    return ref


def _build_ref_dir_fusion(
    axis_dir: adsk.core.Vector3D,
) -> adsk.core.Vector3D:
    """Build an arbitrary reference direction perpendicular to axis_dir."""
    if abs(axis_dir.y) < 0.9:
        up = adsk.core.Vector3D.create(0, 1, 0)
    else:
        up = adsk.core.Vector3D.create(0, 0, 1)
    d = axis_dir.x * up.x + axis_dir.y * up.y + axis_dir.z * up.z
    ref = adsk.core.Vector3D.create(
        up.x - d * axis_dir.x,
        up.y - d * axis_dir.y,
        up.z - d * axis_dir.z,
    )
    ref.normalize()
    return ref


def _log_profile_comparison(
    end_label: str,
    formula_z: list[float],
    sampled_z: list[float],
    units: "UnitConfig",
) -> None:
    """Log comparison between formula z-profile and sampled body profile."""
    futil.log(f"  === PROFILE COMPARISON: {end_label} end ===")

    # Compute deltas only at degrees with sampled coverage
    deltas: list[tuple[int, float]] = []
    for deg in range(360):
        if sampled_z[deg] > 0.001:
            delta = formula_z[deg] - sampled_z[deg]
            deltas.append((deg, delta))

    if not deltas:
        futil.log("  No overlapping data for comparison")
        return

    abs_deltas = [abs(d) for _, d in deltas]
    max_abs = max(abs_deltas)
    avg_abs = sum(abs_deltas) / len(abs_deltas)
    max_deg = deltas[abs_deltas.index(max_abs)][0]

    sampled_max = max(s for s in sampled_z if s > 0.001)
    formula_max = max(formula_z) if formula_z else 0.0

    futil.log(f"  comparison points: {len(deltas)}/360")
    futil.log(f"  formula  max depth: {formula_max:.4f}{units.unit_symbol}")
    futil.log(f"  sampled  max depth: {sampled_max:.4f}{units.unit_symbol}")
    futil.log(f"  avg |delta|: {avg_abs:.4f}{units.unit_symbol}")
    futil.log(f"  max |delta|: {max_abs:.4f}{units.unit_symbol} at {max_deg}°")

    # Detailed comparison at 15-degree intervals
    futil.log(f"  {'Deg':>4} {'Formula':>9} {'Sampled':>9} {'Delta':>9}")
    for deg in range(0, 360, 15):
        fz = formula_z[deg]
        sz = sampled_z[deg]
        if sz > 0.001:
            d = fz - sz
            futil.log(
                f"  {deg:>4}  {fz:>8.4f}{units.unit_symbol}"
                f"  {sz:>8.4f}{units.unit_symbol}"
                f"  {d:>+8.4f}{units.unit_symbol}"
            )
        else:
            futil.log(
                f"  {deg:>4}  {fz:>8.4f}{units.unit_symbol}"
                f"  {'---':>9}"
                f"  {'---':>9}"
            )
