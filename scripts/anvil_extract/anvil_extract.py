"""THROWAWAY PROBE 4 for the Anvil tube-extraction investigation.

Runs the PRODUCTION ordering algorithm (torus-anchored walk + artifact
filtering), not the old endpoint-only `explore_path` logic. Select a
tube body, then run.

Mirrors commands/shared/body_path_extractor.py so we can see, on a real
coped/mitered chassis tube, what `extract_body_path` actually produces:
the ordered straights+bends, the centerline length, the per-bend angle
and rotation, and crucially WHICH cylinder faces get dropped as
artifacts.

Read-only. Delete when the investigation is done.
"""

import adsk.core
import adsk.fusion
import math
import os
import traceback


# Production tolerances (core/tolerances.py)
OD_TOL = 0.01            # OD_FILTER_TOLERANCE_CM
MIN_BEND_ANGLE_DEG = 3.0
COAXIAL_ANGLE_DEG = 2.0
COAXIAL_DIST_CM = 0.5


def _emit(result, name):
    app = adsk.core.Application.get()
    try:
        app.log(result)
    except Exception:
        pass
    print(result)
    path = None
    try:
        path = os.path.join(os.path.expanduser("~"), name + ".txt")
        with open(path, "w") as f:
            f.write(result)
    except Exception:
        path = None
    msg = "Done. Full output in the Text Commands window."
    if path:
        msg += "\n\nAlso saved to:\n" + path
    app.userInterface.messageBox(msg, "Anvil Extract")


def _get_body(entity):
    if isinstance(entity, adsk.fusion.BRepBody):
        return entity
    if isinstance(entity, (adsk.fusion.BRepFace, adsk.fusion.BRepEdge)):
        return entity.body
    if isinstance(entity, adsk.fusion.Occurrence):
        if entity.component.bRepBodies.count > 0:
            return entity.component.bRepBodies.item(0)
    if isinstance(entity, adsk.fusion.Component):
        if entity.bRepBodies.count > 0:
            return entity.bRepBodies.item(0)
    return None


def _find_od_radius(body):
    radii = {}
    for i in range(body.faces.count):
        g = body.faces.item(i).geometry
        if g.surfaceType == 1:
            r = round(g.radius, 4)
            radii[r] = radii.get(r, 0.0) + body.faces.item(i).area
    return max(radii, key=lambda k: radii[k]) if radii else None


def _classify(body, od):
    cyls, tori = [], []
    for i in range(body.faces.count):
        f = body.faces.item(i)
        g = f.geometry
        if g.surfaceType == 1 and abs(g.radius - od) < OD_TOL:
            cyls.append((i, f))
        elif g.surfaceType == 4 and abs(g.minorRadius - od) < OD_TOL:
            tori.append((i, f))
    return cyls, tori


def _torus_bend_angle(face):
    t = face.geometry
    c, ax = t.origin, t.axis
    centers = [e.geometry.center for e in
               (face.edges.item(i) for i in range(face.edges.count))
               if e.geometry.curveType == 2]
    if len(centers) < 2:
        return None
    def proj(p):
        v = adsk.core.Vector3D.create(p.x - c.x, p.y - c.y, p.z - c.z)
        d = v.x * ax.x + v.y * ax.y + v.z * ax.z
        return (v.x - d * ax.x, v.y - d * ax.y, v.z - d * ax.z)
    a = proj(centers[0]); b = proj(centers[1])
    ma = math.sqrt(sum(x * x for x in a)); mb = math.sqrt(sum(x * x for x in b))
    if ma < 1e-8 or mb < 1e-8:
        return None
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (ma * mb)))))


def _shared(fa, fb):
    ids = {fa.edges.item(i).tempId for i in range(fa.edges.count)}
    for j in range(fb.edges.count):
        if fb.edges.item(j).tempId in ids:
            return True
    return False


def _adjacency(faces):
    adj = {idx: [] for idx, _ in faces}
    for i in range(len(faces)):
        ia, fa = faces[i]
        for j in range(i + 1, len(faces)):
            ib, fb = faces[j]
            if _shared(fa, fb):
                adj[ia].append(ib); adj[ib].append(ia)
    return adj


def _order_via_tori(cyls, tori, adj):
    cyl_set = {i for i, _ in cyls}
    torus_set = {i for i, _ in tori}
    faces = {i: ("straight", f) for i, f in cyls}
    faces.update({i: ("bend", f) for i, f in tori})
    cyl_to_tori = {}
    for c in cyl_set:
        nbrs = [n for n in adj.get(c, []) if n in torus_set]
        if nbrs:
            cyl_to_tori[c] = nbrs
    torus_to_cyls = {t: [n for n in adj.get(t, []) if n in cyl_to_tori] for t in torus_set}
    path_cyls = set(cyl_to_tori)
    if not path_cyls:
        return [], cyl_set
    terminals = [c for c, ts in cyl_to_tori.items() if len(ts) == 1]
    start = terminals[0] if terminals else next(iter(path_cyls))
    ordered, vc, vt = [], set(), set()
    cur = start
    while cur is not None:
        vc.add(cur)
        ordered.append((cur, "straight", faces[cur][1]))
        nt = next((t for t in cyl_to_tori.get(cur, []) if t not in vt), None)
        if nt is None:
            break
        vt.add(nt)
        ordered.append((nt, "bend", faces[nt][1]))
        cur = next((c for c in torus_to_cyls.get(nt, []) if c not in vc), None)
    used = {i for i, _, _ in ordered}
    dropped = cyl_set - used
    return ordered, dropped


