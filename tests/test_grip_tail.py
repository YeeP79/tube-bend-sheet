"""
Tests for grip/tail material calculation module.

Run with: pytest tests/test_grip_tail.py -v
"""
from core.grip_tail import MaterialCalculation, calculate_material_requirements
from models import StraightSection


def make_straight(number: int, length: float) -> StraightSection:
    """Create a StraightSection with the given number and length."""
    return StraightSection(
        number=number,
        length=length,
        start=(0.0, 0.0, 0.0),
        end=(length, 0.0, 0.0),
        vector=(length, 0.0, 0.0),
    )


class TestMaterialCalculation:
    """Test MaterialCalculation dataclass."""

    def test_dataclass_creation(self) -> None:
        """Verify dataclass can be created with all fields."""
        result = MaterialCalculation(
            extra_material=2.0,
            synthetic_grip_material=1.5,
            synthetic_tail_material=1.0,
            has_synthetic_grip=True,
            has_synthetic_tail=True,
            grip_cut_position=1.5,
            grip_violations=[1, 2],
            tail_violation=True,
        )
        assert result.extra_material == 2.0
        assert result.synthetic_grip_material == 1.5
        assert result.synthetic_tail_material == 1.0
        assert result.has_synthetic_grip is True
        assert result.has_synthetic_tail is True
        assert result.grip_cut_position == 1.5
        assert result.grip_violations == [1, 2]
        assert result.tail_violation is True

    def test_default_values(self) -> None:
        """Verify default values for optional fields."""
        result = MaterialCalculation(
            extra_material=0.0,
            synthetic_grip_material=0.0,
            synthetic_tail_material=0.0,
            has_synthetic_grip=False,
            has_synthetic_tail=False,
            grip_cut_position=None,
        )
        assert result.grip_violations == []
        assert result.tail_violation is False


