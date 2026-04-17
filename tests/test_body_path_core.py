"""Tests for core.body_path — convert body face segments to bend sheet data."""

from __future__ import annotations

import math

from core.body_path import (
    body_path_to_straights_and_bends,
    detect_path_direction,
    _get_straight_vector,
    _scale_point,
    _find_next_straight_vector,
)
from models.body_path_data import BodyFaceSegment, BodyPathResult
from models.units import UnitConfig


# ── Helpers ──


def _inches_unit() -> UnitConfig:
    """Create a UnitConfig for inches."""
    return UnitConfig(
        is_metric=False,
        unit_name="in",
        unit_symbol='"',
        cm_to_unit=1.0 / 2.54,
        default_tube_od="1.75",
        default_precision=16,
        valid_precisions=(0, 4, 8, 16, 32),
    )


def _mm_unit() -> UnitConfig:
    """Create a UnitConfig for millimetres."""
    return UnitConfig(
        is_metric=True,
        unit_name="mm",
        unit_symbol="mm",
        cm_to_unit=10.0,
        default_tube_od="44.45",
        default_precision=1,
        valid_precisions=(0, 1, 2, 5, 10),
    )


def _straight_seg(
    axis: tuple[float, float, float] = (1.0, 0.0, 0.0),
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    length: float = 10.0,
    start_center: tuple[float, float, float] | None = None,
    end_center: tuple[float, float, float] | None = None,
    non_circle_edges: int = 0,
) -> BodyFaceSegment:
    return BodyFaceSegment(
        face_type="straight",
        axis=axis,
        origin=origin,
        length=length,
        start_center=start_center,
        end_center=end_center,
        non_circle_edges=non_circle_edges,
    )


def _bend_seg(
    bend_angle: float = 90.0,
    clr: float = 5.0,
    torus_axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
    torus_origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> BodyFaceSegment:
    return BodyFaceSegment(
        face_type="bend",
        bend_angle=bend_angle,
        clr=clr,
        torus_axis=torus_axis,
        torus_origin=torus_origin,
    )


def _make_path(
    segments: list[BodyFaceSegment],
    od_radius: float = 1.905,
    clr_values: list[float] | None = None,
    start_point: tuple[float, float, float] = (0.0, 0.0, 0.0),
    end_point: tuple[float, float, float] = (10.0, 0.0, 0.0),
    start_is_coped: bool = False,
    end_is_coped: bool = False,
) -> BodyPathResult:
    if clr_values is None:
        clr_values = [seg.clr for seg in segments if seg.face_type == "bend"]
    return BodyPathResult(
        segments=segments,
        od_radius=od_radius,
        clr_values=clr_values,
        start_point=start_point,
        end_point=end_point,
        start_is_coped=start_is_coped,
        end_is_coped=end_is_coped,
    )


# ── body_path_to_straights_and_bends ──


class TestSingleStraight:
    """Path with just one straight section (no bends)."""

    def test_single_straight_counts(self) -> None:
        path = _make_path([_straight_seg(length=25.4)])
        straights, bends, clr = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(straights) == 1
        assert len(bends) == 0
        assert clr == 0.0

    def test_single_straight_length_inches(self) -> None:
        path = _make_path([_straight_seg(length=25.4)])  # 10 inches in cm
        straights, _, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert abs(straights[0].length - 10.0) < 0.001

    def test_single_straight_length_mm(self) -> None:
        path = _make_path([_straight_seg(length=5.0)])  # 5 cm = 50 mm
        straights, _, _ = body_path_to_straights_and_bends(path, _mm_unit())
        assert abs(straights[0].length - 50.0) < 0.001

    def test_single_straight_numbering(self) -> None:
        path = _make_path([_straight_seg()])
        straights, _, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert straights[0].number == 1


class TestSingleBend:
    """Path with straight-bend-straight (simplest bend path)."""

    def test_one_bend_counts(self) -> None:
        segs = [
            _straight_seg(
                axis=(1.0, 0.0, 0.0), length=10.0,
                start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0),
            ),
            _bend_seg(bend_angle=90.0, clr=5.0),
            _straight_seg(
                axis=(0.0, 1.0, 0.0), length=10.0,
                start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0),
            ),
        ]
        path = _make_path(segs)
        straights, bends, clr = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(straights) == 2
        assert len(bends) == 1
        assert bends[0].number == 1
        assert bends[0].rotation is None  # First bend has no rotation

    def test_one_bend_angle(self) -> None:
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=45.0, clr=5.0),
            _straight_seg(length=10.0, start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0)),
        ]
        path = _make_path(segs)
        _, bends, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert abs(bends[0].angle - 45.0) < 0.001

    def test_arc_length_calculation(self) -> None:
        clr_cm = 5.0
        angle_deg = 90.0
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=angle_deg, clr=clr_cm),
            _straight_seg(length=10.0, start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0)),
        ]
        path = _make_path(segs)
        units = _inches_unit()
        _, bends, _ = body_path_to_straights_and_bends(path, units)
        expected_arc_cm = clr_cm * math.radians(angle_deg)
        expected_arc_in = expected_arc_cm * units.cm_to_unit
        assert abs(bends[0].arc_length - expected_arc_in) < 0.001

    def test_clr_display_units(self) -> None:
        clr_cm = 13.97  # ~5.5 inches
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=90.0, clr=clr_cm),
            _straight_seg(length=10.0, start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0)),
        ]
        path = _make_path(segs, clr_values=[clr_cm])
        units = _inches_unit()
        _, _, clr = body_path_to_straights_and_bends(path, units)
        assert abs(clr - 5.5) < 0.01