def _circle_centers(face):
    out = []
    for i in range(face.edges.count):
        e = face.edges.item(i)
        if e.geometry.curveType == 2:
            c = e.geometry.center
            out.append((c.x, c.y, c.z))
    return out


def _straight_len_and_vec(face):
    cs = _circle_centers(face)
    if len(cs) >= 2:
        best = (0.0, cs[0], cs[1])
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                d = sum((cs[i][k] - cs[j][k]) ** 2 for k in range(3))
                if d > best[0]:
                    best = (d, cs[i], cs[j])
        a, b = best[1], best[2]
        vec = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        return math.sqrt(best[0]), vec
    # bbox fallback along axis
    g = face.geometry
    ax = (g.axis.x, g.axis.y, g.axis.z); o = g.origin
    bb = face.boundingBox
    ps = []
    for x in (bb.minPoint.x, bb.maxPoint.x):
        for y in (bb.minPoint.y, bb.maxPoint.y):
            for z in (bb.minPoint.z, bb.maxPoint.z):
                ps.append((x - o.x) * ax[0] + (y - o.y) * ax[1] + (z - o.z) * ax[2])
    L = max(ps) - min(ps)
    return L, (ax[0] * L, ax[1] * L, ax[2] * L)


def _rotation(v1, v2, v3):
    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    def mag(v):
        return math.sqrt(sum(x*x for x in v))
    n1, n2 = cross(v1, v2), cross(v2, v3)
    if mag(n1) < 1e-9 or mag(n2) < 1e-9:
        return None
    dot = sum(n1[k]*n2[k] for k in range(3)) / (mag(n1)*mag(n2))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        if ui.activeSelections.count == 0:
            ui.messageBox("Select a tube body first."); return
        body = _get_body(ui.activeSelections.item(0).entity)
        if body is None:
            ui.messageBox("Could not resolve a BRepBody."); return

        L = ["body={}  faces={}".format(body.name, body.faces.count)]
        od = _find_od_radius(body)
        if od is None:
            _emit("\n".join(L + ["no cylinders"]), "anvil_extract"); return
        L.append("OD = {:.4f}in".format(2*od/2.54))

        cyls, tori = _classify(body, od)
        # filter artifact tori (< MIN_BEND_ANGLE_DEG)
        real_tori, art_tori = [], []
        for idx, f in tori:
            a = _torus_bend_angle(f)
            (real_tori if (a is not None and a >= MIN_BEND_ANGLE_DEG) else art_tori).append((idx, f))
        L.append("OD cylinders={}  tori total={} (real={}, artifact<3deg={})".format(
            len(cyls), len(tori), len(real_tori), len(art_tori)))

        adj = _adjacency(cyls + real_tori)
        ordered, dropped = _order_via_tori(cyls, real_tori, adj)

        L.append("\n=== PRODUCTION-STYLE ORDERED PATH ({} faces) ===".format(len(ordered)))
        vecs = []
        straights = []
        total_cm = 0.0
        for idx, ftype, face in ordered:
            if ftype == "straight":
                ln, vec = _straight_len_and_vec(face)
                vecs.append(vec); straights.append((idx, ln))
                total_cm += ln
                L.append("  straight face[{}] len={:.3f}in".format(idx, ln/2.54))
            else:
                ang = _torus_bend_angle(face) or 0.0
                clr = face.geometry.majorRadius
                arc = clr * math.radians(ang)
                total_cm += arc
                L.append("  BEND face[{}] angle={:.1f}deg CLR={:.3f}in arc={:.3f}in".format(
                    idx, ang, clr/2.54, arc/2.54))

        # rotations between consecutive bends (cross-product method)
        if len(vecs) >= 3:
            L.append("\n=== ROTATIONS (between bend planes) ===")
            for b in range(len(vecs) - 2):
                rot = _rotation(vecs[b], vecs[b+1], vecs[b+2])
                L.append("  bend {}: rotation={}".format(
                    b + 2, "n/a" if rot is None else "{:.1f}deg".format(rot)))

        L.append("\nTotal centerline (ordered path): {:.3f} in".format(total_cm/2.54))
        L.append("Dropped cylinder faces (artifacts/mitered/cope): {}".format(
            sorted(dropped) if dropped else "none"))
        if dropped:
            L.append("  -> these OD cylinders were NOT on the torus-anchored path.")
            for d in sorted(dropped):
                g = None
                for i in range(body.faces.count):
                    if i == d:
                        g = body.faces.item(i).geometry; break
                if g is not None:
                    ln, _ = _straight_len_and_vec(body.faces.item(d))
                    L.append("     face[{}] axis=({:.3f},{:.3f},{:.3f}) len={:.3f}in".format(
                        d, g.axis.x, g.axis.y, g.axis.z, ln/2.54))

        _emit("\n".join(L), "anvil_extract")
    except:
        ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
