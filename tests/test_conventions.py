"""Tests for shared rotation conventions."""

from core.conventions import (
    MIN_STRAIGHT_BEFORE_END_OD_RATIO,
    ROTATION_DIRECTION,
    ROTATION_REFERENCE,
    ROTATION_ZERO_DESCRIPTION,
    ROTATION_ZERO_STRAIGHT_DESCRIPTION,
)


class TestConventionConstants:
    """Verify convention constants have expected values."""

    def test_rotation_reference_defined(self):
        assert ROTATION_REFERENCE == "back_of_last_bend_extrados"

    def test_rotation_direction_defined(self):
        assert ROTATION_DIRECTION == "clockwise_from_coped_end"

    def test_zero_description_not_empty(self):
        assert len(ROTATION_ZERO_DESCRIPTION) > 0

    def test_straight_description_not_empty(self):
        assert len(ROTATION_ZERO_STRAIGHT_DESCRIPTION) > 0

    def test_min_straight_ratio_positive(self):
        assert MIN_STRAIGHT_BEFORE_END_OD_RATIO > 0