class TestMultiBend:
    """Multi-bend paths with rotation calculations."""

    def _make_two_bend_path(self) -> BodyPathResult:
        """Two 90-degree bends in the XY plane (same bend plane → rotation=0)."""
        segs = [
            _straight_seg(
                axis=(1.0, 0.0, 0.0), length=10.0,
                start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0),
            ),
            _bend_seg(bend_angle=90.0, clr=5.0),
            _straight_seg(
                axis=(0.0, 1.0, 0.0), length=10.0,
                start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0),
            ),
            _bend_seg(bend_angle=90.0, clr=5.0),
            _straight_seg(
                axis=(-1.0, 0.0, 0.0), length=10.0,
                start_center=(10.0, 10.0, 0.0), end_center=(0.0, 10.0, 0.0),
            ),
        ]
        return _make_path(segs, clr_values=[5.0, 5.0])

    def test_two_bends_coplanar_rotation_zero(self) -> None:
        path = self._make_two_bend_path()
        _, bends, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(bends) == 2
        assert bends[0].rotation is None  # First bend
        assert bends[1].rotation is not None
        assert abs(bends[1].rotation) < 0.5  # Coplanar → ~0° rotation

    def test_two_bends_perpendicular_rotation_90(self) -> None:
        """Two bends in perpendicular planes → 90° rotation."""
        segs = [
            _straight_seg(
                axis=(1.0, 0.0, 0.0), length=10.0,
                start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0),
            ),
            _bend_seg(bend_angle=90.0, clr=5.0),
            _straight_seg(
                axis=(0.0, 1.0, 0.0), length=10.0,
                start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0),
            ),
            _bend_seg(bend_angle=90.0, clr=5.0),
            _straight_seg(
                axis=(0.0, 0.0, 1.0), length=10.0,
                start_center=(10.0, 10.0, 0.0), end_center=(10.0, 10.0, 10.0),
            ),
        ]
        path = _make_path(segs, clr_values=[5.0, 5.0])
        _, bends, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(bends) == 2
        assert bends[1].rotation is not None
        assert abs(bends[1].rotation - 90.0) < 0.5

    def test_three_bends_numbering(self) -> None:
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=45.0, clr=5.0),
            _straight_seg(length=10.0, start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0)),
            _bend_seg(bend_angle=60.0, clr=5.0),
            _straight_seg(length=10.0, start_center=(10.0, 10.0, 0.0), end_center=(0.0, 10.0, 0.0)),
            _bend_seg(bend_angle=30.0, clr=5.0),
            _straight_seg(length=10.0, start_center=(0.0, 10.0, 0.0), end_center=(0.0, 10.0, 10.0)),
        ]
        path = _make_path(segs, clr_values=[5.0, 5.0, 5.0])
        straights, bends, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(straights) == 4
        assert len(bends) == 3
        assert [s.number for s in straights] == [1, 2, 3, 4]
        assert [b.number for b in bends] == [1, 2, 3]

    def test_straight_vectors_preserved_for_rotation(self) -> None:
        """Vectors stored in StraightSection should be in internal (cm) units."""
        segs = [
            _straight_seg(
                axis=(1.0, 0.0, 0.0), length=10.0,
                start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0),
            ),
        ]
        path = _make_path(segs)
        straights, _, _ = body_path_to_straights_and_bends(path, _inches_unit())
        # Vector should be (10, 0, 0) in cm (not converted to inches)
        assert abs(straights[0].vector[0] - 10.0) < 0.001
        assert abs(straights[0].vector[1]) < 0.001
        assert abs(straights[0].vector[2]) < 0.001


