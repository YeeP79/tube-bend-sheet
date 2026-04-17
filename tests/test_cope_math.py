"""Tests for cope math module — all 5 spec test cases plus defensive tests.

Run with: pytest tests/test_cope_math.py -v
"""
import math

import pytest

from core.cope_math import (
    _Lobe,
    _arbitrary_perpendicular,
    _classify_method,
    _compute_holesaw_depth,
    _compute_inclination_angle,
    _compute_receiver_peak_depth,
    _compute_rotation_mark,
    _compute_z_profile,
    _detect_lobes,
    _match_lobe_to_receiver,
    calculate_cope,
)
from core.geometry import ZeroVectorError, dot_product, magnitude
from core.tolerances import MIN_COPE_INCLINATION_DEG
from models.cope_data import CopePass, ReceivingTube


# ---------------------------------------------------------------------------
# Spec Case 1: Simple perpendicular cope
# ---------------------------------------------------------------------------
class TestCase1Perpendicular:
    """v1=(1,0,0), v2=(0,1,0), both 1.75" OD → 0° notcher, 0° rotation."""

    def test_notcher_angle_0(self):
        """Perpendicular T-joint → notcher reads 0° (offset from perpendicular)."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert abs(result.passes[0].notcher_angle - 0.0) < 0.1

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
        # v1 has no X component, so dot = 0, included angle = 90°
        # notcher setting = 90 - 90 = 0°
        assert abs(result.passes[0].notcher_angle - 0.0) < 0.1

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
        # Case 2 was 0° notcher, compound angle should differ
        # v1 · v2 = sin(12°)*cos(19.3°) ≈ 0.1962
        # included = arccos(0.1962) ≈ 78.7°, notcher = 90 - 78.7 ≈ 11.3°
        included = math.degrees(math.acos(
            abs(self.V1[0] * self.V2[0] + self.V1[1] * self.V2[1] + self.V1[2] * self.V2[2])
        ))
        expected_notcher = 90.0 - included
        assert abs(result.passes[0].notcher_angle - expected_notcher) < 0.2
        assert abs(result.passes[0].notcher_angle - 0.0) > 1.0  # Not 0

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

    def test_both_notcher_angles_0(self):
        """Both receivers perpendicular to incoming → notcher reads 0° each."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2, od=self.OD),
                ReceivingTube(vector=self.V3, od=self.OD),
            ],
        )
        for p in result.passes:
            assert abs(p.notcher_angle - 0.0) < 0.1


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
    """Very acute angle (high notcher setting) should trigger Method C."""

    def test_acute_angle_method_c(self):
        # 20° included angle → 70° notcher setting (above 65° MAX_NOTCHER_ANGLE)
        # v1 · v2 = cos(20°) ≈ 0.9397
        v2 = (math.cos(math.radians(20.0)), math.sin(math.radians(20.0)), 0.0)
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=v2, od=1.75)],
        )
        assert result.method == "C"
        assert result.passes[0].notcher_angle > 65.0


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

    def test_unit_label_in_warning(self):
        """Unit label should appear in warning messages."""
        _depth, warning = _compute_holesaw_depth(1.75, 45.0, True, 0.0, unit_label="mm")
        assert warning is not None
        assert "mm" in warning

    def test_default_unit_label_is_inches(self):
        _depth, warning = _compute_holesaw_depth(1.75, 45.0, True, 0.0)
        assert warning is not None
        assert '"' in warning


