"""Trace a tube body back to its source sketch/feature.

Select a tube body, then run. Attempts to find the feature that
created it (Sweep, Pipe, etc.) and extract the original sketch
path geometry (lines and arcs = tube centerline).

Uses timeline rollback to access pipe/sweep path data when later
Combine features block direct access.
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


def _describe_sketch_entity(entity):
    """Describe a sketch entity (line, arc, etc.)."""
    if isinstance(entity, adsk.fusion.SketchLine):
        sp = entity.startSketchPoint.geometry
        ep = entity.endSketchPoint.geometry
        dx = ep.x - sp.x
        dy = ep.y - sp.y
        dz = ep.z - sp.z
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        return (
            f"Line: ({sp.x:.3f}, {sp.y:.3f}, {sp.z:.3f}) -> "
            f"({ep.x:.3f}, {ep.y:.3f}, {ep.z:.3f}), "
            f"length={length:.3f} cm ({length/2.54:.3f} in)"
        )
    elif isinstance(entity, adsk.fusion.SketchArc):
        center = entity.centerSketchPoint.geometry
        radius = entity.radius
        sp = entity.startSketchPoint.geometry
        ep = entity.endSketchPoint.geometry
        # Compute sweep angle from arc geometry (Arc3D)
        geom = entity.geometry
        try:
            success, _c, _axis, _ref, _r, start_angle, end_angle = geom.getData()
            if success:
                angle = math.degrees(abs(end_angle - start_angle))
            else:
                dx = ep.x - sp.x
                dy = ep.y - sp.y
                dz = ep.z - sp.z
                chord = math.sqrt(dx*dx + dy*dy + dz*dz)
                angle = math.degrees(2.0 * math.asin(min(1.0, chord / (2.0 * radius))))
        except:
            angle = 0.0
        return (
            f"Arc: center=({center.x:.3f}, {center.y:.3f}, {center.z:.3f}), "
            f"radius={radius:.4f} cm ({radius/2.54:.4f} in), "
            f"sweep={angle:.1f} deg, "
            f"start=({sp.x:.3f}, {sp.y:.3f}, {sp.z:.3f}), "
            f"end=({ep.x:.3f}, {ep.y:.3f}, {ep.z:.3f})"
        )
    elif isinstance(entity, adsk.fusion.SketchCircle):
        center = entity.centerSketchPoint.geometry
        radius = entity.radius
        return (
            f"Circle: center=({center.x:.3f}, {center.y:.3f}, {center.z:.3f}), "
            f"radius={radius:.4f} cm"
        )
    elif isinstance(entity, adsk.fusion.SketchFittedSpline):
        return f"Spline: {entity.fitPoints.count} fit points"
    else:
        return f"Unknown: {type(entity).__name__}"


def _explore_path_entity(path_entity, lines):
    """Explore a path entity (could be a sketch curve, edge, etc.)."""
    entity = path_entity.entity
    lines.append(f"    Entity type: {type(entity).__name__}")
    lines.append(f"    Is opposing: {path_entity.isOpposingDirection}")

    if hasattr(entity, 'startSketchPoint'):
        lines.append(f"    {_describe_sketch_entity(entity)}")
    elif hasattr(entity, 'geometry'):
        geom = entity.geometry
        lines.append(f"    Geometry type: {type(geom).__name__}")
        if hasattr(geom, 'curveType'):
            ctypes = {0: "Line", 1: "Arc", 2: "Circle", 3: "Ellipse", 6: "NURBS"}
            lines.append(f"    Curve type: {ctypes.get(geom.curveType, geom.curveType)}")


def _try_get_pipe_path(pipe, lines, design):
    """Try to get pipe path, rolling timeline back if needed."""
    # First try direct access
    try:
        path = pipe.path
        lines.append(f"  Path entity count: {path.count}")
        for j in range(path.count):
            path_entity = path.item(j)
            lines.append(f"  Path item {j}:")
            _explore_path_entity(path_entity, lines)
        return True
    except Exception as e:
        lines.append(f"  Direct access failed: {e}")

    # Try timeline rollback
    try:
        tl_obj = pipe.timelineObject
        if tl_obj is None:
            lines.append(f"  No timeline object")
            return False

        tl_index = tl_obj.index
        lines.append(f"  Timeline index: {tl_index}")
        lines.append(f"  Rolling timeline to index {tl_index}...")

        # Roll timeline to just after this feature
        tl_obj.rollTo(False)  # False = roll to after this feature

        # Now try accessing the path
        try:
            path = pipe.path
            lines.append(f"  [ROLLED] Path entity count: {path.count}")
            for j in range(path.count):
                path_entity = path.item(j)
                lines.append(f"  [ROLLED] Path item {j}:")
                _explore_path_entity(path_entity, lines)

            # Also try to get pipe properties
            try:
                lines.append(f"  Section size: {pipe.sectionSize:.4f} cm ({pipe.sectionSize/2.54:.4f} in)")
            except:
                pass
            try:
                lines.append(f"  Wall thickness: {pipe.wallThickness:.4f} cm ({pipe.wallThickness/2.54:.4f} in)")
            except:
                pass
            try:
                op_types = {0: "NewBody", 1: "Join", 2: "Cut", 3: "Intersect", 4: "NewComponent"}
                lines.append(f"  Operation: {op_types.get(pipe.operation, pipe.operation)}")
            except:
                pass

            return True
        except Exception as e2:
            lines.append(f"  [ROLLED] Still failed: {e2}")
            return False
        finally:
            # Always roll timeline back to end
            design.timeline.moveToEnd()
            lines.append(f"  Timeline restored to end")

    except Exception as e3:
        lines.append(f"  Timeline rollback failed: {e3}")
        # Try to restore timeline
        try:
            design.timeline.moveToEnd()
        except:
            pass
        return False


def _try_get_sweep_path(sweep, lines, design):
    """Try to get sweep path, rolling timeline back if needed."""
    # First try direct access
    try:
        path = sweep.path
        lines.append(f"  Path entity count: {path.count}")
        for j in range(path.count):
            path_entity = path.item(j)
            lines.append(f"  Path item {j}:")
            _explore_path_entity(path_entity, lines)
        return True
    except Exception as e:
        lines.append(f"  Direct access failed: {e}")

    # Try timeline rollback
    try:
        tl_obj = sweep.timelineObject
        if tl_obj is None:
            lines.append(f"  No timeline object")
            return False

        tl_index = tl_obj.index
        lines.append(f"  Timeline index: {tl_index}")
        lines.append(f"  Rolling timeline to index {tl_index}...")

        tl_obj.rollTo(False)

        try:
            path = sweep.path
            lines.append(f"  [ROLLED] Path entity count: {path.count}")
            for j in range(path.count):
                path_entity = path.item(j)
                lines.append(f"  [ROLLED] Path item {j}:")
                _explore_path_entity(path_entity, lines)
            return True
        except Exception as e2:
            lines.append(f"  [ROLLED] Still failed: {e2}")
            return False
        finally:
            design.timeline.moveToEnd()
            lines.append(f"  Timeline restored to end")

    except Exception as e3:
        lines.append(f"  Timeline rollback failed: {e3}")
        try:
            design.timeline.moveToEnd()
        except:
            pass
        return False


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
        design = adsk.fusion.Design.cast(app.activeProduct)
        lines = []
        lines.append(f"Body: {body.name}")
        lines.append(f"Component: {comp.name}")

        # ── Method 1: Check face.createdByFeature ──
        lines.append(f"\n=== FEATURES FROM FACES ===")
        features_seen = set()
        for i in range(body.faces.count):
            face = body.faces.item(i)
            try:
                feature = face.createdByFeature
                if feature:
                    fid = feature.name
                    if fid not in features_seen:
                        features_seen.add(fid)
                        lines.append(f"  Feature: {feature.name} ({type(feature).__name__})")
            except:
                pass

        # ── Method 2: Pipe features with timeline rollback ──
        lines.append(f"\n=== PIPE FEATURES (with timeline rollback) ===")
        found_path = False
        try:
            pipe_features = comp.features.pipeFeatures
            if pipe_features and pipe_features.count > 0:
                lines.append(f"Found {pipe_features.count} pipe feature(s)")
                for i in range(pipe_features.count):
                    pipe = pipe_features.item(i)
                    lines.append(f"\nPipe: {pipe.name}")
                    if _try_get_pipe_path(pipe, lines, design):
                        found_path = True
            else:
                lines.append("No pipe features found")
        except Exception as e:
            lines.append(f"Error accessing pipe features: {e}")

        # ── Method 3: Sweep features with timeline rollback ──
        lines.append(f"\n=== SWEEP FEATURES (with timeline rollback) ===")
        try:
            sweep_features = comp.features.sweepFeatures
            if sweep_features and sweep_features.count > 0:
                lines.append(f"Found {sweep_features.count} sweep feature(s)")
                for i in range(sweep_features.count):
                    sweep = sweep_features.item(i)
                    lines.append(f"\nSweep: {sweep.name}")
                    if _try_get_sweep_path(sweep, lines, design):
                        found_path = True
            else:
                lines.append("No sweep features found")
        except Exception as e:
            lines.append(f"Error accessing sweep features: {e}")

        # ── Method 4: Sketches (always show) ──
        lines.append(f"\n=== SKETCHES ({comp.sketches.count}) ===")
        for i in range(comp.sketches.count):
            sketch = comp.sketches.item(i)
            n_lines = sketch.sketchCurves.sketchLines.count
            n_arcs = sketch.sketchCurves.sketchArcs.count
            n_circles = sketch.sketchCurves.sketchCircles.count

            # Count non-construction entities
            nc_lines = 0
            for j in range(n_lines):
                if not sketch.sketchCurves.sketchLines.item(j).isConstruction:
                    nc_lines += 1
            nc_arcs = 0
            for j in range(n_arcs):
                if not sketch.sketchCurves.sketchArcs.item(j).isConstruction:
                    nc_arcs += 1

            lines.append(
                f"  {sketch.name}: {nc_lines} lines, {nc_arcs} arcs "
                f"(+{n_lines - nc_lines} constr lines, +{n_arcs - nc_arcs} constr arcs, "
                f"{n_circles} circles)"
            )

            # Show non-construction entities for potential tube paths
            if nc_lines + nc_arcs > 0:
                for j in range(n_lines):
                    line = sketch.sketchCurves.sketchLines.item(j)
                    if not line.isConstruction:
                        lines.append(f"      {_describe_sketch_entity(line)}")
                for j in range(n_arcs):
                    arc = sketch.sketchCurves.sketchArcs.item(j)
                    if not arc.isConstruction:
                        lines.append(f"      {_describe_sketch_entity(arc)}")

        if not found_path:
            lines.append(f"\n=== NOTE ===")
            lines.append("No Sweep/Pipe path could be read on this component.")
            lines.append("Try selecting a body in a component where the")
            lines.append("Pipe/Sweep has not been modified by Combine features.")

        result = "\n".join(lines)
        print(result)
        ui.messageBox(result, "Source Explorer")

    except:
        ui.messageBox(f"Error:\n{traceback.format_exc()}")
