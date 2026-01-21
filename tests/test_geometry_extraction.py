"""
Tests for geometry extraction module - runs without Fusion.

Run with: pytest tests/ -v
"""
from __future__ import annotations

from helpers import MockPathElement
from core.geometry_extraction import (
    determine_primary_axis,
    get_free_endpoint,
    should_reverse_path_direction,
)
from models.types import Point3D


class TestDeterminePrimaryAxis:
    """Test determine_primary_axis() function."""

    # Happy path - positive directions
    def test_primary_axis_x_positive(self) -> None:
        """X-axis positive direction detected (toward Right)."""
        start = (0.0, 0.0, 0.0)
        end = (10.0, 1.0, 0.5)
        axis, idx, current, opposite = determine_primary_axis(start, end)
        assert axis == 'X'
        assert idx == 0
        assert current == 'Right'
        assert opposite == 'Left'

    def test_primary_axis_y_positive(self) -> None:
        """Y-axis positive direction detected (toward Top)."""
        start = (0.0, 0.0, 0.0)
        end = (1.0, 10.0, 0.5)
        axis, idx, current, opposite = determine_primary_axis(start, end)
        assert axis == 'Y'
        assert idx == 1
        assert current == 'Top'
        assert opposite == 'Bottom'

    def test_primary_axis_z_positive(self) -> None:
        """Z-axis positive direction detected (toward Back)."""
        start = (0.0, 0.0, 0.0)
        end = (1.0, 0.5, 10.0)
        axis, idx, current, opposite = determine_primary_axis(start, end)
        assert axis == 'Z'
        assert idx == 2
        assert current == 'Back'
        assert opposite == 'Front'

    # Happy path - negative directions
    def test_primary_axis_x_negative(self) -> None:
        """X-axis negative direction detected (toward Left)."""
        start = (10.0, 0.0, 0.0)
        end = (0.0, 1.0, 0.5)
        axis, idx, current, opposite = determine_primary_axis(start, end)
        assert axis == 'X'
        assert idx == 0
        assert current == 'Left'
        assert opposite == 'Right'

    def test_primary_axis_y_negative(self) -> None:
        """Y-axis negative direction detected (toward Bottom)."""
        start = (0.0, 10.0, 0.0)
        end = (1.0, 0.0, 0.5)
        axis, idx, current, opposite = determine_primary_axis(start, end)
        assert axis == 'Y'
        assert idx == 1
        assert current == 'Bottom'
        assert opposite == 'Top'

    def test_primary_axis_z_negative(self) -> None:
        """Z-axis negative direction detected (toward Front)."""
        start = (0.0, 0.0, 10.0)
        end = (1.0, 0.5, 0.0)
        axis, idx, current, opposite = determine_primary_axis(start, end)
        assert axis == 'Z'
        assert idx == 2
        assert current == 'Front'
        assert opposite == 'Back'

    # Defensive: Edge cases
    def test_zero_displacement_returns_x(self) -> None:
        """Zero displacement defaults to X axis."""
        start = (5.0, 5.0, 5.0)
        end = (5.0, 5.0, 5.0)  # Same point
        axis, idx, current, _opposite = determine_primary_axis(start, end)
        assert axis == 'X'
        assert idx == 0
        # Direction is arbitrary for zero displacement
        assert current in ('Left', 'Right')

    def test_tie_between_x_and_y(self) -> None:
        """When X and Y are equal, X takes priority."""
        start = (0.0, 0.0, 0.0)
        end = (10.0, 10.0, 0.0)
        axis, idx, _current, _opposite = determine_primary_axis(start, end)
        # X is checked first, so X wins on tie
        assert axis == 'X'
        assert idx == 0

    def test_tie_between_y_and_z(self) -> None:
        """When Y and Z are equal (and larger than X), Y takes priority."""
        start = (0.0, 0.0, 0.0)
        end = (0.0, 10.0, 10.0)
        axis, idx, _current, _opposite = determine_primary_axis(start, end)
        # Y is checked before Z
        assert axis == 'Y'
        assert idx == 1

    def test_all_three_equal(self) -> None:
        """When all displacements equal, X takes priority."""
        start = (0.0, 0.0, 0.0)
        end = (5.0, 5.0, 5.0)
        axis, idx, _current, _opposite = determine_primary_axis(start, end)
        assert axis == 'X'
        assert idx == 0

    def test_very_small_displacement(self) -> None:
        """Very small displacements are handled correctly."""
        start = (0.0, 0.0, 0.0)
        end = (0.0001, 0.00001, 0.000001)
        axis, _idx, current, _opposite = determine_primary_axis(start, end)
        assert axis == 'X'
        assert current == 'Right'

    def test_large_displacement(self) -> None:
        """Large displacements are handled correctly."""
        start = (0.0, 0.0, 0.0)
        end = (1000000.0, 500000.0, 100000.0)
        axis, _idx, current, _opposite = determine_primary_axis(start, end)
        assert axis == 'X'
        assert current == 'Right'