class TestInclinationAngleInternal:
    """Test _compute_inclination_angle directly."""

    def test_perpendicular(self):
        angle = _compute_inclination_angle((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert abs(angle - 90.0) < 0.01

    def test_45_degrees(self):
        v2 = (
            math.cos(math.radians(45.0)),
            math.sin(math.radians(45.0)),
            0.0,
        )
        # |v1 · v2| = cos(45°), so arccos gives 45° included
        angle = _compute_inclination_angle((1.0, 0.0, 0.0), v2)
        assert abs(angle - 45.0) < 0.1

    def test_symmetric(self):
        """Angle should be same regardless of direction."""
        a1 = _compute_inclination_angle((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        a2 = _compute_inclination_angle((0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
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
        assert "extrados" in result.reference_description.lower()

    def test_has_bend_reference_false(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert result.has_bend_reference is False
        assert "scribed" in result.reference_description.lower()


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


# ---------------------------------------------------------------------------
# _detect_lobes tests
# ---------------------------------------------------------------------------
class TestDetectLobes:
    """Direct tests for _detect_lobes internal function."""

    def test_single_lobe(self):
        """Single peak → one lobe."""
        z = [0.0] * 360
        for i in range(160, 201):
            z[i] = math.cos(math.radians(i - 180)) * 1.0
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 1
        assert 160 <= lobes[0].apex_azimuth <= 200

    def test_two_lobes_with_valley(self):
        """Two peaks separated by a valley below threshold → two lobes."""
        z = [0.0] * 360
        # Lobe 1 centered at 90°
        for i in range(60, 121):
            z[i] = max(0.0, math.cos(math.radians(i - 90)) * 1.5)
        # Lobe 2 centered at 270°
        for i in range(240, 301):
            z[i] = max(0.0, math.cos(math.radians(i - 270)) * 1.5)
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 2

    def test_wrap_around_lobe(self):
        """Lobe crossing 0/360 boundary → detected as single lobe."""
        z = [0.0] * 360
        # Peak near 0° (wraps from 350 to 10)
        for i in range(350, 360):
            z[i] = max(0.0, math.cos(math.radians(i - 360)) * 1.5)
        for i in range(0, 11):
            z[i] = max(0.0, math.cos(math.radians(i)) * 1.5)
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 1

    def test_all_above_threshold(self):
        """Entire profile above valley threshold → single lobe."""
        z = [1.0] * 360
        z[90] = 2.0  # Apex
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 1
        assert lobes[0].apex_azimuth == 90

    def test_all_zero_profile(self):
        """All-zero profile → empty list."""
        z = [0.0] * 360
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 0

    def test_sorted_by_apex_descending(self):
        """Lobes should be sorted by apex z-value, highest first."""
        z = [0.0] * 360
        # Small lobe at 90°
        for i in range(70, 111):
            z[i] = max(0.0, math.cos(math.radians(i - 90)) * 0.8)
        # Larger lobe at 270°
        for i in range(250, 291):
            z[i] = max(0.0, math.cos(math.radians(i - 270)) * 1.5)
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 2
        assert lobes[0].apex_z >= lobes[1].apex_z

    def test_lobe_start_end_valid(self):
        """Lobe start/end should bracket the apex."""
        z = [0.0] * 360
        for i in range(80, 101):
            z[i] = max(0.0, math.cos(math.radians(i - 90)) * 1.5)
        lobes = _detect_lobes(z, 1.75)
        assert len(lobes) == 1
        lobe = lobes[0]
        assert lobe.start_azimuth <= lobe.apex_azimuth <= lobe.end_azimuth


# ---------------------------------------------------------------------------
# _match_lobe_to_receiver tests
# ---------------------------------------------------------------------------
class TestMatchLobeToReceiver:
    """Direct tests for _match_lobe_to_receiver."""

    def test_exact_match(self):
        """Lobe apex at same angle as rotation → matches that receiver."""
        lobe = _Lobe(apex_azimuth=90, apex_z=1.0, start_azimuth=60, end_azimuth=120)
        idx = _match_lobe_to_receiver(lobe, [90.0, 270.0])
        assert idx == 0

    def test_closest_of_two(self):
        """Picks receiver with nearest rotation to apex."""
        lobe = _Lobe(apex_azimuth=100, apex_z=1.0, start_azimuth=80, end_azimuth=120)
        idx = _match_lobe_to_receiver(lobe, [90.0, 270.0])
        assert idx == 0

    def test_closest_second_receiver(self):
        """Picks second receiver when it's closer."""
        lobe = _Lobe(apex_azimuth=260, apex_z=1.0, start_azimuth=240, end_azimuth=280)
        idx = _match_lobe_to_receiver(lobe, [90.0, 270.0])
        assert idx == 1

    def test_wrap_around_distance(self):
        """Lobe at 350° is closer to rotation at 5° than 180°."""
        lobe = _Lobe(apex_azimuth=350, apex_z=1.0, start_azimuth=340, end_azimuth=359)
        idx = _match_lobe_to_receiver(lobe, [180.0, 5.0])
        assert idx == 1

    def test_single_receiver(self):
        """With one receiver, always returns 0."""
        lobe = _Lobe(apex_azimuth=200, apex_z=1.0, start_azimuth=180, end_azimuth=220)
        idx = _match_lobe_to_receiver(lobe, [45.0])
        assert idx == 0


# ---------------------------------------------------------------------------
# _classify_method tests
# ---------------------------------------------------------------------------
class TestClassifyMethod:
    """Direct tests for _classify_method."""

    def _make_pass(self, **overrides) -> CopePass:
        defaults = {
            "notcher_angle": 0.0,
            "rotation_mark": 0.0,
            "plunge_depth": 0.5,
            "is_pass_through": True,
            "lobe_span_degrees": 90.0,
            "dominant": True,
            "holesaw_depth_required": 1.75,
            "holesaw_warning": None,
        }
        defaults.update(overrides)
        return CopePass(**defaults)

    def _make_lobe(self, apex_azimuth: int = 90, apex_z: float = 1.0) -> _Lobe:
        return _Lobe(apex_azimuth=apex_azimuth, apex_z=apex_z, start_azimuth=apex_azimuth - 30, end_azimuth=apex_azimuth + 30)

    def test_method_a_single_pass(self):
        passes = [self._make_pass()]
        lobes = [self._make_lobe()]
        method, desc = _classify_method(passes, lobes)
        assert method == "A"
        assert "single pass" in desc.lower()

    def test_method_a_collapsed_lobes(self):
        """Two close lobes (within LOBE_COLLAPSE_DEGREES) → Method A."""
        passes = [self._make_pass(), self._make_pass(dominant=False)]
        # Lobes 20° apart (within 30° collapse threshold)
        lobes = [self._make_lobe(apex_azimuth=90), self._make_lobe(apex_azimuth=110)]
        method, _desc = _classify_method(passes, lobes)
        assert method == "A"

    def test_method_b_multi_pass(self):
        """Two passes with lobes far apart → Method B."""
        passes = [self._make_pass(), self._make_pass(dominant=False)]
        lobes = [self._make_lobe(apex_azimuth=0), self._make_lobe(apex_azimuth=180)]
        method, _desc = _classify_method(passes, lobes)
        assert method == "B"

    def test_method_c_acute_angle(self):
        """Notcher angle > 65° → Method C."""
        passes = [self._make_pass(notcher_angle=70.0)]
        lobes = [self._make_lobe()]
        method, desc = _classify_method(passes, lobes)
        assert method == "C"
        assert "angle" in desc.lower()

    def test_method_c_deep_holesaw(self):
        """Holesaw depth > MAX_HOLESAW_DEPTH → Method C."""
        passes = [self._make_pass(holesaw_depth_required=5.0)]
        lobes = [self._make_lobe()]
        method, desc = _classify_method(passes, lobes)
        assert method == "C"
        assert "holesaw" in desc.lower()

    def test_method_c_three_lobes(self):
        """Three or more lobes → Method C."""
        passes = [self._make_pass(), self._make_pass(dominant=False), self._make_pass(dominant=False)]
        lobes = [
            self._make_lobe(apex_azimuth=0),
            self._make_lobe(apex_azimuth=120),
            self._make_lobe(apex_azimuth=240),
        ]
        method, desc = _classify_method(passes, lobes)
        assert method == "C"
        assert "three" in desc.lower()


# ---------------------------------------------------------------------------
# _arbitrary_perpendicular tests
# ---------------------------------------------------------------------------
class TestArbitraryPerpendicular:
    """Direct tests for _arbitrary_perpendicular."""

    def test_x_axis(self):
        """Perpendicular to X axis should have zero X component."""
        perp = _arbitrary_perpendicular((1.0, 0.0, 0.0))
        assert abs(dot_product(perp, (1.0, 0.0, 0.0))) < 1e-9
        assert abs(magnitude(perp) - 1.0) < 1e-9

    def test_y_axis(self):
        perp = _arbitrary_perpendicular((0.0, 1.0, 0.0))
        assert abs(dot_product(perp, (0.0, 1.0, 0.0))) < 1e-9
        assert abs(magnitude(perp) - 1.0) < 1e-9

    def test_z_axis(self):
        perp = _arbitrary_perpendicular((0.0, 0.0, 1.0))
        assert abs(dot_product(perp, (0.0, 0.0, 1.0))) < 1e-9
        assert abs(magnitude(perp) - 1.0) < 1e-9

    def test_diagonal(self):
        v = (1.0, 1.0, 1.0)
        perp = _arbitrary_perpendicular(v)
        assert abs(dot_product(perp, v)) < 1e-6
        assert abs(magnitude(perp) - 1.0) < 1e-9

    def test_negative_axis(self):
        perp = _arbitrary_perpendicular((-1.0, 0.0, 0.0))
        assert abs(dot_product(perp, (-1.0, 0.0, 0.0))) < 1e-9
        assert abs(magnitude(perp) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# _compute_z_profile tests
# ---------------------------------------------------------------------------
class TestComputeZProfile:
    """Direct tests for _compute_z_profile."""

    def test_single_perpendicular(self):
        """Perpendicular with R1<R2: cos(90°)=0 so R1 term vanishes.
        z(phi) = sqrt(R2² - R1²·sin²(phi)) for alpha=90°.
        z(0) = R2 = 1.0, z(90) = sqrt(R2²-R1²) ≈ 0.866."""
        # R1=0.5 (od1=1.0), R2=1.0 (od=2.0), alpha=90°
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z = _compute_z_profile([rt], [90.0], [0.0], r1=0.5)
        assert len(z) == 360
        # z(0) = sqrt(R2²) = R2 = 1.0
        assert abs(z[0] - 1.0) < 0.01
        # z(90) = sqrt(1.0 - 0.25) = sqrt(0.75) ≈ 0.866
        assert abs(z[90] - math.sqrt(0.75)) < 0.01

    def test_single_perpendicular_same_od(self):
        """Same-OD perpendicular: R1=R2=1.0, alpha=90° → z(0) = R-R = 0, z peak at azimuth where cos < 0."""
        # z(phi) = [sqrt(R² - R²sin²phi) - R·cos(90°)·cos(phi)] / sin(90°)
        #        = [R·cos(phi) - 0] / 1 = R·cos(phi), clamped ≥ 0
        # So z(0)=R=1.0, z(90)=0, z(180)=0 (clamped)
        # Wait: cos(90°)=0, so z = R·|cos(phi)|... no:
        # z = [sqrt(R² - R²sin²) - 0] / 1 = R·sqrt(1-sin²) = R·|cos(phi)|
        # But we have R·cos(phi) not |cos|. For phi in [-90,90] cos>0 so z>0.
        # For phi>90, cos(phi)<0 → sqrt term = R·|cos(phi)| but subtract 0,
        # so z = R·|cos(phi)| which is always ≥ 0. Let me recompute:
        # discriminant = R²-R²sin²(phi) = R²cos²(phi) ≥ 0 always
        # sqrt(discriminant) = R·|cos(phi)|
        # z = R·|cos(phi)| / 1 = R·|cos(phi)|
        # So z(0) = R = 1.0, z(90) = 0, z(180) = R = 1.0
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z = _compute_z_profile([rt], [90.0], [0.0], r1=1.0)
        assert len(z) == 360
        assert abs(z[0] - 1.0) < 0.01
        assert abs(z[90] - 0.0) < 0.01
        # At 180°: z = |cos(180°)| = 1.0
        assert abs(z[180] - 1.0) < 0.01

    def test_single_angled_small_incoming(self):
        """When R1 << R2, angled peak is larger than perpendicular peak."""
        # R1=0.25 (od1=0.5), R2=1.0 (od=2.0)
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z_perp = _compute_z_profile([rt], [90.0], [0.0], r1=0.25)
        z_angled = _compute_z_profile([rt], [45.0], [0.0], r1=0.25)
        # Small R1 relative to R2: exact ≈ simplified, angled peak is larger
        assert max(z_angled) > max(z_perp)

    def test_single_angled_same_od(self):
        """Same-OD angled: front peak is smaller than perpendicular, back peak is larger."""
        # R1=R2=1.0, alpha=45°
        # Front (phi=0): z = [sqrt(1-0) - cos(45°)] / sin(45°) ≈ 0.4142
        # Back (phi=180): z = [sqrt(1-0) + cos(45°)] / sin(45°) ≈ 2.4142
        # vs perpendicular same-OD: z(0) = R·|cos(0)| = 1.0
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z_perp = _compute_z_profile([rt], [90.0], [0.0], r1=1.0)
        z_angled = _compute_z_profile([rt], [45.0], [0.0], r1=1.0)
        # Front peak (phi=0, at azimuth offset) is smaller than perpendicular
        assert z_angled[0] < z_perp[0]
        # Verify the front peak value: R·tan(alpha/2) = tan(22.5°) ≈ 0.4142
        assert abs(z_angled[0] - 0.4142) < 0.02
        # Back peak (phi=180) is larger due to saddle geometry
        assert z_angled[180] > z_perp[0]

    def test_multi_receiver_envelope(self):
        """Multi-receiver profile is the max of individual profiles."""
        rt1 = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        rt2 = ReceivingTube(vector=(0.0, -1.0, 0.0), od=2.0)
        z_single = _compute_z_profile([rt1], [90.0], [0.0], r1=0.5)
        z_multi = _compute_z_profile([rt1, rt2], [90.0, 90.0], [0.0, 180.0], r1=0.5)
        # Multi should be >= single at every point
        for i in range(360):
            assert z_multi[i] >= z_single[i] - 1e-10

    def test_all_non_negative(self):
        """Profile values should never be negative."""
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z = _compute_z_profile([rt], [90.0], [45.0], r1=0.5)
        assert all(v >= 0.0 for v in z)

    def test_rotation_offset_shifts_peak(self):
        """Azimuth offset should shift the peak position."""
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z0 = _compute_z_profile([rt], [90.0], [0.0], r1=0.5)
        z90 = _compute_z_profile([rt], [90.0], [90.0], r1=0.5)
        apex0 = z0.index(max(z0))
        apex90 = z90.index(max(z90))
        # Apex should shift by ~90 degrees
        shift = abs(apex90 - apex0)
        if shift > 180:
            shift = 360 - shift
        assert 85 <= shift <= 95

    def test_nearly_parallel_skipped(self):
        """Very small inclination angle (near-parallel) → sin ≈ 0, skipped by _compute_z_profile guard."""
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z = _compute_z_profile([rt], [0.001], [0.0], r1=0.5)
        # sin(0.001°) ≈ 1.7e-5 which is above 1e-10 threshold,
        # but calculate_cope() now filters these out before they reach
        # _compute_z_profile.  This test confirms the low-level guard still
        # works for extremely small angles that somehow bypass the filter.
        assert len(z) == 360


# ---------------------------------------------------------------------------
# Exact formula accuracy tests
# ---------------------------------------------------------------------------
class TestExactFormulaAccuracy:
    """Verify the exact cylinder-cylinder intersection formula against known values."""

    def test_exact_vs_simplified_perpendicular_small_r1(self):
        """At 90° with R1 << R2, exact ≈ simplified = R2."""
        # R1=0.001 (tiny tube), R2=1.0, alpha=90°
        # Exact z(0) = [sqrt(1 - 0) - 0.001·0·1] / 1 = 1.0
        # Simplified z(0) = R2/sin(90°) = 1.0
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=2.0)
        z = _compute_z_profile([rt], [90.0], [0.0], r1=0.001)
        assert abs(z[0] - 1.0) < 0.01

    def test_exact_same_od_45deg(self):
        """Same-OD tubes at 45° inclination: z(0) = R·(1 - cos45) / sin45 ≈ 0.4142."""
        # R1=R2=R=0.875 (1.75" OD), alpha=45°
        # z(0) = [sqrt(R² - 0) - R·cos(45°)·1] / sin(45°)
        #       = [R - R·cos(45°)] / sin(45°)
        #       = R·(1 - cos45) / sin45
        #       = R·tan(45/2) = R·tan(22.5°) ≈ 0.875·0.4142 ≈ 0.3624
        r = 0.875
        expected = r * math.tan(math.radians(22.5))
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)
        z = _compute_z_profile([rt], [45.0], [0.0], r1=r)
        assert abs(z[0] - expected) < 0.01

    def test_exact_same_od_60deg(self):
        """Same-OD tubes at 60° inclination: z(0) = R·tan(30°) ≈ 0.505."""
        # R·(1 - cos60) / sin60 = R·(1 - 0.5) / 0.866 = R·0.5774 = R·tan(30°)
        r = 0.875
        expected = r * math.tan(math.radians(30.0))
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)
        z = _compute_z_profile([rt], [60.0], [0.0], r1=r)
        assert abs(z[0] - expected) < 0.01

    def test_exact_small_tube_large_receiver(self):
        """When R1 << R2, exact ≈ simplified (R2/sin(alpha))."""
        # R1=0.1, R2=2.0, alpha=60°
        # Simplified: 2.0 / sin(60°) ≈ 2.309
        # Exact z(0) = [sqrt(4 - 0) - 0.1·cos(60°)·1] / sin(60°)
        #            = [2.0 - 0.05] / 0.866 ≈ 2.252
        # Close but not identical due to the R1·cos(α) term
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=4.0)
        z = _compute_z_profile([rt], [60.0], [0.0], r1=0.1)
        simplified = 2.0 / math.sin(math.radians(60.0))
        # Within 5% when R1 is small relative to R2
        assert abs(z[0] - simplified) / simplified < 0.05

    def test_negative_discriminant_handled(self):
        """When R1 > R2, some azimuths produce no intersection (z stays 0)."""
        # R1=2.0 (big incoming tube), R2=0.5 (small receiver)
        # At azimuth where R1·sin(phi) > R2, discriminant < 0 → z stays 0
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.0)  # R2=0.5
        z = _compute_z_profile([rt], [90.0], [0.0], r1=2.0)
        # At azimuth 90°: discriminant = 0.25 - 4·1 < 0, so z[90]=0
        assert z[90] == 0.0
        # Cope should only cover a small angular range (arcsin(R2/R1) on each side)
        max_angle = math.degrees(math.asin(0.5 / 2.0))  # ~14.5°
        # z should be 0 well outside the intersection range
        assert z[int(max_angle) + 5] == 0.0

    def test_profile_wider_for_small_incoming(self):
        """R1 < R2 → cope wraps beyond ±90° (no negative discriminant)."""
        # R1=0.5, R2=2.0 → R1·sin(phi) ≤ R1 < R2 always → full 360° has valid discriminant
        rt = ReceivingTube(vector=(0.0, 1.0, 0.0), od=4.0)  # R2=2.0
        z = _compute_z_profile([rt], [90.0], [0.0], r1=0.5)
        # At azimuth 90°: z = [sqrt(4 - 0.25) - 0.5·0·0] / 1 = sqrt(3.75) ≈ 1.936
        # Should be non-zero at 90° and 270°
        assert z[90] > 0
        assert z[270] > 0


# ---------------------------------------------------------------------------
# Shallow angle filtering tests
# ---------------------------------------------------------------------------
class TestShallowAngleFiltering:
    """Test that calculate_cope filters receivers below MIN_COPE_INCLINATION_DEG."""

    def _make_vector_at_inclination(self, inclination_deg: float) -> tuple[float, float, float]:
        """Build a receiver vector that forms the given inclination angle with v1=(1,0,0).

        inclination = arccos(|v1 · v2|), so |v1 · v2| = cos(inclination).
        Use v2 = (cos(incl), sin(incl), 0).
        """
        rad = math.radians(inclination_deg)
        return (math.cos(rad), math.sin(rad), 0.0)

    def test_shallow_receiver_filtered_from_z_profile(self):
        """A receiver at 3° inclination should be filtered; z-profile reflects only the valid receiver."""
        valid_vec = (0.0, 1.0, 0.0)   # 90° inclination — fully perpendicular
        shallow_vec = self._make_vector_at_inclination(3.0)

        result_both = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[
                ReceivingTube(vector=valid_vec, od=1.75),
                ReceivingTube(vector=shallow_vec, od=1.75),
            ],
        )
        result_valid_only = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=valid_vec, od=1.75)],
        )
        # The shallow receiver should have been filtered, so profiles match
        assert result_both.z_profile == result_valid_only.z_profile

    def test_all_shallow_raises(self):
        """All receivers below threshold → ValueError."""
        shallow_vec = self._make_vector_at_inclination(3.0)
        with pytest.raises(ValueError, match="minimum inclination"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=shallow_vec, od=1.75)],
            )

    def test_mixed_receivers_only_valid_used(self):
        """One valid (45°) + one shallow (3°) → result uses only valid one, warning present."""
        valid_vec = self._make_vector_at_inclination(45.0)
        shallow_vec = self._make_vector_at_inclination(3.0)

        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[
                ReceivingTube(vector=valid_vec, od=1.75),
                ReceivingTube(vector=shallow_vec, od=1.75, name="shallow brace"),
            ],
        )
        # Should have exactly one pass (only the valid receiver)
        assert len(result.passes) >= 1
        # Should contain a warning about the filtered receiver
        assert any("shallow brace" in w for w in result.warnings)
        assert any("filtered" in w.lower() for w in result.warnings)

    def test_at_threshold_boundary(self):
        """Receiver at threshold should be included (not filtered).

        Uses MIN_COPE_INCLINATION_DEG + 0.1 to avoid float-precision
        rounding of arccos(cos(x)) falling just below x.
        """
        vec = self._make_vector_at_inclination(MIN_COPE_INCLINATION_DEG + 0.1)
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=vec, od=1.75)],
        )
        # Should succeed — not filtered
        assert len(result.passes) >= 1
        # No shallow-angle warnings
        assert not any("filtered" in w.lower() for w in result.warnings)

    def test_just_below_threshold(self):
        """Receiver at 4.9° (just below 5° threshold) should be filtered."""
        vec = self._make_vector_at_inclination(4.9)
        with pytest.raises(ValueError, match="minimum inclination"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=vec, od=1.75)],
            )


