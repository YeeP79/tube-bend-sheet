"""3D vector math and geometry utilities."""

from __future__ import annotations

import math

from ..models.types import Vector3D, Point3D
from .tolerances import CONNECTIVITY_CM, ZERO_MAGNITUDE

# Re-export for backward compatibility
CONNECTIVITY_TOLERANCE_CM: float = CONNECTIVITY_CM
ZERO_MAGNITUDE_TOLERANCE: float = ZERO_MAGNITUDE


class ZeroVectorError(ValueError):
    """Raised when a zero-length vector is used in calculations requiring non-zero vectors."""

    pass


def cross_product(v1: Vector3D, v2: Vector3D) -> Vector3D:
    """
    Calculate the cross product of two 3D vectors.
    
    Args:
        v1: First vector (x, y, z)
        v2: Second vector (x, y, z)
        
    Returns:
        Cross product vector (x, y, z)
    """
    return (
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0]
    )


def dot_product(v1: Vector3D, v2: Vector3D) -> float:
    """
    Calculate the dot product of two 3D vectors.
    
    Args:
        v1: First vector (x, y, z)
        v2: Second vector (x, y, z)
        
    Returns:
        Scalar dot product
    """
    return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]


def magnitude(v: Vector3D) -> float:
    """
    Calculate the magnitude (length) of a 3D vector.

    Args:
        v: Vector (x, y, z)

    Returns:
        Scalar magnitude
    """
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


def _safe_magnitude_product(v1: Vector3D, v2: Vector3D) -> float:
    """
    Calculate the product of magnitudes, raising if either vector has zero length.

    Args:
        v1: First vector
        v2: Second vector

    Returns:
        Product of magnitudes (mag1 * mag2)

    Raises:
        ZeroVectorError: If either vector has zero or near-zero length
    """
    mag1 = magnitude(v1)
    mag2 = magnitude(v2)

    if mag1 < ZERO_MAGNITUDE_TOLERANCE:
        raise ZeroVectorError(
            f"First vector has zero length (magnitude={mag1}): {v1}"
        )
    if mag2 < ZERO_MAGNITUDE_TOLERANCE:
        raise ZeroVectorError(
            f"Second vector has zero length (magnitude={mag2}): {v2}"
        )

    return mag1 * mag2


def angle_between_vectors(v1: Vector3D, v2: Vector3D) -> float:
    """
    Calculate the angle between two vectors in degrees.

    Args:
        v1: First vector
        v2: Second vector

    Returns:
        Angle in degrees (0-180)

    Raises:
        ZeroVectorError: If either vector has zero length
    """
    mag_product = _safe_magnitude_product(v1, v2)
    cos_angle: float = dot_product(v1, v2) / mag_product
    cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp for floating point errors
    return math.degrees(math.acos(cos_angle))


def calculate_rotation(n1: Vector3D, n2: Vector3D) -> float:
    """
    Calculate the rotation angle between two bend plane normals.

    This is the angle you rotate the tube between bends on the bender.

    Args:
        n1: Normal vector of first bend plane
        n2: Normal vector of second bend plane

    Returns:
        Rotation angle in degrees (0-180)

    Raises:
        ZeroVectorError: If either normal vector has zero length
    """
    mag_product = _safe_magnitude_product(n1, n2)
    cos_theta: float = dot_product(n1, n2) / mag_product
    cos_theta = max(-1.0, min(1.0, cos_theta))  # Clamp for floating point errors
    return math.degrees(math.acos(cos_theta))


def distance_between_points(p1: Point3D, p2: Point3D) -> float:
    """
    Calculate the Euclidean distance between two 3D points.
    
    Args:
        p1: First point (x, y, z)
        p2: Second point (x, y, z)
        
    Returns:
        Distance between points
    """
    return math.sqrt(
        (p2[0] - p1[0])**2 +
        (p2[1] - p1[1])**2 +
        (p2[2] - p1[2])**2
    )


def points_are_close(p1: Point3D, p2: Point3D,
                     tolerance: float = CONNECTIVITY_TOLERANCE_CM) -> bool:
    """
    Check if two points are within tolerance of each other.

    Args:
        p1: First point
        p2: Second point
        tolerance: Maximum distance to consider "close"

    Returns:
        True if points are within or equal to tolerance distance
    """
    return distance_between_points(p1, p2) <= tolerance
