"""
Tests for geometry module - runs without Fusion.

Run with: pytest tests/ -v
"""
import math

import pytest

from core.geometry import (
    ZeroVectorError,
    angle_between_vectors,
    calculate_rotation,
    cross_product,
    distance_between_points,
    dot_product,
    magnitude,
    normalize,
    points_are_close,
    project_onto_plane,
    vectors_are_collinear,
)


class TestVectorOperations:
    """Test basic vector operations."""

    def test_magnitude_unit_vector(self):
        assert magnitude((1.0, 0.0, 0.0)) == 1.0

    def test_magnitude_3_4_5_triangle(self):
        assert magnitude((3.0, 4.0, 0.0)) == 5.0

    def test_magnitude_zero_vector(self):
        assert magnitude((0.0, 0.0, 0.0)) == 0.0

    def test_magnitude_negative_components(self):
        assert magnitude((-3.0, -4.0, 0.0)) == 5.0

    def test_dot_product_perpendicular(self):
        result = dot_product((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert result == 0.0

    def test_dot_product_parallel(self):
        result = dot_product((1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
        assert result == 2.0

    def test_cross_product_unit_vectors(self):
        result = cross_product((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert result == (0.0, 0.0, 1.0)

    def test_cross_product_antiparallel(self):
        result = cross_product((0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
        assert result == (0.0, 0.0, -1.0)


class TestAngleBetweenVectors:
    """Test angle calculations with defensive cases."""

    def test_parallel_vectors_zero_degrees(self):
        angle = angle_between_vectors((1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
        assert abs(angle) < 0.001

    def test_antiparallel_vectors_180_degrees(self):
        angle = angle_between_vectors((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0))
        assert abs(angle - 180.0) < 0.001

    def test_perpendicular_vectors_90_degrees(self):
        angle = angle_between_vectors((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert abs(angle - 90.0) < 0.001

    def test_45_degree_angle(self):
        angle = angle_between_vectors((1.0, 0.0, 0.0), (1.0, 1.0, 0.0))
        assert abs(angle - 45.0) < 0.001

    def test_zero_first_vector_raises(self):
        try:
            angle_between_vectors((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
            raise AssertionError("Should have raised ZeroVectorError")
        except ZeroVectorError as e:
            assert "First vector" in str(e)

    def test_zero_second_vector_raises(self):
        try:
            angle_between_vectors((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            raise AssertionError("Should have raised ZeroVectorError")
        except ZeroVectorError as e:
            assert "Second vector" in str(e)

    def test_near_zero_vector_raises(self):
        """Vectors below tolerance should raise."""
        try:
            angle_between_vectors((1e-11, 0.0, 0.0), (1.0, 0.0, 0.0))
            raise AssertionError("Should have raised ZeroVectorError")
        except ZeroVectorError:
            pass

    def test_no_nan_from_nearly_parallel(self):
        """Ensure floating point edge case doesn't produce NaN."""
        angle = angle_between_vectors((1.0, 0.0, 0.0), (0.9999999, 0.0001, 0.0))
        assert not math.isnan(angle)
        assert 0 <= angle <= 180


class TestCalculateRotation:
    """Test rotation angle calculations."""

    def test_same_plane_zero_rotation(self):
        rotation = calculate_rotation((0.0, 0.0, 1.0), (0.0, 0.0, 1.0))
        assert abs(rotation) < 0.001

    def test_90_degree_rotation(self):
        rotation = calculate_rotation((0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
        assert abs(rotation - 90.0) < 0.001

    def test_180_degree_rotation(self):
        rotation = calculate_rotation((0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
        assert abs(rotation - 180.0) < 0.001

    def test_zero_normal_raises(self):
        try:
            calculate_rotation((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            raise AssertionError("Should have raised ZeroVectorError")
        except ZeroVectorError:
            pass


class TestPointOperations:
    """Test point-related functions."""

    def test_distance_same_point(self):
        dist = distance_between_points((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        assert dist == 0.0

    def test_distance_unit_apart(self):
        dist = distance_between_points((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        assert dist == 1.0

    def test_distance_3d(self):
        dist = distance_between_points((0.0, 0.0, 0.0), (1.0, 2.0, 2.0))
        assert dist == 3.0

    def test_points_are_close_same(self):
        assert points_are_close((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    def test_points_are_close_within_tolerance(self):
        assert points_are_close((0.0, 0.0, 0.0), (0.05, 0.0, 0.0), tolerance=0.1)

    def test_points_are_close_outside_tolerance(self):
        assert not points_are_close((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), tolerance=0.1)


class TestVectorsAreCollinear:
    """Test vectors_are_collinear() function."""

    # Happy path: parallel vectors
    def test_same_direction_parallel(self):
        """Vectors pointing the same direction are collinear."""
        assert vectors_are_collinear((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)) is True

    def test_anti_parallel(self):
        """Vectors pointing opposite directions are collinear."""
        assert vectors_are_collinear((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)) is True

    def test_3d_parallel(self):
        """Parallel vectors in 3D are collinear."""
        assert vectors_are_collinear((1.0, 2.0, 3.0), (2.0, 4.0, 6.0)) is True

    def test_3d_anti_parallel(self):
        """Anti-parallel vectors in 3D are collinear."""
        assert vectors_are_collinear((1.0, 2.0, 3.0), (-1.0, -2.0, -3.0)) is True

    # Non-collinear vectors
    def test_perpendicular_not_collinear(self):
        """Perpendicular vectors are not collinear."""
        assert vectors_are_collinear((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)) is False

    def test_45_degree_not_collinear(self):
        """Vectors at 45 degrees are not collinear."""
        assert vectors_are_collinear((1.0, 0.0, 0.0), (1.0, 1.0, 0.0)) is False

    # Tolerance edge cases
    def test_within_tolerance(self):
        """Vectors with very slight angle (within tolerance) are collinear."""
        # Angle ~0.003 degrees - well within default 0.01 tolerance
        assert vectors_are_collinear((1.0, 0.0, 0.0), (1.0, 0.00005, 0.0)) is True

    def test_beyond_tolerance(self):
        """Vectors beyond tolerance are not collinear."""
        # Use a tight tolerance to demonstrate
        assert vectors_are_collinear(
            (1.0, 0.0, 0.0), (1.0, 0.01, 0.0), tolerance_deg=0.001
        ) is False

    def test_near_anti_parallel_within_tolerance(self):
        """Nearly anti-parallel vectors (within tolerance) are collinear."""
        assert vectors_are_collinear((1.0, 0.0, 0.0), (-1.0, 0.00005, 0.0)) is True

    # Defensive: zero-length vectors
    def test_zero_first_vector_returns_false(self):
        """Zero-length first vector returns False (not an error)."""
        assert vectors_are_collinear((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)) is False

    def test_zero_second_vector_returns_false(self):
        """Zero-length second vector returns False (not an error)."""
        assert vectors_are_collinear((1.0, 0.0, 0.0), (0.0, 0.0, 0.0)) is False

    def test_both_zero_vectors_returns_false(self):
        """Both zero-length vectors returns False."""
        assert vectors_are_collinear((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)) is False

    # Floating point edge cases
    def test_no_crash_on_near_zero_vector(self):
        """Near-zero vector doesn't crash."""
        result = vectors_are_collinear((1e-11, 0.0, 0.0), (1.0, 0.0, 0.0))
        assert result is False  # Below zero magnitude tolerance


class TestNormalize:
    """Test normalize() function."""

    def test_unit_vector_unchanged(self):
        result = normalize((1.0, 0.0, 0.0))
        assert abs(result[0] - 1.0) < 1e-10
        assert abs(result[1]) < 1e-10
        assert abs(result[2]) < 1e-10

    def test_scales_to_unit_length(self):
        result = normalize((3.0, 4.0, 0.0))
        assert abs(magnitude(result) - 1.0) < 1e-10
        assert abs(result[0] - 0.6) < 1e-10
        assert abs(result[1] - 0.8) < 1e-10

    def test_negative_components(self):
        result = normalize((-3.0, -4.0, 0.0))
        assert abs(magnitude(result) - 1.0) < 1e-10
        assert abs(result[0] - (-0.6)) < 1e-10
        assert abs(result[1] - (-0.8)) < 1e-10

    def test_3d_vector(self):
        result = normalize((1.0, 1.0, 1.0))
        expected = 1.0 / math.sqrt(3.0)
        for comp in result:
            assert abs(comp - expected) < 1e-10

    def test_zero_vector_raises(self):
        with pytest.raises(ZeroVectorError):
            normalize((0.0, 0.0, 0.0))

    def test_near_zero_vector_raises(self):
        with pytest.raises(ZeroVectorError):
            normalize((1e-11, 0.0, 0.0))


class TestProjectOntoPlane:
    """Test project_onto_plane() function."""

    def test_vector_already_in_plane(self):
        """Vector in XY plane projected onto XY plane is unchanged."""
        result = project_onto_plane((1.0, 2.0, 0.0), (0.0, 0.0, 1.0))
        assert abs(result[0] - 1.0) < 1e-10
        assert abs(result[1] - 2.0) < 1e-10
        assert abs(result[2]) < 1e-10

    def test_vector_perpendicular_to_plane(self):
        """Vector along plane normal projects to zero."""
        result = project_onto_plane((0.0, 0.0, 5.0), (0.0, 0.0, 1.0))
        assert abs(result[0]) < 1e-10
        assert abs(result[1]) < 1e-10
        assert abs(result[2]) < 1e-10

    def test_45_degree_projection(self):
        """Vector at 45 degrees to plane normal."""
        result = project_onto_plane((1.0, 0.0, 1.0), (0.0, 0.0, 1.0))
        assert abs(result[0] - 1.0) < 1e-10
        assert abs(result[1]) < 1e-10
        assert abs(result[2]) < 1e-10

    def test_non_unit_normal(self):
        """Works with non-unit plane normal."""
        result = project_onto_plane((1.0, 0.0, 1.0), (0.0, 0.0, 3.0))
        assert abs(result[0] - 1.0) < 1e-10
        assert abs(result[1]) < 1e-10
        assert abs(result[2]) < 1e-10

    def test_3d_projection(self):
        """Projection onto arbitrary plane in 3D."""
        # Project (1,1,1) onto plane with normal (1,0,0) -> (0,1,1)
        result = project_onto_plane((1.0, 1.0, 1.0), (1.0, 0.0, 0.0))
        assert abs(result[0]) < 1e-10
        assert abs(result[1] - 1.0) < 1e-10
        assert abs(result[2] - 1.0) < 1e-10

    def test_zero_normal_raises(self):
        with pytest.raises(ZeroVectorError):
            project_onto_plane((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))
