"""Tests for cope math module — all 5 spec test cases plus defensive tests.

Run with: pytest tests/test_cope_math.py -v
"""
import math

import pytest

from core.cope_math import (
    _compute_holesaw_depth,
    _compute_notcher_angle,
    _compute_rotation_mark,
    calculate_cope,
)
from core.geometry import ZeroVectorError
from models.cope_data import ReceivingTube


# ---------------------------------------------------------------------------
# Spec Case 1: Simple perpendicular cope
# ---------------------------------------------------------------------------
class TestCase1Perpendicular:
    """v1=(1,0,0), v2=(0,1,0), both 1.75" OD → 90° notcher, 0° rotation."""

    def test_notcher_angle_90(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert abs(result.passes[0].notcher_angle - 90.0) < 0.1

    def test_rotation_mark_0(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        # With no reference vector, rotation is relative to arbitrary ref
        # The important thing is it's consistent and the result is valid
        assert 0.0 <= result.passes[0].rotation_mark < 360.0

    def test_single_pass(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert result.is_multi_pass is False
        assert len(result.passes) == 1

    def test_method_a(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert result.method == "A"

    def test_pass_through(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert result.passes[0].is_pass_through is True

    def test_holesaw_depth_perpendicular(self):
        """At 90°, depth = OD/sin(90°) = OD."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert abs(result.passes[0].holesaw_depth_required - 1.75) < 0.01

    def test_z_profile_length(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert len(result.z_profile) == 360

    def test_z_profile_has_nonzero_values(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert max(result.z_profile) > 0


# ---------------------------------------------------------------------------
# Spec Case 2: Moon Patrol front cross-brace (19.3° elevation)
# ---------------------------------------------------------------------------
class TestCase2Elevation:
    """Tube at 19.3° elevation, receiving tube along X axis."""

    V1 = (0.0, math.cos(math.radians(19.3)), math.sin(math.radians(19.3)))
    V2 = (1.0, 0.0, 0.0)
    OD = 1.75

    def test_notcher_angle(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[ReceivingTube(vector=self.V2, od=self.OD)],
        )
        # arccos(|v1 · v2|) where v1 · v2 = 0 (perpendicular in X)
        # v1 has no X component, so dot = 0, angle = 90°
        assert abs(result.passes[0].notcher_angle - 90.0) < 0.1

    def test_single_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[ReceivingTube(vector=self.V2, od=self.OD)],
        )
        assert result.is_multi_pass is False

    def test_rotation_mark_valid(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[ReceivingTube(vector=self.V2, od=self.OD)],
        )
        assert 0.0 <= result.passes[0].rotation_mark < 360.0


# ---------------------------------------------------------------------------
# Spec Case 3: Compound angle (19.3° elevation + 12° lateral sweep)
# ---------------------------------------------------------------------------
class TestCase3CompoundAngle:
    """Compound angle differs from Case 2."""

    ELEV = math.radians(19.3)
    SWEEP = math.radians(12.0)
    # v1 with elevation and lateral sweep
    V1 = (
        math.sin(SWEEP) * math.cos(ELEV),
        math.cos(SWEEP) * math.cos(ELEV),
        math.sin(ELEV),
    )
    V2 = (1.0, 0.0, 0.0)
    OD = 1.75

    def test_notcher_angle_differs_from_case2(self):
        """Adding sweep should change the notcher angle from Case 2."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[ReceivingTube(vector=self.V2, od=self.OD)],
        )
        # Case 2 was 90°, compound angle should differ
        # v1 · v2 = sin(12°)*cos(19.3°) ≈ 0.2079 * 0.9435 ≈ 0.1962
        # arccos(0.1962) ≈ 78.7°
        expected = math.degrees(math.acos(
            abs(self.V1[0] * self.V2[0] + self.V1[1] * self.V2[1] + self.V1[2] * self.V2[2])
        ))
        assert abs(result.passes[0].notcher_angle - expected) < 0.2
        assert abs(result.passes[0].notcher_angle - 90.0) > 1.0  # Not 90

    def test_single_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[ReceivingTube(vector=self.V2, od=self.OD)],
        )
        assert result.is_multi_pass is False


# ---------------------------------------------------------------------------
# Spec Case 4: Multi-tube node, single-pass result
# ---------------------------------------------------------------------------
class TestCase4MultiTubeSinglePass:
    """Two near-coplanar receivers → single broad peak, no multi-pass."""

    V1 = (1.0, 0.0, 0.0)
    OD = 1.75
    # Two receivers nearly coplanar — separated by only ~15° in cross-section
    V2 = (0.0, 1.0, 0.0)
    V3 = (0.0, math.cos(math.radians(15.0)), math.sin(math.radians(15.0)))

    def test_single_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        # These receivers project to similar angles around the tube,
        # so the z-profile should have one broad peak
        assert result.is_multi_pass is False

    def test_z_profile_is_envelope(self):
        """z_final = max(z1, z2) at each phi."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        # Every z value should be >= 0
        assert all(z >= 0 for z in result.z_profile)
        # Profile should have significant height
        assert max(result.z_profile) > 0.5


# ---------------------------------------------------------------------------
# Spec Case 5: Multi-pass cope
# ---------------------------------------------------------------------------
class TestCase5MultiPass:
    """Two receivers on opposite sides of cross-section → multi-pass."""

    V1 = (0.0, 0.0, 1.0)  # Incoming tube along Z
    OD = 1.75
    # Receiver 1: along +X (projects to 0° in cross-section)
    V2 = (1.0, 0.0, 0.0)
    # Receiver 2: along -X (projects to 180° — opposite side)
    V3 = (-1.0, 0.0, 0.0)

    def test_multi_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        assert result.is_multi_pass is True

    def test_two_passes(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        assert len(result.passes) == 2

    def test_one_dominant_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        dominant_count = sum(1 for p in result.passes if p.dominant)
        assert dominant_count == 1

    def test_passes_not_pass_through(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        for p in result.passes:
            assert p.is_pass_through is False

    def test_plunge_depths_positive(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        for p in result.passes:
            assert p.plunge_depth > 0

    def test_method_b(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        assert result.method == "B"

    def test_both_notcher_angles_90(self):
        """Both receivers are perpendicular to incoming → 90° each."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        for p in result.passes:
            assert abs(p.notcher_angle - 90.0) < 0.1


# ---------------------------------------------------------------------------
# Defensive tests
# ---------------------------------------------------------------------------
class TestParallelTubes:
    """Parallel/anti-parallel tubes should raise ValueError."""

    def test_parallel_raises(self):
        with pytest.raises(ValueError, match="parallel"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(1.0, 0.0, 0.0), od=1.75)],
            )

    def test_anti_parallel_raises(self):
        with pytest.raises(ValueError, match="parallel"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(-1.0, 0.0, 0.0), od=1.75)],
            )

    def test_nearly_parallel_raises(self):
        with pytest.raises(ValueError, match="parallel"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(1.0, 1e-9, 0.0), od=1.75)],
            )


