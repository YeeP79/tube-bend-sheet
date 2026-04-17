"""Tests for core.body_profile — merge, filter, and build pipeline."""

from __future__ import annotations

from core.body_profile import (
    build_body_profile,
    determine_od_radius,
    filter_od_bends,
    filter_od_straights,
    merge_coaxial_straights,
)
from models.match_data import BodyBend, BodyStraight


# ── Helpers ──

def _straight(
    axis: tuple[float, float, float] = (1.0, 0.0, 0.0),
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    radius: float = 1.905,
    length: float = 10.0,
    centroid: tuple[float, float, float] = (5.0, 0.0, 0.0),
) -> BodyStraight:
    return BodyStraight(
        axis=axis, origin=origin, radius=radius, length=length, centroid=centroid,
    )


def _bend(
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    major_radius: float = 5.0,
    minor_radius: float = 1.905,
) -> BodyBend:
    return BodyBend(
        axis=axis, origin=origin, major_radius=major_radius, minor_radius=minor_radius,
    )


# ── merge_coaxial_straights ──


class TestMergeCoaxialStraights:
    def test_empty_list(self) -> None:
        assert merge_coaxial_straights([]) == []

    def test_single_segment_unchanged(self) -> None:
        seg = _straight()
        result = merge_coaxial_straights([seg])
        assert len(result) == 1
        assert result[0].axis == seg.axis

    def test_coaxial_segments_merged(self) -> None:
        s1 = _straight(axis=(1.0, 0.0, 0.0), origin=(0.0, 0.0, 0.0), length=5.0)
        s2 = _straight(axis=(1.0, 0.0, 0.0), origin=(3.0, 0.0, 0.0), length=8.0)
        result = merge_coaxial_straights([s1, s2])
        assert len(result) == 1
        assert result[0].length == 8.0  # max of the two

    def test_different_axes_not_merged(self) -> None:
        s1 = _straight(axis=(1.0, 0.0, 0.0))
        s2 = _straight(axis=(0.0, 1.0, 0.0))
        result = merge_coaxial_straights([s1, s2])
        assert len(result) == 2

    def test_antiparallel_axes_merged(self) -> None:
        s1 = _straight(axis=(1.0, 0.0, 0.0), origin=(0.0, 0.0, 0.0))
        s2 = _straight(axis=(-1.0, 0.0, 0.0), origin=(5.0, 0.0, 0.0))
        result = merge_coaxial_straights([s1, s2])
        assert len(result) == 1

    def test_different_radii_not_merged(self) -> None:
        s1 = _straight(radius=1.905)
        s2 = _straight(radius=1.5, origin=(1.0, 0.0, 0.0))
        result = merge_coaxial_straights([s1, s2])
        assert len(result) == 2

    def test_far_apart_not_merged(self) -> None:
        s1 = _straight(origin=(0.0, 0.0, 0.0))
        s2 = _straight(origin=(0.0, 5.0, 0.0))  # 5 cm perpendicular
        result = merge_coaxial_straights([s1, s2])
        assert len(result) == 2

    def test_three_coaxial_merged_to_one(self) -> None:
        segs = [
            _straight(origin=(0.0, 0.0, 0.0), length=3.0),
            _straight(origin=(2.0, 0.0, 0.0), length=5.0),
            _straight(origin=(4.0, 0.0, 0.0), length=7.0),
        ]
        result = merge_coaxial_straights(segs)
        assert len(result) == 1
        assert result[0].length == 7.0

    def test_custom_angle_tolerance(self) -> None:
        s1 = _straight(axis=(1.0, 0.0, 0.0))
        s2 = _straight(axis=(0.998, 0.063, 0.0), origin=(1.0, 0.0, 0.0))  # ~3.6 deg
        # Default 2.0 deg tolerance: not merged
        assert len(merge_coaxial_straights([s1, s2])) == 2
        # Wider tolerance: merged
        assert len(merge_coaxial_straights([s1, s2], angle_tol=5.0)) == 1

    def test_zero_length_vector_not_merged(self) -> None:
        s1 = _straight(axis=(1.0, 0.0, 0.0))
        s2 = _straight(axis=(0.0, 0.0, 0.0), origin=(1.0, 0.0, 0.0))
        result = merge_coaxial_straights([s1, s2])
        assert len(result) == 2


