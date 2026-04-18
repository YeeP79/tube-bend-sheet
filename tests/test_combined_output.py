"""Tests for core.combined_output — combined bend sheet + cope template HTML."""

import math

from core.combined_output import (
    CopePageData,
    generate_combined_document,
    _orientation_hint,
)
from core.html_generator import generate_html_bend_sheet
from models.bend_data import BendSheetData, StraightSection
from models.cope_data import CopePass, CopeResult
from models.units import UnitConfig


def _imperial_units() -> UnitConfig:
    return UnitConfig(
        is_metric=False,
        unit_name="in",
        unit_symbol='"',
        cm_to_unit=1.0 / 2.54,
        default_tube_od="1.75",
        default_precision=16,
        valid_precisions=(0, 4, 8, 16, 32),
    )


def _minimal_bend_sheet_data() -> BendSheetData:
    """Build a minimal BendSheetData for testing."""
    units = _imperial_units()
    return BendSheetData(
        component_name="Test Tube",
        tube_od=1.75,
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
        straights=[
            StraightSection(1, 5.0, (0, 0, 0), (5, 0, 0), (5, 0, 0)),
        ],
        bends=[],
        segments=[],
        mark_positions=[],
        extra_material=0.0,
        total_centerline=5.0,
        total_cut_length=5.0,
        units=units,
    )


def _simple_cope_result() -> CopeResult:
    """Build a minimal CopeResult with a single pass."""
    z_profile = [0.0] * 360
    # Simple saddle shape
    for i in range(360):
        z_profile[i] = 0.5 * abs(math.sin(math.radians(i)))

    return CopeResult(
        passes=[
            CopePass(
                notcher_angle=0.0,
                rotation_mark=0.0,
                plunge_depth=0.5,
                is_pass_through=True,
                lobe_span_degrees=180.0,
                dominant=True,
                holesaw_depth_required=1.0,
            ),
        ],
        is_multi_pass=False,
        method="A",
        method_description="Single pass, push through",
        z_profile=z_profile,
        has_bend_reference=True,
        reference_description="Back-of-bend (extrados)",
    )


def _cope_page(
    end_label: str = "End",
    od1: float = 1.75,
    has_bends: bool = True,
) -> CopePageData:
    return CopePageData(
        end_label=end_label,
        cope_result=_simple_cope_result(),
        od1=od1,
        tube_name="Test Tube",
        has_bends=has_bends,
    )


# ── No cope pages ────────────────────────────────────────────────────

class TestCombinedDocumentNoCopes:

    def test_no_cope_pages_matches_bend_sheet(self) -> None:
        """Empty cope_pages → output identical to generate_html_bend_sheet."""
        data = _minimal_bend_sheet_data()
        combined = generate_combined_document(data, [])
        expected = generate_html_bend_sheet(data)
        assert combined == expected

    def test_returns_valid_html(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [])
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html


# ── Single cope page ─────────────────────────────────────────────────

class TestCombinedDocumentSingleCope:

    def test_contains_bend_sheet_content(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page()])
        assert "TUBE BEND SHEET" in html
        assert "<table" in html

    def test_contains_cope_svg(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page()])
        assert "<svg" in html

    def test_has_page_break(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page()])
        assert "page-break-before" in html

    def test_cope_page_heading(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page(end_label="Front Node")])
        assert "Front Node" in html

    def test_svg_no_xml_declaration(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page()])
        assert "<?xml" not in html

    def test_has_scale_bar(self) -> None:
        """The cope SVG should contain the scale bar text."""
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page()])
        assert "scale bar" in html

    def test_returns_valid_html(self) -> None:
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page()])
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "</body>" in html


# ── Both ends ─────────────────────────────────────────────────────────

class TestCombinedDocumentBothEnds:

    def test_two_cope_pages(self) -> None:
        data = _minimal_bend_sheet_data()
        pages = [
            _cope_page(end_label="Start End"),
            _cope_page(end_label="End — Front Node"),
        ]
        html = generate_combined_document(data, pages)
        assert html.count('class="cope-page-first"') == 1
        assert html.count('class="cope-page"') == 1

    def test_both_svgs_present(self) -> None:
        data = _minimal_bend_sheet_data()
        pages = [
            _cope_page(end_label="Start"),
            _cope_page(end_label="End"),
        ]
        html = generate_combined_document(data, pages)
        # Two cope SVGs + zero SVGs from bend sheet = 2
        assert html.count("<svg") == 2

    def test_both_labels_present(self) -> None:
        data = _minimal_bend_sheet_data()
        pages = [
            _cope_page(end_label="Start End"),
            _cope_page(end_label="End — Rear Node"),
        ]
        html = generate_combined_document(data, pages)
        assert "Start End" in html
        assert "Rear Node" in html


# ── Landscape detection ───────────────────────────────────────────────

class TestLandscapeDetection:

    def test_small_od_no_landscape(self) -> None:
        """OD=1.75 → circumference ~5.5in, fits portrait — no orientation hint shown."""
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page(od1=1.75)])
        # The CSS class definitions will contain "landscape-hint", but there
        # should be no actual <p class="landscape-hint"> element in the output.
        assert '<p class="landscape-hint">' not in html
        assert '<p class="wide-format-warning">' not in html

    def test_large_od_landscape(self) -> None:
        """OD=2.5 → circumference ~7.85in → landscape hint."""
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page(od1=2.5)])
        assert "landscape" in html

    def test_very_large_od_warning(self) -> None:
        """OD=3.5 → circumference ~11in → wide-format warning."""
        data = _minimal_bend_sheet_data()
        html = generate_combined_document(data, [_cope_page(od1=3.5)])
        assert "wide-format" in html.lower() or "Wide-format" in html


class TestOrientationHintHelper:

    def test_portrait(self) -> None:
        assert _orientation_hint(5.0) == ""

    def test_landscape(self) -> None:
        hint = _orientation_hint(8.0)
        assert "landscape" in hint

    def test_wide_format(self) -> None:
        hint = _orientation_hint(12.0)
        assert "Wide-format" in hint

    def test_boundary_portrait(self) -> None:
        assert _orientation_hint(7.5) == ""

    def test_boundary_landscape(self) -> None:
        hint = _orientation_hint(10.0)
        assert "landscape" in hint
