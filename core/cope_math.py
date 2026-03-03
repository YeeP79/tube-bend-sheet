"""Pure math module for tube cope calculations.

Zero Fusion 360 dependencies. Takes plain Python vectors and numbers,
returns CopeResult. Fully unit-testable without Fusion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..models.cope_data import CopePass, CopeResult, ReceivingTube
from ..models.types import Vector3D
from .geometry import (
    cross_product,
    dot_product,
    magnitude,
    normalize,
    project_onto_plane,
)
from .tolerances import (
    ACUTE_ANGLE_LIMIT,
    HOLESAW_CLEARANCE,
    LOBE_COLLAPSE_DEGREES,
    MAX_HOLESAW_DEPTH,
    VALLEY_DEPTH_OD_RATIO,
)


@dataclass(slots=True)
class _Lobe:
    """A peak region in the z-profile."""
    apex_phi: int          # Degree index (0-359) of the peak
    apex_z: float          # Z value at the peak
    start_phi: int         # Start of lobe region
    end_phi: int           # End of lobe region
    receiver_index: int    # Which receiving tube dominates this lobe


def calculate_cope(
    v1: Vector3D,
    od1: float,
    receiving_tubes: list[ReceivingTube],
    reference_vector: Vector3D | None = None,
) -> CopeResult:
    """
    Calculate cope settings for a tube at a multi-tube node.

    Args:
        v1: Incoming tube centerline unit vector
        od1: Incoming tube outer diameter (display units, e.g. inches)
        receiving_tubes: Receiving tubes at the node
        reference_vector: Back-of-bend direction for rotation reference.
            None for straight tubes (uses arbitrary reference).

    Returns:
        CopeResult with pass settings, method recommendation, and z-profile

    Raises:
        geometry.ZeroVectorError: If any tube vector has zero length
        ValueError: If tubes are parallel/anti-parallel or no receiving tubes
    """
    if not receiving_tubes:
        raise ValueError("At least one receiving tube is required")

    v1_norm = normalize(v1)

    # Validate all receiving tube vectors
    for i, rt in enumerate(receiving_tubes):
        rt_norm = normalize(rt.vector)
        dot = abs(dot_product(v1_norm, rt_norm))
        if dot > 1.0 - 1e-8:
            name = rt.name or f"tube {i + 1}"
            raise ValueError(
                f"Incoming tube is parallel/anti-parallel to receiving {name}. "
                f"A saddle cope is not meaningful for parallel tubes."
            )

    # Compute notcher angle and rotation for each receiver
    angles: list[float] = []
    rotations: list[float] = []
    for rt in receiving_tubes:
        angles.append(_compute_notcher_angle(v1_norm, normalize(rt.vector)))
        rotations.append(
            _compute_rotation_mark(v1_norm, normalize(rt.vector), reference_vector)
        )

    # Compute combined z-profile
    z_profile = _compute_z_profile(receiving_tubes, angles, rotations)

    # Detect lobes and build passes
    lobes = _detect_lobes(z_profile, od1)
    passes = _build_passes(lobes, angles, rotations, od1)

    # Classify method
    method, method_desc = _classify_method(passes, lobes)

    # Determine reference info
    has_bend_ref = reference_vector is not None
    if has_bend_ref:
        ref_desc = "Back of last bend (extrados)"
    else:
        ref_desc = "User-scribed reference line"

    # Collect warnings
    warnings: list[str] = []
    for p in passes:
        if p.holesaw_warning:
            warnings.append(p.holesaw_warning)

    return CopeResult(
        passes=passes,
        is_multi_pass=len(passes) > 1,
        method=method,
        method_description=method_desc,
        z_profile=z_profile,
        has_bend_reference=has_bend_ref,
        reference_description=ref_desc,
        warnings=warnings,
    )


def _compute_notcher_angle(v1: Vector3D, v2: Vector3D) -> float:
    """
    Compute the included angle between two tube centerlines.

    The notcher degree wheel reads this angle. At 90 degrees the tubes
    are perpendicular.

    Args:
        v1: Incoming tube unit vector
        v2: Receiving tube unit vector

    Returns:
        Included angle in degrees (0-90)
    """
    cos_theta = abs(dot_product(v1, v2))
    cos_theta = min(1.0, cos_theta)
    return math.degrees(math.acos(cos_theta))


def _compute_rotation_mark(
    v1: Vector3D,
    v2: Vector3D,
    reference_vector: Vector3D | None,
) -> float:
    """
    Compute how many degrees CW to rotate the tube from reference to cope apex.

    The cope apex is the deepest point of the saddle cut, located in the
    plane containing both centerlines, on the side facing the receiving tube.

    Convention: 0 degrees = reference mark (back-of-bend or user scribe).
    Angles increase clockwise when viewed from the coped end.

    Args:
        v1: Incoming tube unit vector (points away from coped end)
        v2: Receiving tube unit vector
        reference_vector: Back-of-bend direction projected into cross-section,
            or None to use an arbitrary reference (first perpendicular axis).

    Returns:
        Rotation in degrees [0, 360)
    """
    # The cope apex direction is the projection of v2 onto the cross-section
    # plane of v1 (the plane perpendicular to v1 at the tube end).
    apex_dir = project_onto_plane(v2, v1)
    apex_mag = magnitude(apex_dir)
    if apex_mag < 1e-10:
        return 0.0
    apex_dir = normalize(apex_dir)

    # Establish reference direction in the cross-section plane
    if reference_vector is not None:
        ref_dir = project_onto_plane(reference_vector, v1)
        ref_mag = magnitude(ref_dir)
        if ref_mag < 1e-10:
            ref_dir = _arbitrary_perpendicular(v1)
        else:
            ref_dir = normalize(ref_dir)
    else:
        ref_dir = _arbitrary_perpendicular(v1)

    # Compute signed angle from ref_dir to apex_dir, CW when viewed
    # from coped end (looking along v1 direction).
    # CW from coped end = negative rotation about v1
    cos_a = max(-1.0, min(1.0, dot_product(ref_dir, apex_dir)))
    angle = math.degrees(math.acos(cos_a))

    # Determine sign using cross product
    cross = cross_product(ref_dir, apex_dir)
    # If cross is in same direction as v1, the rotation is CCW from coped end
    # (i.e., CW from coped end is the opposite)
    sign = dot_product(cross, v1)
    if sign < 0:
        angle = 360.0 - angle

    return angle % 360.0


def _arbitrary_perpendicular(v: Vector3D) -> Vector3D:
    """Find an arbitrary unit vector perpendicular to v."""
    # Choose the axis least aligned with v to avoid numerical issues
    ax, ay, az = abs(v[0]), abs(v[1]), abs(v[2])
    if ax <= ay and ax <= az:
        candidate = (1.0, 0.0, 0.0)
    elif ay <= az:
        candidate = (0.0, 1.0, 0.0)
    else:
        candidate = (0.0, 0.0, 1.0)
    perp = project_onto_plane(candidate, v)
    return normalize(perp)


def _compute_z_profile(
    receiving_tubes: list[ReceivingTube],
    angles: list[float],
    rotations: list[float],
) -> list[float]:
    """
    Compute the cope z-profile at 1-degree increments around the tube.

    For each receiving tube, z(phi) = (R_receive / sin(theta)) * cos(phi - phi_offset),
    clamped >= 0. The final profile is the envelope (max) across all receivers.

    Args:
        receiving_tubes: Receiving tube specs
        angles: Notcher angle for each receiver (degrees)
        rotations: Rotation mark for each receiver (degrees)

    Returns:
        360 floats representing z depth at each degree
    """
    z_final: list[float] = [0.0] * 360

    for i, rt in enumerate(receiving_tubes):
        theta_rad = math.radians(angles[i])
        sin_theta = math.sin(theta_rad)
        if sin_theta < 1e-10:
            continue

        r_receive = rt.od / 2.0
        amplitude = r_receive / sin_theta
        phi_offset = rotations[i]

        for phi in range(360):
            cos_val = math.cos(math.radians(phi - phi_offset))
            z_val = amplitude * cos_val
            z_val = max(0.0, z_val)
            z_final[phi] = max(z_final[phi], z_val)

    return z_final


def _detect_lobes(z_profile: list[float], od: float) -> list[_Lobe]:
    """
    Detect distinct lobes (peaks) in the z-profile.

    A lobe is a contiguous region of non-zero z values. Two lobes are
    considered distinct if separated by a valley where z drops below
    VALLEY_DEPTH_OD_RATIO * od.

    Args:
        z_profile: 360 z-values
        od: Incoming tube OD for valley threshold

    Returns:
        List of detected lobes, sorted by apex z descending (dominant first)
    """
    valley_threshold = VALLEY_DEPTH_OD_RATIO * od

    # Find all non-zero regions
    # We work on a circular buffer, so we need to handle wrap-around
    regions: list[tuple[int, int]] = []
    in_region = False
    region_start = 0

    # Find first zero-crossing to establish a clean starting point
    start_idx = -1
    for i in range(360):
        if z_profile[i] <= valley_threshold:
            start_idx = i
            break

    if start_idx == -1:
        # Entire profile is above threshold - single lobe
        apex_phi = max(range(360), key=lambda i: z_profile[i])
        return [_Lobe(
            apex_phi=apex_phi,
            apex_z=z_profile[apex_phi],
            start_phi=0,
            end_phi=359,
            receiver_index=0,
        )]

    for offset in range(360):
        i = (start_idx + offset) % 360
        z = z_profile[i]

        if z > valley_threshold and not in_region:
            in_region = True
            region_start = i
        elif z <= valley_threshold and in_region:
            in_region = False
            regions.append((region_start, (i - 1) % 360))

    # Close any open region
    if in_region:
        regions.append((region_start, (start_idx - 1) % 360))

    if not regions:
        # No significant lobes found - create a single lobe at the max
        apex_phi = max(range(360), key=lambda i: z_profile[i])
        if z_profile[apex_phi] > 0:
            return [_Lobe(
                apex_phi=apex_phi,
                apex_z=z_profile[apex_phi],
                start_phi=apex_phi,
                end_phi=apex_phi,
                receiver_index=0,
            )]
        return []

    # Build lobes from regions
    lobes: list[_Lobe] = []
    for start, end in regions:
        # Find apex within region
        if start <= end:
            indices = range(start, end + 1)
        else:
            # Wraps around 360
            indices = list(range(start, 360)) + list(range(0, end + 1))

        apex_phi = max(indices, key=lambda i: z_profile[i])
        apex_z = z_profile[apex_phi]

        lobes.append(_Lobe(
            apex_phi=apex_phi,
            apex_z=apex_z,
            start_phi=start,
            end_phi=end,
            receiver_index=0,  # Will be assigned below
        ))

    # Sort by apex z descending (dominant first)
    lobes.sort(key=lambda lobe: lobe.apex_z, reverse=True)

    return lobes


def _build_passes(
    lobes: list[_Lobe],
    angles: list[float],
    rotations: list[float],
    od1: float,
) -> list[CopePass]:
    """
    Build CopePass entries from detected lobes.

    Args:
        lobes: Detected lobes, sorted by apex z descending
        angles: Notcher angle per receiver
        rotations: Rotation mark per receiver
        od1: Incoming tube OD

    Returns:
        List of CopePass entries
    """
    if not lobes:
        # Fallback: shouldn't happen with valid inputs
        return []

    single_pass = len(lobes) == 1

    passes: list[CopePass] = []
    for i, lobe in enumerate(lobes):
        # Match lobe to nearest receiver by rotation angle
        receiver_idx = _match_lobe_to_receiver(lobe, rotations)

        notcher_angle = angles[receiver_idx]
        rotation_mark = rotations[receiver_idx]

        # Compute lobe span in degrees
        if lobe.start_phi <= lobe.end_phi:
            span = lobe.end_phi - lobe.start_phi
        else:
            span = (360 - lobe.start_phi) + lobe.end_phi

        # Compute plunge depth and holesaw requirements
        plunge_depth = lobe.apex_z + HOLESAW_CLEARANCE
        is_pass_through = single_pass

        holesaw_depth, holesaw_warning = _compute_holesaw_depth(
            od1, notcher_angle, is_pass_through, plunge_depth
        )

        passes.append(CopePass(
            notcher_angle=round(notcher_angle, 1),
            rotation_mark=round(rotation_mark, 1),
            plunge_depth=round(plunge_depth, 3),
            is_pass_through=is_pass_through,
            lobe_span_degrees=round(float(span), 1),
            dominant=(i == 0),
            holesaw_depth_required=round(holesaw_depth, 3),
            holesaw_warning=holesaw_warning,
        ))

    return passes


def _match_lobe_to_receiver(lobe: _Lobe, rotations: list[float]) -> int:
    """Find which receiver's rotation is closest to the lobe apex angle."""
    best_idx = 0
    best_dist = 360.0

    for i, rot in enumerate(rotations):
        dist = abs(lobe.apex_phi - rot)
        if dist > 180:
            dist = 360 - dist
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    return best_idx


