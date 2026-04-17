"""Match a selected tube body to its source sketch.

Select a tube body, then run. Extracts cylinder face axes from the
body and compares them to sketch line directions to find the best
matching sketch in the same component.

Scoring V2: graduated direction, strong CLR weighting, spatial
proximity, and connected-path bonus.
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


def _vec_length(v):
    return math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])


def _vec_normalize(v):
    m = _vec_length(v)
    if m < 1e-10:
        return (0, 0, 0)
    return (v[0]/m, v[1]/m, v[2]/m)


def _vec_dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _vec_sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def _vec_add(a, b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])


def _vec_scale(v, s):
    return (v[0]*s, v[1]*s, v[2]*s)


def _vec_cross(a, b):
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    )


def _angle_between(v1, v2):
    """Angle in degrees between two direction vectors (0-90, ignoring sign)."""
    d = _vec_dot(_vec_normalize(v1), _vec_normalize(v2))
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(abs(d)))


def _point_to_line_dist(point, line_origin, line_dir):
    """Distance from a point to an infinite line."""
    v = _vec_sub(point, line_origin)
    proj = _vec_dot(v, line_dir)
    closest = _vec_add(line_origin, _vec_scale(line_dir, proj))
    return _vec_length(_vec_sub(point, closest))


def _point_dist(a, b):
    return _vec_length(_vec_sub(a, b))


def _endpoints_match(p1, p2, tol=0.05):
    """Check if two points are coincident (within tolerance in cm)."""
    return _point_dist(p1, p2) < tol


# ─── Body analysis ───

def _extract_body_segments(body):
    """Extract straight segments (cylinder axes) and bend segments (torus axes) from body."""
    straights = []
    bends = []

    for i in range(body.faces.count):
        face = body.faces.item(i)
        surf = face.geometry

        if isinstance(surf, adsk.core.Cylinder):
            axis = (surf.axis.x, surf.axis.y, surf.axis.z)
            origin = (surf.origin.x, surf.origin.y, surf.origin.z)
            radius = surf.radius

            bb = face.boundingBox
            diag = _vec_sub(
                (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z),
                (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z),
            )
            length_est = abs(_vec_dot(diag, _vec_normalize(axis)))

            # Compute face centroid from bounding box center
            centroid = (
                (bb.minPoint.x + bb.maxPoint.x) / 2,
                (bb.minPoint.y + bb.maxPoint.y) / 2,
                (bb.minPoint.z + bb.maxPoint.z) / 2,
            )

            straights.append({
                'axis': _vec_normalize(axis),
                'origin': origin,
                'radius': radius,
                'length': length_est,
                'centroid': centroid,
            })

        elif isinstance(surf, adsk.core.Torus):
            axis = (surf.axis.x, surf.axis.y, surf.axis.z)
            origin = (surf.origin.x, surf.origin.y, surf.origin.z)
            bends.append({
                'axis': _vec_normalize(axis),
                'origin': origin,
                'major_radius': surf.majorRadius,
                'minor_radius': surf.minorRadius,
            })

    return straights, bends


def _merge_coaxial_cylinders(straights, angle_tol=2.0, dist_tol=0.5):
    """Merge cylinder faces that share the same axis (split by cope booleans)."""
    if not straights:
        return []

    merged = [dict(straights[0])]  # copy
    for seg in straights[1:]:
        found_merge = False
        for m in merged:
            angle = _angle_between(seg['axis'], m['axis'])
            if angle < angle_tol:
                dist = _point_to_line_dist(seg['origin'], m['origin'], m['axis'])
                if dist < dist_tol and abs(seg['radius'] - m['radius']) < 0.01:
                    m['length'] = max(m['length'], seg['length'])
                    found_merge = True
                    break
        if not found_merge:
            merged.append(dict(seg))
    return merged


def _get_od_radius(straights):
    if not straights:
        return 0
    return max(s['radius'] for s in straights)


def _filter_od_segments(straights, od_radius, tol=0.01):
    return [s for s in straights if abs(s['radius'] - od_radius) < tol]


def _filter_od_bends(bends, od_radius, tol=0.01):
    """Keep only OD torus faces (minor_radius matches OD radius)."""
    return [b for b in bends if abs(b['minor_radius'] - od_radius) < tol]


# ─── Sketch analysis ───

def _extract_sketch_segments(sketch):
    """Extract line directions and arc data from a sketch (non-construction only)."""
    lines_data = []
    arcs_data = []

    for j in range(sketch.sketchCurves.sketchLines.count):
        line = sketch.sketchCurves.sketchLines.item(j)
        if line.isConstruction:
            continue
        sp = line.startSketchPoint.geometry
        ep = line.endSketchPoint.geometry
        direction = _vec_normalize((ep.x - sp.x, ep.y - sp.y, ep.z - sp.z))
        midpoint = ((sp.x + ep.x) / 2, (sp.y + ep.y) / 2, (sp.z + ep.z) / 2)
        length = _vec_length((ep.x - sp.x, ep.y - sp.y, ep.z - sp.z))
        lines_data.append({
            'direction': direction,
            'start': (sp.x, sp.y, sp.z),
            'end': (ep.x, ep.y, ep.z),
            'midpoint': midpoint,
            'length': length,
        })

    for j in range(sketch.sketchCurves.sketchArcs.count):
        arc = sketch.sketchCurves.sketchArcs.item(j)
        if arc.isConstruction:
            continue
        center = arc.centerSketchPoint.geometry
        radius = arc.radius
        sp = arc.startSketchPoint.geometry
        ep = arc.endSketchPoint.geometry

        v1 = _vec_normalize((sp.x - center.x, sp.y - center.y, sp.z - center.z))
        v2 = _vec_normalize((ep.x - center.x, ep.y - center.y, ep.z - center.z))
        normal = _vec_normalize(_vec_cross(v1, v2))

        geom = arc.geometry
        try:
            success, _c, _axis, _ref, _r, sa, ea = geom.getData()
            sweep = abs(ea - sa) if success else 0
        except:
            sweep = 0

        arcs_data.append({
            'center': (center.x, center.y, center.z),
            'radius': radius,
            'normal': normal,
            'sweep': sweep,
            'start': (sp.x, sp.y, sp.z),
            'end': (ep.x, ep.y, ep.z),
        })

    return lines_data, arcs_data


def _get_sketch_plane_transform(sketch):
    try:
        return sketch.transform
    except:
        return None


def _transform_point(transform, point):
    if transform is None:
        return point
    p = adsk.core.Point3D.create(point[0], point[1], point[2])
    p.transformBy(transform)
    return (p.x, p.y, p.z)


def _transform_vector(transform, vec):
    if transform is None:
        return vec
    v = adsk.core.Vector3D.create(vec[0], vec[1], vec[2])
    v.transformBy(transform)
    return _vec_normalize((v.x, v.y, v.z))


# ─── Connected path detection ───

def _find_connected_path(t_lines, t_arcs, tol=0.05):
    """Find the longest connected chain of lines and arcs.

    Returns (connected_line_indices, connected_arc_indices, chain_length).
    """
    # Build list of all entities with their endpoints
    entities = []
    for i, l in enumerate(t_lines):
        entities.append(('line', i, l['start'], l['end']))
    for i, a in enumerate(t_arcs):
        entities.append(('arc', i, a['start'], a['end']))

    if not entities:
        return set(), set(), 0

    # Build adjacency: entity i connects to entity j if an endpoint matches
    adj = {i: [] for i in range(len(entities))}
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            ei = entities[i]
            ej = entities[j]
            # Check all 4 endpoint combinations
            if (_endpoints_match(ei[2], ej[2], tol) or
                _endpoints_match(ei[2], ej[3], tol) or
                _endpoints_match(ei[3], ej[2], tol) or
                _endpoints_match(ei[3], ej[3], tol)):
                adj[i].append(j)
                adj[j].append(i)

    # Find longest connected chain via DFS from each node
    best_path = []
    for start in range(len(entities)):
        visited = {start}
        stack = [(start, [start])]
        while stack:
            node, path = stack.pop()
            extended = False
            for nbr in adj[node]:
                if nbr not in visited:
                    visited.add(nbr)
                    new_path = path + [nbr]
                    stack.append((nbr, new_path))
                    extended = True
            if not extended and len(path) > len(best_path):
                best_path = path

    # Extract indices
    connected_lines = set()
    connected_arcs = set()
    for idx in best_path:
        etype, eidx, _, _ = entities[idx]
        if etype == 'line':
            connected_lines.add(eidx)
        else:
            connected_arcs.add(eidx)

    return connected_lines, connected_arcs, len(best_path)


# ─── Scoring V2 ───

def _graduated_direction_score(angle_deg):
    """Score based on direction match quality. Higher = better."""
    if angle_deg < 1.0:
        return 12
    elif angle_deg < 3.0:
        return 10
    elif angle_deg < 5.0:
        return 7
    elif angle_deg < 10.0:
        return 4
    elif angle_deg < 15.0:
        return 2
    return 0


def _clr_match_score(clr_diff_cm):
    """Score based on CLR match. Can be negative for bad matches."""
    if clr_diff_cm < 0.1:    # exact match
        return 12
    elif clr_diff_cm < 0.5:  # close
        return 6
    elif clr_diff_cm < 1.0:  # marginal
        return 2
    elif clr_diff_cm < 3.0:  # wrong die
        return -3
    return -8                 # completely wrong


def _proximity_score(body_centroid, sketch_midpoint):
    """Score based on spatial proximity between body segment and sketch line."""
    dist = _point_dist(body_centroid, sketch_midpoint)
    if dist < 2.0:     # < 2cm = very close
        return 8
    elif dist < 5.0:   # < 5cm = close
        return 5
    elif dist < 15.0:  # < 15cm = same neighborhood
        return 2
    elif dist < 30.0:  # < 30cm = same general area
        return 0
    return -3           # far away = probably wrong


def _score_sketch_match(body_od_segs, body_bends, sketch_lines, sketch_arcs,
                        sketch_transform, od_radius):
    """Score how well a sketch matches a body. V2 with tightened criteria."""
    score = 0
    details = []

    # Transform sketch geometry to 3D model space
    transformed_lines = []
    for sl in sketch_lines:
        t_dir = _transform_vector(sketch_transform, sl['direction'])
        t_start = _transform_point(sketch_transform, sl['start'])
        t_end = _transform_point(sketch_transform, sl['end'])
        t_mid = _transform_point(sketch_transform, sl['midpoint'])
        transformed_lines.append({
            'direction': t_dir,
            'start': t_start,
            'end': t_end,
            'midpoint': t_mid,
            'length': sl['length'],
        })

    transformed_arcs = []
    for sa in sketch_arcs:
        t_center = _transform_point(sketch_transform, sa['center'])
        t_normal = _transform_vector(sketch_transform, sa['normal'])
        t_start = _transform_point(sketch_transform, sa['start'])
        t_end = _transform_point(sketch_transform, sa['end'])
        transformed_arcs.append({
            'center': t_center,
            'radius': sa['radius'],
            'normal': t_normal,
            'sweep': sa['sweep'],
            'start': t_start,
            'end': t_end,
        })

    # ── Connected path bonus ──
    conn_lines, conn_arcs, chain_len = _find_connected_path(
        transformed_lines, transformed_arcs
    )
    total_entities = len(transformed_lines) + len(transformed_arcs)
    if total_entities > 0:
        conn_ratio = chain_len / total_entities
    else:
        conn_ratio = 0

    # Bonus for high connectivity (real tube paths are fully connected)
    if conn_ratio > 0.8 and chain_len >= 2:
        path_bonus = 10
    elif conn_ratio > 0.5 and chain_len >= 2:
        path_bonus = 5
    else:
        path_bonus = 0
    score += path_bonus
    details.append(f"  Path connectivity: {chain_len}/{total_entities} entities connected (bonus: +{path_bonus})")

    # ── Match body straights to sketch lines ──
    matched_body = set()
    matched_sketch = set()
    straight_details = []

    for bi, bseg in enumerate(body_od_segs):
        best_score = -999
        best_si = -1
        best_angle = 999
        best_prox = 0
        best_dir_score = 0

        for si, sline in enumerate(transformed_lines):
            if si in matched_sketch:
                continue

            angle = _angle_between(bseg['axis'], sline['direction'])
            dir_score = _graduated_direction_score(angle)

            if dir_score <= 0:
                continue

            # Spatial proximity
            prox = _proximity_score(bseg['centroid'], sline['midpoint'])
            total = dir_score + prox

            if total > best_score:
                best_score = total
                best_si = si
                best_angle = angle
                best_prox = prox
                best_dir_score = dir_score

        if best_si >= 0 and best_score > 0:
            score += best_score
            matched_body.add(bi)
            matched_sketch.add(best_si)
            straight_details.append(
                f"  Straight {bi}: angle={best_angle:.1f} deg (dir:+{best_dir_score}), "
                f"proximity (prox:+{best_prox}), total=+{best_score}"
            )

    details.extend(straight_details)

    # ── Match body bends to sketch arcs ──
    matched_body_bends = set()
    matched_sketch_arcs = set()
    bend_details = []

    for bi, bbend in enumerate(body_bends):
        best_score = -999
        best_si = -1
        best_angle = 999
        best_clr_diff = 999
        best_clr_score = 0
        best_dir_score = 0
        best_prox = 0

        for si, sarc in enumerate(transformed_arcs):
            if si in matched_sketch_arcs:
                continue

            angle = _angle_between(bbend['axis'], sarc['normal'])
            dir_score = _graduated_direction_score(angle)

            if dir_score <= 0:
                continue

            clr_diff = abs(bbend['major_radius'] - sarc['radius'])
            clr_score = _clr_match_score(clr_diff)

            # Proximity: bend center to arc center
            prox = _proximity_score(bbend['origin'], sarc['center'])

            total = dir_score + clr_score + prox

            if total > best_score:
                best_score = total
                best_si = si
                best_angle = angle
                best_clr_diff = clr_diff
                best_clr_score = clr_score
                best_dir_score = dir_score
                best_prox = prox

        if best_si >= 0 and best_score > 0:
            score += best_score
            matched_body_bends.add(bi)
            matched_sketch_arcs.add(best_si)
            bend_details.append(
                f"  Bend {bi}: axis={best_angle:.1f} deg (dir:+{best_dir_score}), "
                f"CLR diff={best_clr_diff:.3f} cm (clr:{best_clr_score:+d}), "
                f"proximity (prox:{best_prox:+d}), total=+{best_score}"
            )

    details.extend(bend_details)

    # ── Penalties ──
    unmatched_body = len(body_od_segs) - len(matched_body)
    unmatched_bends = len(body_bends) - len(matched_body_bends)
    extra_lines = len(transformed_lines) - len(matched_sketch)
    extra_arcs = len(transformed_arcs) - len(matched_sketch_arcs)

    body_penalty = (unmatched_body + unmatched_bends) * -8
    extra_penalty = (extra_lines + extra_arcs) * -3
    score += body_penalty + extra_penalty

    details.append(
        f"  Summary: {len(matched_body)}/{len(body_od_segs)} straights, "
        f"{len(matched_body_bends)}/{len(body_bends)} bends matched"
    )
    details.append(
        f"  Penalties: unmatched body={body_penalty}, extra sketch={extra_penalty}"
    )

    return score, details


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

        comp = body.parentComponent
        lines = []
        lines.append(f"Body: {body.name}")
        lines.append(f"Component: {comp.name}")

        # ── Extract body geometry ──
        straights, bends = _extract_body_segments(body)
        lines.append(f"\nRaw cylinder faces: {len(straights)}")
        lines.append(f"Raw torus faces: {len(bends)}")

        merged = _merge_coaxial_cylinders(straights)
        lines.append(f"Merged cylinder groups: {len(merged)}")

        od_radius = _get_od_radius(merged)
        od_segs = _filter_od_segments(merged, od_radius)
        od_bends = _filter_od_bends(bends, od_radius)
        lines.append(f"OD radius: {od_radius:.4f} cm ({od_radius/2.54:.4f} in)")
        lines.append(f"OD diameter: {od_radius*2:.4f} cm ({od_radius*2/2.54:.4f} in)")
        lines.append(f"OD straight segments: {len(od_segs)}")
        lines.append(f"OD bend segments: {len(od_bends)} (of {len(bends)} total torus faces)")

        for i, seg in enumerate(od_segs):
            lines.append(
                f"  Straight {i}: axis=({seg['axis'][0]:.3f}, {seg['axis'][1]:.3f}, "
                f"{seg['axis'][2]:.3f}), length~{seg['length']:.2f} cm "
                f"({seg['length']/2.54:.2f} in), "
                f"centroid=({seg['centroid'][0]:.1f}, {seg['centroid'][1]:.1f}, {seg['centroid'][2]:.1f})"
            )

        for i, b in enumerate(od_bends):
            lines.append(
                f"  Bend {i}: axis=({b['axis'][0]:.3f}, {b['axis'][1]:.3f}, "
                f"{b['axis'][2]:.3f}), CLR={b['major_radius']:.4f} cm "
                f"({b['major_radius']/2.54:.4f} in), "
                f"center=({b['origin'][0]:.1f}, {b['origin'][1]:.1f}, {b['origin'][2]:.1f})"
            )

        # ── Score each sketch ──
        lines.append(f"\n=== SKETCH MATCHING (V2) ===")
        scores = []

        for i in range(comp.sketches.count):
            sketch = comp.sketches.item(i)
            sketch_lines_data, sketch_arcs_data = _extract_sketch_segments(sketch)

            if len(sketch_lines_data) + len(sketch_arcs_data) == 0:
                continue

            transform = _get_sketch_plane_transform(sketch)
            score, details = _score_sketch_match(
                od_segs, od_bends, sketch_lines_data, sketch_arcs_data,
                transform, od_radius,
            )

            scores.append((score, sketch.name, details, len(sketch_lines_data),
                           len(sketch_arcs_data)))

        scores.sort(key=lambda x: x[0], reverse=True)

        # Show top 5 and any positive scores
        shown = 0
        for rank, (score, name, details, n_lines, n_arcs) in enumerate(scores):
            if shown >= 5 and score <= 0:
                break
            marker = " <<<< BEST MATCH" if rank == 0 and score > 0 else ""
            lines.append(
                f"\n  [{score:+d}] \"{name}\" ({n_lines} lines, {n_arcs} arcs){marker}"
            )
            for d in details:
                lines.append(d)
            shown += 1

        # Confidence indicator
        if len(scores) >= 2 and scores[0][0] > 0:
            margin = scores[0][0] - scores[1][0]
            pct = (margin / max(1, scores[0][0])) * 100
            lines.append(f"\n  Margin over 2nd place: +{margin} points ({pct:.0f}%)")
            if pct > 50:
                lines.append(f"  Confidence: HIGH")
            elif pct > 25:
                lines.append(f"  Confidence: MEDIUM")
            else:
                lines.append(f"  Confidence: LOW — consider verifying")

        if scores and scores[0][0] > 0:
            best_name = scores[0][1]
            lines.append(f"\n=== BEST MATCH: \"{best_name}\" ===")

            for i in range(comp.sketches.count):
                sketch = comp.sketches.item(i)
                if sketch.name == best_name:
                    transform = _get_sketch_plane_transform(sketch)
                    lines.append(f"Path geometry (model space):")

                    for j in range(sketch.sketchCurves.sketchLines.count):
                        line = sketch.sketchCurves.sketchLines.item(j)
                        if line.isConstruction:
                            continue
                        sp = line.startSketchPoint.geometry
                        ep = line.endSketchPoint.geometry
                        t_sp = _transform_point(transform, (sp.x, sp.y, sp.z))
                        t_ep = _transform_point(transform, (ep.x, ep.y, ep.z))
                        length = _vec_length(_vec_sub(t_ep, t_sp))
                        lines.append(
                            f"  Line: ({t_sp[0]:.3f}, {t_sp[1]:.3f}, {t_sp[2]:.3f}) -> "
                            f"({t_ep[0]:.3f}, {t_ep[1]:.3f}, {t_ep[2]:.3f}), "
                            f"length={length:.3f} cm ({length/2.54:.3f} in)"
                        )

                    for j in range(sketch.sketchCurves.sketchArcs.count):
                        arc = sketch.sketchCurves.sketchArcs.item(j)
                        if arc.isConstruction:
                            continue
                        center = arc.centerSketchPoint.geometry
                        t_center = _transform_point(transform, (center.x, center.y, center.z))
                        radius = arc.radius
                        sp = arc.startSketchPoint.geometry
                        ep = arc.endSketchPoint.geometry
                        t_sp = _transform_point(transform, (sp.x, sp.y, sp.z))
                        t_ep = _transform_point(transform, (ep.x, ep.y, ep.z))
                        geom = arc.geometry
                        try:
                            success, _c, _axis, _ref, _r, sa, ea = geom.getData()
                            sweep = math.degrees(abs(ea - sa)) if success else 0
                        except:
                            sweep = 0
                        lines.append(
                            f"  Arc: center=({t_center[0]:.3f}, {t_center[1]:.3f}, "
                            f"{t_center[2]:.3f}), R={radius:.4f} cm ({radius/2.54:.4f} in), "
                            f"sweep={sweep:.1f} deg"
                        )
                    break
        else:
            lines.append(f"\n=== NO GOOD MATCH FOUND ===")

        result = "\n".join(lines)
        print(result)
        ui.messageBox(result, "Sketch Matcher V2")

    except:
        ui.messageBox(f"Error:\n{traceback.format_exc()}")
