"""Tests for core.cope_path — EndReference extraction from path data."""

import math

import pytest

from core.cope_path import compute_end_reference, _compute_extrados
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
        End extrados should point toward -X."""
        straights = [
            _straight(1, (10.0, 0.0, 0.0)),
            _straight(2, (0.0, 10.0, 0.0)),
        ]
        bends = [_bend(1, 90.0)]
        ref = compute_end_reference(straights, bends, "end")
        assert ref.extrados_direction is not None
        assert ref.extrados_direction == pytest.approx((-1.0, 0.0, 0.0), abs=1e-9)

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
        # v_in = (0,10,0), v_out = (0,0,10) → extrados should be (0,-1,0)
        assert ref.extrados_direction == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)

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
        # v_in = (0,10,0), v_out = (10,0,0) → extrados should be (0,-1,0)
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
        """v_in=X, v_out=Y → extrados = -X."""
        result = _compute_extrados((10.0, 0.0, 0.0), (0.0, 10.0, 0.0))
        assert result is not None
        assert result == pytest.approx((-1.0, 0.0, 0.0), abs=1e-9)

    def test_result_is_unit_vector(self) -> None:
        result = _compute_extrados((3.0, 4.0, 0.0), (0.0, 0.0, 7.0))
        assert result is not None
        assert _mag(result) == pytest.approx(1.0, abs=1e-9)