class TestCalculateMaterialRequirements:
    """Test calculate_material_requirements function."""

    # Happy path: Normal path (line-arc-line)
    def test_normal_path_no_synthetic_material(self) -> None:
        """Normal path (line-arc-line) needs no synthetic material."""
        straights = [make_straight(1, 10.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.has_synthetic_grip is False
        assert result.has_synthetic_tail is False
        assert result.synthetic_grip_material == 0.0
        assert result.synthetic_tail_material == 0.0

    def test_normal_path_first_straight_sufficient(self) -> None:
        """No extra material when first straight - offset >= min_grip."""
        straights = [make_straight(1, 10.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # First feed = 10.0 - 2.0 = 8.0, which is > min_grip (6.0)
        assert result.extra_material == 0.0

    def test_normal_path_first_straight_insufficient(self) -> None:
        """Extra material added when first straight - offset < min_grip."""
        straights = [make_straight(1, 6.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # First feed = 6.0 - 2.0 = 4.0, need 6.0 min_grip
        # Extra = 6.0 - 4.0 = 2.0
        assert result.extra_material == 2.0

    # Synthetic grip tests
    def test_synthetic_grip_when_starts_with_arc(self) -> None:
        """Path starting with arc gets synthetic grip material."""
        straights = [make_straight(1, 10.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=True,
            ends_with_arc=False,
        )
        assert result.has_synthetic_grip is True
        assert result.synthetic_grip_material == 6.0
        assert result.grip_cut_position == 6.0
        assert result.extra_material == 6.0

    def test_no_synthetic_grip_when_min_grip_zero(self) -> None:
        """No synthetic grip when min_grip is 0 even if starts with arc."""
        straights = [make_straight(1, 10.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=0.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=True,
            ends_with_arc=False,
        )
        assert result.has_synthetic_grip is False
        assert result.synthetic_grip_material == 0.0
        assert result.grip_cut_position is None

    # Synthetic tail tests
    def test_synthetic_tail_when_ends_with_arc(self) -> None:
        """Path ending with arc gets synthetic tail material."""
        straights = [make_straight(1, 10.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=True,
        )
        assert result.has_synthetic_tail is True
        assert result.synthetic_tail_material == 4.0

    def test_no_synthetic_tail_when_min_tail_zero(self) -> None:
        """No synthetic tail when min_tail is 0 even if ends with arc."""
        straights = [make_straight(1, 10.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=0.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=True,
        )
        assert result.has_synthetic_tail is False
        assert result.synthetic_tail_material == 0.0

    def test_both_synthetic_grip_and_tail(self) -> None:
        """Path with arc at both ends gets both synthetic materials."""
        straights = [make_straight(1, 10.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=True,
            ends_with_arc=True,
        )
        assert result.has_synthetic_grip is True
        assert result.has_synthetic_tail is True
        assert result.synthetic_grip_material == 6.0
        assert result.synthetic_tail_material == 4.0
        assert result.extra_material == 6.0

    # Grip violation tests
    def test_grip_violations_detected(self) -> None:
        """Straights shorter than min_grip are flagged (except last)."""
        straights = [
            make_straight(1, 4.0),  # Too short
            make_straight(2, 5.0),  # Too short
            make_straight(3, 8.0),  # OK (and last, so not checked)
        ]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.grip_violations == [1, 2]

    def test_no_grip_violations_all_sufficient(self) -> None:
        """No violations when all straights meet min_grip."""
        straights = [
            make_straight(1, 8.0),
            make_straight(2, 7.0),
            make_straight(3, 6.0),  # Last - not checked for grip
        ]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.grip_violations == []

    def test_no_grip_validation_when_min_grip_zero(self) -> None:
        """No violations when min_grip is 0."""
        straights = [make_straight(1, 2.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=0.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.grip_violations == []

    def test_single_straight_no_grip_violation_check(self) -> None:
        """Single straight doesn't get grip violation (only checked when > 1)."""
        straights = [make_straight(1, 2.0)]  # Short but it's the only one
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.grip_violations == []

    # Tail violation tests
    def test_tail_violation_detected(self) -> None:
        """Last straight shorter than min_tail is flagged."""
        straights = [make_straight(1, 8.0), make_straight(2, 3.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.tail_violation is True

    def test_no_tail_violation_sufficient(self) -> None:
        """No tail violation when last straight meets min_tail."""
        straights = [make_straight(1, 8.0), make_straight(2, 5.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.tail_violation is False

    def test_no_tail_validation_when_min_tail_zero(self) -> None:
        """No tail violation when min_tail is 0."""
        straights = [make_straight(1, 8.0), make_straight(2, 1.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=0.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.tail_violation is False

    # Boundary condition tests
    def test_straight_exactly_at_min_grip(self) -> None:
        """Straight exactly at min_grip is not a violation."""
        straights = [make_straight(1, 6.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.grip_violations == []

    def test_tail_exactly_at_min_tail(self) -> None:
        """Last straight exactly at min_tail is not a violation."""
        straights = [make_straight(1, 8.0), make_straight(2, 4.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.tail_violation is False

    def test_first_feed_exactly_at_min_grip(self) -> None:
        """No extra material when first feed exactly equals min_grip."""
        straights = [make_straight(1, 8.0), make_straight(2, 6.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # First feed = 8.0 - 2.0 = 6.0, exactly min_grip
        assert result.extra_material == 0.0

    # Edge cases
    def test_empty_straights_no_crash(self) -> None:
        """Function handles empty straights without crashing."""
        straights: list[StraightSection] = []
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # Empty straights should not cause violations
        assert result.grip_violations == []
        assert result.tail_violation is False
        assert result.extra_material == 0.0

    def test_zero_die_offset(self) -> None:
        """Zero die offset is handled correctly."""
        straights = [make_straight(1, 4.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # First feed = 4.0 - 0.0 = 4.0, need 6.0 min_grip
        # Extra = 6.0 - 4.0 = 2.0
        assert result.extra_material == 2.0

    def test_synthetic_grip_takes_precedence_over_regular_extra(self) -> None:
        """When both synthetic grip and regular extra material needed, synthetic wins."""
        straights = [make_straight(1, 4.0)]  # Short first straight
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=True,  # Also starts with arc
            ends_with_arc=False,
        )
        # Regular extra would be: 6.0 - (4.0 - 2.0) = 4.0
        # Synthetic is: 6.0
        # Synthetic takes precedence
        assert result.extra_material == 6.0
        assert result.has_synthetic_grip is True

    def test_all_parameters_zero(self) -> None:
        """All zero parameters produce clean result."""
        straights = [make_straight(1, 5.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=0.0,
            min_tail=0.0,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.extra_material == 0.0
        assert result.synthetic_grip_material == 0.0
        assert result.synthetic_tail_material == 0.0
        assert result.has_synthetic_grip is False
        assert result.has_synthetic_tail is False
        assert result.grip_violations == []
        assert result.tail_violation is False


class TestAllowanceAffectsViolations:
    """Test that start/end allowances are factored into grip/tail violation checks."""

    def test_start_allowance_prevents_grip_violation_on_first_straight(self) -> None:
        """First straight + start_allowance >= min_grip means no violation."""
        straights = [
            StraightSection(1, 3.25, (0, 0, 0), (3.25, 0, 0), (3.25, 0, 0)),
            StraightSection(2, 4.0, (3.25, 0, 0), (7.25, 0, 0), (4.0, 0, 0)),
        ]
        # 3.25 < 3.75 normally, but 3.25 + 0.5 = 3.75 >= 3.75
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=0.0,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
        )
        assert 1 not in result.grip_violations

    def test_end_allowance_prevents_tail_violation(self) -> None:
        """Last straight + end_allowance >= min_tail means no violation."""
        straights = [
            StraightSection(1, 4.0, (0, 0, 0), (4.0, 0, 0), (4.0, 0, 0)),
            StraightSection(2, 3.0, (4.0, 0, 0), (7.0, 0, 0), (3.0, 0, 0)),
        ]
        # 3.0 < 3.5 normally, but 3.0 + 0.5 = 3.5 >= 3.5
        result = calculate_material_requirements(
            straights=straights,
            min_grip=0.0,
            min_tail=3.5,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
            end_allowance=0.5,
        )
        assert result.tail_violation is False

    def test_allowance_still_shows_violation_if_not_enough(self) -> None:
        """Even with allowance, violation shown if still not enough."""
        straights = [
            StraightSection(1, 3.0, (0, 0, 0), (3.0, 0, 0), (3.0, 0, 0)),
            StraightSection(2, 4.0, (3.0, 0, 0), (7.0, 0, 0), (4.0, 0, 0)),
        ]
        # 3.0 + 0.5 = 3.5 < 4.0 min_grip
        result = calculate_material_requirements(
            straights=straights,
            min_grip=4.0,
            min_tail=0.0,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
        )
        assert 1 in result.grip_violations

    def test_allowance_only_affects_first_and_last_straights(self) -> None:
        """Middle straights don't get allowance benefit."""
        straights = [
            StraightSection(1, 4.0, (0, 0, 0), (4.0, 0, 0), (4.0, 0, 0)),
            StraightSection(2, 3.0, (4.0, 0, 0), (7.0, 0, 0), (3.0, 0, 0)),
            StraightSection(3, 4.0, (7.0, 0, 0), (11.0, 0, 0), (4.0, 0, 0)),
        ]
        # Middle straight (2) is 3.0 < 3.5 min_grip, no allowance help
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.5,
            min_tail=0.0,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
        )
        assert 2 in result.grip_violations

    def test_zero_allowance_no_change_in_behavior(self) -> None:
        """Zero allowance gives same result as before."""
        straights = [
            StraightSection(1, 3.25, (0, 0, 0), (3.25, 0, 0), (3.25, 0, 0)),
            StraightSection(2, 4.0, (3.25, 0, 0), (7.25, 0, 0), (4.0, 0, 0)),
        ]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=0.0,
            die_offset=0.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.0,
            end_allowance=0.0,
        )
        # 3.25 < 3.75, should have violation
        assert 1 in result.grip_violations


class TestExtraTailMaterial:
    """Test extra_tail_material calculation when last straight < min_tail.

    This is the key bug fix: when the path ends with a straight (not an arc)
    and that straight is shorter than min_tail, we need to add extra material
    that will be cut off after bending.
    """

    def test_extra_tail_material_when_last_straight_insufficient(self) -> None:
        """Extra tail material added when last straight < min_tail."""
        # Simulates the user's example: last straight = 3.875", min_tail = 6.5"
        straights = [make_straight(1, 8.0), make_straight(2, 3.875)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=6.5,
            die_offset=0.6875,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # Need 6.5 - 3.875 = 2.625 extra tail material
        assert result.extra_tail_material == 2.625
        assert result.has_tail_extension is True

    def test_no_extra_tail_material_when_last_straight_sufficient(self) -> None:
        """No extra tail material when last straight >= min_tail."""
        straights = [make_straight(1, 8.0), make_straight(2, 7.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=6.5,
            die_offset=0.6875,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.extra_tail_material == 0.0
        assert result.has_tail_extension is False

    def test_no_extra_tail_material_when_exactly_at_min_tail(self) -> None:
        """No extra tail material when last straight exactly equals min_tail."""
        straights = [make_straight(1, 8.0), make_straight(2, 6.5)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=6.5,
            die_offset=0.6875,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.extra_tail_material == 0.0
        assert result.has_tail_extension is False

    def test_no_extra_tail_material_when_ends_with_arc(self) -> None:
        """No extra tail material when path ends with arc (uses synthetic instead)."""
        straights = [make_straight(1, 8.0), make_straight(2, 3.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=6.5,
            die_offset=0.6875,
            starts_with_arc=False,
            ends_with_arc=True,  # Path ends with arc
        )
        # Should use synthetic_tail_material, not extra_tail_material
        assert result.extra_tail_material == 0.0
        assert result.has_tail_extension is False
        assert result.synthetic_tail_material == 6.5
        assert result.has_synthetic_tail is True

    def test_no_extra_tail_material_when_min_tail_zero(self) -> None:
        """No extra tail material when min_tail is 0."""
        straights = [make_straight(1, 8.0), make_straight(2, 2.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=0.0,
            die_offset=0.6875,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        assert result.extra_tail_material == 0.0
        assert result.has_tail_extension is False

    def test_extra_tail_material_single_straight(self) -> None:
        """Extra tail material works with single straight section."""
        straights = [make_straight(1, 5.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.0,
            min_tail=6.0,
            die_offset=1.0,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # 5.0 < 6.0, need 1.0 extra
        assert result.extra_tail_material == 1.0
        assert result.has_tail_extension is True

    def test_tail_cut_position_calculated(self) -> None:
        """tail_cut_position is set when extra tail material is added."""
        straights = [make_straight(1, 8.0), make_straight(2, 4.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=3.75,
            min_tail=6.5,
            die_offset=0.6875,
            starts_with_arc=False,
            ends_with_arc=False,
        )
        # extra_tail_material = 6.5 - 4.0 = 2.5
        assert result.extra_tail_material == 2.5
        # tail_cut_position should indicate where to cut (centerline length)
        # Total centerline = 8.0 + 4.0 = 12.0
        # tail_cut_position = centerline length (cut happens at end of original tube)
        assert result.tail_cut_position is not None


class TestAllowanceWithExtensions:
    """Test allowance behavior when grip/tail extensions are added.

    The default behavior should be to skip allowance when extensions are added,
    since there's already extra material to cut off. Users can opt-in to add
    allowance anyway via parameters.
    """

    def test_effective_start_allowance_zero_when_grip_extended(self) -> None:
        """By default, start allowance is 0 when grip extension is added."""
        straights = [make_straight(1, 4.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,  # first_feed = 4.0 - 2.0 = 2.0, needs 4.0 extra
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
        )
        # extra_material = 4.0 (grip extension)
        assert result.extra_material == 4.0
        # effective_start_allowance should be 0 since grip was extended
        assert result.effective_start_allowance == 0.0

    def test_effective_end_allowance_zero_when_tail_extended(self) -> None:
        """By default, end allowance is 0 when tail extension is added."""
        straights = [make_straight(1, 10.0), make_straight(2, 4.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=6.5,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
        )
        # extra_tail_material = 6.5 - 4.0 = 2.5
        assert result.extra_tail_material == 2.5
        # effective_end_allowance should be 0 since tail was extended
        assert result.effective_end_allowance == 0.0

    def test_allowance_added_when_no_extension_needed(self) -> None:
        """Allowance is added when no grip/tail extension is needed."""
        straights = [make_straight(1, 10.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=6.0,
            die_offset=2.0,  # first_feed = 10.0 - 2.0 = 8.0 >= 6.0, no extension
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
        )
        # No extensions needed
        assert result.extra_material == 0.0
        assert result.extra_tail_material == 0.0
        # Allowances should be applied
        assert result.effective_start_allowance == 0.5
        assert result.effective_end_allowance == 0.5

    def test_start_allowance_with_grip_extension_when_opted_in(self) -> None:
        """Start allowance added with grip extension when add_allowance_with_grip_extension=True."""
        straights = [make_straight(1, 4.0), make_straight(2, 8.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=4.0,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
            add_allowance_with_grip_extension=True,
        )
        assert result.extra_material == 4.0  # Grip extension still added
        assert result.effective_start_allowance == 0.5  # Allowance also added

    def test_end_allowance_with_tail_extension_when_opted_in(self) -> None:
        """End allowance added with tail extension when add_allowance_with_tail_extension=True."""
        straights = [make_straight(1, 10.0), make_straight(2, 4.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=6.5,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
            add_allowance_with_tail_extension=True,
        )
        assert result.extra_tail_material == 2.5  # Tail extension still added
        assert result.effective_end_allowance == 0.5  # Allowance also added

    def test_both_allowances_with_both_extensions_when_opted_in(self) -> None:
        """Both allowances added with both extensions when both flags are True."""
        straights = [make_straight(1, 4.0), make_straight(2, 4.0)]
        result = calculate_material_requirements(
            straights=straights,
            min_grip=6.0,
            min_tail=6.5,
            die_offset=2.0,
            starts_with_arc=False,
            ends_with_arc=False,
            start_allowance=0.5,
            end_allowance=0.5,
            add_allowance_with_grip_extension=True,
            add_allowance_with_tail_extension=True,
        )
        assert result.extra_material == 4.0
        assert result.extra_tail_material == 2.5
        assert result.effective_start_allowance == 0.5
        assert result.effective_end_allowance == 0.5