def _compute_holesaw_depth(
    od1: float,
    notcher_angle: float,
    is_pass_through: bool,
    plunge_depth: float,
) -> tuple[float, str | None]:
    """
    Compute minimum holesaw cutting depth required.

    For pass-through: depth = OD1 / sin(theta)
    For plunge-only: depth = plunge_depth

    Args:
        od1: Incoming tube OD
        notcher_angle: Included angle in degrees
        is_pass_through: Whether this is a full pass-through
        plunge_depth: Plunge depth for non-pass-through cuts

    Returns:
        Tuple of (depth_required, warning_message_or_None)
    """
    if is_pass_through:
        theta_rad = math.radians(notcher_angle)
        sin_theta = math.sin(theta_rad)
        if sin_theta < 1e-10:
            depth = od1 * 100  # Effectively infinite
        else:
            depth = od1 / sin_theta
    else:
        depth = plunge_depth

    warning: str | None = None
    if depth > MAX_HOLESAW_DEPTH:
        warning = (
            f"Holesaw depth exceeds {MAX_HOLESAW_DEPTH}\". A standard notcher "
            f"setup cannot complete this pass. Use Method C (wrap template + grinder)."
        )
    elif depth > 3.0:
        warning = (
            f"Requires extra-deep holesaw ({depth:.1f}\" cutting depth). "
            f"These are specialty items — confirm you have the right tool. "
            f"Consider Method C (grinder) instead."
        )
    elif depth > 2.0:
        warning = (
            f"Requires deep holesaw ({depth:.1f}\" cutting depth). "
            f"Verify your holesaw before starting."
        )

    return depth, warning


