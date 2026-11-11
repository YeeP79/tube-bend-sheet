"""Tests for core.cope_path — EndReference extraction from path data."""

import math

import pytest

from core.cope_path import (
    _compute_extrados,
    apply_end_length_adjustments,
    compute_end_reference,
    compute_long_point_adjustment,
)
from models.bend_data import BendData, StraightSection


def _straight(num: int, vector: tuple[float, float, float], length: float = 5.0) -> StraightSection:
    """Helper to build a StraightSection with minimal required fields."""
    return StraightSection(
        number=num,
        length=length,
        start=(0.0, 0.0, 0.0),
        end=vector,
        vector=vector,
    )


def _bend(num: int, angle: float = 90.0, rotation: float | None = None) -> BendData:
    """Helper to build a BendData."""
    return BendData(number=num, angle=angle, rotation=rotation)


def _mag(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# ── No bends ──────────────────────────────────────────────────────────

class TestComputeEndReferenceNoBends:

    def test_single_straight_end_direction(self) -> None:
        """end="end" → tube_dir = normalize(vector), extrados = None."""
        straights = [_straight(1, (10.0, 0.0, 0.0))]
        ref = compute_end_reference(straights, [], "end")
        assert ref.tube_direction == pytest.approx((1.0, 0.0, 0.0))
        assert ref.extrados_direction is None

    def test_single_straight_start_direction(self) -> None:
        """end="start" → tube_dir = -normalize(vector), extrados = None."""
        straights = [_straight(1, (10.0, 0.0, 0.0))]
        ref = compute_end_reference(straights, [], "start")
        assert ref.tube_direction == pytest.approx((-1.0, 0.0, 0.0))
        assert ref.extrados_direction is None

    def test_straight_length_reported(self) -> None:
        straights = [_straight(1, (10.0, 0.0, 0.0), length=7.5)]
        ref = compute_end_reference(straights, [], "end")
        assert ref.straight_length == 7.5


# ── Single bend ───────────────────────────────────────────────────────

class TestComputeEndReferenceSingleBend:

    def test_90_degree_bend_end_extrados(self) -> None:
        """90° XY bend: straights[0]=(10,0,0), straights[1]=(0,10,0).

        The path turns left (toward -X of the +Y leg), so the bend center
        is on the -X side and the end extrados points toward +X."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (0.0, 10.0, 0.0)),
        ]
        bends = [_bend(1, 90.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is not None
        assert ref.extrados_direction == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)

    def test_90_degree_bend_start_extrados(self) -> None:
        """Same setup → start extrados should point toward -Y."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (0.0, 10.0, 0.0)),
        ]
        bends = [_bend(1, 90.0)]
        ref = compute_end_reference(straights, bends, "start")
        assert ref.extrados_direction is not None
        assert ref.extrados_direction == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)

    def test_45_degree_bend_extrados(self) -> None:
        """45° bend in XY plane — verify extrados is computed and perpendicular."""
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (c * 10, s * 10, 0.0)),
        ]
        bends = [_bend(1, 45.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is not None
        # Should be perpendicular to tube direction
        assert abs(_dot(ref.extrados_direction, ref.tube_direction)) < 1e-9

    def test_extrados_perpendicular_to_tube_dir(self) -> None:
        """Dot product of extrados and tube_direction should be ~0."""
        straights = [
            _straight(1, (5.0, 0.0, 0.0)),
            _straight(2, (0.0, 0.0, 8.0)),
        ]
        bends = [_bend(1, 90.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is not None
        assert abs(_dot(ref.extrados_direction, ref.tube_direction)) < 1e-9

    def test_extrados_is_unit_vector(self) -> None:
        """Extrados magnitude should be ~1.0."""
        straights = [
            _straight(1, (3.0, 4.0, 0.0)),
            _straight(2, (0.0, 0.0, 7.0)),
        ]
        bends = [_bend(1)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is not None
        assert _mag(ref.extrados_direction) == pytest.approx(1.0, abs=1e-9)

    def test_tube_direction_is_unit_vector(self) -> None:
        straights = [
            _straight(1, (3.0, 4.0, 0.0)),
            _straight(2, (0.0, 0.0, 7.0)),
        ]
        bends = [_bend(1)]
        ref = compute_end_reference(straights, bends, "end")
        assert _mag(ref.tube_direction) == pytest.approx(1.0, abs=1e-9)


# ── Multiple bends ────────────────────────────────────────────────────

class TestComputeEndReferenceMultipleBends:

    def test_three_straights_end_uses_last_bend(self) -> None:
        """end="end" should use straights[-2] → straights[-1]."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (0.0, 10.0, 0.0)),
            _straight(3, (0.0, 0.0, 10.0)),
        ]
        bends = [_bend(1, 90.0), _bend(2, 90.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is not None
        # +Y then +Z: bend center is on the -Y side of the +Z leg → extrados +Y
        assert ref.extrados_direction == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)

    def test_three_straights_start_uses_first_bend(self) -> None:
        """end="start" should use straights[1] → straights[0]."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (0.0, 10.0, 0.0)),
            _straight(3, (0.0, 0.0, 10.0)),
        ]
        bends = [_bend(1, 90.0), _bend(2, 90.0)]
        ref = compute_end_reference(straights, bends, "start")
        assert ref.extrados_direction is not None
        # +X then +Y: bend center is on the +Y side of the +X leg → extrados -Y
        assert ref.extrados_direction == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)

    def test_end_straight_length_from_last(self) -> None:
        straights = [
            _straight(1, (10.0, 0.0, 0.0), length=5.0),
            _straight(2, (0.0, 10.0, 0.0), length=3.0),
            _straight(3, (0.0, 0.0, 10.0), length=8.0),
        ]
        bends = [_bend(1), _bend(2)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.straight_length == 8.0


# ── Edge cases ────────────────────────────────────────────────────────

class TestComputeEndReferenceEdgeCases:

    def test_empty_straights_raises(self) -> None:
        with pytest.raises(ValueError, match="empty straights"):
            compute_end_reference([], [], "end")

    def test_collinear_vectors_no_extrados(self) -> None:
        """Collinear straights (no real bend) → extrados = None."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (5.0, 0.0, 0.0)),
        ]
        bends = [_bend(1, 0.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is None

    def test_antiparallel_vectors_no_extrados(self) -> None:
        """Anti-parallel (180° bend) → collinear, extrados = None."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (-10.0, 0.0, 0.0)),
        ]
        bends = [_bend(1, 180.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is None

    def test_single_straight_no_bends_end(self) -> None:
        """One straight, no bends — should work without error."""
        straights = [_straight(1, (0.0, 0.0, 5.0), length=5.0)]
        ref = compute_end_reference(straights, [], "end")
        assert ref.tube_direction == pytest.approx((0.0, 0.0, 1.0))
        assert ref.extrados_direction is None
        assert ref.straight_length == 5.0


# ── Helper function ───────────────────────────────────────────────────

class TestComputeExtrados:

    def test_returns_none_for_zero_v_in(self) -> None:
        result = _compute_extrados((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        assert result is None

    def test_returns_none_for_zero_v_out(self) -> None:
        result = _compute_extrados((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        assert result is None

    def test_returns_none_for_collinear(self) -> None:
        result = _compute_extrados((1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
        assert result is None

    def test_90_degree_xy(self) -> None:
        """v_in=X, v_out=Y → path turns toward -X, so extrados = +X."""
        result = _compute_extrados((10.0, 0.0, 0.0), (0.0, 10.0, 0.0))
        assert result is not None
        assert result == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)

    def test_result_is_unit_vector(self) -> None:
        result = _compute_extrados((3.0, 4.0, 0.0), (0.0, 0.0, 7.0))
        assert result is not None
        assert _mag(result) == pytest.approx(1.0, abs=1e-9)


class TestSymmetricFrameExtrados:
    """Both ends of a symmetric frame must reference the outside of their bend."""

    def test_trapezoid_legs_extrados_point_outward(self) -> None:
        # Left leg up-right, top straight +X, right leg down-right
        s = 1.0 / math.sqrt(2.0)
        straights = [
            _straight(1, (s, s, 0.0)),
            _straight(2, (1.0, 0.0, 0.0)),
            _straight(3, (s, -s, 0.0)),
        ]
        bends = [_bend(1, 45.0), _bend(2, 45.0)]
        start = compute_end_reference(straights, bends, "start")
        end = compute_end_reference(straights, bends, "end")
        # Outside of each bend faces up and away from the frame center
        assert start.extrados_direction == pytest.approx((-s, s, 0.0), abs=1e-9)
        assert end.extrados_direction == pytest.approx((s, s, 0.0), abs=1e-9)

    def test_extrados_mirror_symmetric_across_frame(self) -> None:
        s = 1.0 / math.sqrt(2.0)
        straights = [
            _straight(1, (s, s, 0.0)),
            _straight(2, (1.0, 0.0, 0.0)),
            _straight(3, (s, -s, 0.0)),
        ]
        bends = [_bend(1, 45.0), _bend(2, 45.0)]
        start = compute_end_reference(straights, bends, "start")
        end = compute_end_reference(straights, bends, "end")
        assert start.extrados_direction is not None
        assert end.extrados_direction is not None
        # Mirror across the YZ plane maps x → -x
        sx, sy, sz = start.extrados_direction
        assert end.extrados_direction == pytest.approx((-sx, sy, sz), abs=1e-9)


class TestComputeLongPointAdjustment:
    """Cut-length correction so the tube ends at the cope's long point."""

    def test_end_already_at_long_point_needs_nothing(self) -> None:
        # Tube runs along -X toward a receiver on the Z axis through origin;
        # long point 1.5 before the crossing, modelled end exactly there.
        adj = compute_long_point_adjustment(
            (1.5, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 5.0), (0.0, 0.0, 1.0), 1.5, 0.875,
        )
        assert adj == pytest.approx(0.0, abs=1e-12)

    def test_end_at_crossing_is_trimmed(self) -> None:
        adj = compute_long_point_adjustment(
            (0.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 1.5, 0.875,
        )
        assert adj == pytest.approx(-1.5)

    def test_short_end_is_extended(self) -> None:
        # Modelled end stops 4 before the crossing; long point is 1.5 before
        adj = compute_long_point_adjustment(
            (4.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 1.5, 0.875,
        )
        assert adj == pytest.approx(2.5)

    def test_receiver_axis_sign_irrelevant(self) -> None:
        args = ((3.0, 1.0, 0.0), (-1.0, -1.0, 0.0), (0.0, 0.0, 0.0))
        plus = compute_long_point_adjustment(*args, (1.0, 0.0, 0.0), 1.0, 0.875)
        minus = compute_long_point_adjustment(*args, (-1.0, 0.0, 0.0), 1.0, 0.875)
        assert plus == pytest.approx(minus)

    def test_angled_tube(self) -> None:
        # 45° leg ending exactly at the crossing: adjustment is -z_min
        s = 1.0 / math.sqrt(2.0)
        adj = compute_long_point_adjustment(
            (0.0, 0.0, 0.0), (-s, -s, 0.0), (7.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1.26, 0.875,
        )
        assert adj == pytest.approx(-1.26)

    def test_skewed_axes_return_none(self) -> None:
        adj = compute_long_point_adjustment(
            (0.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 1.0), 1.5, 0.875,
        )
        assert adj is None

    def test_parallel_axes_return_none(self) -> None:
        adj = compute_long_point_adjustment(
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-1.0, 0.0, 0.0), 1.5, 0.875,
        )
        assert adj is None

    def test_zero_vectors_return_none(self) -> None:
        assert compute_long_point_adjustment(
            (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 1.5, 0.875,
        ) is None
        assert compute_long_point_adjustment(
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.5, 0.875,
        ) is None

    def test_matches_raycast_long_point(self) -> None:
        """End-to-end: formula z_min + adjustment lands on the true long point."""
        from core.cope_math import calculate_cope
        from models.cope_data import ReceivingTube

        a = math.radians(43.1)
        v1 = (-math.cos(a), -math.sin(a), 0.0)
        ref = (-math.sin(a), math.cos(a), 0.0)
        r1, r2 = 0.875, 1.5
        z = calculate_cope(v1, 1.75, [ReceivingTube((1.0, 0.0, 0.0), 2 * r2)], ref).z_profile
        # Modelled end 2.0 short of the axle centerline along the leg
        end = (-2.0 * v1[0], -2.0 * v1[1], 0.0)
        adj = compute_long_point_adjustment(end, v1, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), min(z), r1)
        assert adj is not None
        # Longest OD line touches the axle exactly at the adjusted end:
        # march each surface line from the adjusted end plane to the axle
        k = (0.0, 0.0, 1.0)
        tips: list[float] = []
        for deg in range(0, 360, 5):
            c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            base = [end[i] + adj * v1[i] + r1 * (c * ref[i] + s_ * k[i]) for i in range(3)]
            lo, hi = -10.0, 10.0
            for _ in range(80):
                mid = (lo + hi) / 2.0
                p = [base[i] + mid * v1[i] for i in range(3)]
                if p[1] ** 2 + p[2] ** 2 <= r2 * r2:
                    hi = mid
                else:
                    lo = mid
            tips.append(hi)
        # Long point (last line to reach the axle) meets it exactly at the
        # adjusted end plane; the heel meets it 1.870" sooner.
        assert max(tips) == pytest.approx(0.0, abs=1e-6)
        assert min(tips) == pytest.approx(-1.870, abs=1e-3)


class TestApplyEndLengthAdjustments:
    """Cut-length corrections applied to the terminal straights."""

    def _three(self) -> list[StraightSection]:
        return [_straight(i, (10.0, 0.0, 0.0)) for i in (1, 2, 3)]

    def test_both_ends(self) -> None:
        base = self._three()
        out = apply_end_length_adjustments(base, 1.5, -0.25)
        assert [s.length for s in out] == pytest.approx(
            [base[0].length + 1.5, base[1].length, base[2].length - 0.25]
        )

    def test_none_leaves_end_alone(self) -> None:
        base = self._three()
        out = apply_end_length_adjustments(base, None, None)
        assert [s.length for s in out] == [s.length for s in base]

    def test_input_not_mutated(self) -> None:
        base = self._three()
        before = [s.length for s in base]
        apply_end_length_adjustments(base, 2.0, 2.0)
        assert [s.length for s in base] == before

    def test_single_straight_gets_both(self) -> None:
        base = [_straight(1, (10.0, 0.0, 0.0))]
        out = apply_end_length_adjustments(base, 1.0, 0.5)
        assert out[0].length == pytest.approx(base[0].length + 1.5)

    def test_never_negative(self) -> None:
        base = [_straight(1, (1.0, 0.0, 0.0))]
        out = apply_end_length_adjustments(base, -1000.0, None)
        assert out[0].length == 0.0

    def test_empty(self) -> None:
        assert apply_end_length_adjustments([], 1.0, 1.0) == []
