"""
Tests for HTML generator module - runs without Fusion.

Run with: pytest tests/ -v
"""
import pytest

from core.html_generator import _escape_html, generate_html_bend_sheet
from models import BendData, BendSheetData, MarkPosition, PathSegment, StraightSection
from models.units import UnitConfig


# Test fixtures for unit configurations
@pytest.fixture
def imperial_units() -> UnitConfig:
    """Create imperial (inch) unit configuration."""
    return UnitConfig(
        is_metric=False,
        unit_name='in',
        unit_symbol='"',
        cm_to_unit=1.0 / 2.54,
        default_tube_od='1.75',
        default_precision=16,
        valid_precisions=(0, 4, 8, 16, 32),
    )


@pytest.fixture
def metric_units() -> UnitConfig:
    """Create metric (mm) unit configuration."""
    return UnitConfig(
        is_metric=True,
        unit_name='mm',
        unit_symbol='mm',
        cm_to_unit=10.0,
        default_tube_od='44.45',
        default_precision=1,
        valid_precisions=(0, 1, 2, 5, 10),
    )


@pytest.fixture
def minimal_bend_sheet_data(imperial_units: UnitConfig) -> BendSheetData:
    """Create minimal BendSheetData for testing."""
    return BendSheetData(
        component_name="Test Component",
        tube_od=1.5,
        clr=4.5,
        die_offset=0.5,
        precision=16,
        min_grip=6.0,
        travel_direction="Left to Right",
        starts_with_arc=False,
        ends_with_arc=False,
        clr_mismatch=False,
        clr_values=[4.5],
        continuity_errors=[],
        straights=[
            StraightSection(1, 10.0, (0, 0, 0), (10, 0, 0), (10, 0, 0)),
            StraightSection(2, 8.0, (10, 0, 0), (18, 0, 0), (8, 0, 0)),
        ],
        bends=[
            BendData(number=1, angle=45.0, rotation=None, arc_length=3.14),
        ],
        segments=[
            PathSegment('straight', 'Straight 1', 10.0, 0.0, 10.0, None, None),
            PathSegment('bend', 'BEND 1', 3.14, 10.0, 13.14, 45.0, None),
            PathSegment('straight', 'Straight 2', 8.0, 13.14, 21.14, None, None),
        ],
        mark_positions=[
            MarkPosition(1, 9.5, 45.0, None),
        ],
        extra_material=0.0,
        total_centerline=21.14,
        total_cut_length=21.14,
        units=imperial_units,
        bender_name="",
        die_name="",
    )


@pytest.fixture
def multi_bend_data(imperial_units: UnitConfig) -> BendSheetData:
    """Create BendSheetData with multiple bends for testing."""
    return BendSheetData(
        component_name="Multi-Bend Tube",
        tube_od=1.75,
        clr=5.25,
        die_offset=0.75,
        precision=16,
        min_grip=8.0,
        travel_direction="Top to Bottom",
        starts_with_arc=False,
        ends_with_arc=False,
        clr_mismatch=False,
        clr_values=[5.25, 5.25],
        continuity_errors=[],
        straights=[
            StraightSection(1, 12.0, (0, 0, 0), (12, 0, 0), (12, 0, 0)),
            StraightSection(2, 8.0, (12, 0, 0), (20, 0, 0), (8, 0, 0)),
            StraightSection(3, 10.0, (20, 0, 0), (30, 0, 0), (10, 0, 0)),
        ],
        bends=[
            BendData(number=1, angle=45.0, rotation=None, arc_length=4.0),
            BendData(number=2, angle=90.0, rotation=30.0, arc_length=6.0),
        ],
        segments=[
            PathSegment('straight', 'Straight 1', 12.0, 2.0, 14.0, None, None),
            PathSegment('bend', 'BEND 1', 4.0, 14.0, 18.0, 45.0, None),
            PathSegment('straight', 'Straight 2', 8.0, 18.0, 26.0, None, 30.0),
            PathSegment('bend', 'BEND 2', 6.0, 26.0, 32.0, 90.0, None),
            PathSegment('straight', 'Straight 3', 10.0, 32.0, 42.0, None, None),
        ],
        mark_positions=[
            MarkPosition(1, 13.25, 45.0, None),
            MarkPosition(2, 25.25, 90.0, 30.0),
        ],
        extra_material=2.0,
        total_centerline=40.0,
        total_cut_length=42.0,
        units=imperial_units,
        bender_name="Rogue RB-2",
        die_name='1.75" x 5.25"',
    )


