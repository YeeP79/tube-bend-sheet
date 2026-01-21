"""
Tests for calculations module - runs without Fusion.

Run with: pytest tests/ -v
"""
from dataclasses import dataclass

from core.calculations import build_segments_and_marks, validate_clr_consistency
from core.direction_validation import (
    validate_grip_for_direction,
    validate_direction_aware,
)
from models import BendData, StraightSection


@dataclass
class MockArc:
    """Mock SketchArc that only provides radius attribute."""
    radius: float


@dataclass
class MockUnitConfig:
    """Mock UnitConfig for testing."""
    cm_to_unit: float = 1.0  # 1:1 for simplicity in tests


class TestValidateClrConsistency:
    """Test CLR validation function."""

    # Happy path tests
    def test_single_arc(self) -> None:
        arcs = [MockArc(radius=5.0)]
        units = MockUnitConfig()
        clr, has_mismatch, values = validate_clr_consistency(arcs, units)
        assert clr == 5.0
        assert has_mismatch is False
        assert values == [5.0]

    def test_multiple_matching_arcs(self) -> None:
        arcs = [MockArc(radius=5.0), MockArc(radius=5.0), MockArc(radius=5.0)]
        units = MockUnitConfig()
        clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        assert clr == 5.0
        assert has_mismatch is False

    def test_arcs_within_tolerance(self) -> None:
        # 0.2% of 5.0 is 0.01, so 5.005 should be within tolerance
        arcs = [MockArc(radius=5.0), MockArc(radius=5.005)]
        units = MockUnitConfig()
        clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        assert clr == 5.0
        assert has_mismatch is False

    def test_arcs_outside_tolerance(self) -> None:
        # 5.0 and 5.1 differ by 0.1, which is 2% - way outside 0.2% tolerance
        arcs = [MockArc(radius=5.0), MockArc(radius=5.1)]
        units = MockUnitConfig()
        clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        assert clr == 5.0
        assert has_mismatch is True

    # Empty list tests
    def test_empty_arcs_list(self) -> None:
        arcs: list[MockArc] = []
        units = MockUnitConfig()
        clr, has_mismatch, values = validate_clr_consistency(arcs, units)
        assert clr == 0.0
        assert has_mismatch is False
        assert values == []

    # Issue 4 fix: Zero/negative CLR tests
    def test_zero_clr_returns_mismatch(self) -> None:
        """Zero CLR should return mismatch flag (Issue 4 fix)."""
        arcs = [MockArc(radius=0.0)]
        units = MockUnitConfig()
        clr, has_mismatch, values = validate_clr_consistency(arcs, units)
        assert clr == 0.0
        assert has_mismatch is True
        assert values == [0.0]

    def test_negative_clr_returns_mismatch(self) -> None:
        """Negative CLR should return mismatch flag (Issue 4 fix)."""
        arcs = [MockArc(radius=-1.0)]
        units = MockUnitConfig()
        clr, has_mismatch, values = validate_clr_consistency(arcs, units)
        assert clr == 0.0
        assert has_mismatch is True
        assert values == [-1.0]

    def test_multiple_arcs_first_zero(self) -> None:
        """If first arc has zero radius, should return mismatch."""
        arcs = [MockArc(radius=0.0), MockArc(radius=5.0)]
        units = MockUnitConfig()
        clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        assert clr == 0.0
        assert has_mismatch is True

    # Unit conversion tests
    def test_unit_conversion(self) -> None:
        # Simulating inches: 1 inch = 2.54 cm, so cm_to_unit = 1/2.54
        arcs = [MockArc(radius=2.54)]  # 2.54 cm = 1 inch
        units = MockUnitConfig(cm_to_unit=1 / 2.54)
        clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        assert abs(clr - 1.0) < 0.0001  # Should be 1 inch
        assert has_mismatch is False

    # Minimum tolerance floor tests
    def test_very_small_clr_uses_minimum_tolerance(self) -> None:
        """Very small CLR should use minimum tolerance floor of 0.001."""
        # With CLR = 0.01, ratio tolerance = 0.00002 (too small)
        # Should use minimum floor of 0.001 instead
        arcs = [MockArc(radius=0.01), MockArc(radius=0.0105)]
        units = MockUnitConfig()
        clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        assert clr == 0.01
        # 0.0005 difference is within 0.001 tolerance floor
        assert has_mismatch is False

    # Defensive: NaN and Infinity handling
    def test_nan_clr_returns_mismatch(self) -> None:
        """NaN radius should return mismatch flag (defensive behavior)."""
        arcs = [MockArc(radius=float('nan'))]
        units = MockUnitConfig()
        _clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        # NaN should trigger mismatch - we can't work with invalid geometry
        assert has_mismatch is True

    def test_inf_clr_returns_mismatch(self) -> None:
        """Infinity radius should return mismatch flag (defensive behavior)."""
        arcs = [MockArc(radius=float('inf'))]
        units = MockUnitConfig()
        _clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        # Infinity should trigger mismatch - not a valid CLR value
        assert has_mismatch is True

    def test_negative_inf_clr_returns_mismatch(self) -> None:
        """Negative infinity should return mismatch flag."""
        arcs = [MockArc(radius=float('-inf'))]
        units = MockUnitConfig()
        _clr, has_mismatch, _values = validate_clr_consistency(arcs, units)
        # Negative infinity is caught by clr <= 0 check
        assert has_mismatch is True


