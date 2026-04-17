"""Extract tube bend path from a body's face topology.

Select a tube body, then run. Walks the OD cylinder and torus faces
to extract straights, bends, rotations, and CLR — the same data the
bend sheet currently gets from sketch geometry.
"""

import adsk.core
import adsk.fusion
import math
import traceback


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


def _vec_dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


def _vec_cross(a, b):
    return adsk.core.Vector3D.create(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _vec_mag(v):
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def _find_od_radius(body):
    """Find the outer diameter radius (largest cylinder radius)."""
    radii = {}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType == 1:  # Cylinder
            r = round(face.geometry.radius, 4)
            radii[r] = radii.get(r, 0) + face.area
    if not radii:
        return None
    return max(radii, key=radii.get)


def _find_id_radius(body, od_radius):
    """Find the inner diameter radius (second most common cylinder radius)."""
    radii = {}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType == 1:
            r = round(face.geometry.radius, 4)
            if abs(r - od_radius) > 0.01:
                radii[r] = radii.get(r, 0) + face.area
    if not radii:
        return None
    return max(radii, key=radii.get)


def _classify_od_faces(body, od_radius):
    """Classify OD faces into cylinders (straights) and tori (bends).

    Returns (cylinders, tori) where each is a list of (face_index, face).
    Only includes faces with radius matching od_radius.
    """
    cylinders = []
    tori = []

    for i in range(body.faces.count):
        face = body.faces.item(i)
        st = face.geometry.surfaceType

        if st == 1:  # Cylinder
            if abs(face.geometry.radius - od_radius) < 0.01:
                cylinders.append((i, face))
        elif st == 4:  # Torus
            # OD torus has minor radius = tube OD radius
            torus = face.geometry
            if abs(torus.minorRadius - od_radius) < 0.01:
                tori.append((i, face))

    return cylinders, tori


def _shared_edge(face_a, face_b):
    """Find the shared edge between two faces, or None."""
    for i in range(face_a.edges.count):
        edge_a = face_a.edges.item(i)
        for j in range(face_b.edges.count):
            edge_b = face_b.edges.item(j)
            if edge_a.tempId == edge_b.tempId:
                return edge_a
    return None


def _build_adjacency(faces):
    """Build adjacency map: face_index -> list of (neighbor_index, shared_edge).

    Only considers adjacency among the provided face set.
    """
    adjacency = {idx: [] for idx, _ in faces}
    face_list = [(idx, face) for idx, face in faces]

    for i in range(len(face_list)):
        idx_a, face_a = face_list[i]
        for j in range(i + 1, len(face_list)):
            idx_b, face_b = face_list[j]
            edge = _shared_edge(face_a, face_b)
            if edge is not None:
                adjacency[idx_a].append((idx_b, edge))
                adjacency[idx_b].append((idx_a, edge))

    return adjacency


def _get_torus_bend_angle(face):
    """Extract the bend angle from a torus face.

    The bend angle is the angular sweep of the torus face.
    We compute it from the two circle edges (where torus meets cylinders).
    """
    torus = face.geometry
    center = torus.origin
    axis = torus.axis
    major_r = torus.majorRadius

    # Find the two circular edges (these connect to cylinder faces)
    circle_centers = []
    for i in range(face.edges.count):
        edge = face.edges.item(i)
        if edge.geometry.curveType == 2:  # Circle
            circ = edge.geometry
            circle_centers.append(circ.center)

    if len(circle_centers) < 2:
        return None

    # Vectors from torus center to each circle center
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

    # Project onto plane perpendicular to torus axis
    d1 = _vec_dot(v1, axis)
    v1_proj = adsk.core.Vector3D.create(
        v1.x - d1 * axis.x, v1.y - d1 * axis.y, v1.z - d1 * axis.z
    )
    d2 = _vec_dot(v2, axis)
    v2_proj = adsk.core.Vector3D.create(
        v2.x - d2 * axis.x, v2.y - d2 * axis.y, v2.z - d2 * axis.z
    )

    mag1 = _vec_mag(v1_proj)
    mag2 = _vec_mag(v2_proj)
    if mag1 < 1e-8 or mag2 < 1e-8:
        return None

    cos_angle = _vec_dot(v1_proj, v2_proj) / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def _get_cylinder_length(face):
    """Estimate the length of a cylinder face along its axis.

    Uses the bounding box projected onto the axis.
    """
    axis = face.geometry.axis
    bbox = face.boundingBox

    # Project bounding box corners onto axis
    corners = [
        bbox.minPoint,
        bbox.maxPoint,
    ]

    origin = face.geometry.origin
    projections = []
    for c in corners:
        dx = c.x - origin.x
        dy = c.y - origin.y
        dz = c.z - origin.z
        proj = dx * axis.x + dy * axis.y + dz * axis.z
        projections.append(proj)

    return abs(max(projections) - min(projections))


def _get_cylinder_endpoints(face):
    """Get the two endpoint centers of a cylinder face from its circle edges."""
    centers = []
    for i in range(face.edges.count):
        edge = face.edges.item(i)
        if edge.geometry.curveType == 2:  # Circle
            centers.append(edge.geometry.center)
    return centers


def _order_path(cylinders, tori, adjacency):
    """Walk the face adjacency graph to produce an ordered path.

    Returns ordered list of (face_index, face_type, face) where
    face_type is 'straight' or 'bend'.
    """
    all_faces = {idx: ('straight', face) for idx, face in cylinders}
    all_faces.update({idx: ('bend', face) for idx, face in tori})

    # Find path endpoints — faces with only 1 neighbor in the path
    endpoints = []
    for idx in all_faces:
        neighbors_in_path = [n for n, _ in adjacency.get(idx, []) if n in all_faces]
        if len(neighbors_in_path) <= 1:
            endpoints.append(idx)

    if not endpoints:
        return []

    # Start from a cylinder endpoint if possible
    start = endpoints[0]
    for ep in endpoints:
        if all_faces[ep][0] == 'straight':
            start = ep
            break

    # Walk the path
    ordered = []
    visited = set()
    current = start

    while current is not None:
        visited.add(current)
        ftype, face = all_faces[current]
        ordered.append((current, ftype, face))

        # Find unvisited neighbor
        next_face = None
        for neighbor, _ in adjacency.get(current, []):
            if neighbor not in visited and neighbor in all_faces:
                next_face = neighbor
                break
        current = next_face

    return ordered


def _compute_rotation(normal1, normal2):
    """Compute rotation angle between two bend plane normals."""
    d = _vec_dot(normal1, normal2)
    mag1 = _vec_mag(normal1)
    mag2 = _vec_mag(normal2)
    if mag1 < 1e-8 or mag2 < 1e-8:
        return None
    cos_angle = d / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def _get_bend_plane_normal(pre_axis, post_axis):
    """Compute the bend plane normal from the straight sections before and after."""
    return _vec_cross(pre_axis, post_axis)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        sel = ui.activeSelections
        if sel.count == 0:
            ui.messageBox("Select a tube body first.")
            return

        body = _get_body(sel.item(0).entity)
        if body is None:
            ui.messageBox(f"Could not find body from: {type(sel.item(0).entity).__name__}")
            return

        lines = []
        lines.append(f"Body: {body.name}")

        # ── Tube dimensions ──
        od_r = _find_od_radius(body)
        if od_r is None:
            ui.messageBox("No cylindrical faces found.")
            return
        id_r = _find_id_radius(body, od_r)

        od = 2 * od_r / 2.54
        lines.append(f"\n=== TUBE DIMENSIONS ===")
        lines.append(f"OD: {od:.4f} in ({2*od_r:.4f} cm)")
        if id_r:
            wall = (od_r - id_r) / 2.54
            lines.append(f"ID: {2*id_r/2.54:.4f} in ({2*id_r:.4f} cm)")
            lines.append(f"Wall: {wall:.4f} in")
        else:
            lines.append("ID: not detected (solid rod?)")

        # ── Classify faces ──
        cylinders, tori = _classify_od_faces(body, od_r)
        lines.append(f"\n=== OD FACE CLASSIFICATION ===")
        lines.append(f"Cylinder (straight) faces: {len(cylinders)}")
        lines.append(f"Torus (bend) faces: {len(tori)}")

        for idx, face in cylinders:
            axis = face.geometry.axis
            length_cm = _get_cylinder_length(face)
            lines.append(
                f"  Face {idx}: Cylinder, axis=({axis.x:.3f}, {axis.y:.3f}, {axis.z:.3f}), "
                f"length={length_cm:.3f} cm ({length_cm/2.54:.3f} in)"
            )

        for idx, face in tori:
            torus = face.geometry
            clr = torus.majorRadius
            angle = _get_torus_bend_angle(face)
            angle_str = f"{angle:.1f}" if angle else "?"
            lines.append(
                f"  Face {idx}: Torus, CLR={clr:.4f} cm ({clr/2.54:.4f} in), "
                f"bend={angle_str} deg"
            )

        # ── Build adjacency and order path ──
        all_od_faces = cylinders + tori
        adjacency = _build_adjacency(all_od_faces)

        lines.append(f"\n=== ADJACENCY ===")
        for idx in adjacency:
            neighbors = [str(n) for n, _ in adjacency[idx]]
            face_type = "Cyl" if any(i == idx for i, _ in cylinders) else "Tor"
            lines.append(f"  Face {idx} ({face_type}) -> [{', '.join(neighbors)}]")

        # ── Walk ordered path ──
        ordered = _order_path(cylinders, tori, adjacency)
        lines.append(f"\n=== ORDERED PATH ({len(ordered)} faces) ===")

        bend_number = 0
        straight_number = 0
        prev_bend_normal = None
        prev_straight_axis = None
        total_centerline = 0.0

        path_summary = []

        for i, (idx, ftype, face) in enumerate(ordered):
            if ftype == 'straight':
                straight_number += 1
                axis = face.geometry.axis
                length_cm = _get_cylinder_length(face)
                length_in = length_cm / 2.54
                total_centerline += length_cm

                lines.append(
                    f"  Straight {straight_number}: Face {idx}, "
                    f"axis=({axis.x:.3f}, {axis.y:.3f}, {axis.z:.3f}), "
                    f"length={length_in:.3f} in"
                )
                path_summary.append(f"S{straight_number}: {length_in:.3f}\"")
                prev_straight_axis = axis

            elif ftype == 'bend':
                bend_number += 1
                torus = face.geometry
                clr = torus.majorRadius
                angle = _get_torus_bend_angle(face)
                angle_str = f"{angle:.1f}" if angle else "?"

                # Arc length
                if angle:
                    arc_cm = clr * math.radians(angle)
                    total_centerline += arc_cm
                    arc_in = arc_cm / 2.54
                else:
                    arc_in = 0

                # Compute bend plane normal from adjacent straights
                rotation_str = "—"
                if prev_straight_axis is not None:
                    # Find the straight AFTER this bend
                    post_axis = None
                    if i + 1 < len(ordered) and ordered[i + 1][1] == 'straight':
                        post_axis = ordered[i + 1][2].geometry.axis
                    if post_axis is not None:
                        bend_normal = _get_bend_plane_normal(prev_straight_axis, post_axis)
                        if prev_bend_normal is not None:
                            rotation = _compute_rotation(prev_bend_normal, bend_normal)
                            if rotation is not None:
                                rotation_str = f"{rotation:.1f} deg"
                        prev_bend_normal = bend_normal

                lines.append(
                    f"  Bend {bend_number}: Face {idx}, "
                    f"angle={angle_str} deg, CLR={clr/2.54:.4f} in, "
                    f"arc={arc_in:.3f} in, rotation={rotation_str}"
                )
                path_summary.append(f"B{bend_number}: {angle_str}deg")

        # ── Summary ──
        lines.append(f"\n=== SUMMARY ===")
        lines.append(f"Path: {' -> '.join(path_summary)}")
        lines.append(f"Straights: {straight_number}")
        lines.append(f"Bends: {bend_number}")
        lines.append(f"Total centerline: {total_centerline/2.54:.3f} in ({total_centerline:.3f} cm)")
        lines.append(f"Tube OD: {od:.4f} in")
        if id_r:
            lines.append(f"Wall: {(od_r - id_r)/2.54:.4f} in")

        # ── CLR consistency ──
        clr_values = set()
        for idx, face in tori:
            clr_values.add(round(face.geometry.majorRadius, 3))
        if len(clr_values) == 1:
            clr_val = list(clr_values)[0]
            lines.append(f"CLR: {clr_val/2.54:.4f} in (consistent)")
        elif len(clr_values) > 1:
            clr_strs = [f"{c/2.54:.4f}\"" for c in sorted(clr_values)]
            lines.append(f"CLR: MISMATCH — {', '.join(clr_strs)}")

        # ── Cope detection ──
        lines.append(f"\n=== COPE END DETECTION ===")
        if ordered:
            first_idx, first_type, first_face = ordered[0]
            last_idx, last_type, last_face = ordered[-1]

            for label, idx, ftype, face in [
                ("Start", first_idx, first_type, first_face),
                ("End", last_idx, last_type, last_face),
            ]:
                if ftype == 'straight':
                    # Check if this cylinder has non-circle edges (cope indicators)
                    non_circle = 0
                    for j in range(face.edges.count):
                        if face.edges.item(j).geometry.curveType != 2:
                            non_circle += 1
                    if non_circle > 0:
                        lines.append(f"  {label} (Face {idx}): COPED ({non_circle} intersection edges)")
                    else:
                        lines.append(f"  {label} (Face {idx}): Clean cut")
                elif ftype == 'bend':
                    lines.append(f"  {label} (Face {idx}): Ends with bend (no straight tail)")

        result = "\n".join(lines)
        print(result)
        ui.messageBox(result, "Tube Path Explorer")

    except:
        ui.messageBox(f"Error:\n{traceback.format_exc()}")