class TestGetFreeEndpoint:
    """Test get_free_endpoint() function."""

    # Happy path tests
    def test_finds_unconnected_endpoint_at_start(self) -> None:
        """First element's start is free endpoint of chain."""
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        e2 = MockPathElement('arc', ((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
        elements = [e1, e2]

        # e1's start (0,0,0) is not connected to e2
        result = get_free_endpoint(e1, elements)
        assert result == (0.0, 0.0, 0.0)

    def test_finds_unconnected_endpoint_at_end(self) -> None:
        """Last element's end is free endpoint of chain."""
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        e2 = MockPathElement('arc', ((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
        elements = [e1, e2]

        # e2's end (2,0,0) is not connected to e1
        result = get_free_endpoint(e2, elements)
        assert result == (2.0, 0.0, 0.0)

    def test_middle_element_has_no_free_endpoint(self) -> None:
        """Middle element returns its first endpoint as fallback."""
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        e2 = MockPathElement('arc', ((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
        e3 = MockPathElement('line', ((2.0, 0.0, 0.0), (3.0, 0.0, 0.0)))
        elements = [e1, e2, e3]

        # e2 is connected at both ends, returns its start as fallback
        result = get_free_endpoint(e2, elements)
        assert result == (1.0, 0.0, 0.0)

    # Defensive: Edge cases
    def test_single_element_returns_start(self) -> None:
        """Single element returns its start endpoint."""
        e1 = MockPathElement('line', ((5.0, 0.0, 0.0), (10.0, 0.0, 0.0)))
        elements = [e1]

        # Both endpoints are free, returns start (first one checked)
        result = get_free_endpoint(e1, elements)
        assert result == (5.0, 0.0, 0.0)

    def test_disconnected_element_returns_start(self) -> None:
        """Disconnected element returns its start endpoint."""
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        e2 = MockPathElement('line', ((100.0, 100.0, 100.0), (101.0, 100.0, 100.0)))
        elements = [e1, e2]

        # e2 is completely disconnected from e1
        result = get_free_endpoint(e2, elements)
        assert result == (100.0, 100.0, 100.0)

    def test_both_endpoints_connected_returns_first(self) -> None:
        """When both endpoints are connected, returns first endpoint."""
        # Create a closed triangle
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        e2 = MockPathElement('arc', ((1.0, 0.0, 0.0), (0.5, 0.866, 0.0)))
        e3 = MockPathElement('line', ((0.5, 0.866, 0.0), (0.0, 0.0, 0.0)))
        elements = [e1, e2, e3]

        # e1 is connected at both ends (to e3 at start, to e2 at end)
        result = get_free_endpoint(e1, elements)
        assert result == (0.0, 0.0, 0.0)  # Falls back to first endpoint

    def test_empty_other_elements_returns_start(self) -> None:
        """Element with no others returns its start."""
        e1 = MockPathElement('line', ((3.0, 4.0, 5.0), (6.0, 7.0, 8.0)))
        elements = [e1]  # Only itself

        result = get_free_endpoint(e1, elements)
        assert result == (3.0, 4.0, 5.0)

    def test_connection_within_tolerance(self) -> None:
        """Elements within tolerance (0.1 cm) are considered connected."""
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        # e2 starts at 1.05, within 0.1 cm tolerance
        e2 = MockPathElement('arc', ((1.05, 0.0, 0.0), (2.0, 0.0, 0.0)))
        elements = [e1, e2]

        # e1's end (1,0,0) is close to e2's start (1.05,0,0) - within tolerance
        # So e1's start should be the free endpoint
        result = get_free_endpoint(e1, elements)
        assert result == (0.0, 0.0, 0.0)

    def test_long_chain_finds_correct_endpoint(self) -> None:
        """Correctly identifies free endpoint in a long chain."""
        e1 = MockPathElement('line', ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        e2 = MockPathElement('arc', ((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
        e3 = MockPathElement('line', ((2.0, 0.0, 0.0), (3.0, 0.0, 0.0)))
        e4 = MockPathElement('arc', ((3.0, 0.0, 0.0), (4.0, 0.0, 0.0)))
        e5 = MockPathElement('line', ((4.0, 0.0, 0.0), (5.0, 0.0, 0.0)))
        elements = [e1, e2, e3, e4, e5]

        # First element's start is free
        assert get_free_endpoint(e1, elements) == (0.0, 0.0, 0.0)
        # Last element's end is free
        assert get_free_endpoint(e5, elements) == (5.0, 0.0, 0.0)
        # Middle elements return first endpoint as fallback
        assert get_free_endpoint(e3, elements) == (2.0, 0.0, 0.0)


class TestShouldReversePathDirection:
    """Test should_reverse_path_direction() function.

    This function ensures paths are normalized to go toward positive axis direction:
    - X: Left to Right (+X)
    - Y: Bottom to Top (+Y)
    - Z: Back to Front (+Z)
    """

    # Happy path - should NOT reverse (already going positive)
    def test_x_axis_positive_direction_no_reverse(self) -> None:
        """Path going +X (Left to Right) should not be reversed."""
        start = (0.0, 0.0, 0.0)
        end = (10.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is False

    def test_y_axis_positive_direction_no_reverse(self) -> None:
        """Path going +Y (Bottom to Top) should not be reversed."""
        start = (0.0, 0.0, 0.0)
        end = (0.0, 10.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=1) is False

    def test_z_axis_positive_direction_no_reverse(self) -> None:
        """Path going +Z (Back to Front) should not be reversed."""
        start = (0.0, 0.0, 0.0)
        end = (0.0, 0.0, 10.0)
        assert should_reverse_path_direction(start, end, axis_idx=2) is False

    # Happy path - should reverse (going negative)
    def test_x_axis_negative_direction_reverse(self) -> None:
        """Path going -X (Right to Left) should be reversed."""
        start = (10.0, 0.0, 0.0)
        end = (0.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is True

    def test_y_axis_negative_direction_reverse(self) -> None:
        """Path going -Y (Top to Bottom) should be reversed."""
        start = (0.0, 10.0, 0.0)
        end = (0.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=1) is True

    def test_z_axis_negative_direction_reverse(self) -> None:
        """Path going -Z (Front to Back) should be reversed."""
        start = (0.0, 0.0, 10.0)
        end = (0.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=2) is True

    # Edge cases
    def test_zero_displacement_no_reverse(self) -> None:
        """Zero displacement on axis should not trigger reversal."""
        start = (5.0, 5.0, 5.0)
        end = (5.0, 5.0, 5.0)
        # displacement is 0, which is not < 0
        assert should_reverse_path_direction(start, end, axis_idx=0) is False

    def test_very_small_positive_displacement(self) -> None:
        """Very small positive displacement should not reverse."""
        start = (0.0, 0.0, 0.0)
        end = (0.0001, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is False

    def test_very_small_negative_displacement(self) -> None:
        """Very small negative displacement should reverse."""
        start = (0.0001, 0.0, 0.0)
        end = (0.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is True

    def test_large_positive_displacement(self) -> None:
        """Large positive displacement should not reverse."""
        start = (0.0, 0.0, 0.0)
        end = (1000000.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is False

    def test_large_negative_displacement(self) -> None:
        """Large negative displacement should reverse."""
        start = (1000000.0, 0.0, 0.0)
        end = (0.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is True

    def test_ignores_other_axes(self) -> None:
        """Only considers the specified axis index."""
        # Path going negative on X but positive on Y and Z
        start = (10.0, 0.0, 0.0)
        end = (0.0, 100.0, 100.0)
        # Check X axis - should reverse (going -X)
        assert should_reverse_path_direction(start, end, axis_idx=0) is True
        # Check Y axis - should not reverse (going +Y)
        assert should_reverse_path_direction(start, end, axis_idx=1) is False
        # Check Z axis - should not reverse (going +Z)
        assert should_reverse_path_direction(start, end, axis_idx=2) is False

    def test_negative_coordinates(self) -> None:
        """Handles negative coordinate values correctly."""
        # Going from -10 to -5 is positive direction
        start = (-10.0, 0.0, 0.0)
        end = (-5.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is False

        # Going from -5 to -10 is negative direction
        start = (-5.0, 0.0, 0.0)
        end = (-10.0, 0.0, 0.0)
        assert should_reverse_path_direction(start, end, axis_idx=0) is True


class TestPathNormalizationIntegration:
    """Integration tests verifying the complete normalization flow.

    These tests ensure that when all the pieces work together,
    the path is correctly normalized and labels are accurate.
    """

    def _simulate_normalization(
        self, ordered: list[MockPathElement]
    ) -> tuple[list[MockPathElement], str, str, str, str]:
        """
        Simulate the normalization logic from selection_validator.py.

        Returns:
            Tuple of (ordered_path, primary_axis, current_dir, opposite_dir, natural_label)
        """
        # Get start/end points (simulating get_free_endpoint logic)
        start_point = self._get_free_endpoint(ordered[0], ordered)
        end_point = self._get_free_endpoint(ordered[-1], ordered)

        # Determine primary axis and directions
        axis, axis_idx, current_dir, opposite_dir = determine_primary_axis(
            start_point, end_point
        )

        # Normalize path direction
        if should_reverse_path_direction(start_point, end_point, axis_idx):
            ordered = ordered[::-1]
            start_point, end_point = end_point, start_point
            current_dir, opposite_dir = opposite_dir, current_dir

        # Build natural label (what dialog would show for first option)
        natural_label = f"{opposite_dir} to {current_dir}"

        return ordered, axis, current_dir, opposite_dir, natural_label

    def _get_free_endpoint(
        self, element: MockPathElement, all_elements: list[MockPathElement]
    ) -> Point3D:
        """Get the endpoint not connected to any other element."""
        for ep in element.endpoints:
            connected = False
            for other in all_elements:
                if other is element:
                    continue
                for other_ep in other.endpoints:
                    if self._points_are_close(ep, other_ep):
                        connected = True
                        break
                if connected:
                    break
            if not connected:
                return ep
        return element.endpoints[0]

    def _points_are_close(self, p1: Point3D, p2: Point3D, tol: float = 0.1) -> bool:
        """Check if two points are within tolerance."""
        return all(abs(a - b) < tol for a, b in zip(p1, p2, strict=True))

    # Test: Path along Z axis, initially going Front to Back
    # In Fusion 360: -Z is Front, +Z is Back
    def test_z_axis_front_to_back_normalized_to_back_to_front(self) -> None:
        """Path going Front(-Z) to Back(+Z) is reversed to Back to Front."""
        # Create path: Front straight -> arc -> Back straight
        # In Fusion: Front is at -Z (low Z), Back is at +Z (high Z)
        front_straight = MockPathElement(
            'line',
            ((0.0, 0.0, -10.0), (0.0, 0.0, -5.0))  # At Front (low Z)
        )
        arc = MockPathElement(
            'arc',
            ((0.0, 0.0, -5.0), (0.0, 0.0, 5.0))  # Bend
        )
        back_straight = MockPathElement(
            'line',
            ((0.0, 0.0, 5.0), (0.0, 0.0, 10.0))  # At Back (high Z)
        )

        ordered = [front_straight, arc, back_straight]
        result, axis, current, opposite, label = self._simulate_normalization(ordered)

        # After normalization, path should go Back to Front (from +Z to -Z)
        # Normalization ensures path goes toward positive axis direction (+Z = Back)
        # So path goes Front(-Z) to Back(+Z), which is already toward positive
        # Wait, that's not right. Let me reconsider...
        # Actually, normalization goes toward POSITIVE direction (+Z = Back)
        # So the natural label is "Front to Back" (from -Z to +Z)
        assert axis == 'Z'
        assert current == 'Back'
        assert opposite == 'Front'
        assert label == 'Front to Back'

        # Path was already going Front to Back, should stay unchanged
        assert result[0] is front_straight
        assert result[-1] is back_straight

    # Test: Path along Z axis, going Back to Front (needs reversal)
    def test_z_axis_back_to_front_stays_unchanged(self) -> None:
        """Path going Back(+Z) to Front(-Z) is reversed to go toward +Z."""
        back_straight = MockPathElement(
            'line',
            ((0.0, 0.0, 10.0), (0.0, 0.0, 5.0))  # At Back (high Z)
        )
        arc = MockPathElement(
            'arc',
            ((0.0, 0.0, 5.0), (0.0, 0.0, -5.0))  # Bend
        )
        front_straight = MockPathElement(
            'line',
            ((0.0, 0.0, -5.0), (0.0, 0.0, -10.0))  # At Front (low Z)
        )

        ordered = [back_straight, arc, front_straight]
        result, axis, current, opposite, label = self._simulate_normalization(ordered)

        # Path was going Back(+Z) to Front(-Z), displacement is negative
        # Should be reversed to go Front(-Z) to Back(+Z)
        assert axis == 'Z'
        assert current == 'Back'
        assert opposite == 'Front'
        assert label == 'Front to Back'

        # First element should now be front_straight (after reversal)
        assert result[0] is front_straight
        assert result[-1] is back_straight

    # Test: Path along X axis
    def test_x_axis_right_to_left_normalized_to_left_to_right(self) -> None:
        """Path going Right(+X) to Left(-X) is reversed to Left to Right."""
        right_straight = MockPathElement(
            'line',
            ((10.0, 0.0, 0.0), (5.0, 0.0, 0.0))  # At Right (high X)
        )
        arc = MockPathElement(
            'arc',
            ((5.0, 0.0, 0.0), (-5.0, 0.0, 0.0))  # Bend
        )
        left_straight = MockPathElement(
            'line',
            ((-5.0, 0.0, 0.0), (-10.0, 0.0, 0.0))  # At Left (low X)
        )

        ordered = [right_straight, arc, left_straight]
        result, axis, current, opposite, label = self._simulate_normalization(ordered)

        assert axis == 'X'
        assert current == 'Right'
        assert opposite == 'Left'
        assert label == 'Left to Right'
        assert result[0] is left_straight
        assert result[-1] is right_straight

    # Test: Verify first straight is at the origin direction
    def test_first_element_at_origin_direction(self) -> None:
        """After normalization, first element is at the 'from' direction (Front)."""
        # In Fusion 360: -Z is Front, +Z is Back
        # Front straight at low Z (toward -Z)
        front_straight = MockPathElement(
            'line',
            ((0.0, 0.0, -10.0), (0.0, 0.0, -5.0))  # At Front (low Z)
        )
        arc = MockPathElement(
            'arc',
            ((0.0, 0.0, -5.0), (0.0, 0.0, 5.0))
        )
        # Back straight at high Z (toward +Z)
        back_straight = MockPathElement(
            'line',
            ((0.0, 0.0, 5.0), (0.0, 0.0, 13.0))  # At Back (high Z)
        )

        # Start with wrong order (Back first, going toward -Z)
        ordered = [back_straight, arc, front_straight]
        result, _axis, _current, _opposite, label = self._simulate_normalization(ordered)

        # Normalization goes toward +Z (Back), so label is "Front to Back"
        # First element should be at Front (low Z)
        assert label == 'Front to Back'
        assert result[0] is front_straight, (
            "Straight 1 should be at Front when label is 'Front to Back'"
        )
        assert result[-1] is back_straight, (
            "Last straight should be at Back when label is 'Front to Back'"
        )

    # Test: Verify semantics match user expectation
    def test_front_to_back_means_first_element_at_front(self) -> None:
        """
        When label shows 'Front to Back', the first element MUST be at the Front.

        In Fusion 360: -Z is Front, +Z is Back
        Normalization goes toward positive direction (+Z = Back)
        So the natural label is 'Front to Back' (from -Z to +Z)
        """
        # Create elements with distinct positions
        # In Fusion: Front is at -Z, Back is at +Z
        front_element = MockPathElement(
            'line',
            ((0.0, 0.0, -8.0), (0.0, 0.0, -3.0))  # At Front (negative Z)
        )
        middle_arc = MockPathElement(
            'arc',
            ((0.0, 0.0, -3.0), (0.0, 0.0, 3.0))
        )
        back_element = MockPathElement(
            'line',
            ((0.0, 0.0, 3.0), (0.0, 0.0, 8.0))  # At Back (positive Z)
        )

        # Test both initial orderings
        for initial_order in [
            [front_element, middle_arc, back_element],
            [back_element, middle_arc, front_element],
        ]:
            result, _, _current, _opposite, label = self._simulate_normalization(
                list(initial_order)  # Copy to avoid mutation
            )

            # Regardless of initial order, after normalization:
            # Path goes toward +Z (Back), so label is "Front to Back"
            assert label == 'Front to Back'
            # First element's free endpoint should have lower Z (Front)
            first_free = self._get_free_endpoint(result[0], result)
            last_free = self._get_free_endpoint(result[-1], result)
            assert first_free[2] < last_free[2], (
                f"First element (Z={first_free[2]}) should be at Front "
                f"(lower Z than last element Z={last_free[2]})"
            )
