"""Dump complete junction geometry for cope math verification.

Select the incoming tube body, then run. The script:
1. Extracts the incoming tube's path, endpoints, and direction.
2. Finds all nearby bodies (potential receivers) at each endpoint.
3. For each receiver, lists ALL OD cylinder faces with:
   - Axis, origin, area
   - Distance from the cope point (which face is "nearest")
   - Inclination angle relative to the incoming tube
4. Shows which face our algorithm selects and the resulting math.

Output goes to the Text Command window (app.log) and junction_output.txt.
"""

import adsk.core
import adsk.fusion
import math
import traceback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_body(entity):
    if isinstance(entity, adsk.fusion.BRepBody):
        return entity
    if isinstance(entity, (adsk.fusion.BRepFace, adsk.fusion.BRepEdge)):
        return entity.body
    if isinstance(entity, adsk.fusion.Occurrence):
        comp = entity.component
        if comp.bRepBodies.count > 0:
            return comp.bRepBodies.item(0)
    if isinstance(entity, adsk.fusion.Component):
        if entity.bRepBodies.count > 0:
            return entity.bRepBodies.item(0)
    return None


def _mag(v):
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _normalize(v):
    m = _mag(v)
    if m < 1e-10:
        raise ValueError("zero vector")
    return (v[0] / m, v[1] / m, v[2] / m)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _point_to_line_dist(point, line_origin, line_dir):
    """Perpendicular distance from point to infinite line."""
    d = _normalize(line_dir)
    v = (point[0] - line_origin[0], point[1] - line_origin[1], point[2] - line_origin[2])
    t = _dot(v, d)
    proj = (line_origin[0] + t * d[0], line_origin[1] + t * d[1], line_origin[2] + t * d[2])
    dx = point[0] - proj[0]
    dy = point[1] - proj[1]
    dz = point[2] - proj[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _find_od_radius(body):
    radii = {}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType == 1:
            r = round(face.geometry.radius, 4)
            radii[r] = radii.get(r, 0) + face.area
    if not radii:
        return None
    return max(radii, key=radii.get)


def _inclination_deg(v1, v2):
    """Included angle between two directions (0-90)."""
    d = abs(_dot(v1, v2))
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


def _get_circle_centers(face):
    """Get circle edge centers from a face."""
    centers = []
    for i in range(face.edges.count):
        edge = face.edges.item(i)
        if edge.geometry.curveType == 2:
            c = edge.geometry.center
            centers.append((c.x, c.y, c.z))
    return centers


def _dist_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _get_coaxial_od_faces(body, od_r, lines):
    """Get OD cylinder faces filtered to only coaxial faces (no cope artifacts).

    Mirrors the cope code's approach:
    1. Find dominant axis from largest-area OD cylinder face.
    2. Keep only faces whose axis is parallel to the dominant axis.

    Returns list of (face_index, face) and the dominant axis tuple, plus
    any torus faces found.
    """
    tol = 0.01
    coaxial_angle_tol = math.cos(math.radians(2.0))  # COAXIAL_MERGE_ANGLE_DEG

    # Collect all OD cylinder and torus faces
    cylinders = []
    tori = []
    for i in range(body.faces.count):
        face = body.faces.item(i)
        st = face.geometry.surfaceType
        if st == 1 and abs(face.geometry.radius - od_r) < tol:
            cylinders.append((i, face))
        elif st == 4 and abs(face.geometry.minorRadius - od_r) < tol:
            tori.append((i, face))

    if not cylinders:
        return [], None, tori

    # Dominant axis from largest-area face
    _, largest = max(cylinders, key=lambda c: c[1].area)
    dom_axis = (largest.geometry.axis.x, largest.geometry.axis.y, largest.geometry.axis.z)

    # Filter to coaxial faces only
    coaxial = []
    for idx, face in cylinders:
        ax = (face.geometry.axis.x, face.geometry.axis.y, face.geometry.axis.z)
        dot_val = abs(_dot(dom_axis, ax))
        if dot_val > coaxial_angle_tol:
            coaxial.append((idx, face))
        else:
            lines.append(f"    Face {idx}: FILTERED (non-coaxial cope artifact)")

    return coaxial, dom_axis, tori


def _get_path_endpoints_and_direction(coaxial_faces, dom_axis, tori, lines):
    """Extract tube endpoints and direction from coaxial OD faces.

    Uses bounding box projection along the dominant axis to find
    the two extreme centerline points.  This works even when cope
    cuts have removed circle edges from the tube ends.

    Args:
        coaxial_faces: List of (face_index, face) — coaxial OD cylinders.
        dom_axis: Dominant axis direction tuple.
        tori: List of (face_index, face) — OD torus (bend) faces.
        lines: Output lines list for logging.

    Returns:
        (start_point, end_point, direction) or None.
    """
    if not coaxial_faces and not tori:
        return None

    try:
        norm_axis = _normalize(dom_axis)
    except ValueError:
        return None

    # Use the first coaxial cylinder's origin as the projection reference
    if coaxial_faces:
        ref_face = coaxial_faces[0][1]
        origin = (ref_face.geometry.origin.x, ref_face.geometry.origin.y, ref_face.geometry.origin.z)
    else:
        ref_face = tori[0][1]
        origin = (ref_face.geometry.origin.x, ref_face.geometry.origin.y, ref_face.geometry.origin.z)

    # Project all bounding box corners from all coaxial faces onto the axis
    t_min = float("inf")
    t_max = float("-inf")

    all_faces_to_scan = [f for _, f in coaxial_faces] + [f for _, f in tori]

    for face in all_faces_to_scan:
        bbox = face.boundingBox
        for x in (bbox.minPoint.x, bbox.maxPoint.x):
            for y in (bbox.minPoint.y, bbox.maxPoint.y):
                for z in (bbox.minPoint.z, bbox.maxPoint.z):
                    dx = x - origin[0]
                    dy = y - origin[1]
                    dz = z - origin[2]
                    t = dx * norm_axis[0] + dy * norm_axis[1] + dz * norm_axis[2]
                    if t < t_min:
                        t_min = t
                    if t > t_max:
                        t_max = t

    start_pt = (
        origin[0] + t_min * norm_axis[0],
        origin[1] + t_min * norm_axis[1],
        origin[2] + t_min * norm_axis[2],
    )
    end_pt = (
        origin[0] + t_max * norm_axis[0],
        origin[1] + t_max * norm_axis[1],
        origin[2] + t_max * norm_axis[2],
    )

    direction = _normalize((end_pt[0] - start_pt[0], end_pt[1] - start_pt[1], end_pt[2] - start_pt[2]))
    return start_pt, end_pt, direction


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        sel = ui.activeSelections
        if sel.count == 0:
            ui.messageBox("Select the incoming tube body first, then run.")
            return

        body = _get_body(sel.item(0).entity)
        if body is None:
            ui.messageBox(f"Could not find body from: {type(sel.item(0).entity).__name__}")
            return

        lines = []
        lines.append("=" * 70)
        lines.append("JUNCTION ANALYSIS — Cope Math Verification")
        lines.append("=" * 70)

        od_r = _find_od_radius(body)
        if od_r is None:
            ui.messageBox("No cylindrical faces found on selected body.")
            return

        od_in = 2 * od_r / 2.54
        lines.append(f"\nINCOMING TUBE: {body.name}")
        lines.append(f"  OD: {od_in:.4f}\" ({2*od_r:.4f} cm)")
        lines.append(f"  Faces: {body.faces.count}")

        # List all OD cylinder faces of incoming tube
        lines.append(f"\n  All OD Cylinder Faces (before filtering):")
        for i in range(body.faces.count):
            face = body.faces.item(i)
            if face.geometry.surfaceType != 1:
                continue
            if abs(face.geometry.radius - od_r) > 0.01:
                continue
            cyl = face.geometry
            axis = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
            origin = (cyl.origin.x, cyl.origin.y, cyl.origin.z)
            lines.append(
                f"    Face {i}: area={face.area:.2f}cm2, "
                f"axis=({axis[0]:.4f}, {axis[1]:.4f}, {axis[2]:.4f}), "
                f"origin=({origin[0]:.2f}, {origin[1]:.2f}, {origin[2]:.2f})"
            )
            centers = _get_circle_centers(face)
            for ci, c in enumerate(centers):
                lines.append(
                    f"      circle {ci}: ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})"
                )
            non_circ = sum(1 for j in range(face.edges.count) if face.edges.item(j).geometry.curveType != 2)
            if non_circ > 0:
                lines.append(f"      non-circle edges: {non_circ} (COPED)")

        # Filter to coaxial faces (remove cope artifacts)
        lines.append(f"\n  Coaxial filtering:")
        coaxial, dom_axis, tori = _get_coaxial_od_faces(body, od_r, lines)

        if dom_axis:
            lines.append(f"  Dominant axis: ({dom_axis[0]:.4f}, {dom_axis[1]:.4f}, {dom_axis[2]:.4f})")
            lines.append(f"  Coaxial faces kept: {len(coaxial)}")
            lines.append(f"  Torus (bend) faces: {len(tori)}")
        else:
            lines.append("  No cylinder faces found!")

        # Endpoints using coaxial faces only
        ep = _get_path_endpoints_and_direction(coaxial, dom_axis, tori, lines)
        if ep is None:
            lines.append("\n  Could not extract endpoints!")
            result = "\n".join(lines)
            app.log(result)
            ui.messageBox(result, "Junction Analysis")
            return

        start_pt, end_pt, direction = ep
        lines.append(f"\n  Endpoint A (start): ({start_pt[0]:.3f}, {start_pt[1]:.3f}, {start_pt[2]:.3f}) cm")
        lines.append(f"  Endpoint B (end):   ({end_pt[0]:.3f}, {end_pt[1]:.3f}, {end_pt[2]:.3f}) cm")
        lines.append(f"  Direction A→B:      ({direction[0]:.4f}, {direction[1]:.4f}, {direction[2]:.4f})")
        lines.append(f"  Tube length:        {math.sqrt(_dist_sq(start_pt, end_pt))/2.54:.3f}\"")

        # Search for receivers at both endpoints
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            lines.append("ERROR: No active Fusion design.")
            result = "\n".join(lines)
            app.log(result)
            ui.messageBox(result, "Junction Analysis")
            return

        body_token = body.entityToken

        # Collect all visible bodies in assembly (deduplicated by token)
        root = design.rootComponent
        all_bodies = []
        seen_tokens = {body_token}  # skip self

        for i in range(root.bRepBodies.count):
            b = root.bRepBodies.item(i)
            if b.entityToken not in seen_tokens and b.isVisible:
                seen_tokens.add(b.entityToken)
                all_bodies.append(b)

        all_occs = root.allOccurrences
        for i in range(all_occs.count):
            occ = all_occs.item(i)
            if not occ.isVisible:
                continue
            for j in range(occ.bRepBodies.count):
                b = occ.bRepBodies.item(j)
                if b.entityToken not in seen_tokens and b.isVisible:
                    seen_tokens.add(b.entityToken)
                    all_bodies.append(b)

        lines.append(f"\n  Visible bodies in assembly: {len(all_bodies)}")

        for ep_label, cope_pt, tube_dir in [
            ("ENDPOINT A (start)", start_pt, (-direction[0], -direction[1], -direction[2])),
            ("ENDPOINT B (end)", end_pt, direction),
        ]:
            lines.append(f"\n{'=' * 70}")
            lines.append(f"RECEIVERS AT {ep_label}")
            lines.append(f"  Cope point: ({cope_pt[0]:.3f}, {cope_pt[1]:.3f}, {cope_pt[2]:.3f}) cm")
            lines.append(f"  Tube direction (outward): ({tube_dir[0]:.4f}, {tube_dir[1]:.4f}, {tube_dir[2]:.4f})")
            lines.append(f"{'=' * 70}")

            receiver_count = 0

            for other in all_bodies:
                other_od_r = _find_od_radius(other)
                if other_od_r is None:
                    continue
                # Skip non-tube bodies (OD too large)
                if other_od_r > od_r * 5.0:
                    continue

                # Check all OD cylinder faces
                face_data = []
                for j in range(other.faces.count):
                    face = other.faces.item(j)
                    if face.geometry.surfaceType != 1:
                        continue
                    if abs(face.geometry.radius - other_od_r) > 0.01:
                        continue
                    cyl = face.geometry
                    face_axis = (cyl.axis.x, cyl.axis.y, cyl.axis.z)
                    face_origin = (cyl.origin.x, cyl.origin.y, cyl.origin.z)
                    try:
                        norm = _normalize(face_axis)
                    except ValueError:
                        continue
                    dist = _point_to_line_dist(cope_pt, face_origin, norm)
                    incl = _inclination_deg(tube_dir, norm)
                    face_data.append({
                        "face_idx": j,
                        "axis": face_axis,
                        "origin": face_origin,
                        "area": face.area,
                        "dist": dist,
                        "incl": incl,
                    })

                if not face_data:
                    continue

                # Find the face nearest to cope point (our algorithm's selection)
                nearest = min(face_data, key=lambda f: f["dist"])

                # Only show bodies where nearest face axis is within
                # the receiver match threshold (same as cope code)
                threshold = other_od_r * 1.5
                if nearest["dist"] > threshold:
                    continue

                receiver_count += 1
                other_od_in = 2 * other_od_r / 2.54

                lines.append(f"\n  --- {other.name} ---")
                lines.append(f"  OD: {other_od_in:.4f}\" ({2*other_od_r:.4f} cm)")
                lines.append(f"  Faces: {other.faces.count}, OD cylinders: {len(face_data)}")
                lines.append(f"  Match threshold: {threshold:.4f} cm ({threshold/2.54:.4f}\")")
                lines.append(f"  SELECTED face: {nearest['face_idx']} (dist={nearest['dist']:.4f}cm)")
                lines.append(
                    f"  SELECTED inclination: {nearest['incl']:.1f}deg, "
                    f"notcher: {90 - nearest['incl']:.1f}deg"
                )
                lines.append(f"  IS RECEIVER: YES")

                lines.append(f"  All OD cylinder faces:")
                for fd in sorted(face_data, key=lambda f: f["dist"]):
                    marker = " <<< SELECTED" if fd["face_idx"] == nearest["face_idx"] else ""
                    lines.append(
                        f"    Face {fd['face_idx']}: "
                        f"dist={fd['dist']:.4f}cm, "
                        f"incl={fd['incl']:.1f}deg, "
                        f"area={fd['area']:.2f}cm2, "
                        f"axis=({fd['axis'][0]:.4f}, {fd['axis'][1]:.4f}, {fd['axis'][2]:.4f}), "
                        f"origin=({fd['origin'][0]:.2f}, {fd['origin'][1]:.2f}, {fd['origin'][2]:.2f})"
                        f"{marker}"
                    )

            if receiver_count == 0:
                lines.append(f"\n  No nearby bodies found.")

        result = "\n".join(lines)
        app.log(result)
        # Also write to a file for easy copy/paste
        import os
        out_path = os.path.join(os.path.dirname(__file__), "junction_output.txt")
        with open(out_path, "w") as f:
            f.write(result)
        ui.messageBox(
            f"Junction analysis complete — {len(lines)} lines.\n\n"
            f"Output written to:\n{out_path}\n\n"
            f"Also logged to Text Command window (app.log).",
            "Junction Analysis",
        )

    except:
        ui.messageBox(f"Error:\n{traceback.format_exc()}")
