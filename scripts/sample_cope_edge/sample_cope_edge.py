"""Sample the cope edge profile from a tube body.

Select anything on a coped tube body, then run this script.

V4 — Collects intersection edges from ALL OD cylinder faces (incoming
+ receiving tubes), converts everything to the incoming tube's cylindrical
coordinates, filters by radius + Z window, and takes min depth at each
angle for the full 360-degree profile. Shows which axis group contributed
each angle region.
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


def _axes_parallel(a, b, tol=0.02):
    return abs(_vec_dot(a, b)) > (1.0 - tol)


def _find_tube_od_radius(body):
    radii = {}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType == 1:
            r = round(face.geometry.radius, 4)
            radii[r] = radii.get(r, 0) + face.area
    if not radii:
        return None
    return max(radii, key=radii.get)


def _classify_cylinder_faces(body, tube_radius):
    """Group OD cylinder faces by axis direction. Returns [(axis, [indices], area)]."""
    groups = []
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType != 1:
            continue
        if abs(face.geometry.radius - tube_radius) > 0.001:
            continue
        axis = face.geometry.axis
        placed = False
        for g in groups:
            if _axes_parallel(g[0], axis):
                g[1].append(i)
                g[2] += face.area
                placed = True
                break
        if not placed:
            groups.append([axis, [i], face.area])
    groups.sort(key=lambda g: g[2], reverse=True)
    return groups


def _count_intersection_edges(body, face_indices):
    """Count unique non-circle edges on these faces."""
    seen = set()
    for idx in face_indices:
        face = body.faces.item(idx)
        for j in range(face.edges.count):
            edge = face.edges.item(j)
            if edge.geometry.curveType != 2:
                seen.add(edge.tempId)
    return len(seen)


def _collect_all_od_intersection_edges(body, tube_radius):
    """Collect ALL unique non-circle edges from ALL OD cylinder faces, with face info."""
    edges = []
    seen = set()
    types_map = {0: "Plane", 1: "Cylinder", 2: "Cone", 3: "Sphere", 4: "Torus", 5: "NURBS"}
    for i in range(body.faces.count):
        face = body.faces.item(i)
        if face.geometry.surfaceType != 1:
            continue
        if abs(face.geometry.radius - tube_radius) > 0.001:
            continue
        for j in range(face.edges.count):
            edge = face.edges.item(j)
            if edge.geometry.curveType == 2:
                continue
            eid = edge.tempId
            if eid in seen:
                continue
            seen.add(eid)
            # Record which face axis this edge belongs to
            edges.append((edge, face.geometry.axis, i))
    return edges


def _sample_edge_points(edge, num_samples=100):
    evaluator = edge.evaluator
    ok_range, t_start, t_end = evaluator.getParameterExtents()
    if not ok_range:
        return []
    points = []
    for i in range(num_samples + 1):
        t = t_start + (t_end - t_start) * i / num_samples
        ok, point = evaluator.getPointAtParameter(t)
        if ok:
            points.append(point)
    return points


def _point_to_cylindrical(point, axis_origin, axis_dir, ref_dir):
    dx = point.x - axis_origin.x
    dy = point.y - axis_origin.y
    dz = point.z - axis_origin.z
    z = dx * axis_dir.x + dy * axis_dir.y + dz * axis_dir.z
    rx = dx - z * axis_dir.x
    ry = dy - z * axis_dir.y
    rz = dz - z * axis_dir.z
    r = math.sqrt(rx * rx + ry * ry + rz * rz)
    cos_a = rx * ref_dir.x + ry * ref_dir.y + rz * ref_dir.z
    perp_x = axis_dir.y * ref_dir.z - axis_dir.z * ref_dir.y
    perp_y = axis_dir.z * ref_dir.x - axis_dir.x * ref_dir.z
    perp_z = axis_dir.x * ref_dir.y - axis_dir.y * ref_dir.x
    sin_a = rx * perp_x + ry * perp_y + rz * perp_z
    angle = math.degrees(math.atan2(sin_a, cos_a)) % 360
    return angle, z, r


def _build_ref_direction(axis_dir):
    if abs(axis_dir.y) < 0.9:
        up = adsk.core.Vector3D.create(0, 1, 0)
    else:
        up = adsk.core.Vector3D.create(0, 0, 1)
    d = _vec_dot(up, axis_dir)
    ref = adsk.core.Vector3D.create(
        up.x - d * axis_dir.x,
        up.y - d * axis_dir.y,
        up.z - d * axis_dir.z,
    )
    ref.normalize()
    return ref


def _find_cope_axis_group(axis_groups, body, tube_radius):
    """Find the axis group that is the cope end of the incoming tube.

    Strategy: the cope end group has intersection edges AND is NOT the
    largest area group (the largest is the main straight section).
    Among candidates, pick the one with the most intersection edges.
    """
    best = None
    best_edge_count = 0
    for gi, (axis, face_ids, area) in enumerate(axis_groups):
        n_edges = _count_intersection_edges(body, face_ids)
        if n_edges > 0 and n_edges >= best_edge_count:
            # Prefer groups with more intersection edges
            # If tied, prefer smaller area (cope end fragment vs full straight)
            if n_edges > best_edge_count or (best is not None and area < axis_groups[best][2]):
                best = gi
                best_edge_count = n_edges
    return best


def _format_gap_ranges(gap_degrees):
    if not gap_degrees:
        return "none"
    ranges = []
    start = gap_degrees[0]
    prev = start
    for d in gap_degrees[1:]:
        if d != prev + 1:
            ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = d
        prev = d
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(ranges)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        sel = ui.activeSelections
        if sel.count == 0:
            ui.messageBox("Select something on a coped tube body first.")
            return

        body = _get_body(sel.item(0).entity)
        if body is None:
            ui.messageBox(f"Could not find body from: {type(sel.item(0).entity).__name__}")
            return

        lines = []
        lines.append(f"Body: {body.name}")
        lines.append(f"Total faces: {body.faces.count}, edges: {body.edges.count}")

        tube_radius = _find_tube_od_radius(body)
        if tube_radius is None:
            ui.messageBox("No cylindrical faces found.")
            return
        od_in = 2 * tube_radius / 2.54
        lines.append(f"Tube OD: {od_in:.4f} in (radius={tube_radius:.4f} cm)")

        # ── Classify OD cylinder faces by axis ──
        axis_groups = _classify_cylinder_faces(body, tube_radius)
        lines.append(f"\n=== OD CYLINDER AXIS GROUPS ({len(axis_groups)}) ===")
        for gi, (axis, face_ids, area) in enumerate(axis_groups):
            n_edges = _count_intersection_edges(body, face_ids)
            lines.append(
                f"  G{gi}: axis=({axis.x:.3f}, {axis.y:.3f}, {axis.z:.3f}), "
                f"faces={face_ids}, area={area:.0f} cm2, "
                f"intersect_edges={n_edges}"
            )

        # ── Identify cope axis ──
        cope_gi = _find_cope_axis_group(axis_groups, body, tube_radius)
        if cope_gi is None:
            ui.messageBox("No cope edges found on any axis group.")
            return

        cope_axis = axis_groups[cope_gi][0]
        cope_face_ids = axis_groups[cope_gi][1]
        lines.append(f"\n=== COPE END ===")
        lines.append(f"Cope group: G{cope_gi}")
        lines.append(f"Cope axis: ({cope_axis.x:.4f}, {cope_axis.y:.4f}, {cope_axis.z:.4f})")

        # ── Identify receiving tubes ──
        lines.append(f"\n=== RECEIVING TUBES ===")
        receiving = []
        for gi, (axis, face_ids, area) in enumerate(axis_groups):
            if gi == cope_gi:
                continue
            n_edges = _count_intersection_edges(body, face_ids)
            if n_edges > 0:
                dot = _vec_dot(cope_axis, axis)
                angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(dot)))))
                receiving.append((gi, axis, angle))
                lines.append(
                    f"  G{gi}: axis=({axis.x:.3f}, {axis.y:.3f}, {axis.z:.3f}), "
                    f"angle={angle:.1f} deg from incoming, edges={n_edges}"
                )
        if not receiving:
            lines.append("  (none detected)")

        # ── Collect ALL intersection edges from ALL OD faces ──
        ref_dir = _build_ref_direction(cope_axis)
        cope_origin = body.faces.item(cope_face_ids[0]).geometry.origin

        all_edges_info = _collect_all_od_intersection_edges(body, tube_radius)
        lines.append(f"\n=== EDGE SAMPLING ===")
        lines.append(f"Total unique intersection edges: {len(all_edges_info)}")

        ctypes = {0: "Line", 1: "Arc", 2: "Circle", 3: "Ellipse", 4: "EllArc", 5: "InfLine", 6: "NURBS"}

        # First pass: sample everything to find Z bounds
        all_raw = []  # (angle, z, r, group_index, edge_index)
        for ei, (edge, face_axis, face_idx) in enumerate(all_edges_info):
            # Determine which axis group this edge's face belongs to
            group_idx = -1
            for gi, (axis, face_ids, _) in enumerate(axis_groups):
                if face_idx in face_ids:
                    group_idx = gi
                    break

            pts = _sample_edge_points(edge, 100)
            ct = edge.geometry.curveType

            on_od = 0
            for pt in pts:
                angle, z, r = _point_to_cylindrical(pt, cope_origin, cope_axis, ref_dir)
                if abs(r - tube_radius) < 0.05:
                    all_raw.append((angle, z, r, group_idx, ei))
                    on_od += 1

            lines.append(
                f"  E{ei}: {ctypes.get(ct, ct)}, face={face_idx} (G{group_idx}), "
                f"{len(pts)} sampled, {on_od} on OD, len={edge.length:.3f} cm"
            )

        if not all_raw:
            ui.messageBox("No valid OD points sampled.")
            return

        # ── Z-window filter ──
        # The cope profile lives near the tube end. Reject points that are
        # deep inside the body (interior boolean intersections).
        z_all = [p[1] for p in all_raw]
        z_min_global = min(z_all)
        z_max_global = max(z_all)
        # Allow cope depth up to 4x tube OD from the shallowest point
        z_window_max = z_min_global + 4 * (2 * tube_radius)
        z_filtered = [(a, z, r, g, e) for a, z, r, g, e in all_raw if z <= z_window_max]
        z_rejected = len(all_raw) - len(z_filtered)

        lines.append(f"\n=== FILTERING ===")
        lines.append(f"Raw OD points: {len(all_raw)}")
        lines.append(f"Z window: {z_min_global:.2f} to {z_window_max:.2f} cm (4x OD from min)")
        lines.append(f"After Z filter: {len(z_filtered)} ({z_rejected} rejected as too deep)")

        if not z_filtered:
            ui.messageBox("All points rejected by Z filter.")
            return

        # ── Build 1-degree profile: min Z per angle ──
        bins_min_z = {}   # degree -> min z (cm)
        bins_group = {}   # degree -> group that contributed min z
        bins_count = {}   # degree -> total point count

        for angle, z, r, group, edge in z_filtered:
            deg = int(round(angle)) % 360
            bins_count[deg] = bins_count.get(deg, 0) + 1
            if deg not in bins_min_z or z < bins_min_z[deg]:
                bins_min_z[deg] = z
                bins_group[deg] = group

        profile_z_min = min(bins_min_z.values())
        covered = sorted(bins_min_z.keys())
        gaps = [d for d in range(360) if d not in bins_min_z]

        # ── Profile stats ──
        z_profile_max = max(bins_min_z.values())
        depth_in = (z_profile_max - profile_z_min) / 2.54

        lines.append(f"\n=== PROFILE STATS ===")
        lines.append(f"Coverage: {len(covered)} / 360 degrees ({len(covered)/3.6:.0f}%)")
        lines.append(f"Gaps: {len(gaps)} degrees")
        if gaps:
            lines.append(f"Gap ranges: {_format_gap_ranges(gaps)}")
        lines.append(f"Cope depth: {depth_in:.4f} in ({(z_profile_max - profile_z_min):.3f} cm)")

        # ── Per-group contribution ──
        group_contrib = {}
        for deg, g in bins_group.items():
            group_contrib[g] = group_contrib.get(g, 0) + 1
        lines.append(f"\nContributing groups:")
        for g in sorted(group_contrib.keys()):
            pct = group_contrib[g] / len(covered) * 100
            lines.append(f"  G{g}: {group_contrib[g]} degrees ({pct:.0f}%)")

        # ── Display profile at 5-degree bins ──
        max_depth_in = depth_in if depth_in > 0 else 1.0
        bar_scale = 40.0 / max_depth_in

        lines.append(f"\n=== PROFILE (min depth per 5-deg, inches) ===")
        lines.append(f"{'Angle':>6}  {'Depth':>8}  {'Pts':>3}  {'Grp':>3}")
        lines.append("-" * 50)

        for deg5 in range(0, 360, 5):
            span_z = []
            span_count = 0
            span_group = set()
            for d in range(deg5, deg5 + 5):
                dd = d % 360
                if dd in bins_min_z:
                    span_z.append(bins_min_z[dd])
                    span_count += bins_count.get(dd, 0)
                    span_group.add(bins_group[dd])

            if span_z:
                min_z = min(span_z)
                depth = (min_z - profile_z_min) / 2.54
                grp_str = ",".join(f"G{g}" for g in sorted(span_group))
                bar = "#" * int(depth * bar_scale)
                lines.append(f"{deg5:>5}d  {depth:>7.4f}\"  {span_count:>3}  {grp_str:<6} {bar}")
            else:
                lines.append(f"{deg5:>5}d   0.0000\"    0  fill")

        # ── Profile continuity check ──
        lines.append(f"\n=== CONTINUITY CHECK ===")
        if not gaps:
            lines.append("Full 360-degree coverage — profile is complete")
        else:
            # Check if gaps are only in the clean-cut region
            # (contiguous block where depth would be 0)
            gap_blocks = []
            start = gaps[0]
            prev = start
            for d in gaps[1:]:
                if d != prev + 1:
                    gap_blocks.append((start, prev, prev - start + 1))
                    start = d
                prev = d
            gap_blocks.append((start, prev, prev - start + 1))

            for s, e, count in gap_blocks:
                lines.append(f"  Gap {s}-{e} deg ({count} degrees)")
                # Check if adjacent data points have depth near 0
                before = bins_min_z.get(s - 1)
                after = bins_min_z.get((e + 1) % 360)
                if before is not None:
                    d_before = (before - profile_z_min) / 2.54
                    lines.append(f"    depth at {s-1} deg (before gap): {d_before:.4f} in")
                if after is not None:
                    d_after = (after - profile_z_min) / 2.54
                    lines.append(f"    depth at {(e+1)%360} deg (after gap): {d_after:.4f} in")

        # ── Feasibility verdict ──
        lines.append(f"\n=== FEASIBILITY ===")
        coverage_pct = len(covered) / 3.6
        if coverage_pct > 95:
            lines.append("EXCELLENT: Near-complete coverage from body edges")
            lines.append("Unwrap approach is directly viable")
        elif coverage_pct > 70:
            lines.append("GOOD: Majority covered, gaps likely at clean-cut regions")
            lines.append("Fill gaps with depth=0, should produce correct template")
        elif coverage_pct > 40:
            lines.append("PARTIAL: Multiple receiving tubes create complex topology")
            lines.append("Need to verify gap-filling produces smooth profile")
        else:
            lines.append("LOW: May need surface evaluator approach instead of edge walking")

        # Smoothness check — large depth jumps between adjacent degrees
        jumps = []
        prev_z = None
        for d in range(360):
            if d in bins_min_z:
                z = bins_min_z[d]
                if prev_z is not None:
                    delta = abs(z - prev_z) / 2.54
                    if delta > 0.1:  # More than 0.1" jump in one degree
                        jumps.append((d, delta))
                prev_z = z
            else:
                prev_z = None

        if jumps:
            lines.append(f"\nWARNING: {len(jumps)} discontinuities (>0.1\" jump in 1 degree):")
            for d, delta in jumps[:10]:
                lines.append(f"  at {d} deg: {delta:.3f}\" jump")
        else:
            lines.append("Profile is smooth (no discontinuities detected)")

        result = "\n".join(lines)
        print(result)
        ui.messageBox(result, "Cope Profile V4")

    except:
        ui.messageBox(f"Error:\n{traceback.format_exc()}")