class TestEscapeHtml:
    """Test the _escape_html helper function."""

    def test_escape_script_tag(self) -> None:
        result = _escape_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_escape_angle_brackets(self) -> None:
        result = _escape_html("<div>content</div>")
        assert "&lt;" in result
        assert "&gt;" in result

    def test_escape_ampersand(self) -> None:
        result = _escape_html("A & B")
        assert "&amp;" in result

    def test_escape_quotes(self) -> None:
        result = _escape_html('He said "hello"')
        assert "&quot;" in result

    def test_none_returns_empty(self) -> None:
        result = _escape_html(None)
        assert result == ""

    def test_normal_text_unchanged(self) -> None:
        text = "Normal component name 123"
        result = _escape_html(text)
        assert result == text

    def test_unicode_preserved(self) -> None:
        text = "Tube 45° bend"
        result = _escape_html(text)
        assert result == text


class TestXssPrevention:
    """Test XSS prevention patterns."""

    def test_script_injection_blocked(self) -> None:
        """Test that script tags are escaped in component names."""
        malicious = "<script>alert('xss')</script>"
        escaped = _escape_html(malicious)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_event_handler_injection_blocked(self) -> None:
        """Test that img tags with event handlers are escaped."""
        malicious = "<img src=x onerror=alert('xss')>"
        escaped = _escape_html(malicious)
        assert "<img" not in escaped
        assert "&lt;img" in escaped

    def test_href_injection_blocked(self) -> None:
        """Test that anchor tags with javascript URLs are escaped."""
        malicious = '<a href="javascript:alert(1)">click</a>'
        escaped = _escape_html(malicious)
        assert "<a" not in escaped
        assert "&lt;a" in escaped

    def test_html_tags_escaped(self) -> None:
        """Test that HTML tags are fully escaped."""
        malicious = "<b>bold</b>"
        escaped = _escape_html(malicious)
        assert "&lt;b&gt;" in escaped

    def test_special_chars_all_escaped(self) -> None:
        """Test all HTML special characters."""
        malicious = '<script>alert("test & \'quote\'")</script>'
        escaped = _escape_html(malicious)
        assert "<" not in escaped
        assert ">" not in escaped
        assert '"' not in escaped or "&quot;" in escaped
        assert "&" not in escaped or "&amp;" in escaped or "&lt;" in escaped