# Helper function to create StraightSection objects
def make_straight(num: int, length: float) -> StraightSection:
    """Create a StraightSection for testing."""
    return StraightSection(
        number=num,
        length=length,
        start=(0.0, 0.0, 0.0),
        end=(length, 0.0, 0.0),
        vector=(length, 0.0, 0.0),
    )


class TestBuildSegmentsAndMarks:
    """Test build_segments_and_marks() function."""

    # Happy path tests
    def test_single_bend_path(self) -> None:
        """Simple path: straight -> bend -> straight."""
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        segments, marks = build_segments_and_marks(
            straights, bends, extra_material=2.0, die_offset=0.5
        )

        # Should have 3 segments: straight, bend, straight
        assert len(segments) == 3

        # Check segment order and types
        assert segments[0].segment_type == 'straight'
        assert segments[0].name == 'Straight 1'
        assert segments[1].segment_type == 'bend'
        assert segments[1].name == 'BEND 1'
        assert segments[2].segment_type == 'straight'
        assert segments[2].name == 'Straight 2'

        # Check cumulative positions
        assert segments[0].starts_at == 2.0  # extra_material
        assert segments[0].ends_at == 12.0  # 2 + 10
        assert segments[1].starts_at == 12.0
        assert segments[1].ends_at == 17.0  # 12 + 5
        assert segments[2].starts_at == 17.0
        assert segments[2].ends_at == 27.0  # 17 + 10

        # Check mark position
        assert len(marks) == 1
        assert marks[0].bend_num == 1
        assert marks[0].mark_position == 11.5  # 12 - 0.5 (die_offset)
        assert marks[0].bend_angle == 45.0

    def test_multi_bend_path(self) -> None:
        """Path with multiple bends."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 8.0),
            make_straight(3, 12.0),
        ]
        bends = [
            BendData(number=1, angle=45.0, rotation=None, arc_length=4.0),
            BendData(number=2, angle=90.0, rotation=30.0, arc_length=6.0),
        ]

        segments, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=1.0
        )

        # Should have 5 segments
        assert len(segments) == 5
        assert segments[0].segment_type == 'straight'
        assert segments[1].segment_type == 'bend'
        assert segments[2].segment_type == 'straight'
        assert segments[3].segment_type == 'bend'
        assert segments[4].segment_type == 'straight'

        # Check mark positions
        assert len(marks) == 2
        assert marks[0].bend_num == 1
        assert marks[0].mark_position == 9.0  # 10 - 1 (die_offset)
        assert marks[1].bend_num == 2
        assert marks[1].mark_position == 21.0  # (10 + 4 + 8) - 1

    # Defensive: Edge cases
    def test_empty_bends(self) -> None:
        """Path with no bends (just straights)."""
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends: list[BendData] = []

        segments, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.0
        )

        # Should have 2 straight segments only
        assert len(segments) == 2
        assert all(s.segment_type == 'straight' for s in segments)
        assert len(marks) == 0

    def test_zero_extra_material(self) -> None:
        """Path with no extra material at start."""
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        segments, _marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.5
        )

        # First segment should start at 0
        assert segments[0].starts_at == 0.0

    def test_zero_die_offset(self) -> None:
        """Path with zero die offset."""
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        _segments, marks = build_segments_and_marks(
            straights, bends, extra_material=2.0, die_offset=0.0
        )

        # Mark should be at bend start (no offset)
        assert marks[0].mark_position == 12.0  # 2 + 10, no offset

    def test_very_small_lengths(self) -> None:
        """Handle very small lengths without precision issues."""
        straights = [make_straight(1, 0.001), make_straight(2, 0.001)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=0.0005)]

        segments, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.0001
        )

        # Should complete without errors
        assert len(segments) == 3
        assert len(marks) == 1
        # Verify precision is maintained
        assert abs(segments[0].ends_at - 0.001) < 1e-10

    def test_cumulative_position_accuracy(self) -> None:
        """Verify cumulative positions are calculated correctly."""
        straights = [
            make_straight(1, 5.0),
            make_straight(2, 7.0),
            make_straight(3, 3.0),
        ]
        bends = [
            BendData(number=1, angle=45.0, rotation=None, arc_length=2.0),
            BendData(number=2, angle=90.0, rotation=15.0, arc_length=4.0),
        ]

        segments, _marks = build_segments_and_marks(
            straights, bends, extra_material=1.0, die_offset=0.0
        )

        # Verify total length
        # Extra: 1, S1: 5, B1: 2, S2: 7, B2: 4, S3: 3 = 22 total
        assert segments[-1].ends_at == 22.0

        # Verify each segment connects to the next
        for i in range(len(segments) - 1):
            assert segments[i].ends_at == segments[i + 1].starts_at

    def test_rotation_on_segments(self) -> None:
        """Verify rotation is set correctly on straight segments."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 10.0),
            make_straight(3, 10.0),
        ]
        bends = [
            BendData(number=1, angle=45.0, rotation=None, arc_length=5.0),  # First - no rotation
            BendData(number=2, angle=90.0, rotation=30.0, arc_length=5.0),  # Has rotation
        ]

        segments, _marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.0
        )

        # First straight has rotation from first bend (None)
        assert segments[0].rotation is None
        # Second straight has rotation from second bend (30.0)
        assert segments[2].rotation == 30.0
        # Third straight has no following bend, so rotation is None
        assert segments[4].rotation is None

        # Bend segments should have no rotation set
        assert segments[1].rotation is None
        assert segments[3].rotation is None

    def test_die_offset_always_subtracts(self) -> None:
        """Die offset always subtracts from bend position."""
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]
        die_offset = 0.5

        _segments, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=die_offset
        )

        # Bend starts at 10.0 (after first straight)
        # Mark should be at 10.0 - 0.5 = 9.5 (before bend tangent point)
        # Die offset is a physical property of the die and always subtracts
        assert len(marks) == 1
        assert marks[0].mark_position == 9.5

    def test_zero_die_offset_mark_at_bend_start(self) -> None:
        """Zero die offset places mark exactly at bend start."""
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        _, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.0
        )

        # With zero offset, mark is exactly where bend starts
        assert marks[0].mark_position == 10.0

    def test_negative_die_offset_handled(self) -> None:
        """Negative die offset should work (mark position after normal point).

        A negative die offset means the mark is placed beyond the bend tangent
        point, toward the bend. This is unusual but mathematically valid.
        """
        straights = [make_straight(1, 10.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        _segments, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=-1.0
        )

        # With negative offset, mark position is bend_starts_at - (-1.0) = 10 + 1 = 11
        # This places the mark 1 unit AFTER the normal tangent point
        assert len(marks) == 1
        assert marks[0].mark_position == 11.0


class TestEdgeCasePathStructures:
    """Tests for edge case path structures.

    These tests document expected behavior for unusual path configurations:
    - Paths that start with a bend (no leading straight)
    - Paths that end with a bend (no trailing straight)
    - First/last straight too short for min_grip/min_tail
    """

    def test_short_first_straight_needs_extra_grip_material(self) -> None:
        """When first straight is shorter than min_grip, extra material is added.

        If first straight is 3" but min_grip is 6", we need 3" of extra material
        added at the start so the bender has enough to grip.
        """
        # First straight = 3" (too short for 6" min_grip)
        # Need: 6" grip - (3" - 0.5" offset) = 6" - 2.5" = 3.5" extra material
        straights = [make_straight(1, 3.0), make_straight(2, 10.0)]
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        # Simulating min_grip check: first_feed = 3.0 - 0.5 = 2.5
        # extra_material = max(0, 6.0 - 2.5) = 3.5
        extra_material = 3.5

        segments, marks = build_segments_and_marks(
            straights, bends, extra_material=extra_material, die_offset=0.5
        )

        # Extra material shifts all positions
        # Straight 1: 3.5 to 6.5 (length 3)
        # Bend 1: 6.5 to 11.5 (length 5)
        # Straight 2: 11.5 to 21.5 (length 10)
        assert segments[0].starts_at == 3.5
        assert segments[0].ends_at == 6.5

        # Mark position: bend_starts_at (6.5) - die_offset (0.5) = 6.0
        assert marks[0].mark_position == 6.0

    def test_short_last_straight_needs_tail_warning(self) -> None:
        """When last straight is shorter than min_tail, a warning should be shown.

        Currently the system validates and warns but doesn't add material.
        This documents the current expected behavior.
        """
        # This test documents current behavior:
        # - min_tail validation happens in bend_sheet_generator
        # - build_segments_and_marks just builds segments from what it's given
        straights = [make_straight(1, 10.0), make_straight(2, 2.0)]  # Last is short
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        segments, _marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.5
        )

        # Segments built normally - validation happens at higher level
        assert len(segments) == 3
        assert segments[2].length == 2.0  # Short last straight

    def test_zero_straights_produces_no_segments_but_marks(self) -> None:
        """Path with no straights produces no segments but still creates marks.

        Current behavior: build_segments_and_marks only creates segments
        for straights (with bends between them). With no straights, no
        segments are created, but marks are still generated for bends.

        Note: calculate_straights_and_bends raises ValueError if no lines,
        so this case is caught earlier in the pipeline.

        Future enhancement: Could add synthetic grip/tail sections when
        path starts/ends with bend.
        """
        straights: list[StraightSection] = []
        bends = [BendData(number=1, angle=45.0, rotation=None, arc_length=5.0)]

        segments, marks = build_segments_and_marks(
            straights, bends, extra_material=0.0, die_offset=0.0
        )

        # Current behavior: no straights = no segments
        # But marks are still created for bends (with mark_position = 0 - offset)
        assert len(segments) == 0
        assert len(marks) == 1  # Mark created but position is 0 (no bend found)