class TestEdgeCases:
    """Edge cases: empty path, no bends, starts/ends with bend."""

    def test_empty_path(self) -> None:
        path = _make_path([])
        straights, bends, clr = body_path_to_straights_and_bends(path, _inches_unit())
        assert straights == []
        assert bends == []
        assert clr == 0.0

    def test_no_clr_values(self) -> None:
        """Path with no bends should return clr=0."""
        path = _make_path([_straight_seg()], clr_values=[])
        _, _, clr = body_path_to_straights_and_bends(path, _inches_unit())
        assert clr == 0.0

    def test_starts_with_bend(self) -> None:
        """Bend at the start of the path (no incoming straight for first bend)."""
        segs = [
            _bend_seg(bend_angle=90.0, clr=5.0),
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
        ]
        path = _make_path(segs, clr_values=[5.0])
        straights, bends, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(straights) == 1
        assert len(bends) == 1
        assert bends[0].rotation is None

    def test_ends_with_bend(self) -> None:
        """Bend at the end of the path (no outgoing straight for last bend)."""
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=90.0, clr=5.0),
        ]
        path = _make_path(segs, clr_values=[5.0])
        straights, bends, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert len(straights) == 1
        assert len(bends) == 1

    def test_axis_fallback_when_no_circle_centers(self) -> None:
        """When circle centers are missing, fall back to axis * length."""
        seg = _straight_seg(
            axis=(0.0, 0.0, 1.0),
            length=20.0,
            start_center=None,
            end_center=None,
        )
        path = _make_path([seg])
        straights, _, _ = body_path_to_straights_and_bends(path, _inches_unit())
        # Vector should be (0, 0, 20) — axis direction * length
        assert abs(straights[0].vector[2] - 20.0) < 0.001

    def test_zero_length_straight(self) -> None:
        """Zero-length straight should produce zero-length vector."""
        seg = _straight_seg(length=0.0, start_center=None, end_center=None, axis=(1.0, 0.0, 0.0))
        path = _make_path([seg])
        straights, _, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert abs(straights[0].length) < 0.001


class TestUnitConversion:
    """Verify unit conversion for different UnitConfigs."""

    def test_cm_to_inches(self) -> None:
        length_cm = 2.54  # 1 inch
        path = _make_path([_straight_seg(length=length_cm)])
        straights, _, _ = body_path_to_straights_and_bends(path, _inches_unit())
        assert abs(straights[0].length - 1.0) < 0.0001

    def test_cm_to_mm(self) -> None:
        length_cm = 1.0  # 10 mm
        path = _make_path([_straight_seg(length=length_cm)])
        straights, _, _ = body_path_to_straights_and_bends(path, _mm_unit())
        assert abs(straights[0].length - 10.0) < 0.0001

    def test_clr_conversion(self) -> None:
        """CLR should be converted to display units."""
        clr_cm = 2.54  # 1 inch
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=90.0, clr=clr_cm),
            _straight_seg(length=10.0, start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0)),
        ]
        path = _make_path(segs, clr_values=[clr_cm])
        _, _, clr = body_path_to_straights_and_bends(path, _inches_unit())
        assert abs(clr - 1.0) < 0.0001

    def test_arc_length_conversion(self) -> None:
        """Arc length should be in display units."""
        clr_cm = 2.54  # 1 inch
        angle = 180.0
        segs = [
            _straight_seg(length=10.0, start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0)),
            _bend_seg(bend_angle=angle, clr=clr_cm),
            _straight_seg(length=10.0, start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0)),
        ]
        path = _make_path(segs, clr_values=[clr_cm])
        units = _inches_unit()
        _, bends, _ = body_path_to_straights_and_bends(path, units)
        expected = math.pi * clr_cm * units.cm_to_unit  # pi * 1 inch
        assert abs(bends[0].arc_length - expected) < 0.001


# ── detect_path_direction ──


