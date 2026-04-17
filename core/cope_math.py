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
from .conventions import (
    ROTATION_ZERO_DESCRIPTION,
    ROTATION_ZERO_STRAIGHT_DESCRIPTION,
)
from .tolerances import (
    HOLESAW_CLEARANCE,
    HOLESAW_DEEP_THRESHOLD,
    HOLESAW_EXTRA_DEEP_THRESHOLD,
    LOBE_COLLAPSE_DEGREES,
    MAX_HOLESAW_DEPTH,
    MAX_NOTCHER_ANGLE,
    MIN_COPE_INCLINATION_DEG,
    VALLEY_DEPTH_OD_RATIO,
)


@dataclass(slots=True)
class _Lobe:
    """A peak region in the z-profile."""
    apex_azimuth: int      # Degree index (0-359) of the peak
    apex_z: float          # Z value at the peak
    start_azimuth: int     # Start of lobe region
    end_azimuth: int       # End of lobe region


def calculate_cope(
    v1: Vector3D,
    od1: float,
    receiving_tubes: list[ReceivingTube],
    reference_vector: Vector3D | None = None,
    unit_label: str = '"',
) -> CopeResult:
    """
    Calculate cope settings for a tube at a multi-tube node.

    Args:
        v1: Incoming tube centerline unit vector
        od1: Incoming tube outer diameter (display units, e.g. inches)
        receiving_tubes: Receiving tubes at the node
        reference_vector: Back-of-bend direction for rotation reference.
            None for straight tubes (uses arbitrary reference).
        unit_label: Unit suffix for warning messages (default: '"' for inches)

    Returns:
        CopeResult with pass settings, method recommendation, and z-profile

    Raises:
        geometry.ZeroVectorError: If any tube vector has zero length
        ValueError: If tubes are parallel/anti-parallel or no receiving tubes
    """
    if not receiving_tubes:
        raise ValueError("At least one receiving tube is required")

    if od1 <= 0.0:
        raise ValueError(f"Incoming tube OD must be positive, got {od1}")
    for i, rt in enumerate(receiving_tubes):
        if rt.od <= 0.0:
            name = rt.name or f"tube {i + 1}"
            raise ValueError(f"Receiving tube OD must be positive for {name}, got {rt.od}")

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

    # Compute inclination angle and azimuth for each receiver
    inclination_angles: list[float] = []
    azimuths: list[float] = []
    for rt in receiving_tubes:
        inclination_angles.append(_compute_inclination_angle(v1_norm, normalize(rt.vector)))
        azimuths.append(
            _compute_rotation_mark(v1_norm, normalize(rt.vector), reference_vector)
        )

    # Filter out shallow-angle receivers whose inclination is below the
    # minimum threshold.  At very small angles sin(α) → 0 and the saddle
    # formula produces impractically tall z-profiles (z ∝ 1/sin(α)).
    # These are almost always false-positive detections (parallel braces,
    # duplicate occurrences of the same body, etc.).
    shallow_warnings: list[str] = []
    valid_indices: list[int] = []
    for i, angle in enumerate(inclination_angles):
        if angle < MIN_COPE_INCLINATION_DEG:
            name = receiving_tubes[i].name or f"tube {i + 1}"
            shallow_warnings.append(
                f"Receiver '{name}' filtered: inclination {angle:.1f}° is below "
                f"{MIN_COPE_INCLINATION_DEG}° minimum (near-parallel, likely false positive)."
            )
        else:
            valid_indices.append(i)

    if not valid_indices:
        raise ValueError(
            f"All receiving tubes are below the {MIN_COPE_INCLINATION_DEG}° "
            f"minimum inclination threshold. No valid cope can be computed. "
            f"Check that the correct receiving tubes were detected."
        )

    # Build filtered lists for downstream computation
    filtered_tubes = [receiving_tubes[i] for i in valid_indices]
    filtered_inclinations = [inclination_angles[i] for i in valid_indices]
    filtered_azimuths = [azimuths[i] for i in valid_indices]

    # Compute combined z-profile
    z_profile = _compute_z_profile(filtered_tubes, filtered_inclinations, filtered_azimuths, od1 / 2.0)

    # Detect lobes and build passes
    lobes = _detect_lobes(z_profile, od1)
    passes = _build_passes(lobes, filtered_inclinations, filtered_azimuths, filtered_tubes, od1, unit_label)

    # Classify method
    method, method_desc = _classify_method(passes, lobes)

    # Determine reference info
    has_bend_ref = reference_vector is not None
    if has_bend_ref:
        ref_desc = ROTATION_ZERO_DESCRIPTION
    else:
        ref_desc = ROTATION_ZERO_STRAIGHT_DESCRIPTION

    # Collect warnings
    warnings: list[str] = list(shallow_warnings)
    for p in passes:
        if p.holesaw_warning:
            warnings.append(p.holesaw_warning)

    # Collect all receiver names (including those merged into a single pass)
    all_receiver_names = [rt.name for rt in filtered_tubes if rt.name]

    return CopeResult(
        passes=passes,
        is_multi_pass=len(passes) > 1,
        method=method,
        method_description=method_desc,
        z_profile=z_profile,
        has_bend_reference=has_bend_ref,
        reference_description=ref_desc,
        warnings=warnings,
        all_receiver_names=all_receiver_names,
    )


