"""THROWAWAY PROBE 3 for the Anvil tube-extraction investigation.

Run from Fusion: Scripts & Add-Ins > Scripts > + > select this file.
Nothing needs to be selected.

Goal: figure out how the model's WORLD coordinate frame maps to vehicle
semantics — the centerline (L/R symmetry plane), the fore/aft axis, and
up — so a tube's world position can be expressed as "X off centerline,
Y aft of front, Z up."

It reports:
  1. Active design units + overall bounding box of all root bodies
     (extents per axis -> longest horizontal axis is usually fore/aft).
  2. Named construction planes and sketches (builders often leave a
     "Front" / "CL" / "Centerline" / "Datum" we can use).
  3. Per-body bounding-box centers.
  4. A symmetry test per axis: does the set of body centers mirror about
     a plane?  The axis with the strongest mirror pairing = the LATERAL
     axis, and the mirror value = the CENTERLINE plane.

Read-only. Delete when the investigation is done.
"""

import adsk.core
import adsk.fusion
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


SYM_TOL = 0.5   # cm, tolerance for calling two centers a mirror pair


def _visible_bodies(coll):
    return [coll.item(i) for i in range(coll.count) if coll.item(i).isVisible]


def _collect_occ(occ, out):
    """Recursively collect visible proxy bodies from a visible occurrence tree."""
    if not occ.isVisible:
        return
    out.extend(_visible_bodies(occ.bRepBodies))
    children = occ.childOccurrences
    if children:
        for i in range(children.count):
            _collect_occ(children.item(i), out)


def _all_root_bodies(root):
    """All VISIBLE bodies across root + the full occurrence tree."""
    out = _visible_bodies(root.bRepBodies)
    for i in range(root.occurrences.count):
        _collect_occ(root.occurrences.item(i), out)
    return out


def _bbox_center(b):
    bb = b.boundingBox
    return ((bb.minPoint.x + bb.maxPoint.x) / 2.0,
            (bb.minPoint.y + bb.maxPoint.y) / 2.0,
            (bb.minPoint.z + bb.maxPoint.z) / 2.0)


def _pairs_at_plane(centers, axis_idx, plane):
    """Count centers that have a mirror partner across `plane` on this axis."""
    other = [i for i in range(3) if i != axis_idx]
    paired = 0
    for c in centers:
        mirror = 2 * plane - c[axis_idx]  # reflect c across the plane
        for d in centers:
            if d is c:
                continue
            if (abs(d[axis_idx] - mirror) < SYM_TOL
                    and abs(d[other[0]] - c[other[0]]) < SYM_TOL
                    and abs(d[other[1]] - c[other[1]]) < SYM_TOL):
                paired += 1
                break
    return paired


def _symmetry_for_axis(centers, axis_idx):
    """For one axis, find the mirror plane that best pairs the centers.

    Tests a few candidate planes — 0 (global origin), the mean, and the
    median — and returns the one with the most mirror pairs. Many chassis
    put the centerline on the global origin plane, so 0 must be tried
    explicitly (the mean is skewed by one-sided sub-clusters).
    Returns (plane_value, pair_count, total).
    """
    coords = sorted(c[axis_idx] for c in centers)
    mean = sum(coords) / len(coords)
    median = coords[len(coords) // 2]
    best_plane, best_pairs = 0.0, _pairs_at_plane(centers, axis_idx, 0.0)
    for cand in (mean, median):
        p = _pairs_at_plane(centers, axis_idx, cand)
        if p > best_pairs:
            best_plane, best_pairs = cand, p
    return best_plane, best_pairs, len(centers)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = app.activeProduct
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("Active product is not a Fusion Design.")
            return
        root = design.rootComponent
        um = design.unitsManager

        lines = ["units = {}".format(um.defaultLengthUnits)]

        # --- Overall extents ---
        bodies = _all_root_bodies(root)
        if bodies:
            xs = []
            ys = []
            zs = []
            centers = []
            for b in bodies:
                bb = b.boundingBox
                xs += [bb.minPoint.x, bb.maxPoint.x]
                ys += [bb.minPoint.y, bb.maxPoint.y]
                zs += [bb.minPoint.z, bb.maxPoint.z]
                centers.append(_bbox_center(b))
            ex = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
            lines.append("\n--- OVERALL EXTENTS (cm) ---")
            lines.append("X: {:.1f} .. {:.1f}  (len {:.1f})".format(
                min(xs), max(xs), ex[0]))
            lines.append("Y: {:.1f} .. {:.1f}  (len {:.1f})".format(
                min(ys), max(ys), ex[1]))
            lines.append("Z: {:.1f} .. {:.1f}  (len {:.1f})".format(
                min(zs), max(zs), ex[2]))
            longest = ["X", "Y", "Z"][ex.index(max(ex))]
            lines.append("longest axis = {} (often fore/aft)".format(longest))

        # --- Construction planes / sketches (named datums) ---
        lines.append("\n--- NAMED CONSTRUCTION PLANES ---")
        cps = root.constructionPlanes
        if cps.count == 0:
            lines.append("  (none — model uses the global origin planes only)")
        for i in range(cps.count):
            lines.append("  '{}'".format(cps.item(i).name))

        lines.append("\n--- SKETCHES ---")
        sk = root.sketches
        if sk.count == 0:
            lines.append("  (none)")
        for i in range(sk.count):
            lines.append("  '{}'".format(sk.item(i).name))

        # --- Per-body centers ---
        if bodies:
            lines.append("\n--- BODY BBOX CENTERS (cm) ---")
            for b in bodies:
                c = _bbox_center(b)
                lines.append("  {:<16} ({:8.2f}, {:8.2f}, {:8.2f})".format(
                    b.name[:16], c[0], c[1], c[2]))

            # --- Symmetry test ---
            lines.append("\n--- L/R SYMMETRY TEST (finds centerline) ---")
            best = None
            for idx, name in enumerate(("X", "Y", "Z")):
                plane, paired, total = _symmetry_for_axis(centers, idx)
                lines.append("  {} : mirror plane @ {:.2f}cm  pairs {}/{}".format(
                    name, plane, paired, total))
                if best is None or paired > best[2]:
                    best = (name, plane, paired)
            if best and best[2] > 0:
                lines.append("  => likely CENTERLINE: plane normal to {} at "
                             "{:.2f}cm ({} mirror pairs)".format(
                                 best[0], best[1], best[2]))
            else:
                lines.append("  => no clear mirror symmetry (model may be a "
                             "half/partial, or asymmetric).")

        _emit("\n".join(lines), "anvil_context")
    except:
        ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
