"""Run from Fusion: Scripts & Add-Ins > Scripts > + > select this file.

Select anything on a tube body — a face, edge, body, or the component
in the browser — then run.  The script finds the body automatically.
"""

import adsk.core
import adsk.fusion
import traceback


def _get_body(entity) -> "adsk.fusion.BRepBody | None":
    """Walk up from any selection to its parent BRepBody."""
    # Direct body selection
    if isinstance(entity, adsk.fusion.BRepBody):
        return entity
    # Face or edge → .body
    if isinstance(entity, (adsk.fusion.BRepFace, adsk.fusion.BRepEdge)):
        return entity.body
    # Occurrence → first body in the component
    if isinstance(entity, adsk.fusion.Occurrence):
        comp = entity.component
        if comp.bRepBodies.count > 0:
            return comp.bRepBodies.item(0)
    # Component directly
    if isinstance(entity, adsk.fusion.Component):
        if entity.bRepBodies.count > 0:
            return entity.bRepBodies.item(0)
    return None


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        sel = ui.activeSelections
        if sel.count == 0:
            ui.messageBox("Select something on a tube body first, then run this script.")
            return

        entity = sel.item(0).entity
        body = _get_body(entity)
        if body is None:
            ui.messageBox(
                f"Could not find a body from selection.\n"
                f"Selected type: {type(entity).__name__}\n\n"
                f"Try selecting the body directly in the browser or a face on the tube."
            )
            return

        types = {0: "Plane", 1: "Cylinder", 2: "Cone", 3: "Sphere", 4: "Torus", 5: "NURBS"}
        ctypes = {0: "Line", 1: "Arc", 2: "Circle", 3: "Ellipse", 5: "NURBS"}
        lines = []

        lines.append(f"Body: {body.name}")
        lines.append(f"Selected as: {type(entity).__name__}")
        lines.append(f"Faces: {body.faces.count}, Edges: {body.edges.count}")
        lines.append("=" * 60)

        # --- Face summary ---
        lines.append("\n--- FACES ---")
        for i in range(body.faces.count):
            face = body.faces.item(i)
            st = face.geometry.surfaceType
            area = face.area
            lines.append(f"Face {i}: {types.get(st, st)}, area={area:.4f} cm2, edges={face.edges.count}")

            if st == 1:  # Cylinder
                cyl = face.geometry
                r = cyl.radius
                axis = cyl.axis
                lines.append(f"  radius={r:.4f} cm ({r/2.54:.4f} in)")
                lines.append(f"  axis=({axis.x:.4f}, {axis.y:.4f}, {axis.z:.4f})")

            if st == 0:  # Plane
                n = face.geometry.normal
                lines.append(f"  normal=({n.x:.3f}, {n.y:.3f}, {n.z:.3f})")

        # --- Edge loops on each face ---
        lines.append("\n--- EDGE LOOPS ---")
        for i in range(body.faces.count):
            face = body.faces.item(i)
            st = face.geometry.surfaceType
            for j in range(face.loops.count):
                loop = face.loops.item(j)
                lines.append(f"Face {i} ({types.get(st, st)}), Loop {j}: {loop.edges.count} edges, isOuter={loop.isOuter}")
                for k in range(loop.edges.count):
                    edge = loop.edges.item(k)
                    ct = edge.geometry.curveType
                    f1 = edge.faces.item(0)
                    f2 = edge.faces.item(1) if edge.faces.count > 1 else None
                    t1 = types.get(f1.geometry.surfaceType, "?")
                    t2 = types.get(f2.geometry.surfaceType, "?") if f2 else "OPEN"
                    lines.append(f"  Edge {k}: {ctypes.get(ct, ct)}, len={edge.length:.4f} cm, faces={t1}/{t2}")

        result = "\n".join(lines)
        print(result)
        ui.messageBox(result, "Tube Body Explorer")

    except:
        ui.messageBox(f"Error:\n{traceback.format_exc()}")