def _compute_inclination_angle(v1: Vector3D, v2: Vector3D) -> float:
    """
    Compute the inclination angle between two tube centerlines.

    The inclination angle (a.k.a. included angle) is the geometric angle
    between the tube axis vectors (0-90 range). It is used internally for
    saddle math (sin(alpha) in the z-profile and holesaw depth formulas).
    The notcher degree wheel reads the *complement*:
    notcher_setting = 90 - inclination_angle.

    Args:
        v1: Incoming tube unit vector
        v2: Receiving tube unit vector

    Returns:
        Inclination angle in degrees (0-90)
    """
    cos_theta = abs(dot_product(v1, v2))
    cos_theta = max(0.0, min(1.0, cos_theta))
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
    inclination_angles: list[float],
    azimuths: list[float],
    r1: float,
) -> list[float]:
    """
    Compute the cope z-profile at 1-degree increments around the tube.

    Uses the exact cylinder-cylinder intersection formula:
        z(azimuth) = [sqrt(R2² - R1²·sin²(azimuth)) - R1·cos(alpha)·cos(azimuth)] / sin(alpha)

    where alpha is the inclination angle (a.k.a. included angle) between tube
    axes, R1 is the incoming tube radius, and R2 is the receiving tube radius.
    The azimuth is the angle around the incoming tube circumference measured
    from the cope apex direction.

    The final profile is the envelope (max) across all receivers.

    Args:
        receiving_tubes: Receiving tube specs
        inclination_angles: Inclination angle for each receiver (degrees, 0-90)
        azimuths: Azimuth offset for each receiver (degrees, 0-360)
        r1: Incoming tube radius (display units)

    Returns:
        360 floats representing z depth at each degree
    """
    z_final: list[float] = [0.0] * 360

    for i, rt in enumerate(receiving_tubes):
        alpha_rad = math.radians(inclination_angles[i])
        sin_alpha = math.sin(alpha_rad)
        if sin_alpha < 1e-10:
            continue

        cos_alpha = math.cos(alpha_rad)
        r2 = rt.od / 2.0
        azimuth_offset = azimuths[i]
        r1_sq = r1 * r1

        for phi in range(360):
            theta = math.radians(phi - azimuth_offset)
            sin_phi = math.sin(theta)
            cos_phi = math.cos(theta)
            discriminant = r2 * r2 - r1_sq * sin_phi * sin_phi
            if discriminant < 0.0:
                continue  # no intersection at this azimuth
            z_val = (math.sqrt(discriminant) - r1 * cos_alpha * cos_phi) / sin_alpha
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
        apex_azimuth = max(range(360), key=lambda d: z_profile[d])
        return [_Lobe(
            apex_azimuth=apex_azimuth,
            apex_z=z_profile[apex_azimuth],
            start_azimuth=0,
            end_azimuth=359,
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
        apex_azimuth = max(range(360), key=lambda d: z_profile[d])
        if z_profile[apex_azimuth] > 0:
            return [_Lobe(
                apex_azimuth=apex_azimuth,
                apex_z=z_profile[apex_azimuth],
                start_azimuth=apex_azimuth,
                end_azimuth=apex_azimuth,
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

        apex_azimuth = max(indices, key=lambda d: z_profile[d])
        apex_z = z_profile[apex_azimuth]

        lobes.append(_Lobe(
            apex_azimuth=apex_azimuth,
            apex_z=apex_z,
            start_azimuth=start,
            end_azimuth=end,
        ))

    # Sort by apex z descending (dominant first)
    lobes.sort(key=lambda lobe: lobe.apex_z, reverse=True)

    return lobes


def _build_passes(
    lobes: list[_Lobe],
    inclination_angles: list[float],
    azimuths: list[float],
    receiving_tubes: list[ReceivingTube],
    od1: float,
    unit_label: str = '"',
) -> list[CopePass]:
    """
    Build CopePass entries from detected lobes.

    Orchestrates: classify → assign → create passes → sort & mark dominant.

    Args:
        lobes: Detected lobes, sorted by apex z descending
        inclination_angles: Inclination angle per receiver (degrees, 0-90)
        azimuths: Azimuth offset per receiver (degrees, 0-360)
        receiving_tubes: Receiving tube specs (for OD lookup)
        od1: Incoming tube OD
        unit_label: Unit suffix for warning messages

    Returns:
        List of CopePass entries
    """
    if not lobes:
        return []

    front_lobes, back_lobes = _classify_lobes_front_back(lobes, azimuths)
    unique_lobes, merged_receivers = _assign_lobes_to_receivers(
        front_lobes, back_lobes, azimuths, inclination_angles,
    )

    total_passes = len(unique_lobes) + len(merged_receivers)
    single_pass = total_passes == 1

    passes: list[CopePass] = []
    for lobe, recv_idx in unique_lobes:
        plunge_depth = lobe.apex_z + HOLESAW_CLEARANCE
        span = _lobe_span(lobe)
        passes.append(_create_cope_pass(
            inclination_angles[recv_idx], azimuths[recv_idx],
            plunge_depth, receiving_tubes[recv_idx].name,
            od1, single_pass, span, unit_label,
        ))

    for recv_idx in merged_receivers:
        r2 = receiving_tubes[recv_idx].od / 2.0
        peak_depth = _compute_receiver_peak_depth(
            inclination_angles[recv_idx], od1 / 2.0, r2,
        )
        plunge_depth = peak_depth + HOLESAW_CLEARANCE
        passes.append(_create_cope_pass(
            inclination_angles[recv_idx], azimuths[recv_idx],
            plunge_depth, receiving_tubes[recv_idx].name,
            od1, False, 180.0, unit_label,
        ))

    return _sort_and_mark_dominant(passes)


def _classify_lobes_front_back(
    lobes: list[_Lobe],
    azimuths: list[float],
) -> tuple[list[_Lobe], list[_Lobe]]:
    """Separate lobes into front (within 90° of any receiver) and back."""
    front: list[_Lobe] = []
    back: list[_Lobe] = []
    for lobe in lobes:
        is_front = any(
            _azimuth_dist(lobe.apex_azimuth, az) <= 90 for az in azimuths
        )
        if is_front:
            front.append(lobe)
        else:
            back.append(lobe)
    return front, back


def _assign_lobes_to_receivers(
    front_lobes: list[_Lobe],
    back_lobes: list[_Lobe],
    azimuths: list[float],
    inclination_angles: list[float],
) -> tuple[list[tuple[_Lobe, int]], list[int]]:
    """
    Assign front lobes to receivers; detect merged receivers needing separate passes.

    Returns:
        unique_lobes: List of (lobe, receiver_index) tuples, sorted by apex_z descending.
        merged_receivers: Receiver indices whose saddles merged into another lobe
            but whose notcher angles differ enough to warrant separate passes.
    """
    # Assign front lobes to receivers (one per receiver, highest apex first).
    seen_receivers: set[int] = set()
    unique_lobes: list[tuple[_Lobe, int]] = []
    for lobe in front_lobes:
        receiver_idx = _match_lobe_to_receiver(lobe, azimuths)
        if receiver_idx not in seen_receivers:
            seen_receivers.add(receiver_idx)
            unique_lobes.append((lobe, receiver_idx))

    # For receivers with no front lobe, check merged or back lobes.
    merged_receivers: list[int] = []
    if len(seen_receivers) < len(azimuths):
        for recv_idx in range(len(azimuths)):
            if recv_idx in seen_receivers:
                continue
            is_merged = any(
                _azimuth_dist(lobe.apex_azimuth, azimuths[recv_idx]) <= 90
                for lobe, _ in unique_lobes
            )
            if is_merged:
                nearest_lobe = (
                    unique_lobes[0][0] if len(unique_lobes) == 1
                    else min(
                        (lb for lb, _ in unique_lobes),
                        key=lambda lb: _azimuth_dist(lb.apex_azimuth, azimuths[recv_idx]),
                    )
                )
                owner_idx = _match_lobe_to_receiver(nearest_lobe, azimuths)
                owner_notcher = 90.0 - inclination_angles[owner_idx]
                recv_notcher = 90.0 - inclination_angles[recv_idx]
                if abs(owner_notcher - recv_notcher) > LOBE_COLLAPSE_DEGREES:
                    merged_receivers.append(recv_idx)
            else:
                for lobe in back_lobes:
                    bl_recv = _match_lobe_to_receiver(lobe, azimuths)
                    if bl_recv == recv_idx:
                        unique_lobes.append((lobe, recv_idx))
                        seen_receivers.add(recv_idx)
                        break

    # Re-sort by apex_z descending (dominant first) after possible insertions.
    unique_lobes.sort(key=lambda pair: pair[0].apex_z, reverse=True)
    return unique_lobes, merged_receivers


def _lobe_span(lobe: _Lobe) -> float:
    """Compute the angular span of a lobe in degrees."""
    if lobe.start_azimuth <= lobe.end_azimuth:
        return float(lobe.end_azimuth - lobe.start_azimuth)
    return float((360 - lobe.start_azimuth) + lobe.end_azimuth)


def _create_cope_pass(
    inclination_angle: float,
    azimuth: float,
    plunge_depth: float,
    receiver_name: str,
    od1: float,
    is_pass_through: bool,
    lobe_span_degrees: float,
    unit_label: str,
) -> CopePass:
    """Build a single CopePass from receiver parameters."""
    notcher_angle = 90.0 - inclination_angle
    holesaw_depth, holesaw_warning = _compute_holesaw_depth(
        od1, inclination_angle, is_pass_through, plunge_depth, unit_label,
    )
    return CopePass(
        notcher_angle=round(notcher_angle, 1),
        rotation_mark=round(azimuth, 1),
        plunge_depth=round(plunge_depth, 3),
        is_pass_through=is_pass_through,
        lobe_span_degrees=round(lobe_span_degrees, 1),
        dominant=False,
        holesaw_depth_required=round(holesaw_depth, 3),
        holesaw_warning=holesaw_warning,
        receiver_name=receiver_name,
    )


def _sort_and_mark_dominant(passes: list[CopePass]) -> list[CopePass]:
    """Sort passes by plunge depth descending; mark deepest as dominant."""
    passes.sort(key=lambda p: p.plunge_depth, reverse=True)
    if passes:
        for p in passes:
            p.dominant = False
        passes[0].dominant = True
    return passes


def _match_lobe_to_receiver(lobe: _Lobe, azimuths: list[float]) -> int:
    """Find which receiver's azimuth is closest to the lobe apex azimuth."""
    best_idx = 0
    best_dist = 360.0
    for i, az in enumerate(azimuths):
        dist = _azimuth_dist(lobe.apex_azimuth, az)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _azimuth_dist(a: float, b: float) -> float:
    """Shortest angular distance between two azimuths (0-180)."""
    d = abs(a - b)
    return d if d <= 180 else 360 - d


def _compute_receiver_peak_depth(
    inclination_angle: float,
    r1: float,
    r2: float,
) -> float:
    """
    Compute the maximum saddle depth for a single receiver.

    The maximum occurs at the back of the saddle (phi=180° from the
    receiver azimuth), where sin(phi) = 0 and cos(phi) = -1:

        z_max = [R2 + R1·cos(alpha)] / sin(alpha)

    This is the deepest point the holesaw must reach for a plunge cut
    to fully clear the receiving tube.

    Args:
        inclination_angle: Inclination angle between tube axes (degrees, 0-90)
        r1: Incoming tube radius
        r2: Receiving tube radius

    Returns:
        Maximum saddle z depth (always >= 0)
    """
    alpha_rad = math.radians(inclination_angle)
    sin_alpha = math.sin(alpha_rad)
    if sin_alpha < 1e-10:
        return 0.0
    cos_alpha = math.cos(alpha_rad)
    z_max = (r2 + r1 * cos_alpha) / sin_alpha
    return max(0.0, z_max)


def _compute_holesaw_depth(
    od1: float,
    inclination_angle: float,
    is_pass_through: bool,
    plunge_depth: float,
    unit_label: str = '"',
) -> tuple[float, str | None]:
    """
    Compute minimum holesaw cutting depth required.

    For pass-through: depth = OD1 / sin(inclination_angle)
    For plunge-only: depth = plunge_depth

    Args:
        od1: Incoming tube OD
        inclination_angle: Inclination angle (a.k.a. included angle) between
            tube centerlines (degrees, 0-90)
        is_pass_through: Whether this is a full pass-through
        plunge_depth: Plunge depth for non-pass-through cuts
        unit_label: Unit suffix for warning messages (default: '"' for inches)

    Returns:
        Tuple of (depth_required, warning_message_or_None)
    """
    if is_pass_through:
        alpha_rad = math.radians(inclination_angle)
        sin_alpha = math.sin(alpha_rad)
        if sin_alpha < 1e-10:
            depth = od1 * 100  # Effectively infinite
        else:
            depth = od1 / sin_alpha
    else:
        depth = plunge_depth

    warning: str | None = None
    if depth > MAX_HOLESAW_DEPTH:
        warning = (
            f"Holesaw depth exceeds {MAX_HOLESAW_DEPTH}{unit_label}. A standard notcher "
            f"setup cannot complete this pass. Use Method C (wrap template + grinder)."
        )
    elif depth > HOLESAW_EXTRA_DEEP_THRESHOLD:
        warning = (
            f"Requires extra-deep holesaw ({depth:.1f}{unit_label} cutting depth). "
            f"These are specialty items — confirm you have the right tool. "
            f"Consider Method C (grinder) instead."
        )
    elif depth > HOLESAW_DEEP_THRESHOLD:
        warning = (
            f"Requires deep holesaw ({depth:.1f}{unit_label} cutting depth). "
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
        if p.notcher_angle > MAX_NOTCHER_ANGLE:
            return ("C", "Wrap template + grinder — angle too acute for reliable notcher work")
        if p.holesaw_depth_required > MAX_HOLESAW_DEPTH:
            return ("C", "Wrap template + grinder — holesaw depth exceeds notcher capacity")

    if len(lobes) >= 3:
        return ("C", "Wrap template + grinder — three or more lobes detected")

    # Check for close lobes that can't collapse to single pass
    if len(lobes) == 2:
        sep = abs(lobes[0].apex_azimuth - lobes[1].apex_azimuth)
        if sep > 180:
            sep = 360 - sep
        if sep < LOBE_COLLAPSE_DEGREES:
            # Lobes are close — could potentially be single pass
            return ("A", "Notcher, single pass — lobes are close enough to merge")

    if len(passes) == 1:
        return ("A", "Notcher, single pass — straightforward push-through")

    return ("B", "Notcher, multi-pass — read pass sequence carefully before cutting")