class TestGenerateHtmlBendSheet:
    """Test generate_html_bend_sheet() function."""

    # Happy path tests
    def test_generates_valid_html(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Generated output is valid HTML."""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_html_contains_component_name(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Component name appears in output."""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Test Component" in html

    def test_html_contains_all_segments(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """All segments appear in the bend data table."""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Straight 1" in html
        assert "BEND 1" in html
        assert "Straight 2" in html

    def test_html_contains_mark_positions(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Mark positions appear in the bender setup table."""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "45.0°" in html  # Bend angle

    def test_html_contains_cut_length(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Cut length appears in header."""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Cut Length:" in html

    def test_html_contains_clr(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """CLR appears in header and specs."""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "CLR:" in html

    # Multi-bend tests
    def test_multi_bend_shows_rotation(
        self, multi_bend_data: BendSheetData
    ) -> None:
        """Multi-bend path shows rotation values."""
        html = generate_html_bend_sheet(multi_bend_data)
        assert "30.0°" in html  # Rotation before bend 2
        assert "BEND 2" in html

    def test_multi_bend_shows_bender_info(
        self, multi_bend_data: BendSheetData
    ) -> None:
        """Bender and die names appear in output."""
        html = generate_html_bend_sheet(multi_bend_data)
        assert "Rogue RB-2" in html
        assert "1.75" in html  # Part of die name

    def test_multi_bend_shows_extra_material(
        self, multi_bend_data: BendSheetData
    ) -> None:
        """Extra material section appears when set."""
        html = generate_html_bend_sheet(multi_bend_data)
        assert "Extra Grip Material" in html
        assert "cut off after bending" in html

    # Defensive: Edge cases
    def test_escapes_special_chars_in_component_name(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Component name with special chars is escaped."""
        minimal_bend_sheet_data.component_name = "<script>alert('xss')</script>"
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_clr_mismatch_warning_shown(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """CLR mismatch warning is displayed."""
        minimal_bend_sheet_data.clr_mismatch = True
        minimal_bend_sheet_data.clr_values = [4.5, 4.7]
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "CLR Mismatch" in html
        assert "⚠️" in html

    def test_continuity_errors_displayed(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Continuity errors are displayed."""
        minimal_bend_sheet_data.continuity_errors = ["Gap at bend 1"]
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Continuity Errors" in html
        assert "Gap at bend 1" in html

    def test_empty_bender_name_handled(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Empty bender name doesn't break output."""
        minimal_bend_sheet_data.bender_name = ""
        minimal_bend_sheet_data.die_name = ""
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        # Should not have bender info div
        assert "Bender:" not in html

    def test_zero_die_offset_handled(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Zero die offset shows appropriate message."""
        minimal_bend_sheet_data.die_offset = 0.0
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Not specified" in html

    def test_starts_with_arc_noted(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Starting with arc is noted in specs."""
        minimal_bend_sheet_data.starts_with_arc = True
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Starts With" in html
        assert ">Bend<" in html

    def test_ends_with_arc_noted(
        self, minimal_bend_sheet_data: BendSheetData
    ) -> None:
        """Ending with arc is noted in specs."""
        minimal_bend_sheet_data.ends_with_arc = True
        html = generate_html_bend_sheet(minimal_bend_sheet_data)
        assert "Ends With" in html
        assert ">Bend<" in html

    # Metric unit test
    def test_metric_units_displayed(
        self, metric_units: UnitConfig
    ) -> None:
        """Metric units are displayed correctly."""
        data = BendSheetData(
            component_name="Metric Tube",
            tube_od=38.1,
            clr=114.3,
            die_offset=12.7,
            precision=1,
            min_grip=152.4,
            travel_direction="Left to Right",
            starts_with_arc=False,
            ends_with_arc=False,
            clr_mismatch=False,
            clr_values=[114.3],
            continuity_errors=[],
            straights=[
                StraightSection(1, 254.0, (0, 0, 0), (254, 0, 0), (254, 0, 0)),
                StraightSection(2, 203.2, (254, 0, 0), (457.2, 0, 0), (203.2, 0, 0)),
            ],
            bends=[
                BendData(number=1, angle=90.0, rotation=None, arc_length=179.5),
            ],
            segments=[
                PathSegment('straight', 'Straight 1', 254.0, 0.0, 254.0, None, None),
                PathSegment('bend', 'BEND 1', 179.5, 254.0, 433.5, 90.0, None),
                PathSegment('straight', 'Straight 2', 203.2, 433.5, 636.7, None, None),
            ],
            mark_positions=[
                MarkPosition(1, 241.3, 90.0, None),
            ],
            extra_material=0.0,
            total_centerline=636.7,
            total_cut_length=636.7,
            units=metric_units,
        )
        html = generate_html_bend_sheet(data)
        assert "mm" in html  # Unit symbol appears
        assert "Metric Tube" in html