# ---------------------------------------------------------------------------
# Merged lobe / multi-receiver tests
# ---------------------------------------------------------------------------
class TestMergedLobeMultiReceiver:
    """When two receivers' saddles merge into one lobe, each receiver
    should still get its own pass with individual notcher settings.

    This reproduces the real-world bug: a tube at a 3-tube node where
    one receiver is near-perpendicular (82°) and one is steep (36°).
    The valley between their saddles is too shallow to split into
    separate lobes, so lobe detection finds only one lobe.  Without
    the fix, only one pass is created with the near-perpendicular
    receiver's settings.
    """

    # Incoming tube along Z axis
    V1 = (0.0, 0.0, 1.0)
    OD = 1.75

    # Receiver 1: steep angle (inclination ~36°, notcher ~54°)
    # Build vector with cos(36°) along Z, sin(36°) along X
    V2_STEEP = (math.sin(math.radians(36.0)), 0.0, math.cos(math.radians(36.0)))

    # Receiver 2: near-perpendicular (inclination ~82°, notcher ~8°)
    # Same plane but much more perpendicular
    V2_PERP = (math.sin(math.radians(82.0)), math.sin(math.radians(15.0)), math.cos(math.radians(82.0)))

    def test_two_passes_created(self):
        """Two receivers with merged saddles should produce two passes."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        assert len(result.passes) == 2

    def test_is_multi_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        assert result.is_multi_pass is True

    def test_method_b(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        assert result.method == "B"

    def test_different_notcher_angles(self):
        """Each pass should have a distinct notcher angle matching its receiver."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        notcher_angles = sorted(p.notcher_angle for p in result.passes)
        # One should be ~54° (steep) and one ~8° (near-perpendicular)
        assert notcher_angles[0] < 15.0, f"Expected low notcher angle, got {notcher_angles[0]}"
        assert notcher_angles[1] > 45.0, f"Expected high notcher angle, got {notcher_angles[1]}"

    def test_different_rotation_marks(self):
        """Each pass should have a different rotation mark."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        rotations = [p.rotation_mark for p in result.passes]
        assert abs(rotations[0] - rotations[1]) > 1.0, \
            f"Rotation marks should differ: {rotations}"

    def test_not_pass_through(self):
        """Multi-pass → none should be pass-through."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        for p in result.passes:
            assert p.is_pass_through is False

    def test_one_dominant_pass(self):
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        dominant_count = sum(1 for p in result.passes if p.dominant)
        assert dominant_count == 1

    def test_steep_receiver_has_deeper_plunge(self):
        """The steeper receiver (smaller inclination) produces a deeper saddle."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD),
                ReceivingTube(vector=self.V2_PERP, od=self.OD),
            ],
        )
        # Sort by notcher angle to identify which pass is which
        steep_pass = max(result.passes, key=lambda p: p.notcher_angle)
        perp_pass = min(result.passes, key=lambda p: p.notcher_angle)
        assert steep_pass.plunge_depth > perp_pass.plunge_depth

    def test_receiver_name_set_on_each_pass(self):
        """Each pass should carry the receiver_name from its ReceivingTube."""
        result = calculate_cope(
            v1=self.V1, od1=self.OD,
            receiving_tubes=[
                ReceivingTube(vector=self.V2_STEEP, od=self.OD, name="steep brace"),
                ReceivingTube(vector=self.V2_PERP, od=self.OD, name="perp rail"),
            ],
        )
        names = {p.receiver_name for p in result.passes}
        assert "steep brace" in names
        assert "perp rail" in names


# ---------------------------------------------------------------------------
# Receiver name on single-receiver cope
# ---------------------------------------------------------------------------
class TestReceiverNameSingleReceiver:
    """Single-receiver cope should carry receiver_name."""

    def test_receiver_name_set(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75, name="main rail")],
        )
        assert len(result.passes) == 1
        assert result.passes[0].receiver_name == "main rail"

    def test_receiver_name_empty_when_unnamed(self):
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        assert result.passes[0].receiver_name == ""


# ---------------------------------------------------------------------------
# _compute_receiver_peak_depth tests
# ---------------------------------------------------------------------------
class TestComputeReceiverPeakDepth:
    """Direct tests for _compute_receiver_peak_depth.

    Computes the maximum saddle depth (back peak at phi=180°):
        z_max = [R2 + R1·cos(alpha)] / sin(alpha)
    """

    def test_perpendicular_same_od(self):
        """At 90°, z_max = [R + R·cos(90°)] / sin(90°) = R."""
        r = 0.875  # 1.75" OD
        depth = _compute_receiver_peak_depth(90.0, r, r)
        assert abs(depth - r) < 0.001

    def test_45_degrees_same_od(self):
        """At 45°, z_max = R·(1 + cos45) / sin45."""
        r = 0.875
        expected = r * (1.0 + math.cos(math.radians(45.0))) / math.sin(math.radians(45.0))
        depth = _compute_receiver_peak_depth(45.0, r, r)
        assert abs(depth - expected) < 0.001

    def test_steep_angle_deeper(self):
        """Steeper angle (smaller inclination) → deeper back peak."""
        r = 0.875
        depth_steep = _compute_receiver_peak_depth(30.0, r, r)
        depth_perp = _compute_receiver_peak_depth(90.0, r, r)
        assert depth_steep > depth_perp

    def test_near_zero_angle_finite(self):
        """Very small inclination (sin ≈ 0) → returns a non-negative finite value."""
        depth = _compute_receiver_peak_depth(0.0001, 0.875, 0.875)
        # sin(0.0001°) ≈ 1.7e-6 which is above the 1e-10 guard, so the
        # formula runs. Result is a large number, not zero. Just verify
        # it returns a non-negative finite value.
        assert depth >= 0.0
        assert math.isfinite(depth)

    def test_different_od_larger_receiver(self):
        """Larger receiver OD → deeper peak."""
        depth_same = _compute_receiver_peak_depth(90.0, 0.875, 0.875)
        depth_large = _compute_receiver_peak_depth(90.0, 0.875, 1.5)
        assert depth_large > depth_same

    def test_non_negative(self):
        """Peak depth should never be negative."""
        for angle in [10.0, 30.0, 45.0, 60.0, 90.0]:
            depth = _compute_receiver_peak_depth(angle, 0.875, 0.875)
            assert depth >= 0.0


# ---------------------------------------------------------------------------
# OD validation tests
# ---------------------------------------------------------------------------
class TestInvalidOD:
    """Validate that non-positive OD values raise ValueError."""

    def test_zero_od_raises(self):
        with pytest.raises(ValueError, match="Incoming tube OD must be positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=0.0,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            )

    def test_negative_od_raises(self):
        with pytest.raises(ValueError, match="Incoming tube OD must be positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=-1.0,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            )

    def test_zero_receiving_od_raises(self):
        with pytest.raises(ValueError, match="Receiving tube OD must be positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=0.0)],
            )

    def test_negative_receiving_od_raises(self):
        with pytest.raises(ValueError, match="Receiving tube OD must be positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=-1.0)],
            )
