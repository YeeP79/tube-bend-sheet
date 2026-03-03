"""Geometry extraction from Fusion BRepBody objects for cope calculations.

Extracts cylinder axes, outer diameters, and bend reference vectors
from solid tube bodies.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import adsk.core
    import adsk.fusion

from ...models.types import Point3D, Vector3D


def extract_cylinder_axis(body: adsk.fusion.BRepBody) -> tuple[Vector3D, float]:
    """
    Extract the centerline axis and outer diameter from a cylindrical body.

    Walks BRepFaces looking for CylinderSurfaceType. Returns the axis
    direction and the largest cylinder diameter found (the OD).

    Args:
        body: A Fusion BRepBody representing a tube

    Returns:
        Tuple of (axis_vector, outer_diameter)

    Raises:
        ValueError: If no cylindrical face is found
    """
    import adsk.core

    largest_radius = 0.0
    axis_vector: Vector3D | None = None

    for face in body.faces:
        geom = face.geometry
        if isinstance(geom, adsk.core.Cylinder):
            radius = geom.radius
            if radius > largest_radius:
                largest_radius = radius
                axis = geom.axis
                axis_vector = (axis.x, axis.y, axis.z)

    if axis_vector is None:
        raise ValueError(f"No cylindrical face found on body '{body.name}'")

    od = largest_radius * 2.0
    return axis_vector, od


def extract_bend_reference(
    body: adsk.fusion.BRepBody,
    cope_end: Point3D,
) -> tuple[Vector3D | None, str]:
    """
    Extract the back-of-bend reference vector from the last bend before the cope end.

    Walks BRepFaces from the cope end inward, finds the first toroidal face
    (representing a bend), and computes the back-of-bend direction.

    Args:
        body: The incoming tube body
        cope_end: 3D point at the cope end of the tube

    Returns:
        Tuple of (reference_vector_or_None, description).
        If no bend found, returns (None, "straight tube").
    """
    import adsk.core

    for face in body.faces:
        geom = face.geometry
        if isinstance(geom, adsk.core.Torus):
            # Found a toroidal face (bend)
            center = geom.origin

            # Back-of-bend = vector from torus center outward
            # (away from the center of curvature = extrados)
            # Project onto cross-section plane of the tube at cope end
            cope_x, cope_y, cope_z = cope_end
            cx, cy, cz = center.x, center.y, center.z

            # Direction from torus center to tube centerline
            ref_x = cope_x - cx
            ref_y = cope_y - cy
            ref_z = cope_z - cz

            mag = math.sqrt(ref_x**2 + ref_y**2 + ref_z**2)
            if mag > 1e-10:
                ref_vector: Vector3D = (ref_x / mag, ref_y / mag, ref_z / mag)
                return ref_vector, "Back of last bend (extrados)"

    return None, "Straight tube — use scribed reference line"


def identify_cope_end(
    body: adsk.fusion.BRepBody,
    receiving_bodies: list[adsk.fusion.BRepBody],
) -> Point3D:
    """
    Determine which end of the incoming tube faces the node.

    Finds the endpoint closest to the centroid of receiving body positions.

    Args:
        body: The incoming tube body
        receiving_bodies: Bodies at the target node

    Returns:
        3D point at the cope end

    Raises:
        ValueError: If tube endpoints cannot be determined
    """
    # Get bounding box endpoints along the tube axis
    bbox = body.boundingBox
    min_pt = bbox.minPoint
    max_pt = bbox.maxPoint

    # Tube endpoint candidates: min and max of bounding box
    end1: Point3D = (min_pt.x, min_pt.y, min_pt.z)
    end2: Point3D = (max_pt.x, max_pt.y, max_pt.z)

    # Compute centroid of receiving bodies
    if not receiving_bodies:
        return end1

    cx, cy, cz = 0.0, 0.0, 0.0
    for rb in receiving_bodies:
        rb_bbox = rb.boundingBox
        cx += (rb_bbox.minPoint.x + rb_bbox.maxPoint.x) / 2
        cy += (rb_bbox.minPoint.y + rb_bbox.maxPoint.y) / 2
        cz += (rb_bbox.minPoint.z + rb_bbox.maxPoint.z) / 2
    n = len(receiving_bodies)
    centroid: Point3D = (cx / n, cy / n, cz / n)

    # Return the endpoint closest to the receiving bodies centroid
    d1 = sum((a - b) ** 2 for a, b in zip(end1, centroid, strict=True))
    d2 = sum((a - b) ** 2 for a, b in zip(end2, centroid, strict=True))

    return end1 if d1 < d2 else end2