class TestDirectionAwareValidation:
    """Tests for direction-aware grip/tail validation.

    These tests verify the validation logic that checks if middle straights
    are long enough for the bender's min_grip requirement, and whether
    reversing direction would help.
    """

    def test_all_straights_long_enough_valid(self) -> None:
        """When all middle straights are >= min_grip, validation passes."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 8.0),
            make_straight(3, 10.0),
        ]

        result = validate_grip_for_direction(
            straights, min_grip=6.0, min_tail=4.0, reversed=False
        )

        assert result.is_valid is True
        assert result.violations == []

    def test_middle_straight_too_short_fails(self) -> None:
        """When a middle straight is shorter than min_grip, validation fails."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 3.0),  # Too short!
            make_straight(3, 10.0),
        ]

        result = validate_grip_for_direction(
            straights, min_grip=6.0, min_tail=4.0, reversed=False
        )

        assert result.is_valid is False
        assert 2 in result.violations

    def test_multiple_middle_straights_too_short(self) -> None:
        """Multiple middle straights can be too short."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 3.0),  # Too short!
            make_straight(3, 4.0),  # Also too short!
            make_straight(4, 10.0),
        ]

        result = validate_grip_for_direction(
            straights, min_grip=6.0, min_tail=4.0, reversed=False
        )

        assert result.is_valid is False
        assert 2 in result.violations
        assert 3 in result.violations

    def test_single_straight_always_valid(self) -> None:
        """Single straight path has no middle sections to validate."""
        straights = [make_straight(1, 3.0)]  # Even if short

        result = validate_grip_for_direction(
            straights, min_grip=6.0, min_tail=4.0, reversed=False
        )

        assert result.is_valid is True

    def test_two_straights_no_middle(self) -> None:
        """Two straights have no middle sections (first/last only)."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 10.0),
        ]

        result = validate_grip_for_direction(
            straights, min_grip=6.0, min_tail=4.0, reversed=False
        )

        assert result.is_valid is True

    def test_zero_min_grip_always_valid(self) -> None:
        """When min_grip is 0, all sections are valid."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 1.0),  # Very short but min_grip=0
            make_straight(3, 10.0),
        ]

        result = validate_grip_for_direction(
            straights, min_grip=0.0, min_tail=4.0, reversed=False
        )

        assert result.is_valid is True


class TestDirectionAwareValidationWithSuggestion:
    """Tests for the direction-aware validation that suggests reversing."""

    def test_current_direction_valid_no_suggestion(self) -> None:
        """When current direction is valid, no suggestion is given."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 8.0),
            make_straight(3, 10.0),
        ]

        result = validate_direction_aware(
            straights,
            min_grip=6.0,
            min_tail=4.0,
            current_direction="Back to Front",
            opposite_direction="Front to Back",
        )

        assert result.can_fabricate is True
        assert result.current_direction_valid is True
        assert result.suggestion == ""

    def test_neither_direction_works_error(self) -> None:
        """When neither direction works, error message explains this."""
        straights = [
            make_straight(1, 10.0),
            make_straight(2, 2.0),  # Too short in both directions
            make_straight(3, 10.0),
        ]

        result = validate_direction_aware(
            straights,
            min_grip=6.0,
            min_tail=4.0,
            current_direction="Back to Front",
            opposite_direction="Front to Back",
        )

        assert result.can_fabricate is False
        assert result.current_direction_valid is False
        assert result.reversed_direction_valid is False
        assert "cannot be fabricated in either direction" in result.error_message

    def test_empty_straights_valid(self) -> None:
        """Empty straights list is technically valid (no middle sections)."""
        straights: list[StraightSection] = []

        result = validate_direction_aware(
            straights,
            min_grip=6.0,
            min_tail=4.0,
            current_direction="Back to Front",
            opposite_direction="Front to Back",
        )

        assert result.can_fabricate is True
        assert result.current_direction_valid is True


