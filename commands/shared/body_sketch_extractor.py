"""Bridge between Fusion API objects and the Fusion-free matching engine.

Converts Fusion BRepBody faces and Sketch entities into plain
dataclasses, then delegates to core.body_profile and core.sketch_matching
for scoring. This is the only file in the matching pipeline that imports
Fusion types.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import adsk.core
    import adsk.fusion

from ...lib import fusionAddInUtils as futil
from ...models.match_data import (
    BodyBend,
    BodyProfile,
    BodyStraight,
    MatchResult,
    SketchArcData,
    SketchLineData,
    SketchProfile,
    TransformedSketchProfile,
)
from ...core.body_profile import build_body_profile
from ...core.geometry import normalize, ZeroVectorError
from ...core.sketch_matching import rank_matches, score_sketch_match


def extract_body_segments(
    body: adsk.fusion.BRepBody,
) -> tuple[list[BodyStraight], list[BodyBend]]:
    """Walk BRepFaces and extract cylinder/torus geometry.

    Args:
        body: A Fusion BRepBody representing a tube.

    Returns:
        Tuple of (raw_straights, raw_bends) with geometry in cm.
    """
    import adsk.core

    straights: list[BodyStraight] = []
    bends: list[BodyBend] = []

    for face in body.faces:
        surf = face.geometry

        if isinstance(surf, adsk.core.Cylinder):
            axis_raw = (surf.axis.x, surf.axis.y, surf.axis.z)
            try:
                axis = normalize(axis_raw)
            except ZeroVectorError:
                continue

            origin = (surf.origin.x, surf.origin.y, surf.origin.z)
            radius = surf.radius

            bb = face.boundingBox
            diag = (
                bb.maxPoint.x - bb.minPoint.x,
                bb.maxPoint.y - bb.minPoint.y,
                bb.maxPoint.z - bb.minPoint.z,
            )
            length_est = abs(
                diag[0] * axis[0] + diag[1] * axis[1] + diag[2] * axis[2]
            )

            centroid = (
                (bb.minPoint.x + bb.maxPoint.x) / 2,
                (bb.minPoint.y + bb.maxPoint.y) / 2,
                (bb.minPoint.z + bb.maxPoint.z) / 2,
            )

            straights.append(BodyStraight(
                axis=axis,
                origin=origin,
                radius=radius,
                length=length_est,
                centroid=centroid,
            ))

        elif isinstance(surf, adsk.core.Torus):
            axis_raw = (surf.axis.x, surf.axis.y, surf.axis.z)
            try:
                axis = normalize(axis_raw)
            except ZeroVectorError:
                continue

            origin = (surf.origin.x, surf.origin.y, surf.origin.z)
            bends.append(BodyBend(
                axis=axis,
                origin=origin,
                major_radius=surf.majorRadius,
                minor_radius=surf.minorRadius,
            ))

    return straights, bends


def extract_body_profile(body: adsk.fusion.BRepBody) -> BodyProfile:
    """Extract and process a body into a BodyProfile ready for matching.

    Args:
        body: A Fusion BRepBody representing a tube.

    Returns:
        Processed BodyProfile (merged, filtered to OD).
    """
    raw_straights, raw_bends = extract_body_segments(body)
    return build_body_profile(raw_straights, raw_bends)


def extract_sketch_profile(sketch: adsk.fusion.Sketch) -> SketchProfile:
    """Extract non-construction lines and arcs from a sketch.

    Args:
        sketch: A Fusion Sketch.

    Returns:
        SketchProfile with lines and arcs in sketch-local coordinates.
    """
    from ...core.geometry import cross_product, magnitude

    lines: list[SketchLineData] = []
    arcs: list[SketchArcData] = []

    for j in range(sketch.sketchCurves.sketchLines.count):
        line = sketch.sketchCurves.sketchLines.item(j)
        if line.isConstruction:
            continue
        sp = line.startSketchPoint.geometry
        ep = line.endSketchPoint.geometry
        dx, dy, dz = ep.x - sp.x, ep.y - sp.y, ep.z - sp.z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-10:
            continue
        direction = (dx / length, dy / length, dz / length)
        midpoint = ((sp.x + ep.x) / 2, (sp.y + ep.y) / 2, (sp.z + ep.z) / 2)
        lines.append(SketchLineData(
            direction=direction,
            start=(sp.x, sp.y, sp.z),
            end=(ep.x, ep.y, ep.z),
            midpoint=midpoint,
            length=length,
        ))

    for j in range(sketch.sketchCurves.sketchArcs.count):
        arc = sketch.sketchCurves.sketchArcs.item(j)
        if arc.isConstruction:
            continue

        center = arc.centerSketchPoint.geometry
        radius = arc.radius
        sp = arc.startSketchPoint.geometry
        ep = arc.endSketchPoint.geometry

        v1 = (sp.x - center.x, sp.y - center.y, sp.z - center.z)
        v2 = (ep.x - center.x, ep.y - center.y, ep.z - center.z)
        normal_raw = cross_product(v1, v2)
        mag = magnitude(normal_raw)
        if mag < 1e-10:
            normal = (0.0, 0.0, 1.0)
        else:
            normal = (normal_raw[0] / mag, normal_raw[1] / mag, normal_raw[2] / mag)

        geom = arc.geometry
        try:
            success, _c, _axis, _ref, _r, sa, ea = geom.getData()
            sweep = abs(ea - sa) if success else 0.0
        except Exception:
            sweep = 0.0

        arcs.append(SketchArcData(
            center=(center.x, center.y, center.z),
            radius=radius,
            normal=normal,
            sweep=sweep,
            start=(sp.x, sp.y, sp.z),
            end=(ep.x, ep.y, ep.z),
        ))

    return SketchProfile(name=sketch.name, lines=lines, arcs=arcs)


def transform_sketch_profile(
    profile: SketchProfile,
    transform: adsk.core.Matrix3D | None,
) -> TransformedSketchProfile:
    """Transform a sketch profile from sketch space to model space.

    Args:
        profile: SketchProfile in sketch-local coordinates.
        transform: Sketch-to-model-space transform (or None for identity).

    Returns:
        TransformedSketchProfile with geometry in model space.
    """
    import adsk.core

    def xform_point(pt: tuple[float, float, float]) -> tuple[float, float, float]:
        if transform is None:
            return pt
        p = adsk.core.Point3D.create(pt[0], pt[1], pt[2])
        p.transformBy(transform)
        return (p.x, p.y, p.z)

    def xform_vec(v: tuple[float, float, float]) -> tuple[float, float, float]:
        if transform is None:
            return v
        vec = adsk.core.Vector3D.create(v[0], v[1], v[2])
        vec.transformBy(transform)
        mag = math.sqrt(vec.x ** 2 + vec.y ** 2 + vec.z ** 2)
        if mag < 1e-10:
            return (0.0, 0.0, 0.0)
        return (vec.x / mag, vec.y / mag, vec.z / mag)

    t_lines: list[SketchLineData] = []
    for sl in profile.lines:
        t_lines.append(SketchLineData(
            direction=xform_vec(sl.direction),
            start=xform_point(sl.start),
            end=xform_point(sl.end),
            midpoint=xform_point(sl.midpoint),
            length=sl.length,
        ))

    t_arcs: list[SketchArcData] = []
    for sa in profile.arcs:
        t_arcs.append(SketchArcData(
            center=xform_point(sa.center),
            radius=sa.radius,
            normal=xform_vec(sa.normal),
            sweep=sa.sweep,
            start=xform_point(sa.start),
            end=xform_point(sa.end),
        ))

    return TransformedSketchProfile(
        name=profile.name,
        lines=t_lines,
        arcs=t_arcs,
    )


def find_matching_sketch(
    body: adsk.fusion.BRepBody,
    component: adsk.fusion.Component | None = None,
) -> tuple[adsk.fusion.Sketch | None, MatchResult | None]:
    """Find the sketch in the component that best matches the tube body.

    Args:
        body: The tube body to match.
        component: Component to search. Defaults to body.parentComponent.

    Returns:
        Tuple of (best_sketch, best_result). Both None if no good match.
    """
    comp = component or body.parentComponent
    if comp is None:
        return None, None

    body_profile = extract_body_profile(body)
    if not body_profile.straights and not body_profile.bends:
        return None, None

    results: list[tuple[adsk.fusion.Sketch, MatchResult]] = []

    for i in range(comp.sketches.count):
        sketch = comp.sketches.item(i)
        profile = extract_sketch_profile(sketch)

        if not profile.lines and not profile.arcs:
            continue

        try:
            transform = sketch.transform
        except Exception:
            transform = None

        t_profile = transform_sketch_profile(profile, transform)
        result = score_sketch_match(body_profile, t_profile)
        results.append((sketch, result))

    if not results:
        return None, None

    match_results = [r for _, r in results]
    ranked = rank_matches(match_results)

    if not ranked or ranked[0].score <= 0:
        return None, None

    best_name = ranked[0].sketch_name
    for sketch, result in results:
        if result.sketch_name == best_name:
            futil.log(
                f"Sketch match: '{best_name}' score={ranked[0].score} "
                f"confidence={ranked[0].confidence}"
            )
            return sketch, ranked[0]

    return None, None


def extract_sketch_entities(
    sketch: adsk.fusion.Sketch,
) -> tuple[list[adsk.fusion.SketchLine], list[adsk.fusion.SketchArc]]:
    """Get actual Fusion sketch entities (non-construction) for downstream use.

    Args:
        sketch: A Fusion Sketch.

    Returns:
        Tuple of (sketch_lines, sketch_arcs) — the actual Fusion objects.
    """
    lines: list[adsk.fusion.SketchLine] = []
    arcs: list[adsk.fusion.SketchArc] = []

    for j in range(sketch.sketchCurves.sketchLines.count):
        line = sketch.sketchCurves.sketchLines.item(j)
        if not line.isConstruction:
            lines.append(line)

    for j in range(sketch.sketchCurves.sketchArcs.count):
        arc = sketch.sketchCurves.sketchArcs.item(j)
        if not arc.isConstruction:
            arcs.append(arc)

    return lines, arcs
