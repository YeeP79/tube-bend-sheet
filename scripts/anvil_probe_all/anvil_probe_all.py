"""THROWAWAY PROBE 2 for the Anvil tube-extraction investigation.

Run from Fusion: Scripts & Add-Ins > Scripts > + > select this file.
Nothing needs to be selected — it sweeps EVERY body in the active
component (and direct child occurrences) and prints a one-block summary
per body so we can see whether Anvil models one tube per body or merges
several tubes into one body.

Per body it reports:
  - OD (area-dominant cylinder radius -> diameter)
  - the DISTINCT wall thicknesses present (a concentric bore with a
    *different* wall = a different tube sharing the body -> MULTI-TUBE)
  - number of distinct cylinder-axis directions
  - number of straight legs (coaxial OD-cylinder groups)
  - number of torus (bend) faces
  - a one-line verdict

Read-only. Delete when the investigation is done.
"""

import adsk.core
import adsk.fusion
import math
import os
import traceback


def _emit(result, name):
    """Dump full output to the Text Commands window + a .txt failsafe."""
    app = adsk.core.Application.get()
    try:
        app.log(result)   # full text, no length cap, into Text Commands
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
    msg = "Done. Full output is in the Text Commands window\n(View > Show Text Commands)."
    if path:
        msg += "\n\nAlso saved to:\n" + path
    app.userInterface.messageBox(msg, "Anvil Probe")


OD_TOL = 0.01        # cm, radius match tolerance
AXIS_TOL_DEG = 2.0   # axes within this angle treated as same direction
DIST_TOL = 0.05      # cm, perpendicular distance for "coaxial"
WALL_ROUND = 3       # cm decimals for distinct-wall bucketing


def _axis_angle(a, b):
    dot = abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def _perp_dist(p, q, axis):
    """Perpendicular distance of point p from the line through q dir axis."""
    d = (p[0] - q[0], p[1] - q[1], p[2] - q[2])
    t = d[0] * axis[0] + d[1] * axis[1] + d[2] * axis[2]
    proj = (q[0] + t * axis[0], q[1] + t * axis[1], q[2] + t * axis[2])
    return math.sqrt((p[0] - proj[0]) ** 2 + (p[1] - proj[1]) ** 2
                     + (p[2] - proj[2]) ** 2)


def _coaxial(c1, c2):
    """c = (r, axis_tuple, origin_tuple). True if same axis line."""
    if _axis_angle(c1[1], c2[1]) > AXIS_TOL_DEG:
        return False
    return _perp_dist(c2[2], c1[2], c1[1]) < DIST_TOL


