"""Extract tube path from a BRepBody's face topology.

Walks the OD cylinder and torus faces via adjacency graphs to extract
straights, bends, rotations, and CLR — the same data the bend sheet
currently gets from sketch geometry.

This is the Fusion 360 bridge layer. It converts Fusion BRep objects
into the Fusion-free BodyPathResult model.

Key challenge: cope cuts on tube ends create additional OD-radius
cylinder faces (from the receiving tube surface). These "cope artifacts"
must be excluded from the tube path. The torus-anchored ordering
strategy handles this by building the path outward from bend faces,
which are always reliable path members.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import adsk.core
import adsk.fusion

from ...models.body_path_data import BodyFaceSegment, BodyPathResult
from ...models.types import Vector3D, Point3D
from ...core.tolerances import (
    OD_FILTER_TOLERANCE_CM,
    COAXIAL_MERGE_ANGLE_DEG,
    COAXIAL_MERGE_DISTANCE_CM,
    MIN_BEND_ANGLE_DEG,
    MAX_RECEIVING_OD_RATIO,
)
from ...core.geometry import normalize, point_to_line_distance
from ...lib import fusionAddInUtils as futil

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_body_path(body: adsk.fusion.BRepBody) -> BodyPathResult | None:
    """Extract the complete tube path from a body's face topology.

    Pipeline:
    1. Find OD radius (largest cylinder by total face area).
    2. Optionally find ID radius (second largest).
    3. Classify OD faces into cylinders (straights) vs tori (bends).
    4. Build face adjacency graph.
    5. Order path using torus-anchored walk (handles cope artifacts).
    6. Extend terminal straights with coaxial split faces.
    7. Extract geometry from each ordered face → BodyFaceSegment.
    8. Detect coped ends.

    Args:
        body: The BRepBody to analyze.

    Returns:
        BodyPathResult or None if the body has no cylindrical faces.
    """
    futil.log(f"extract_body_path: body={body.name}, faces={body.faces.count}")

    od_radius = _find_od_radius(body)
    if od_radius is None:
        futil.log("extract_body_path: FAIL — no cylindrical faces found")
        return None
    futil.log(f"extract_body_path: od_radius={od_radius:.4f} cm")

    id_radius = _find_id_radius(body, od_radius)
    cylinders, tori = _classify_od_faces(body, od_radius)
    futil.log(f"extract_body_path: cylinders={len(cylinders)}, tori={len(tori)}")

    if not cylinders and not tori:
        futil.log("extract_body_path: FAIL — no OD faces after classification")
        return None

    # Filter out cope artifact torus faces (tiny bend angles from tube
    # intersections) — these are NOT real bends in the tube path.
    tori = _filter_artifact_tori(tori)
    futil.log(f"extract_body_path: after torus filter: cylinders={len(cylinders)}, tori={len(tori)}")

    all_od_faces = cylinders + tori
    adjacency = _build_adjacency(all_od_faces)

    # Order path — use torus-anchored walk when bends exist
    if tori:
        ordered = _order_path_via_tori(cylinders, tori, adjacency)
    else:
        # For straight tubes (no tori), filter cope artifact cylinders.
        # These are OD-radius faces from receiving tubes that have a
        # different axis than the main tube.
        filtered_cyls = _filter_coaxial_cylinders(cylinders)
        if len(filtered_cyls) < len(cylinders):
            futil.log(
                f"  filtered {len(cylinders) - len(filtered_cyls)} "
                f"non-coaxial cope artifact(s)"
            )
            cylinders = filtered_cyls
            all_od_faces = cylinders + tori
            adjacency = _build_adjacency(all_od_faces)
        ordered = _order_path_endpoints(cylinders, tori, adjacency)

    futil.log(f"extract_body_path: ordered path has {len(ordered)} faces")

    if not ordered:
        futil.log("extract_body_path: FAIL — could not order path")
        return None

    # Extend terminal straights with coaxial adjacent cylinder faces
    # (cope cuts can split a terminal straight into pieces)
    cyl_set = {idx for idx, _ in cylinders}
    group_faces = _extend_terminal_straights(ordered, adjacency, cyl_set)

    # Build segments
    segments: list[BodyFaceSegment] = []
    clr_values: list[float] = []

    for idx, ftype, face in ordered:
        if ftype == "straight":
            faces_in_group = group_faces.get(idx, [face])
            segments.append(_extract_cylinder_segment_from_faces(faces_in_group))
        elif ftype == "bend":
            seg = _extract_torus_segment(face)
            segments.append(seg)
            clr_values.append(seg.clr)

    # CLR consistency
    clr_consistent = True
    if len(clr_values) > 1:
        first = clr_values[0]
        tolerance = max(first * 0.002, 0.001)
        clr_consistent = all(
            abs(c - first) <= tolerance for c in clr_values
        )

    # Detect cope ends
    start_is_coped = False
    end_is_coped = False
    if segments:
        if segments[0].face_type == "straight":
            start_is_coped = segments[0].non_circle_edges > 0
        if segments[-1].face_type == "straight":
            end_is_coped = segments[-1].non_circle_edges > 0

    # Determine start/end points using group faces
    if len(ordered) == 1:
        # Single-segment path — compute both endpoints from the same face
        idx, ftype, face = ordered[0]
        if ftype == "straight":
            faces = group_faces.get(idx, [face])
            start_point, end_point = _compute_single_segment_endpoints(faces)
        else:
            center = face.geometry.origin
            start_point = end_point = (center.x, center.y, center.z)
    else:
        start_point = _get_path_start_point_grouped(ordered, group_faces)
        end_point = _get_path_end_point_grouped(ordered, group_faces)

    futil.log(
        f"extract_body_path: OK — {len(segments)} segments, "
        f"start_coped={start_is_coped}, end_coped={end_is_coped}"
    )

    return BodyPathResult(
        segments=segments,
        od_radius=od_radius,
        id_radius=id_radius,
        clr_values=clr_values,
        clr_consistent=clr_consistent,
        start_is_coped=start_is_coped,
        end_is_coped=end_is_coped,
        start_point=start_point,
        end_point=end_point,
    )


def detect_receiving_tubes(
    body: adsk.fusion.BRepBody,
    cope_end_point: Point3D,
    component: adsk.fusion.Component,
) -> list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]]:
    """Find receiving tubes near a cope end point.

    For each other body in the component, checks if its largest cylinder
    axis passes near the cope endpoint. Returns matches sorted by
    distance.

    Args:
        body: The incoming tube body (excluded from results).
        cope_end_point: The center point of the coped end (cm).
        component: The parent component containing all bodies.

    Returns:
        List of (body, axis, od_radius, axis_origin) tuples for receiving
        tubes, sorted by closest first. All values in cm.
    """
    results: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D, float]] = []

    body_count = component.bRepBodies.count

    for i in range(body_count):
        other = component.bRepBodies.item(i)
        if other.entityToken == body.entityToken:
            continue
        if not other.isVisible:
            continue

        od_r = _find_od_radius(other)
        if od_r is None:
            continue

        # Find the OD cylinder face whose axis passes closest to the
        # cope point.  For bent tubes, the largest face may be far from
        # the junction — its axis would represent the wrong tube section.
        best_dist = float("inf")
        best_axis: Vector3D | None = None
        best_origin: Point3D | None = None

        for j in range(other.faces.count):
            face = other.faces.item(j)
            if face.geometry.surfaceType != 1:  # Cylinder
                continue
            if abs(face.geometry.radius - od_r) > OD_FILTER_TOLERANCE_CM:
                continue
            cyl = face.geometry
            face_axis: Vector3D = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
            face_origin: Point3D = (cyl.origin.x, cyl.origin.y, cyl.origin.z)
            try:
                norm = normalize(face_axis)
            except ValueError:
                continue
            d = point_to_line_distance(cope_end_point, face_origin, norm)
            if d < best_dist:
                best_dist = d
                best_axis = face_axis
                best_origin = face_origin

        if best_axis is None or best_origin is None:
            continue

        try:
            norm_axis = normalize(best_axis)
        except ValueError:
            continue

        dist = best_dist
        threshold = od_r * 1.5

        if dist >= threshold:
            continue

        # Axis passes near the cope point — verify the cope point is near
        # the physical tube body, not just its infinite axis extension.
        overshoot = _axial_overshoot(
            cope_end_point, best_origin, norm_axis, other,
        )
        overshoot_limit = od_r * 3.0
        if overshoot > overshoot_limit:
            futil.log(
                f"  REJECTED {other.name}: axis passes near cope point "
                f"but body is {overshoot:.1f}cm beyond along axis"
            )
            continue

        futil.log(
            f"  MATCH {other.name}: OD_r={od_r:.4f}cm, dist={dist:.4f}cm"
        )
        results.append((other, best_axis, od_r, best_origin, dist))

    # Sort by distance, return without the sort key
    results.sort(key=lambda x: x[4])
    return [(r[0], r[1], r[2], r[3]) for r in results]


def detect_receiving_tubes_assembly(
    body: adsk.fusion.BRepBody,
    cope_end_point: Point3D,
    design: adsk.fusion.Design,
    incoming_od_r: float | None = None,
) -> list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D]]:
    """Find receiving tubes near a cope end point across the entire assembly.

    Searches all bodies in the assembly (root component + all occurrences)
    using proxy bodies in assembly coordinates. This handles the common case
    where incoming and receiving tubes are in different components.

    Args:
        body: The incoming tube body (excluded from results).
        cope_end_point: The center point of the coped end (assembly coords).
        design: The active Fusion design.
        incoming_od_r: OD radius of the incoming tube (cm). Used to reject
            non-tube bodies (panels, brackets) with unreasonably large OD.

    Returns:
        List of (body, axis, od_radius, axis_origin) tuples for receiving
        tubes, sorted by closest first. All geometry in assembly coordinates.
    """
    results: list[tuple[adsk.fusion.BRepBody, Vector3D, float, Point3D, float]] = []
    body_token = body.entityToken
    checked = 0
    max_od_r = incoming_od_r * MAX_RECEIVING_OD_RATIO if incoming_od_r else None

    skipped_hidden = 0

    skipped_occs = 0

    def _check(other: adsk.fusion.BRepBody) -> None:
        nonlocal checked, skipped_hidden
        if other.entityToken == body_token:
            return
        if not other.isVisible:
            skipped_hidden += 1
            return
        checked += 1

        od_r = _find_od_radius(other)
        if od_r is None:
            return

        # Reject non-tube bodies with unreasonably large OD
        if max_od_r is not None and od_r > max_od_r:
            return

        # Find the OD cylinder face whose axis passes closest to the
        # cope point.  For bent tubes, the largest face may be far from
        # the junction — its axis would represent the wrong tube section.
        best_dist = float("inf")
        best_axis: Vector3D | None = None
        best_origin: Point3D | None = None

        for j in range(other.faces.count):
            face = other.faces.item(j)
            if face.geometry.surfaceType != 1:  # Cylinder
                continue
            if abs(face.geometry.radius - od_r) > OD_FILTER_TOLERANCE_CM:
                continue
            cyl = face.geometry
            face_axis: Vector3D = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
            face_origin: Point3D = (cyl.origin.x, cyl.origin.y, cyl.origin.z)
            try:
                norm = normalize(face_axis)
            except ValueError:
                continue
            d = point_to_line_distance(cope_end_point, face_origin, norm)
            if d < best_dist:
                best_dist = d
                best_axis = face_axis
                best_origin = face_origin

        if best_axis is None or best_origin is None:
            return

        try:
            norm_axis = normalize(best_axis)
        except ValueError:
            return

        dist = best_dist
        threshold = od_r * 1.5

        if dist >= threshold:
            return

        # Axis passes near the cope point — verify the cope point is near
        # the physical tube body, not just its infinite axis extension.
        overshoot = _axial_overshoot(
            cope_end_point, best_origin, norm_axis, other,
        )
        overshoot_limit = od_r * 3.0
        if overshoot > overshoot_limit:
            futil.log(
                f"  REJECTED {other.name}: axis passes near cope point "
                f"but body is {overshoot:.1f}cm beyond along axis"
            )
            return

        futil.log(
            f"  MATCH {other.name}: OD_r={od_r:.4f}cm, dist={dist:.4f}cm"
        )
        results.append((other, best_axis, od_r, best_origin, dist))

    root = design.rootComponent

    # Check root component bodies
    for i in range(root.bRepBodies.count):
        _check(root.bRepBodies.item(i))

    # Check all occurrences (proxy bodies in assembly coordinates)
    all_occs = root.allOccurrences
    for i in range(all_occs.count):
        occ = all_occs.item(i)
        if not occ.isVisible:
            skipped_occs += 1
            continue
        for j in range(occ.bRepBodies.count):
            _check(occ.bRepBodies.item(j))

    futil.log(
        f"detect_receiving_assembly: checked {checked} bodies, "
        f"skipped {skipped_hidden} hidden bodies + {skipped_occs} hidden occurrences, "
        f"found {len(results)} matches"
    )

    results.sort(key=lambda x: x[4])
    return [(r[0], r[1], r[2], r[3]) for r in results]


# ---------------------------------------------------------------------------
# Private helpers — receiver proximity
# ---------------------------------------------------------------------------


def _axial_overshoot(
    point: Point3D,
    axis_origin: Point3D,
    axis_dir: Vector3D,
    body: adsk.fusion.BRepBody,
) -> float:
    """Compute how far a point extends beyond a body's extent along an axis.

    Projects the body's bounding box corners onto the axis to find the
    body's axial extent, then checks if the point projects beyond that range.

    This catches false positives where a tube's *infinite* axis line passes
    near the cope point but the physical tube body is far away.

    Args:
        point: The query point (cope endpoint, cm).
        axis_origin: A point on the axis (cylinder geometry origin, cm).
        axis_dir: Normalized axis direction.
        body: The candidate receiving tube body.

    Returns:
        0.0 if the point is within the axial extent, or the overshoot
        distance in cm if it extends beyond.
    """
    bbox = body.boundingBox
    t_min = float("inf")
    t_max = float("-inf")

    for x in (bbox.minPoint.x, bbox.maxPoint.x):
        for y in (bbox.minPoint.y, bbox.maxPoint.y):
            for z in (bbox.minPoint.z, bbox.maxPoint.z):
                dx = x - axis_origin[0]
                dy = y - axis_origin[1]
                dz = z - axis_origin[2]
                t = dx * axis_dir[0] + dy * axis_dir[1] + dz * axis_dir[2]
                t_min = min(t_min, t)
                t_max = max(t_max, t)

    # Project the query point onto the axis
    dx = point[0] - axis_origin[0]
    dy = point[1] - axis_origin[1]
    dz = point[2] - axis_origin[2]
    t_point = dx * axis_dir[0] + dy * axis_dir[1] + dz * axis_dir[2]

    if t_point < t_min:
        return t_min - t_point
    if t_point > t_max:
        return t_point - t_max
    return 0.0


# ---------------------------------------------------------------------------
# Private helpers — tube dimensions
# ---------------------------------------------------------------------------


def _find_od_radius(body: adsk.fusion.BRepBody) -> float | None:
    """Find the outer diameter radius (largest cylinder by total face area)."""
    radii: dict[float, float] = {}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType == 1:  # Cylinder
            r = round(face.geometry.radius, 4)
            radii[r] = radii.get(r, 0) + face.area
    if not radii:
        return None
    return max(radii, key=lambda k: radii[k])


def _find_id_radius(
    body: adsk.fusion.BRepBody,
    od_radius: float,
) -> float | None:
    """Find the inner diameter radius (second largest cylinder by area)."""
    radii: dict[float, float] = {}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType == 1:  # Cylinder
            r = round(face.geometry.radius, 4)
            if abs(r - od_radius) > OD_FILTER_TOLERANCE_CM:
                radii[r] = radii.get(r, 0) + face.area
    if not radii:
        return None
    return max(radii, key=lambda k: radii[k])


# ---------------------------------------------------------------------------
# Private helpers — face classification
# ---------------------------------------------------------------------------


def _classify_od_faces(
    body: adsk.fusion.BRepBody,
    od_radius: float,
) -> tuple[list[tuple[int, adsk.fusion.BRepFace]], list[tuple[int, adsk.fusion.BRepFace]]]:
    """Classify OD faces into cylinders (straights) and tori (bends).

    Returns (cylinders, tori) where each is a list of (face_index, face).
    """
    cylinders: list[tuple[int, adsk.fusion.BRepFace]] = []
    tori: list[tuple[int, adsk.fusion.BRepFace]] = []

    for i in range(body.faces.count):
        face = body.faces.item(i)
        st = face.geometry.surfaceType

        if st == 1:  # Cylinder
            if abs(face.geometry.radius - od_radius) < OD_FILTER_TOLERANCE_CM:
                cylinders.append((i, face))
        elif st == 4:  # Torus
            torus = face.geometry
            if abs(torus.minorRadius - od_radius) < OD_FILTER_TOLERANCE_CM:
                tori.append((i, face))

    return cylinders, tori


def _filter_artifact_tori(
    tori: list[tuple[int, adsk.fusion.BRepFace]],
) -> list[tuple[int, adsk.fusion.BRepFace]]:
    """Remove torus faces with bend angles below the minimum threshold.

    Cope cuts (cylinder-cylinder intersections) can create small torus
    faces at the joint. These have very small bend angles and should not
    be treated as real bends in the tube path.

    Args:
        tori: List of (face_index, face) from face classification.

    Returns:
        Filtered list with artifact tori removed.
    """
    filtered: list[tuple[int, adsk.fusion.BRepFace]] = []
    for idx, face in tori:
        angle = _get_torus_bend_angle(face)
        if angle is not None and angle >= MIN_BEND_ANGLE_DEG:
            filtered.append((idx, face))
        else:
            futil.log(
                f"  filtered torus face {idx}: "
                f"bend_angle={angle:.2f}° < {MIN_BEND_ANGLE_DEG}°"
                if angle is not None
                else f"  filtered torus face {idx}: no measurable bend angle"
            )
    return filtered


def _filter_coaxial_cylinders(
    cylinders: list[tuple[int, adsk.fusion.BRepFace]],
) -> list[tuple[int, adsk.fusion.BRepFace]]:
    """Filter OD cylinders to only faces coaxial with the dominant axis.

    For straight tubes (no tori), cope artifact cylinder faces from
    receiving tubes of the same OD pass the radius filter but have a
    different axis. This function keeps only faces whose axis is
    parallel to the largest cylinder face.

    Args:
        cylinders: List of (face_index, face) from face classification.

    Returns:
        Filtered list with non-coaxial artifacts removed.
    """
    if len(cylinders) <= 1:
        return cylinders

    # Dominant axis from largest face by area
    _, largest_face = max(cylinders, key=lambda c: c[1].area)
    dom = largest_face.geometry.axis

    filtered: list[tuple[int, adsk.fusion.BRepFace]] = []
    for idx, face in cylinders:
        ax = face.geometry.axis
        dot = abs(dom.x * ax.x + dom.y * ax.y + dom.z * ax.z)
        if dot > math.cos(math.radians(COAXIAL_MERGE_ANGLE_DEG)):
            filtered.append((idx, face))
        else:
            futil.log(f"  filtered non-coaxial cylinder face {idx}")

    return filtered


# ---------------------------------------------------------------------------
# Private helpers — adjacency and ordering
# ---------------------------------------------------------------------------


def _shared_edge(
    face_a: adsk.fusion.BRepFace,
    face_b: adsk.fusion.BRepFace,
) -> adsk.fusion.BRepEdge | None:
    """Find the shared edge between two faces, or None."""
    for i in range(face_a.edges.count):
        edge_a = face_a.edges.item(i)
        for j in range(face_b.edges.count):
            edge_b = face_b.edges.item(j)
            if edge_a.tempId == edge_b.tempId:
                return edge_a
    return None


def _build_adjacency(
    faces: list[tuple[int, adsk.fusion.BRepFace]],
) -> dict[int, list[tuple[int, adsk.fusion.BRepEdge]]]:
    """Build adjacency map: face_index -> list of (neighbor_index, shared_edge)."""
    adjacency: dict[int, list[tuple[int, adsk.fusion.BRepEdge]]] = {
        idx: [] for idx, _ in faces
    }

    for i in range(len(faces)):
        idx_a, face_a = faces[i]
        for j in range(i + 1, len(faces)):
            idx_b, face_b = faces[j]
            edge = _shared_edge(face_a, face_b)
            if edge is not None:
                adjacency[idx_a].append((idx_b, edge))
                adjacency[idx_b].append((idx_a, edge))

    return adjacency


def _order_path_via_tori(
    cylinders: list[tuple[int, adsk.fusion.BRepFace]],
    tori: list[tuple[int, adsk.fusion.BRepFace]],
    adjacency: dict[int, list[tuple[int, adsk.fusion.BRepEdge]]],
) -> list[tuple[int, str, adsk.fusion.BRepFace]]:
    """Build ordered path anchored by tori.

    Cope cuts create OD-radius cylinder faces from the receiving tube
    geometry (cope artifacts). These artifacts are adjacent to path
    cylinders but NOT to tori. By anchoring the walk on tori, we
    naturally exclude artifacts.

    Algorithm:
    1. Find cylinders adjacent to tori (guaranteed path members).
    2. Start from a terminal cylinder (adjacent to exactly 1 torus).
    3. Walk: cylinder → torus → cylinder → torus → ...

    Returns ordered list of (face_index, face_type, face).
    """
    cyl_set = {idx for idx, _ in cylinders}
    torus_set = {idx for idx, _ in tori}
    all_faces: dict[int, tuple[str, adsk.fusion.BRepFace]] = {
        idx: ("straight", face) for idx, face in cylinders
    }
    all_faces.update({idx: ("bend", face) for idx, face in tori})

    # Map cylinders to their torus neighbors and vice versa
    cyl_to_tori: dict[int, list[int]] = {}
    for c_idx in cyl_set:
        tori_nbrs = [n for n, _ in adjacency.get(c_idx, []) if n in torus_set]
        if tori_nbrs:
            cyl_to_tori[c_idx] = tori_nbrs

    torus_to_cyls: dict[int, list[int]] = {}
    for t_idx in torus_set:
        cyl_nbrs = [n for n, _ in adjacency.get(t_idx, []) if n in cyl_to_tori]
        torus_to_cyls[t_idx] = cyl_nbrs

    path_cyls = set(cyl_to_tori.keys())
    futil.log(
        f"  torus-anchored: {len(path_cyls)} path cylinders "
        f"(of {len(cyl_set)} total), {len(torus_set)} tori"
    )

    if not path_cyls:
        return []

    # Find terminal cylinders (adjacent to exactly 1 torus)
    terminal_cyls = [c for c, t_list in cyl_to_tori.items() if len(t_list) == 1]

    if terminal_cyls:
        start_cyl = terminal_cyls[0]
    else:
        # All path cylinders connect to 2+ tori — pick any
        start_cyl = next(iter(path_cyls))

    # Walk: cylinder → torus → cylinder → torus → ...
    ordered: list[tuple[int, str, adsk.fusion.BRepFace]] = []
    visited_cyls: set[int] = set()
    visited_tori: set[int] = set()

    current: int | None = start_cyl
    while current is not None:
        visited_cyls.add(current)
        ordered.append((current, "straight", all_faces[current][1]))

        # Find unvisited torus neighbor
        next_torus: int | None = None
        for t in cyl_to_tori.get(current, []):
            if t not in visited_tori:
                next_torus = t
                break

        if next_torus is None:
            break  # End of path

        visited_tori.add(next_torus)
        ordered.append((next_torus, "bend", all_faces[next_torus][1]))

        # Find the cylinder on the other side of this torus
        next_cyl: int | None = None
        for c in torus_to_cyls.get(next_torus, []):
            if c not in visited_cyls:
                next_cyl = c
                break

        current = next_cyl

    futil.log(f"  torus-anchored path: {[idx for idx, _, _ in ordered]}")
    return ordered


def _order_path_endpoints(
    cylinders: list[tuple[int, adsk.fusion.BRepFace]],
    tori: list[tuple[int, adsk.fusion.BRepFace]],
    adjacency: dict[int, list[tuple[int, adsk.fusion.BRepEdge]]],
) -> list[tuple[int, str, adsk.fusion.BRepFace]]:
    """Walk adjacency graph using endpoint detection.

    Fallback for straight tubes (no tori). Finds faces with <=1
    neighbor and walks from one endpoint to the other.
    """
    all_faces: dict[int, tuple[str, adsk.fusion.BRepFace]] = {
        idx: ("straight", face) for idx, face in cylinders
    }
    all_faces.update({idx: ("bend", face) for idx, face in tori})

    endpoints: list[int] = []
    for idx in all_faces:
        neighbors = [n for n, _ in adjacency.get(idx, []) if n in all_faces]
        if len(neighbors) <= 1:
            endpoints.append(idx)

    if not endpoints:
        return []

    # Prefer starting from a cylinder endpoint
    start = endpoints[0]
    for ep in endpoints:
        if all_faces[ep][0] == "straight":
            start = ep
            break

    ordered: list[tuple[int, str, adsk.fusion.BRepFace]] = []
    visited: set[int] = set()
    current: int | None = start

    while current is not None:
        visited.add(current)
        ftype, face = all_faces[current]
        ordered.append((current, ftype, face))

        next_face: int | None = None
        for neighbor, _ in adjacency.get(current, []):
            if neighbor not in visited and neighbor in all_faces:
                next_face = neighbor
                break
        current = next_face

    return ordered


def _extend_terminal_straights(
    ordered: list[tuple[int, str, adsk.fusion.BRepFace]],
    adjacency: dict[int, list[tuple[int, adsk.fusion.BRepEdge]]],
    cyl_set: set[int],
) -> dict[int, list[adsk.fusion.BRepFace]]:
    """Extend terminal straights by absorbing coaxial adjacent cylinders.

    When cope cuts split a terminal straight into pieces, the torus-
    anchored walk only picks up the piece adjacent to the torus. This
    function finds additional coaxial cylinder faces adjacent to the
    terminal faces and includes them in the face group for geometry
    extraction.

    Args:
        ordered: The ordered path from the walk.
        adjacency: Full adjacency map.
        cyl_set: Set of all cylinder face indices.

    Returns:
        Map from path cylinder index → list of all faces in its group.
    """
    group_faces: dict[int, list[adsk.fusion.BRepFace]] = {}
    path_indices = {idx for idx, _, _ in ordered}

    for idx, ftype, face in ordered:
        if ftype != "straight":
            continue

        faces = [face]

        # Find adjacent cylinders NOT already in the path
        for neighbor, _ in adjacency.get(idx, []):
            if neighbor in path_indices or neighbor not in cyl_set:
                continue
            # Check if coaxial with this face
            nbr_face = _face_from_adjacency(adjacency, neighbor, cyl_set)
            if nbr_face is not None and _are_coaxial(face, nbr_face):
                faces.append(nbr_face)
                futil.log(f"  extended face {idx} with coaxial face {neighbor}")

        group_faces[idx] = faces

    return group_faces


def _face_from_adjacency(
    adjacency: dict[int, list[tuple[int, adsk.fusion.BRepEdge]]],
    target_idx: int,
    cyl_set: set[int],
) -> adsk.fusion.BRepFace | None:
    """Retrieve a face object from the adjacency graph by index.

    Looks through neighbors of faces adjacent to target_idx to find
    the actual face object.
    """
    for _idx, neighbors in adjacency.items():
        for nbr_idx, edge in neighbors:
            if nbr_idx == target_idx:
                for k in range(edge.faces.count):
                    f = edge.faces.item(k)
                    if f.geometry.surfaceType == 1:  # Cylinder
                        if _shared_edge_exists_between(f, adjacency, target_idx):
                            return f
    return None


def _shared_edge_exists_between(
    face: adsk.fusion.BRepFace,
    adjacency: dict[int, list[tuple[int, adsk.fusion.BRepEdge]]],
    target_idx: int,
) -> bool:
    """Check if a face has a shared edge with the target index."""
    for _idx, neighbors in adjacency.items():
        for nbr_idx, _ in neighbors:
            if nbr_idx == target_idx:
                return True
    return False


def _are_coaxial(
    face_a: adsk.fusion.BRepFace,
    face_b: adsk.fusion.BRepFace,
) -> bool:
    """Check if two cylinder faces are coaxial (same axis line)."""
    cyl_a = face_a.geometry
    cyl_b = face_b.geometry

    dot = abs(
        cyl_a.axis.x * cyl_b.axis.x
        + cyl_a.axis.y * cyl_b.axis.y
        + cyl_a.axis.z * cyl_b.axis.z
    )
    if dot < math.cos(math.radians(COAXIAL_MERGE_ANGLE_DEG)):
        return False

    origin_b: Point3D = (cyl_b.origin.x, cyl_b.origin.y, cyl_b.origin.z)
    origin_a: Point3D = (cyl_a.origin.x, cyl_a.origin.y, cyl_a.origin.z)
    axis_a: Vector3D = (cyl_a.axis.x, cyl_a.axis.y, cyl_a.axis.z)

    try:
        dist = point_to_line_distance(origin_b, origin_a, axis_a)
    except (ValueError, ZeroDivisionError):
        return False

    return dist < COAXIAL_MERGE_DISTANCE_CM


# ---------------------------------------------------------------------------
# Private helpers — geometry extraction
# ---------------------------------------------------------------------------


def _extract_cylinder_segment_from_faces(
    faces: list[adsk.fusion.BRepFace],
) -> BodyFaceSegment:
    """Extract geometry from one or more coaxial cylinder faces.

    When a cope cut splits a cylinder, this function collects circle
    edge centers and non-circle edges from ALL faces in the group.
    """
    if not faces:
        raise ValueError("No faces provided")

    cyl = faces[0].geometry
    axis: Vector3D = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
    origin: Point3D = (cyl.origin.x, cyl.origin.y, cyl.origin.z)

    all_centers: list[Point3D] = []
    non_circle_edges = 0
    seen_edge_ids: set[int] = set()

    for face in faces:
        for i in range(face.edges.count):
            edge = face.edges.item(i)
            eid = edge.tempId
            if eid in seen_edge_ids:
                continue
            seen_edge_ids.add(eid)

            if edge.geometry.curveType == 2:  # Circle
                c = edge.geometry.center
                center: Point3D = (c.x, c.y, c.z)
                is_dup = False
                for existing in all_centers:
                    if _dist_sq(center, existing) < 0.0001:
                        is_dup = True
                        break
                if not is_dup:
                    all_centers.append(center)
            else:
                non_circle_edges += 1

    start_center: Point3D | None = None
    end_center: Point3D | None = None

    if len(all_centers) >= 2:
        max_dist = -1.0
        best_i, best_j = 0, 1
        for i in range(len(all_centers)):
            for j in range(i + 1, len(all_centers)):
                d = _dist_sq(all_centers[i], all_centers[j])
                if d > max_dist:
                    max_dist = d
                    best_i, best_j = i, j
        start_center = all_centers[best_i]
        end_center = all_centers[best_j]
    elif len(all_centers) == 1:
        start_center = all_centers[0]

    if start_center is not None and end_center is not None:
        dx = end_center[0] - start_center[0]
        dy = end_center[1] - start_center[1]
        dz = end_center[2] - start_center[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
    else:
        largest = max(faces, key=lambda f: f.area)
        length = _get_cylinder_length_bbox(largest)

    return BodyFaceSegment(
        face_type="straight",
        axis=axis,
        origin=origin,
        length=length,
        start_center=start_center,
        end_center=end_center,
        non_circle_edges=non_circle_edges,
    )


def _get_cylinder_length_bbox(face: adsk.fusion.BRepFace) -> float:
    """Calculate cylinder length by projecting bounding box onto axis."""
    axis = face.geometry.axis
    origin = face.geometry.origin
    bbox = face.boundingBox

    projections: list[float] = []
    for corner in (bbox.minPoint, bbox.maxPoint):
        dx = corner.x - origin.x
        dy = corner.y - origin.y
        dz = corner.z - origin.z
        proj = dx * axis.x + dy * axis.y + dz * axis.z
        projections.append(proj)

    return abs(max(projections) - min(projections))


def _extract_torus_segment(face: adsk.fusion.BRepFace) -> BodyFaceSegment:
    """Extract geometry from a torus (bend) face."""
    torus = face.geometry
    clr = torus.majorRadius
    torus_axis: Vector3D = (torus.axis.x, torus.axis.y, torus.axis.z)
    torus_origin: Point3D = (torus.origin.x, torus.origin.y, torus.origin.z)

    bend_angle = _get_torus_bend_angle(face) or 0.0

    return BodyFaceSegment(
        face_type="bend",
        bend_angle=bend_angle,
        clr=clr,
        torus_axis=torus_axis,
        torus_origin=torus_origin,
    )


def _get_torus_bend_angle(face: adsk.fusion.BRepFace) -> float | None:
    """Extract the bend angle from a torus face.

    Computed from the two circle edges where torus meets cylinders,
    projected onto the plane perpendicular to the torus axis.
    """
    torus = face.geometry
    center = torus.origin
    axis = torus.axis

    circle_centers: list[adsk.core.Point3D] = []
    for i in range(face.edges.count):
        edge = face.edges.item(i)
        if edge.geometry.curveType == 2:  # Circle
            circle_centers.append(edge.geometry.center)

    if len(circle_centers) < 2:
        return None

    v1 = adsk.core.Vector3D.create(
        circle_centers[0].x - center.x,
        circle_centers[0].y - center.y,
        circle_centers[0].z - center.z,
    )
    v2 = adsk.core.Vector3D.create(
        circle_centers[1].x - center.x,
        circle_centers[1].y - center.y,
        circle_centers[1].z - center.z,
    )

    d1 = v1.x * axis.x + v1.y * axis.y + v1.z * axis.z
    v1_proj = adsk.core.Vector3D.create(
        v1.x - d1 * axis.x, v1.y - d1 * axis.y, v1.z - d1 * axis.z,
    )
    d2 = v2.x * axis.x + v2.y * axis.y + v2.z * axis.z
    v2_proj = adsk.core.Vector3D.create(
        v2.x - d2 * axis.x, v2.y - d2 * axis.y, v2.z - d2 * axis.z,
    )

    mag1 = math.sqrt(v1_proj.x ** 2 + v1_proj.y ** 2 + v1_proj.z ** 2)
    mag2 = math.sqrt(v2_proj.x ** 2 + v2_proj.y ** 2 + v2_proj.z ** 2)
    if mag1 < 1e-8 or mag2 < 1e-8:
        return None

    dot = v1_proj.x * v2_proj.x + v1_proj.y * v2_proj.y + v1_proj.z * v2_proj.z
    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


# ---------------------------------------------------------------------------
# Private helpers — path endpoints
# ---------------------------------------------------------------------------


def _get_circle_centers_from_faces(
    faces: list[adsk.fusion.BRepFace],
) -> list[Point3D]:
    """Get deduplicated circle edge centers from one or more faces."""
    centers: list[Point3D] = []
    seen_edge_ids: set[int] = set()

    for face in faces:
        for i in range(face.edges.count):
            edge = face.edges.item(i)
            if edge.tempId in seen_edge_ids:
                continue
            seen_edge_ids.add(edge.tempId)

            if edge.geometry.curveType == 2:  # Circle
                c = edge.geometry.center
                center: Point3D = (c.x, c.y, c.z)
                is_dup = False
                for existing in centers:
                    if _dist_sq(center, existing) < 0.0001:
                        is_dup = True
                        break
                if not is_dup:
                    centers.append(center)

    return centers


def _get_path_start_point_grouped(
    ordered: list[tuple[int, str, adsk.fusion.BRepFace]],
    group_faces: dict[int, list[adsk.fusion.BRepFace]],
) -> Point3D:
    """Get the center point at the start of the ordered path."""
    if not ordered:
        return (0.0, 0.0, 0.0)

    idx, ftype, face = ordered[0]
    if ftype == "straight":
        faces = group_faces.get(idx, [face])
        centers = _get_circle_centers_from_faces(faces)

        # Get the reference point from the next segment
        next_ref: Point3D | None = None
        if len(ordered) > 1:
            next_idx, _, next_face = ordered[1]
            next_faces = group_faces.get(next_idx, [next_face])
            next_centers = _get_circle_centers_from_faces(next_faces)
            if next_centers:
                next_ref = next_centers[0]

        if centers and len(centers) >= 2 and next_ref:
            return _farther_center(centers, next_ref)

        # Only 1 circle center or no next reference — use axis extrapolation
        # to find the actual endpoint (important for coped ends where the
        # outer circle edge is replaced by the cope profile)
        if next_ref:
            extreme = _axis_extreme_point(faces, next_ref, away=True)
            if extreme:
                return extreme

        if centers:
            return centers[0]
    elif ftype == "bend":
        center = face.geometry.origin
        return (center.x, center.y, center.z)

    return (0.0, 0.0, 0.0)


def _get_path_end_point_grouped(
    ordered: list[tuple[int, str, adsk.fusion.BRepFace]],
    group_faces: dict[int, list[adsk.fusion.BRepFace]],
) -> Point3D:
    """Get the center point at the end of the ordered path."""
    if not ordered:
        return (0.0, 0.0, 0.0)

    idx, ftype, face = ordered[-1]
    if ftype == "straight":
        faces = group_faces.get(idx, [face])
        centers = _get_circle_centers_from_faces(faces)

        # Get the reference point from the previous segment
        prev_ref: Point3D | None = None
        if len(ordered) > 1:
            prev_idx, _, prev_face = ordered[-2]
            prev_faces = group_faces.get(prev_idx, [prev_face])
            prev_centers = _get_circle_centers_from_faces(prev_faces)
            if prev_centers:
                prev_ref = prev_centers[0]

        if centers and len(centers) >= 2 and prev_ref:
            return _farther_center(centers, prev_ref)

        # Only 1 circle center — use axis extrapolation for coped ends
        if prev_ref:
            extreme = _axis_extreme_point(faces, prev_ref, away=True)
            if extreme:
                return extreme

        if centers:
            return centers[-1] if len(centers) > 1 else centers[0]
    elif ftype == "bend":
        center = face.geometry.origin
        return (center.x, center.y, center.z)

    return (0.0, 0.0, 0.0)


def _axis_extreme_point(
    faces: list[adsk.fusion.BRepFace],
    reference: Point3D,
    away: bool = True,
) -> Point3D | None:
    """Find the centerline point at the axial extreme of cylinder faces.

    Projects bounding box corners onto the cylinder axis to find the
    two extreme center points along the axis, then returns the one
    that is farthest from (away=True) or nearest to (away=False)
    the reference point.

    This is critical for coped ends where the cope profile replaces
    the circle edge, leaving no circle center at the tube endpoint.

    Args:
        faces: One or more coaxial cylinder faces.
        reference: Reference point (typically from the adjacent segment).
        away: If True, return the extreme farthest from reference.

    Returns:
        The extreme center point, or None if no cylinder face found.
    """
    # Find a cylinder face for axis info
    cyl_face: adsk.fusion.BRepFace | None = None
    for f in faces:
        if f.geometry.surfaceType == 1:  # Cylinder
            cyl_face = f
            break
    if cyl_face is None:
        return None

    cyl = cyl_face.geometry
    axis: Vector3D = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
    origin: Point3D = (cyl.origin.x, cyl.origin.y, cyl.origin.z)

    # Project all bounding box corners from all faces onto the axis
    projections: list[float] = []
    for f in faces:
        if f.geometry.surfaceType != 1:
            continue
        bbox = f.boundingBox
        for corner in (bbox.minPoint, bbox.maxPoint):
            dx = corner.x - origin[0]
            dy = corner.y - origin[1]
            dz = corner.z - origin[2]
            proj = dx * axis[0] + dy * axis[1] + dz * axis[2]
            projections.append(proj)

    if not projections:
        return None

    min_proj = min(projections)
    max_proj = max(projections)

    center_min: Point3D = (
        origin[0] + min_proj * axis[0],
        origin[1] + min_proj * axis[1],
        origin[2] + min_proj * axis[2],
    )
    center_max: Point3D = (
        origin[0] + max_proj * axis[0],
        origin[1] + max_proj * axis[1],
        origin[2] + max_proj * axis[2],
    )

    dist_min = _dist_sq(center_min, reference)
    dist_max = _dist_sq(center_max, reference)

    if away:
        return center_max if dist_max > dist_min else center_min
    return center_min if dist_min < dist_max else center_max


def _compute_single_segment_endpoints(
    faces: list[adsk.fusion.BRepFace],
) -> tuple[Point3D, Point3D]:
    """Compute both endpoints for a single-segment straight path.

    Handles coped ends where circle edges are replaced by the cope
    profile, using bounding box projection onto the cylinder axis.

    Returns:
        (start_point, end_point) — the two axial extremes of the
        cylinder face group.
    """
    centers = _get_circle_centers_from_faces(faces)

    if len(centers) >= 2:
        # Two+ circle edges — pick the farthest pair
        max_dist = -1.0
        best_i, best_j = 0, 1
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                d = _dist_sq(centers[i], centers[j])
                if d > max_dist:
                    max_dist = d
                    best_i, best_j = i, j
        return centers[best_i], centers[best_j]

    # Not enough circle centers — use axis extremes from bounding box
    extremes = _axis_both_extremes(faces)
    if extremes is not None:
        if len(centers) == 1:
            # One circle center (one coped end). Assign the circle
            # center to the nearer extreme, axis extreme to the coped end.
            d0 = _dist_sq(centers[0], extremes[0])
            d1 = _dist_sq(centers[0], extremes[1])
            if d0 < d1:
                # centers[0] is near extremes[0] → start=far (coped), end=near
                return extremes[1], extremes[0]
            else:
                return extremes[0], extremes[1]
        return extremes

    if centers:
        return centers[0], centers[0]
    return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)


def _axis_both_extremes(
    faces: list[adsk.fusion.BRepFace],
) -> tuple[Point3D, Point3D] | None:
    """Return both axial extreme center points of cylinder faces.

    Projects bounding box corners onto the cylinder axis to find the
    min and max projections, then returns the corresponding center
    points on the axis.
    """
    cyl_face: adsk.fusion.BRepFace | None = None
    for f in faces:
        if f.geometry.surfaceType == 1:  # Cylinder
            cyl_face = f
            break
    if cyl_face is None:
        return None

    cyl = cyl_face.geometry
    axis: Vector3D = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
    origin: Point3D = (cyl.origin.x, cyl.origin.y, cyl.origin.z)

    projections: list[float] = []
    for f in faces:
        if f.geometry.surfaceType != 1:
            continue
        bbox = f.boundingBox
        for corner in (bbox.minPoint, bbox.maxPoint):
            dx = corner.x - origin[0]
            dy = corner.y - origin[1]
            dz = corner.z - origin[2]
            proj = dx * axis[0] + dy * axis[1] + dz * axis[2]
            projections.append(proj)

    if not projections:
        return None

    min_proj = min(projections)
    max_proj = max(projections)

    center_min: Point3D = (
        origin[0] + min_proj * axis[0],
        origin[1] + min_proj * axis[1],
        origin[2] + min_proj * axis[2],
    )
    center_max: Point3D = (
        origin[0] + max_proj * axis[0],
        origin[1] + max_proj * axis[1],
        origin[2] + max_proj * axis[2],
    )

    return center_min, center_max


def _farther_center(
    centers: list[Point3D],
    reference: Point3D,
) -> Point3D:
    """Return the center that is farther from reference."""
    if not centers:
        return (0.0, 0.0, 0.0)

    best = centers[0]
    best_dist = _dist_sq(best, reference)
    for c in centers[1:]:
        d = _dist_sq(c, reference)
        if d > best_dist:
            best = c
            best_dist = d
    return best


def _dist_sq(a: Point3D, b: Point3D) -> float:
    """Squared distance between two points."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