class TestDetectPathDirection:
    """Direction detection from path endpoints."""

    def test_positive_x(self) -> None:
        path = _make_path([], start_point=(0.0, 0.0, 0.0), end_point=(100.0, 1.0, 0.0))
        axis, current, opposite = detect_path_direction(path)
        assert axis == "X"
        assert current == "Right"
        assert opposite == "Left"

    def test_negative_x(self) -> None:
        path = _make_path([], start_point=(100.0, 0.0, 0.0), end_point=(0.0, 0.0, 0.0))
        axis, current, opposite = detect_path_direction(path)
        assert axis == "X"
        assert current == "Left"
        assert opposite == "Right"

    def test_positive_y(self) -> None:
        path = _make_path([], start_point=(0.0, 0.0, 0.0), end_point=(0.0, 100.0, 0.0))
        axis, current, opposite = detect_path_direction(path)
        assert axis == "Y"
        assert current == "Top"
        assert opposite == "Bottom"

    def test_negative_z(self) -> None:
        path = _make_path([], start_point=(0.0, 0.0, 100.0), end_point=(0.0, 0.0, 0.0))
        axis, current, opposite = detect_path_direction(path)
        assert axis == "Z"
        assert current == "Front"
        assert opposite == "Back"

    def test_positive_z(self) -> None:
        path = _make_path([], start_point=(0.0, 0.0, 0.0), end_point=(0.0, 0.0, 100.0))
        axis, current, opposite = detect_path_direction(path)
        assert axis == "Z"
        assert current == "Back"
        assert opposite == "Front"

    def test_diagonal_path_picks_dominant_axis(self) -> None:
        """When displacement has components in multiple axes, largest wins."""
        path = _make_path([], start_point=(0.0, 0.0, 0.0), end_point=(5.0, 10.0, 3.0))
        axis, _, _ = detect_path_direction(path)
        assert axis == "Y"

    def test_zero_displacement(self) -> None:
        """When start == end, should still return valid axis (Z by default)."""
        path = _make_path([], start_point=(0.0, 0.0, 0.0), end_point=(0.0, 0.0, 0.0))
        axis, current, opposite = detect_path_direction(path)
        # All zero → max picks first tie, which goes to Z
        assert axis in ("X", "Y", "Z")


# ── _get_straight_vector (private helper) ──


class TestGetStraightVector:
    """Tests for the private vector computation helper."""

    def test_circle_centers_preferred(self) -> None:
        seg = _straight_seg(
            start_center=(0.0, 0.0, 0.0),
            end_center=(5.0, 3.0, 0.0),
            axis=(1.0, 0.0, 0.0),  # Different from center-based direction
            length=10.0,
        )
        vec = _get_straight_vector(seg)
        assert abs(vec[0] - 5.0) < 0.001
        assert abs(vec[1] - 3.0) < 0.001

    def test_axis_fallback(self) -> None:
        seg = _straight_seg(
            start_center=None,
            end_center=None,
            axis=(0.0, 1.0, 0.0),
            length=7.5,
        )
        vec = _get_straight_vector(seg)
        assert abs(vec[1] - 7.5) < 0.001

    def test_no_data_returns_zero(self) -> None:
        seg = BodyFaceSegment(face_type="straight")
        vec = _get_straight_vector(seg)
        assert vec == (0.0, 0.0, 0.0)


# ── _scale_point ──


class TestScalePoint:
    def test_scale_by_factor(self) -> None:
        assert _scale_point((1.0, 2.0, 3.0), 2.54) == (2.54, 5.08, 7.62)

    def test_scale_by_zero(self) -> None:
        assert _scale_point((5.0, 10.0, 15.0), 0.0) == (0.0, 0.0, 0.0)


# ── _find_next_straight_vector ──


class TestFindNextStraightVector:
    def test_finds_next_straight(self) -> None:
        s1 = _straight_seg(start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0))
        b = _bend_seg()
        s2 = _straight_seg(start_center=(10.0, 0.0, 0.0), end_center=(10.0, 10.0, 0.0))
        segments = [s1, b, s2]
        vec = _find_next_straight_vector(segments, b)
        assert vec is not None
        assert abs(vec[1] - 10.0) < 0.001

    def test_no_straight_after_bend(self) -> None:
        s1 = _straight_seg(start_center=(0.0, 0.0, 0.0), end_center=(10.0, 0.0, 0.0))
        b = _bend_seg()
        segments = [s1, b]
        vec = _find_next_straight_vector(segments, b)
        assert vec is None

    def test_empty_segments(self) -> None:
        b = _bend_seg()
        vec = _find_next_straight_vector([], b)
        assert vec is None
