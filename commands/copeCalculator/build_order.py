"""Build order validation for cope calculator.

Checks that receiving tube bodies at a node have already been coped
before calculating the incoming tube's cope profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import adsk.fusion


@dataclass(slots=True)
class ValidationResult:
    """Result of validating a single receiving body."""
    body_name: str
    is_valid: bool
    message: str


def validate_receiving_bodies(
    incoming: adsk.fusion.BRepBody,
    receiving: list[adsk.fusion.BRepBody],
) -> list[ValidationResult]:
    """
    Validate that receiving bodies appear to have been properly coped.

    Checks each receiving body for non-cylindrical faces in the intersection
    region, which would indicate a previous cope has been cut.

    Args:
        incoming: The incoming tube body being coped
        receiving: List of receiving tube bodies at the node

    Returns:
        List of ValidationResult for each receiving body
    """
    import adsk.core

    results: list[ValidationResult] = []

    for body in receiving:
        # Check if body has any non-cylindrical, non-planar faces
        # (indicating a cope or other modification has been made)
        has_non_cylindrical = False
        face_count = 0

        for face in body.faces:
            face_count += 1
            geom = face.geometry
            if not isinstance(geom, (adsk.core.Cylinder, adsk.core.Plane)):
                has_non_cylindrical = True
                break

        if has_non_cylindrical:
            results.append(ValidationResult(
                body_name=body.name,
                is_valid=True,
                message="Body has cope geometry — OK",
            ))
        elif face_count <= 3:
            # Simple cylinder (2 cylindrical faces + 0-2 planar end caps)
            # Likely an un-coped tube
            results.append(ValidationResult(
                body_name=body.name,
                is_valid=False,
                message=(
                    f"'{body.name}' appears to be an un-coped tube. "
                    f"Cope this tube first before calculating the incoming tube's cope."
                ),
            ))
        else:
            results.append(ValidationResult(
                body_name=body.name,
                is_valid=True,
                message="Body geometry appears modified — OK",
            ))

    return results