def _classify_method(
    passes: list[CopePass],
    lobes: list[_Lobe],
) -> tuple[Literal["A", "B", "C"], str]:
    """
    Classify the recommended fabrication method.

    Method A: Single-pass push-through (notcher)
    Method B: Multi-pass controlled plunge (notcher)
    Method C: Wrap template + grinder

    Returns:
        Tuple of (method letter, human description)
    """
    # Check for Method C triggers
    for p in passes:
        if p.notcher_angle < ACUTE_ANGLE_LIMIT:
            return ("C", "Wrap template + grinder — angle too acute for reliable notcher work")
        if p.holesaw_depth_required > MAX_HOLESAW_DEPTH:
            return ("C", "Wrap template + grinder — holesaw depth exceeds notcher capacity")

    if len(lobes) >= 3:
        return ("C", "Wrap template + grinder — three or more lobes detected")

    # Check for close lobes that can't collapse to single pass
    if len(lobes) == 2:
        sep = abs(lobes[0].apex_phi - lobes[1].apex_phi)
        if sep > 180:
            sep = 360 - sep
        if sep < LOBE_COLLAPSE_DEGREES:
            # Lobes are close — could potentially be single pass
            return ("A", "Notcher, single pass — lobes are close enough to merge")

    if len(passes) == 1:
        return ("A", "Notcher, single pass — straightforward push-through")

    return ("B", "Notcher, multi-pass — read pass sequence carefully before cutting")