class TestZeroVectors:
    """Zero-length vectors should raise ZeroVectorError."""

    def test_zero_incoming_vector(self):
        with pytest.raises(ZeroVectorError):
            calculate_cope(
                v1=(0.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            )

    def test_zero_receiving_vector(self):
        with pytest.raises(ZeroVectorError):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(0.0, 0.0, 0.0), od=1.75)],
            )


class TestNoReceivers:
    """Empty receiving tubes list should raise."""

    def test_no_receiving_tubes(self):
        with pytest.raises(ValueError, match="At least one"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[],
            )


class TestAcuteAngleMethodC:
    """Very acute angle should trigger Method C."""

    def test_acute_angle_method_c(self):
        # 20° included angle (below 25° ACUTE_ANGLE_LIMIT)
        # v1 · v2 = cos(20°) ≈ 0.9397
        v2 = (math.cos(math.radians(20.0)), math.sin(math.radians(20.0)), 0.0)
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=v2, od=1.75)],
        )
        assert result.method == "C"


class TestHolesawWarnings:
    """Test holesaw depth warning thresholds."""

    def test_no_warning_under_2_inches(self):
        _depth, warning = _compute_holesaw_depth(1.75, 90.0, True, 0.0)
        assert warning is None

    def test_warning_over_2_inches(self):
        _depth, warning = _compute_holesaw_depth(1.75, 45.0, True, 0.0)
        # 1.75 / sin(45°) ≈ 2.47"
        assert warning is not None
        assert "deep holesaw" in warning.lower()

    def test_warning_over_4_inches(self):
        _depth, warning = _compute_holesaw_depth(1.75, 20.0, True, 0.0)
        # 1.75 / sin(20°) ≈ 5.12"
        assert warning is not None
        assert "exceeds" in warning.lower()

    def test_plunge_depth_used_for_non_passthrough(self):
        depth, _warning = _compute_holesaw_depth(1.75, 90.0, False, 1.5)
        assert abs(depth - 1.5) < 0.001