class TestSyntheticGripTailFields:
    """Tests for BendSheetData synthetic grip/tail fields."""

    def test_bend_sheet_data_has_synthetic_fields(self) -> None:
        """BendSheetData has fields for synthetic grip/tail tracking."""
        from models import BendSheetData, UnitConfig

        # Create minimal BendSheetData
        units = UnitConfig(
            is_metric=False,
            unit_name="in",
            unit_symbol='"',
            cm_to_unit=1 / 2.54,
            default_tube_od="1.75",
            default_precision=16,
            valid_precisions=(0, 4, 8, 16, 32),
        )

        data = BendSheetData(
            component_name="Test",
            tube_od=1.5,
            clr=4.5,
            die_offset=0.5,
            precision=16,
            min_grip=6.0,
            travel_direction="Back to Front",
            starts_with_arc=True,
            ends_with_arc=True,
            clr_mismatch=False,
            clr_values=[4.5],
            continuity_errors=[],
            straights=[],
            bends=[],
            segments=[],
            mark_positions=[],
            extra_material=6.0,
            total_centerline=20.0,
            total_cut_length=30.0,
            units=units,
            has_synthetic_grip=True,
            has_synthetic_tail=True,
            grip_cut_position=6.0,
            tail_cut_position=26.0,
        )

        assert data.has_synthetic_grip is True
        assert data.has_synthetic_tail is True
        assert data.grip_cut_position == 6.0
        assert data.tail_cut_position == 26.0

    def test_bend_sheet_data_defaults_no_synthetic(self) -> None:
        """BendSheetData defaults to no synthetic material."""
        from models import BendSheetData, UnitConfig

        units = UnitConfig(
            is_metric=False,
            unit_name="in",
            unit_symbol='"',
            cm_to_unit=1 / 2.54,
            default_tube_od="1.75",
            default_precision=16,
            valid_precisions=(0, 4, 8, 16, 32),
        )

        data = BendSheetData(
            component_name="Test",
            tube_od=1.5,
            clr=4.5,
            die_offset=0.5,
            precision=16,
            min_grip=6.0,
            travel_direction="Back to Front",
            starts_with_arc=False,
            ends_with_arc=False,
            clr_mismatch=False,
            clr_values=[4.5],
            continuity_errors=[],
            straights=[],
            bends=[],
            segments=[],
            mark_positions=[],
            extra_material=0.0,
            total_centerline=20.0,
            total_cut_length=20.0,
            units=units,
        )

        assert data.has_synthetic_grip is False
        assert data.has_synthetic_tail is False
        assert data.grip_cut_position is None
        assert data.tail_cut_position is None
