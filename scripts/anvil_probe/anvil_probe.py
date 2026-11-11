"""THROWAWAY PROBE for the Anvil tube-extraction investigation.

Run from Fusion: Scripts & Add-Ins > Scripts > + > select this file.

Select anything on an Anvil tube body — a face, edge, body, or the
component in the browser — then run.  The script finds the body
automatically.

It reports, for one body:
  1. Every face: cylinders (radius + axis + origin), tori/bends
     (CLR = majorRadius, OD_r = minorRadius), planes, other.
  2. The area-dominant OD radius -> OD diameter, and a second-largest
     (ID) radius -> wall thickness if an inner bore exists.
  3. The distinct cylinder-axis directions (the "one tube per body vs
     merged body" tell).
  4. Circle-edge centers on each OD cylinder face — the centerline
     endpoints — flagging non-circle edges (coped ends).

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


SURF = {0: "Plane", 1: "Cylinder", 2: "Cone", 3: "Sphere", 4: "Torus",
        5: "EllipticalCylinder", 6: "EllipticalCone", 7: "Nurbs"}
CURVE = {0: "Line", 1: "Arc", 2: "Circle", 3: "Ellipse", 4: "EllipticalArc",
         5: "Nurbs"}

OD_TOL = 0.01      # cm, radius match tolerance for "is this the OD?"
AXIS_TOL_DEG = 2.0  # axes within this angle are treated as the same direction


def _get_body(entity):
    """Walk up from any selection to its parent BRepBody."""
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


def _axis_seen(axes, ax):
    """Return True if a parallel axis is already in the list."""
    for a in axes:
        dot = abs(a[0] * ax.x + a[1] * ax.y + a[2] * ax.z)
        dot = max(-1.0, min(1.0, dot))
        if math.degrees(math.acos(dot)) < AXIS_TOL_DEG:
            return True
    return False


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        sel = ui.activeSelections
        if sel.count == 0:
            ui.messageBox("Select a tube body (or a face/edge on it) first.")
            return

        body = _get_body(sel.item(0).entity)
        if body is None:
            ui.messageBox(
                "Could not resolve a BRepBody from the selection "
                "(type={}).".format(type(sel.item(0).entity).__name__)
            )
            return

        lines = []
        lines.append("body={}  faces={}".format(body.name, body.faces.count))

        radii = {}        # rounded radius -> total area
        cyl_axes = []     # distinct cylinder axis directions
        torus_count = 0

        # --- Pass 1: faces ---
        lines.append("\n--- FACES ---")
        for i in range(body.faces.count):
            f = body.faces.item(i)
            g = f.geometry
            st = g.surfaceType
            if st == 1:  # Cylinder
                r = round(g.radius, 4)
                radii[r] = radii.get(r, 0.0) + f.area
                ax = g.axis
                if not _axis_seen(cyl_axes, ax):
                    cyl_axes.append((ax.x, ax.y, ax.z))
                lines.append(
                    "  [{}] CYL  r={:.4f}cm ({:.4f}in)  area={:.3f}  "
                    "axis=({:.3f},{:.3f},{:.3f})  origin=({:.3f},{:.3f},{:.3f})"
                    .format(i, g.radius, g.radius / 2.54, f.area,
                            ax.x, ax.y, ax.z, g.origin.x, g.origin.y, g.origin.z)
                )
            elif st == 4:  # Torus (bend)
                torus_count += 1
                ax = g.axis
                lines.append(
                    "  [{}] TORUS  major(CLR)={:.4f}cm ({:.4f}in)  "
                    "minor(OD_r)={:.4f}cm  axis=({:.3f},{:.3f},{:.3f})"
                    .format(i, g.majorRadius, g.majorRadius / 2.54,
                            g.minorRadius, ax.x, ax.y, ax.z)
                )
            elif st == 0:  # Plane
                n = g.normal
                lines.append(
                    "  [{}] PLANE  area={:.3f}  normal=({:.3f},{:.3f},{:.3f})"
                    .format(i, f.area, n.x, n.y, n.z)
                )
            else:
                lines.append(
                    "  [{}] {}  area={:.3f}".format(i, SURF.get(st, st), f.area)
                )

        # --- OD / ID summary ---
        lines.append("\n--- DIMENSIONS ---")
        od = None
        if radii:
            od = max(radii, key=lambda k: radii[k])
            lines.append(
                "OD radius (area-dominant) = {:.4f}cm  ->  OD = {:.4f}cm "
                "({:.4f}in)".format(od, 2 * od, 2 * od / 2.54)
            )
            inner = {r: a for r, a in radii.items() if abs(r - od) > OD_TOL}
            if inner:
                idr = max(inner, key=lambda k: inner[k])
                wall = od - idr
                lines.append(
                    "ID radius (2nd largest)   = {:.4f}cm  ->  wall = {:.4f}cm "
                    "({:.4f}in)".format(idr, wall, wall / 2.54)
                )
            else:
                lines.append("ID radius: none found (solid bar, or no inner bore)")
        else:
            lines.append("No cylindrical faces found — not a round tube?")

        # --- Verdict hints ---
        lines.append("\n--- VERDICT HINTS ---")
        lines.append("distinct cylinder-axis directions = {}".format(len(cyl_axes)))
        lines.append("torus (bend) faces = {}".format(torus_count))
        if len(cyl_axes) <= 1 and torus_count == 0:
            lines.append("=> looks like ONE straight tube in this body.")
        elif torus_count > 0 and len(cyl_axes) >= 2:
            lines.append("=> looks like ONE bent tube (straights + bends share a path).")
        else:
            lines.append("=> multiple unrelated axes: possibly MERGED/multi-tube "
                         "body, or cope artifacts from a receiving tube.")

        # --- Centerline endpoints: circle-edge centers on OD cylinders ---
        if od is not None:
            lines.append("\n--- OD CYLINDER CIRCLE-EDGE CENTERS (centerline ends) ---")
            for i in range(body.faces.count):
                f = body.faces.item(i)
                g = f.geometry
                if g.surfaceType != 1 or abs(g.radius - od) > OD_TOL:
                    continue
                lines.append("CYL[{}] r={:.4f}".format(i, g.radius))
                for j in range(f.edges.count):
                    e = f.edges.item(j)
                    ct = e.geometry.curveType
                    if ct == 2:  # Circle
                        c = e.geometry.center
                        lines.append(
                            "   circle center=({:.4f},{:.4f},{:.4f})  r={:.4f}"
                            .format(c.x, c.y, c.z, e.geometry.radius)
                        )
                    else:
                        lines.append(
                            "   non-circle edge: {} (coped/trimmed end?)"
                            .format(CURVE.get(ct, ct))
                        )

        _emit("\n".join(lines), "anvil_probe")

    except:
        ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