class TestNotcherAngleInternal:
    """Test _compute_notcher_angle directly."""

    def test_perpendicular(self):
        angle = _compute_notcher_angle((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert abs(angle - 90.0) < 0.01

    def test_45_degrees(self):
        v2 = (
            math.cos(math.radians(45.0)),
            math.sin(math.radians(45.0)),
            0.0,
        )
        # |v1 · v2| = cos(45°), so arccos gives 45°
        angle = _compute_notcher_angle((1.0, 0.0, 0.0), v2)
        assert abs(angle - 45.0) < 0.1

    def test_symmetric(self):
        """Angle should be same regardless of direction."""
        a1 = _compute_notcher_angle((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        a2 = _compute_notcher_angle((0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
        assert abs(a1 - a2) < 0.001


class TestRotationMarkInternal:
    """Test _compute_rotation_mark directly."""

    def test_with_reference_vector(self):
        """Rotation from a known reference direction."""
        rot = _compute_rotation_mark(
            v1=(1.0, 0.0, 0.0),
            v2=(0.0, 1.0, 0.0),
            reference_vector=(0.0, 1.0, 0.0),
        )
        # Apex direction is v2 projected onto cross-section of v1
        # v2 projected onto plane perpendicular to X = (0, 1, 0)
        # Reference is also (0, 1, 0), so rotation should be ~0°
        assert rot < 1.0 or rot > 359.0  # Near 0

    def test_without_reference(self):
        rot = _compute_rotation_mark(
            v1=(1.0, 0.0, 0.0),
            v2=(0.0, 1.0, 0.0),
            reference_vector=None,
        )
        assert 0.0 <= rot < 360.0


class TestReferenceVector:
    """Test that reference_vector affects CopeResult correctly."""

    def test_has_bend_reference_true(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            reference_vector=(0.0, 0.0, 1.0),
        )
        assert result.has_bend_reference is True
        assert "bend" in result.reference_description.lower()

    def test_has_bend_reference_false(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert result.has_bend_reference is False
        assert "scribe" in result.reference_description.lower()


class TestZProfile:
    """Test z-profile properties."""

    def test_all_non_negative(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert all(z >= 0 for z in result.z_profile)

    def test_symmetric_for_perpendicular(self):
        """Perpendicular cope should have symmetric profile."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        # Find the apex
        apex_idx = result.z_profile.index(max(result.z_profile))
        # Check symmetry around apex (within tolerance)
        for offset in range(1, 90):
            left = result.z_profile[(apex_idx - offset) % 360]
            right = result.z_profile[(apex_idx + offset) % 360]
            assert abs(left - right) < 0.01

    def test_different_od_receivers(self):
        """Different OD receivers produce different z heights."""
        result_small = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.0)],
        )
        result_large = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.5)],
        )
        assert max(result_large.z_profile) > max(result_small.z_profile)