# ── determine_od_radius ──


class TestDetermineOdRadius:
    def test_empty_list(self) -> None:
        assert determine_od_radius([]) == 0.0

    def test_single_segment(self) -> None:
        assert determine_od_radius([_straight(radius=1.905)]) == 1.905

    def test_multiple_radii(self) -> None:
        segs = [
            _straight(radius=1.0),
            _straight(radius=1.905),
            _straight(radius=1.5),
        ]
        assert determine_od_radius(segs) == 1.905

    def test_all_same_radius(self) -> None:
        segs = [_straight(radius=2.0), _straight(radius=2.0)]
        assert determine_od_radius(segs) == 2.0


# ── filter_od_straights ──


class TestFilterOdStraights:
    def test_filters_non_od(self) -> None:
        segs = [_straight(radius=1.905), _straight(radius=1.0)]
        result = filter_od_straights(segs, od_radius=1.905)
        assert len(result) == 1
        assert result[0].radius == 1.905

    def test_keeps_within_tolerance(self) -> None:
        segs = [_straight(radius=1.906)]
        result = filter_od_straights(segs, od_radius=1.905, tol=0.01)
        assert len(result) == 1

    def test_rejects_outside_tolerance(self) -> None:
        segs = [_straight(radius=1.92)]
        result = filter_od_straights(segs, od_radius=1.905, tol=0.01)
        assert len(result) == 0

    def test_empty_input(self) -> None:
        assert filter_od_straights([], od_radius=1.905) == []


# ── filter_od_bends ──


class TestFilterOdBends:
    def test_filters_non_od_bends(self) -> None:
        bends = [_bend(minor_radius=1.905), _bend(minor_radius=1.0)]
        result = filter_od_bends(bends, od_radius=1.905)
        assert len(result) == 1
        assert result[0].minor_radius == 1.905

    def test_keeps_within_tolerance(self) -> None:
        bends = [_bend(minor_radius=1.906)]
        result = filter_od_bends(bends, od_radius=1.905, tol=0.01)
        assert len(result) == 1

    def test_empty_input(self) -> None:
        assert filter_od_bends([], od_radius=1.905) == []


# ── build_body_profile ──


class TestBuildBodyProfile:
    def test_empty_inputs(self) -> None:
        profile = build_body_profile([], [])
        assert profile.straights == []
        assert profile.bends == []
        assert profile.od_radius == 0.0

    def test_basic_profile(self) -> None:
        straights = [
            _straight(radius=1.905, origin=(0.0, 0.0, 0.0)),
            _straight(radius=1.0, origin=(0.0, 10.0, 0.0), axis=(0.0, 1.0, 0.0)),
        ]
        bends = [
            _bend(minor_radius=1.905),
            _bend(minor_radius=1.0),
        ]
        profile = build_body_profile(straights, bends)
        assert profile.od_radius == 1.905
        assert len(profile.straights) == 1
        assert len(profile.bends) == 1

    def test_coaxial_merged_then_filtered(self) -> None:
        # Two coaxial OD segments + one bore segment
        straights = [
            _straight(radius=1.905, origin=(0.0, 0.0, 0.0), length=5.0),
            _straight(radius=1.905, origin=(3.0, 0.0, 0.0), length=8.0),
            _straight(radius=1.0, origin=(0.0, 0.0, 0.0), axis=(0.0, 1.0, 0.0)),
        ]
        profile = build_body_profile(straights, [])
        assert len(profile.straights) == 1
        assert profile.straights[0].length == 8.0
        assert profile.od_radius == 1.905