def _summarize_body(body):
    lines = []
    cyls = []   # (r, axis, origin, area, face_index)
    tori = 0
    for i in range(body.faces.count):
        f = body.faces.item(i)
        g = f.geometry
        st = g.surfaceType
        if st == 1:
            cyls.append((g.radius, (g.axis.x, g.axis.y, g.axis.z),
                         (g.origin.x, g.origin.y, g.origin.z), f.area, i))
        elif st == 4:
            tori += 1

    if not cyls:
        lines.append("  no cylindrical faces (not a round tube)")
        return lines

    # OD = area-dominant radius
    radii = {}
    for r, _, _, area, _ in cyls:
        rr = round(r, 4)
        radii[rr] = radii.get(rr, 0.0) + area
    od = max(radii, key=lambda k: radii[k])
    lines.append("  OD = {:.4f}cm ({:.4f}in)".format(2 * od, 2 * od / 2.54))

    od_cyls = [c for c in cyls if abs(c[0] - od) < OD_TOL]
    inner_cyls = [c for c in cyls if c[0] < od - OD_TOL]

    # Distinct straight legs = coaxial OD-cylinder groups
    leg_axes = []   # representative axis tuples
    legs = []       # list of representative cyl
    for c in od_cyls:
        placed = False
        for leg in legs:
            if _coaxial(leg, c):
                placed = True
                break
        if not placed:
            legs.append(c)
            leg_axes.append(c[1])

    # Distinct wall thicknesses: for each leg, find a coaxial inner cyl
    walls = {}
    for leg in legs:
        for ic in inner_cyls:
            if _coaxial(leg, ic):
                w = round(od - ic[0], WALL_ROUND)
                walls[w] = walls.get(w, 0) + 1
                break

    lines.append("  straight legs (coaxial OD groups) = {}".format(len(legs)))
    lines.append("  bend (torus) faces = {}".format(tori))
    if walls:
        wall_str = ", ".join(
            "{:.4f}cm/{:.4f}in".format(w, w / 2.54) for w in sorted(walls)
        )
        lines.append("  distinct wall thicknesses = {}  [{}]".format(
            len(walls), wall_str))
    else:
        lines.append("  distinct wall thicknesses = 0 (solid bar / no bore)")

    # Verdict
    if len(walls) > 1:
        lines.append("  => MIXED WALLS ({}) in one body: either two welded "
                     "tubes, OR one tube with a leftover join seam. If the OD "
                     "faces form a single connected path, treat as one tube."
                     .format(len(walls)))
    elif len(legs) <= 1 and tori == 0:
        lines.append("  => one straight tube.")
    elif tori > 0:
        lines.append("  => looks like one bent tube ({} legs, {} bend faces) "
                     "-- but confirm legs form a single chain.".format(
                         len(legs), tori))
    else:
        lines.append("  => {} disconnected straight legs, no bends: possibly "
                     "multiple straight tubes in one body.".format(len(legs)))
    return lines


def _split_bodies(bodies):
    """Return (visible, hidden) from a BRepBodies collection."""
    vis = []
    hid = []
    for i in range(bodies.count):
        b = bodies.item(i)
        (vis if b.isVisible else hid).append(b)
    return vis, hid


def _walk_occ(occ, depth, lines):
    """Recursively summarise an occurrence's visible bodies + sub-occurrences."""
    pad = "  " * depth
    if not occ.isVisible:
        lines.append("{}Occurrence '{}'  (HIDDEN — skipped)".format(pad, occ.name))
        return
    # Proxy bodies in this occurrence's context
    ovis, ohid = _split_bodies(occ.bRepBodies)
    children = occ.childOccurrences
    nchild = children.count if children else 0
    lines.append("{}Occurrence '{}'  ({} visible bodies, {} hidden, {} sub-occ)"
                 .format(pad, occ.name, len(ovis), len(ohid), nchild))
    for b in ovis:
        lines.append("{}  Body '{}' (faces={})".format(pad, b.name, b.faces.count))
        for ln in _summarize_body(b):
            lines.append(pad + "  " + ln)
    if children:
        for i in range(nchild):
            _walk_occ(children.item(i), depth + 1, lines)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("Active product is not a Fusion Design.")
            return
        root = design.rootComponent

        lines = ["Active design: {}".format(root.name)]

        # Root-component bodies — VISIBLE only (hidden = stale/reference)
        vis, hid = _split_bodies(root.bRepBodies)
        lines.append("\n=== ROOT COMPONENT — VISIBLE BODIES ({}) ===".format(len(vis)))
        for b in vis:
            lines.append("\nBody '{}'  (faces={})".format(b.name, b.faces.count))
            lines.extend(_summarize_body(b))

        if hid:
            lines.append("\n=== SKIPPED {} HIDDEN ROOT BODIES ===".format(len(hid)))
            for b in hid:
                lines.append("  (hidden) '{}'  faces={}".format(b.name, b.faces.count))

        # Full occurrence tree (recursive, visible-only)
        occ_count = root.occurrences.count
        if occ_count:
            lines.append("\n=== OCCURRENCE TREE ({} top-level) ===".format(occ_count))
            for i in range(occ_count):
                _walk_occ(root.occurrences.item(i), 0, lines)

        _emit("\n".join(lines), "anvil_probe_all")
    except:
        ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
