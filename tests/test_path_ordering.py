"""
Tests for path ordering module - runs without Fusion.

These tests use mock PathElement objects that don't require Fusion API.
"""
from __future__ import annotations

import pytest

from helpers import MockPathElement
from core.path_ordering import (
    build_ordered_path,
    elements_are_connected,
    validate_path_alternation,
)


# Test fixtures for common path patterns
@pytest.fixture
def line_element() -> MockPathElement:
    """A line element from (0,0,0) to (1,0,0)."""
    return MockPathElement(
        element_type='line',
        endpoints=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    )


@pytest.fixture
def arc_element() -> MockPathElement:
    """An arc element from (1,0,0) to (2,0,0)."""
    return MockPathElement(
        element_type='arc',
        endpoints=((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
    )


@pytest.fixture
def line_element_2() -> MockPathElement:
    """A second line element from (2,0,0) to (3,0,0)."""
    return MockPathElement(
        element_type='line',
        endpoints=((2.0, 0.0, 0.0), (3.0, 0.0, 0.0)),
    )


@pytest.fixture
def disconnected_element() -> MockPathElement:
    """An element not connected to others."""
    return MockPathElement(
        element_type='line',
        endpoints=((100.0, 100.0, 100.0), (101.0, 100.0, 100.0)),
    )


class TestElementsAreConnected:
    """Test elements_are_connected() function."""

    def test_connected_at_end_to_start(
        self, line_element: MockPathElement, arc_element: MockPathElement
    ) -> None:
        """Elements connected: line end matches arc start."""
        # line ends at (1,0,0), arc starts at (1,0,0)
        assert elements_are_connected(line_element, arc_element) is True

    def test_connected_at_start_to_end(
        self, line_element: MockPathElement, arc_element: MockPathElement
    ) -> None:
        """Reverse order should also be connected."""
        assert elements_are_connected(arc_element, line_element) is True

    def test_not_connected(
        self, line_element: MockPathElement, disconnected_element: MockPathElement
    ) -> None:
        """Elements with no shared endpoints are not connected."""
        assert elements_are_connected(line_element, disconnected_element) is False

    def test_same_element_connected(self, line_element: MockPathElement) -> None:
        """Element is connected to itself (shares endpoints with itself)."""
        assert elements_are_connected(line_element, line_element) is True

    def test_within_tolerance(self) -> None:
        """Elements within point tolerance (0.1 cm) are connected."""
        e1 = MockPathElement(
            element_type='line',
            endpoints=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        )
        e2 = MockPathElement(
            element_type='arc',
            endpoints=((1.05, 0.0, 0.0), (2.0, 0.0, 0.0)),  # 0.05 cm off, within 0.1 tolerance
        )
        assert elements_are_connected(e1, e2) is True

    def test_outside_tolerance(self) -> None:
        """Elements outside tolerance (0.1 cm) are not connected."""
        e1 = MockPathElement(
            element_type='line',
            endpoints=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        )
        e2 = MockPathElement(
            element_type='arc',
            endpoints=((1.2, 0.0, 0.0), (2.0, 0.0, 0.0)),  # 0.2 cm off, > 0.1 tolerance
        )
        assert elements_are_connected(e1, e2) is False


class TestValidatePathAlternation:
    """Test validate_path_alternation() function."""

    # Happy path tests
    def test_valid_line_arc_line_pattern(self) -> None:
        """Valid pattern: line -> arc -> line."""
        path = [
            MockPathElement('line', ((0, 0, 0), (1, 0, 0))),
            MockPathElement('arc', ((1, 0, 0), (2, 0, 0))),
            MockPathElement('line', ((2, 0, 0), (3, 0, 0))),
        ]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is True
        assert error == ""

    def test_valid_arc_line_arc_pattern(self) -> None:
        """Valid pattern: arc -> line -> arc."""
        path = [
            MockPathElement('arc', ((0, 0, 0), (1, 0, 0))),
            MockPathElement('line', ((1, 0, 0), (2, 0, 0))),
            MockPathElement('arc', ((2, 0, 0), (3, 0, 0))),
        ]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is True
        assert error == ""

    def test_single_line_valid(self) -> None:
        """Single line element is valid."""
        path = [MockPathElement('line', ((0, 0, 0), (1, 0, 0)))]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is True
        assert error == ""

    def test_single_arc_valid(self) -> None:
        """Single arc element is valid."""
        path = [MockPathElement('arc', ((0, 0, 0), (1, 0, 0)))]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is True
        assert error == ""

    def test_two_elements_line_arc_valid(self) -> None:
        """Two elements: line -> arc is valid."""
        path = [
            MockPathElement('line', ((0, 0, 0), (1, 0, 0))),
            MockPathElement('arc', ((1, 0, 0), (2, 0, 0))),
        ]
        is_valid, _error = validate_path_alternation(path)
        assert is_valid is True

    # Defensive: Invalid patterns
    def test_two_consecutive_lines_invalid(self) -> None:
        """Two lines in a row is invalid."""
        path = [
            MockPathElement('line', ((0, 0, 0), (1, 0, 0))),
            MockPathElement('line', ((1, 0, 0), (2, 0, 0))),
        ]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is False
        assert "Position 2" in error
        assert "expected arc" in error

    def test_two_consecutive_arcs_invalid(self) -> None:
        """Two arcs in a row is invalid."""
        path = [
            MockPathElement('arc', ((0, 0, 0), (1, 0, 0))),
            MockPathElement('arc', ((1, 0, 0), (2, 0, 0))),
        ]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is False
        assert "Position 2" in error
        assert "expected line" in error

    def test_empty_path_invalid(self) -> None:
        """Empty path is invalid."""
        is_valid, error = validate_path_alternation([])
        assert is_valid is False
        assert "Empty path" in error

    def test_break_in_middle_invalid(self) -> None:
        """Break in alternation pattern is detected."""
        path = [
            MockPathElement('line', ((0, 0, 0), (1, 0, 0))),
            MockPathElement('arc', ((1, 0, 0), (2, 0, 0))),
            MockPathElement('arc', ((2, 0, 0), (3, 0, 0))),  # Should be line
        ]
        is_valid, error = validate_path_alternation(path)
        assert is_valid is False
        assert "Position 3" in error
        assert "expected line" in error


class TestBuildOrderedPath:
    """Test build_ordered_path() function."""

    # Happy path tests
    def test_simple_three_element_path(self) -> None:
        """Order a simple line -> arc -> line path."""
        # Create elements in random order
        line1 = MockPathElement('line', ((0, 0, 0), (1, 0, 0)))
        arc = MockPathElement('arc', ((1, 0, 0), (2, 0, 0)))
        line2 = MockPathElement('line', ((2, 0, 0), (3, 0, 0)))

        # Pass them out of order
        elements = [arc, line2, line1]
        ordered, error = build_ordered_path(elements)

        assert ordered is not None
        assert error == ""
        assert len(ordered) == 3

        # Should be ordered by connectivity
        # Either line1->arc->line2 or line2->arc->line1
        endpoints_seq = [e.endpoints for e in ordered]
        assert endpoints_seq[0][1] == endpoints_seq[1][0] or endpoints_seq[0][0] == endpoints_seq[1][1]

    def test_two_element_path(self) -> None:
        """Minimum valid path: 2 connected elements."""
        line = MockPathElement('line', ((0, 0, 0), (1, 0, 0)))
        arc = MockPathElement('arc', ((1, 0, 0), (2, 0, 0)))

        ordered, error = build_ordered_path([arc, line])

        assert ordered is not None
        assert error == ""
        assert len(ordered) == 2

    # Defensive: Edge cases
    def test_single_arc_succeeds(self) -> None:
        """Single arc is a valid path (arc-only bend sheet)."""
        arc = MockPathElement('arc', ((0, 0, 0), (1, 0, 0)))
        ordered, error = build_ordered_path([arc])

        assert ordered is not None
        assert error == ""
        assert len(ordered) == 1
        assert ordered[0].element_type == 'arc'

    def test_single_line_fails(self) -> None:
        """Single line is not a valid path (need at least one bend)."""
        line = MockPathElement('line', ((0, 0, 0), (1, 0, 0)))
        ordered, error = build_ordered_path([line])

        assert ordered is None
        assert "must be an arc" in error

    def test_empty_list_fails(self) -> None:
        """Empty element list is not a valid path."""
        ordered, error = build_ordered_path([])

        assert ordered is None
        assert "at least 1 element" in error

    def test_disconnected_element_fails(self) -> None:
        """Disconnected element causes failure."""
        line1 = MockPathElement('line', ((0, 0, 0), (1, 0, 0)))
        arc = MockPathElement('arc', ((1, 0, 0), (2, 0, 0)))
        disconnected = MockPathElement('line', ((100, 100, 100), (101, 100, 100)))

        ordered, error = build_ordered_path([line1, arc, disconnected])

        assert ordered is None
        assert "disconnected" in error.lower()

    def test_branching_path_fails(self) -> None:
        """Y-junction (3 branches) causes failure."""
        # Create a Y shape: center point connects to 3 elements
        center = (1, 0, 0)
        e1 = MockPathElement('line', ((0, 0, 0), center))
        e2 = MockPathElement('line', (center, (2, 0, 0)))
        e3 = MockPathElement('line', (center, (1, 1, 0)))

        ordered, error = build_ordered_path([e1, e2, e3])

        assert ordered is None
        assert "branches" in error.lower() or "endpoints" in error.lower()

    def test_closed_loop_fails(self) -> None:
        """Closed loop (no free endpoints) causes failure."""
        # Create a triangle - each element has 2 neighbors
        e1 = MockPathElement('line', ((0, 0, 0), (1, 0, 0)))
        e2 = MockPathElement('arc', ((1, 0, 0), (0.5, 0.866, 0)))
        e3 = MockPathElement('line', ((0.5, 0.866, 0), (0, 0, 0)))

        ordered, error = build_ordered_path([e1, e2, e3])

        assert ordered is None
        assert "closed loop" in error.lower()

    def test_maintains_all_elements(self) -> None:
        """All input elements appear in output."""
        e1 = MockPathElement('line', ((0, 0, 0), (1, 0, 0)))
        e2 = MockPathElement('arc', ((1, 0, 0), (2, 0, 0)))
        e3 = MockPathElement('line', ((2, 0, 0), (3, 0, 0)))
        e4 = MockPathElement('arc', ((3, 0, 0), (4, 0, 0)))

        ordered, _error = build_ordered_path([e3, e1, e4, e2])

        assert ordered is not None
        assert len(ordered) == 4
        # All original elements should be in output
        assert {id(e) for e in [e1, e2, e3, e4]} == {id(e) for e in ordered}
