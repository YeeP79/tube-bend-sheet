"""Tests for vector utility functions added to core.geometry."""

from __future__ import annotations

import pytest

from core.geometry import (
    ZeroVectorError,
    add_vectors,
    point_to_line_distance,
    scale_vector,
    subtract_vectors,
    unsigned_angle_between,
)


# ── subtract_vectors ──


class TestSubtractVectors:
    def test_basic_subtraction(self) -> None:
        assert subtract_vectors((3.0, 5.0, 7.0), (1.0, 2.0, 3.0)) == (2.0, 3.0, 4.0)

    def test_subtract_from_self(self) -> None:
        assert subtract_vectors((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == (0.0, 0.0, 0.0)

    def test_negative_result(self) -> None:
        result = subtract_vectors((1.0, 1.0, 1.0), (3.0, 4.0, 5.0))
        assert result == (-2.0, -3.0, -4.0)


# ── add_vectors ──


class TestAddVectors:
    def test_basic_addition(self) -> None:
        assert add_vectors((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)) == (5.0, 7.0, 9.0)

    def test_add_zero_vector(self) -> None:
        assert add_vectors((1.0, 2.0, 3.0), (0.0, 0.0, 0.0)) == (1.0, 2.0, 3.0)

    def test_negative_components(self) -> None:
        result = add_vectors((1.0, -2.0, 3.0), (-1.0, 2.0, -3.0))
        assert result == (0.0, 0.0, 0.0)


# ── scale_vector ──


class TestScaleVector:
    def test_scale_by_two(self) -> None:
        assert scale_vector((1.0, 2.0, 3.0), 2.0) == (2.0, 4.0, 6.0)

    def test_scale_by_zero(self) -> None:
        assert scale_vector((5.0, 10.0, 15.0), 0.0) == (0.0, 0.0, 0.0)

    def test_scale_by_negative(self) -> None:
        assert scale_vector((1.0, 2.0, 3.0), -1.0) == (-1.0, -2.0, -3.0)

    def test_scale_by_fraction(self) -> None:
        result = scale_vector((4.0, 6.0, 8.0), 0.5)
        assert result == (2.0, 3.0, 4.0)


# ── point_to_line_distance ──


class TestPointToLineDistance:
    def test_point_on_line(self) -> None:
        dist = point_to_line_distance(
            (5.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
        )
        assert dist < 1e-10

    def test_point_perpendicular_to_x_axis(self) -> None:
        dist = point_to_line_distance(
            (0.0, 3.0, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
        )
        assert abs(dist - 3.0) < 1e-10

    def test_point_off_axis(self) -> None:
        dist = point_to_line_distance(
            (5.0, 4.0, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
        )
        assert abs(dist - 4.0) < 1e-10

    def test_3d_distance(self) -> None:
        # Point at (0, 3, 4) distance from Z-axis = sqrt(9+16) = 5
        dist = point_to_line_distance(
            (0.0, 3.0, 4.0),
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
        )
        assert abs(dist - 5.0) < 1e-10


# ── unsigned_angle_between ──


class TestUnsignedAngleBetween:
    def test_parallel_vectors(self) -> None:
        angle = unsigned_angle_between((1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
        assert abs(angle) < 0.001

    def test_antiparallel_vectors(self) -> None:
        angle = unsigned_angle_between((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0))
        assert abs(angle) < 0.001

    def test_perpendicular_vectors(self) -> None:
        angle = unsigned_angle_between((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert abs(angle - 90.0) < 0.001

    def test_45_degree_angle(self) -> None:
        angle = unsigned_angle_between((1.0, 0.0, 0.0), (1.0, 1.0, 0.0))
        assert abs(angle - 45.0) < 0.001

    def test_135_degrees_maps_to_45(self) -> None:
        # 135 degree angle should map to 45 since unsigned
        angle = unsigned_angle_between((1.0, 0.0, 0.0), (-1.0, 1.0, 0.0))
        assert abs(angle - 45.0) < 0.001

    def test_zero_vector_raises(self) -> None:
        with pytest.raises(ZeroVectorError):
            unsigned_angle_between((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))

    def test_near_zero_vector_raises(self) -> None:
        with pytest.raises(ZeroVectorError):
            unsigned_angle_between((1e-15, 0.0, 0.0), (1.0, 0.0, 0.0))
