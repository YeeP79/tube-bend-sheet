"""Tests for SVG cope template generator.

Run with: pytest tests/test_cope_template.py -v
"""
import math
import xml.etree.ElementTree as ET

import pytest

from core.cope_math import calculate_cope
from core.cope_template import (
    _apex_angle,
    _label_center_x,
    _choose_seam_angle,
    _reflect_profile,
    generate_cope_svg,
)
from models.cope_data import ReceivingTube


def _make_single_pass_result(od: float = 1.75):
    """Helper: perpendicular single-pass cope result."""
    return calculate_cope(
        v1=(1.0, 0.0, 0.0),
        od1=od,
        receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=od)],
    )


def _make_multi_pass_result(od: float = 1.75):
    """Helper: multi-pass cope result with two lobes."""
    return calculate_cope(
        v1=(0.0, 0.0, 1.0),
        od1=od,
        receiving_tubes=[
            ReceivingTube(vector=(1.0, 0.0, 0.0), od=od),
            ReceivingTube(vector=(-1.0, 0.0, 0.0), od=od),
        ],
    )


class TestSvgWellFormed:
    """SVG output must be parseable XML."""

    def test_single_pass_is_valid_xml(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", False)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"

    def test_multi_pass_is_valid_xml(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", False)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"

    def test_with_bends_is_valid_xml(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", True)
        ET.fromstring(svg)  # Should not raise


class TestSvgDimensions:
    """SVG width should match pi * OD1 + margins + dimension space."""

    def test_width_matches_circumference(self):
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        root = ET.fromstring(svg)
        width_str = root.get("width", "")
        # Width is in inches: e.g., "6.140486in"
        assert width_str.endswith("in")
        width = float(width_str.replace("in", ""))
        expected = math.pi * od + 0.6 + 0.25  # circumference + 2*margin + dim_margin
        assert abs(width - expected) < 0.01

    def test_different_od(self):
        od = 2.0
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=od,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=od)],
        )
        svg = generate_cope_svg(result, od, "Tube2", "", False)
        root = ET.fromstring(svg)
        width_str = root.get("width", "")
        width = float(width_str.replace("in", ""))
        expected = math.pi * od + 0.6 + 0.25
        assert abs(width - expected) < 0.01


class TestSinglePassContent:
    """Single-pass SVGs should not have warning blocks."""

    def test_no_warning_block(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "MULTI-PASS" not in svg

    def test_has_method_a(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "Method A" in svg

    def test_has_scale_bar(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "scale bar" in svg

    def test_has_apex_mark(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "APEX" in svg

    def test_has_notcher_angle(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "0.0" in svg  # Perpendicular T-joint → notcher reads 0°


class TestMultiPassContent:
    """Multi-pass SVGs should have notcher procedure and colored fills."""

    def test_has_multi_pass_procedure(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "MULTI-PASS" in svg

    def test_has_method_b(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "Method B" in svg

    def test_has_pass_labels(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "Pass 1" in svg
        assert "Pass 2" in svg

    def test_has_plunge_depth_warning(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "DO NOT pass through" in svg

    def test_has_scale_bar(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "scale bar" in svg


class TestMethodC:
    """Method C SVGs should have grinder guidance."""

    def test_method_c_has_grinder_guidance(self):
        # 20-degree included angle → Method C
        v2 = (math.cos(math.radians(20.0)), math.sin(math.radians(20.0)), 0.0)
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=v2, od=1.75)],
        )
        assert result.method == "C"
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "GRINDER GUIDANCE" in svg
        assert '1/32"' in svg


class TestBentTubeProcedure:
    """Bent tube flag adds reference setup procedure."""

    def test_bent_tube_procedure_present(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True)
        assert "BENT TUBE" in svg
        assert "reference marks" in svg

    def test_no_bent_tube_procedure_when_straight(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "BENT TUBE" not in svg

    def test_bent_tube_has_ref_mark_alignment(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True)
        assert "REF marks aligned" in svg

    def test_bent_tube_mentions_cut_edge(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True)
        assert "cut edge" in svg

    def test_bent_tube_rotation_for_verification(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True)
        assert "verification only" in svg

    def test_ref_mark_length_parameter(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True, ref_mark_length=0.75)
        assert '0.75"' in svg


class TestPrintVerification:
    """Print verification section should always be present."""

    def test_has_print_verification(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "PRINT VERIFICATION" in svg
        assert "100% scale" in svg

    def test_has_circumference_verification(self):
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        expected_circ = f"{math.pi * od:.3f}\""
        assert expected_circ in svg
        assert "\u03c0 \u00d7 OD" in svg

    def test_has_node_label(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "Front Node", False)
        assert "Front Node" in svg

    def test_has_tube_name(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "CrossBrace", "", False)
        assert "CrossBrace" in svg


class TestTemplateUsage:
    """Template usage instructions should always be present."""

    def test_has_template_usage_section(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "TEMPLATE USAGE" in svg

    def test_mentions_straight_edge(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "straight" in svg
        assert "TUBE END" in svg

    def test_mentions_tube_end(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "tube end" in svg

    def test_has_cope_depth_note(self):
        result = _make_single_pass_result()
        max_z = max(result.z_profile)
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert f"{max_z:.3f}\"" in svg
        assert "deepest point" in svg

    def test_mentions_profile_curve(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "profile curve" in svg


class TestNotcherProcedure:
    """Method-specific notcher procedures."""

    def test_method_a_has_procedure(self):
        result = _make_single_pass_result()
        assert result.method == "A"
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "NOTCHER PROCEDURE" in svg

    def test_method_a_push_through(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "single continuous pass" in svg

    def test_method_b_has_multi_pass_header(self):
        result = _make_multi_pass_result()
        assert result.method == "B"
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "MULTI-PASS" in svg

    def test_method_b_stop_and_withdraw(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "STOP and withdraw" in svg

    def test_method_b_has_per_pass_depth(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        for cope_pass in result.passes:
            assert f"{cope_pass.plunge_depth:.3f}\"" in svg

    def test_method_c_no_notcher_procedure(self):
        v2 = (math.cos(math.radians(20.0)), math.sin(math.radians(20.0)), 0.0)
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=v2, od=1.75)],
        )
        assert result.method == "C"
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "NOTCHER PROCEDURE" not in svg


class TestEdgeLabels:
    """Template should have visual labels showing which side is the tube end."""

    def test_has_tube_end_label(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "TUBE END" in svg
        assert "align flush" in svg

    def test_has_cut_line_label(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "CUT LINE" in svg

    def test_has_waste_label(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "WASTE" in svg

    def test_multi_pass_has_edge_labels(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "TUBE END" in svg
        assert "CUT LINE" in svg
        assert "WASTE" in svg


# ---------------------------------------------------------------------------
# SVG edge cases
# ---------------------------------------------------------------------------
class TestSvgEdgeCases:
    """Edge cases for SVG template generation."""

    def test_empty_tube_name(self):
        """Empty tube name should not break SVG."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "", "", False)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        assert "Cope Template" in svg

    def test_empty_node_label(self):
        """Empty node label should not include 'at' text."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert " at " not in svg or "Tube1 at " not in svg

    def test_very_shallow_cope(self):
        """Very small receiving tube → shallow cope should still render."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=0.25)],
        )
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"

    def test_large_od_difference(self):
        """Large OD receiving tube should still produce valid SVG."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.0,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=6.0)],
        )
        svg = generate_cope_svg(result, 1.0, "SmallTube", "", False)
        ET.fromstring(svg)  # Should not raise

    def test_multi_pass_wrap_around_lobe(self):
        """Multi-pass with wrap-around lobe should produce valid SVG."""
        # Use three receivers at 120° apart to get multi-pass
        result = calculate_cope(
            v1=(0.0, 0.0, 1.0),
            od1=1.75,
            receiving_tubes=[
                ReceivingTube(vector=(1.0, 0.0, 0.0), od=1.75),
                ReceivingTube(vector=(-1.0, 0.0, 0.0), od=1.75),
            ],
        )
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"

    def test_method_c_svg_well_formed(self):
        """Method C (acute angle) should produce valid SVG with grinder guidance."""
        v2 = (math.cos(math.radians(20.0)), math.sin(math.radians(20.0)), 0.0)
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=v2, od=1.75)],
        )
        svg = generate_cope_svg(result, 1.75, "Tube1", "TestNode", True)
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        # Should have grinder guidance AND bent tube procedure
        assert "GRINDER GUIDANCE" in svg
        assert "BENT TUBE" in svg

    def test_special_characters_in_names(self):
        """Names with special XML characters should be escaped."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube<1>&2", "Node 'A'", False)
        # Should be valid XML (ET.fromstring would fail on unescaped)
        ET.fromstring(svg)


# ---------------------------------------------------------------------------
# REF marks and APEX position
# ---------------------------------------------------------------------------
class TestRefMarks:
    """REF marks should appear on the template."""

    def test_has_ref_marks(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert svg.count("REF") >= 2  # REF label + REF in usage instructions

    def test_single_ref_mark_for_bent_tubes(self):
        """Bent tubes: one REF line, not split across both paper edges."""
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", True)
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        ref_texts = [
            t for t in root.findall(".//svg:text", ns)
            if t.text == "REF"
        ]
        assert len(ref_texts) == 1

    def test_ref_at_center_for_straight_tubes(self):
        """Straight tubes: single REF mark at template center."""
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        ref_texts = [
            t for t in root.findall(".//svg:text", ns)
            if t.text == "REF"
        ]
        assert len(ref_texts) == 1

        # REF should be near the center (x = margin + circumference / 2 + small offset)
        circumference = math.pi * od
        margin = 0.3
        expected_x = margin + circumference / 2
        actual_x = float(ref_texts[0].get("x", "0"))
        assert abs(actual_x - expected_x) < 0.05  # Allow for x_offset nudge


class TestApexPosition:
    """APEX label should be at profile peak, not fixed center."""

    def test_has_apex_mark(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "APEX" in svg

    def test_apex_at_peak_position(self):
        """APEX x-position should correspond to the z_profile peak index."""
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", True)
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        # Find the template's APEX label (vertical text; the diagram has its own)
        apex_texts = [
            t for t in root.findall(".//svg:text", ns)
            if t.text == "APEX" and t.get("transform")
        ]
        assert len(apex_texts) == 1
        apex_x = float(apex_texts[0].get("x", "0"))

        # Calculate expected position (small x-offset nudges label right of dashed line)
        circumference = math.pi * od
        margin = 0.3  # _MARGIN
        profile = _reflect_profile(result.z_profile)
        apex = _apex_angle(profile)
        assert apex is not None
        peak_idx = (apex - _choose_seam_angle(apex)) % 360
        expected_x = margin + (peak_idx / 360.0) * circumference
        assert abs(apex_x - expected_x) < 0.05  # Allow for x_offset nudge


class TestCopeDepth:
    """Cope depth should appear in SVG info section and as dimension."""

    def test_cope_depth_shown(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "Cope depth:" in svg

    def test_cope_depth_value_correct(self):
        result = _make_single_pass_result()
        max_z = max(result.z_profile)
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert f"{max_z:.3f}\"" in svg

    def test_depth_dimension_present(self):
        """Depth dimension line should be drawn on the right side."""
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        root = ET.fromstring(svg)

        # Check SVG width is wider than circumference + 2*margin (has dimension space)
        width_str = root.get("width", "")
        width = float(width_str.replace("in", ""))
        circumference = math.pi * od
        assert width > circumference + 0.6 + 0.2  # margin + dimension space


# ---------------------------------------------------------------------------
# Location label
# ---------------------------------------------------------------------------
class TestLocationLabel:
    """Location label should appear when provided and be absent when empty."""

    def test_location_shown_when_provided(self):
        """Non-empty location should appear as 'Location: ...' in the SVG."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", False, location="Front end")
        assert "Location: Front end" in svg

    def test_location_not_shown_when_empty(self):
        """Empty location should not produce a Location: line."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", False, location="")
        assert "Location:" not in svg

    def test_location_with_all_features(self):
        """Location + bends + multi-pass should produce valid XML."""
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", True, location="Back end")
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        assert "Location: Back end" in svg
        assert "BENT TUBE" in svg
        assert "MULTI-PASS" in svg


# ---------------------------------------------------------------------------
# Cutting margin
# ---------------------------------------------------------------------------
class TestCuttingMargin:
    """Template should extend below tube end for cutting grip."""

    def test_template_taller_than_profile(self):
        """Template background should be taller than the cope profile height."""
        od = 1.75
        result = _make_single_pass_result(od)
        max_z = max(result.z_profile)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        # Find the template background rect (first rect element)
        rects = root.findall(".//svg:rect", ns)
        assert len(rects) >= 1
        rect_h = float(rects[0].get("height", "0"))
        profile_h = max(max_z, 0.5)
        assert rect_h > profile_h  # Background extends past profile

    def test_tube_end_alignment_line_present(self):
        """A solid line should mark the tube end inside the template."""
        od = 1.75
        result = _make_single_pass_result(od)
        max_z = max(result.z_profile)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        # Find horizontal lines at the tube end position
        margin = 0.3
        profile_h = max(max_z, 0.5)
        tube_end_y = margin + profile_h
        lines = root.findall(".//svg:line", ns)
        tube_end_lines = [
            ln for ln in lines
            if abs(float(ln.get("y1", "0")) - tube_end_y) < 0.01
            and abs(float(ln.get("y2", "0")) - tube_end_y) < 0.01
        ]
        assert len(tube_end_lines) >= 1


# ---------------------------------------------------------------------------
# Receiver names on cope templates
# ---------------------------------------------------------------------------
class TestReceiverNames:
    """Receiver tube names should appear in the SVG template."""

    def test_receiver_names_shown(self):
        """Named receiving tubes produce a 'Receiving:' summary line."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75, name="main rail")],
        )
        svg = generate_cope_svg(result, 1.75, "CrossBrace", "NodeA", False)
        assert "Receiving: main rail" in svg

    def test_no_receiver_names_when_empty(self):
        """Unnamed receiving tubes should not produce a 'Receiving:' line."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )
        svg = generate_cope_svg(result, 1.75, "CrossBrace", "NodeA", False)
        assert "Receiving:" not in svg

    def test_multi_pass_shows_receiver_per_pass(self):
        """Each pass label should include its receiver name."""
        result = calculate_cope(
            v1=(0.0, 0.0, 1.0),
            od1=1.75,
            receiving_tubes=[
                ReceivingTube(vector=(1.0, 0.0, 0.0), od=1.75, name="left rail"),
                ReceivingTube(vector=(-1.0, 0.0, 0.0), od=1.75, name="right rail"),
            ],
        )
        svg = generate_cope_svg(result, 1.75, "CrossBrace", "NodeA", False)
        assert "left rail" in svg
        assert "right rail" in svg
        # Both names in "Receiving:" summary
        assert "Receiving:" in svg

    def test_receiver_names_deduped(self):
        """Duplicate receiver names should appear only once in the summary."""
        result = _make_single_pass_result()
        # Manually set duplicate names for testing
        for p in result.passes:
            object.__setattr__(p, 'receiver_name', 'same tube')
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        # Should appear once in the "Receiving:" line, not duplicated
        assert svg.count("Receiving: same tube") == 1

    def test_receiver_names_valid_xml(self):
        """SVG with receiver names should be well-formed XML."""
        result = calculate_cope(
            v1=(0.0, 0.0, 1.0),
            od1=1.75,
            receiving_tubes=[
                ReceivingTube(vector=(1.0, 0.0, 0.0), od=1.75, name="tube <A>"),
                ReceivingTube(vector=(-1.0, 0.0, 0.0), od=1.75, name="tube &B"),
            ],
        )
        svg = generate_cope_svg(result, 1.75, "CrossBrace", "", False)
        ET.fromstring(svg)  # Should not raise


# ---------------------------------------------------------------------------
# Setback layout (waste_side="bottom")
# ---------------------------------------------------------------------------
class TestSetbackLayout:
    """Setback layout flips the template so waste is at the bottom."""

    def test_setback_is_valid_xml(self):
        """Setback SVG should be parseable XML."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "NodeA", False, waste_side="bottom")
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"

    def test_setback_has_reference_edge_label(self):
        """Setback template should have 'REFERENCE EDGE' label."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        assert "REFERENCE EDGE" in svg
        assert "cope depth from tube end" in svg

    def test_setback_has_waste_at_bottom(self):
        """Setback template should mention WASTE (discard below curve)."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        assert "WASTE" in svg
        assert "discard below curve" in svg

    def test_setback_no_tube_end_label(self):
        """Setback template should NOT have 'TUBE END' edge label."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        assert "TUBE END" not in svg

    def test_setback_profile_flipped(self):
        """In setback mode, z=0 values should map near the top of the profile area."""
        result = _make_single_pass_result()
        svg_default = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="top")
        svg_setback = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")

        # Parse profile curves: find the <path> elements with stroke="#000000"
        root_default = ET.fromstring(svg_default)
        root_setback = ET.fromstring(svg_setback)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        def get_profile_path(root: ET.Element) -> str:
            paths = root.findall(".//svg:path", ns)
            for p in paths:
                if p.get("stroke") == "#000000" and p.get("fill") == "none":
                    return p.get("d", "")
            return ""

        d_default = get_profile_path(root_default)
        d_setback = get_profile_path(root_setback)

        # The profile path data should differ (Y coordinates are flipped)
        assert d_default != d_setback
        assert d_default  # Ensure non-empty
        assert d_setback

    def test_setback_multi_pass_valid_xml(self):
        """Multi-pass setback SVG should be well-formed."""
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        assert "REFERENCE EDGE" in svg

    def test_setback_with_bends_valid_xml(self):
        """Setback + bent tube should produce valid SVG."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True, waste_side="bottom")
        ET.fromstring(svg)  # Should not raise
        assert "BENT TUBE" in svg
        assert "REFERENCE EDGE" in svg

    def test_setback_usage_instructions(self):
        """Setback template usage should mention keeping the REFERENCE EDGE piece."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        assert "keep the piece with the straight REFERENCE EDGE" in svg

    def test_default_usage_instructions(self):
        """Default template usage should mention keeping the TUBE END piece."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="top")
        assert "keep the piece with the straight TUBE END edge" in svg

    def test_setback_has_cut_line(self):
        """Setback template should still have CUT LINE label."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        assert "CUT LINE" in svg

    def test_setback_has_scale_bar(self):
        """Setback template should still have scale bar."""
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False, waste_side="bottom")
        assert "scale bar" in svg


class TestReflectProfile:
    """Tests for _reflect_profile outside-surface wrapping convention."""

    def test_empty_profile(self):
        from core.cope_template import _reflect_profile
        assert _reflect_profile([]) == []

    def test_degree_zero_invariant(self):
        """Index 0 (REF position) should be preserved."""
        from core.cope_template import _reflect_profile
        profile = [float(i) for i in range(360)]
        result = _reflect_profile(profile)
        assert result[0] == 0.0

    def test_degree_180_invariant(self):
        """Index 180 should be preserved (diametrically opposite REF)."""
        from core.cope_template import _reflect_profile
        profile = [float(i) for i in range(360)]
        result = _reflect_profile(profile)
        assert result[180] == 180.0

    def test_swaps_cw_to_ccw(self):
        """Index 1 should get old index 359, index 90 should get old 270."""
        from core.cope_template import _reflect_profile
        profile = [float(i) for i in range(360)]
        result = _reflect_profile(profile)
        assert result[1] == 359.0
        assert result[90] == 270.0
        assert result[270] == 90.0
        assert result[359] == 1.0

    def test_double_reflect_is_identity(self):
        """Reflecting twice should return the original profile."""
        from core.cope_template import _reflect_profile
        profile = [float(i) for i in range(360)]
        result = _reflect_profile(_reflect_profile(profile))
        assert result == profile

    def test_symmetric_profile_unchanged(self):
        """A profile symmetric about degree 0 should be unchanged."""
        from core.cope_template import _reflect_profile
        # cos(theta) is symmetric: cos(d) == cos(360-d)
        profile = [math.cos(math.radians(d)) for d in range(360)]
        result = _reflect_profile(profile)
        for i in range(360):
            assert abs(result[i] - profile[i]) < 1e-10


# ---------------------------------------------------------------------------
# Seam placement, long-point depth, single cut line
# ---------------------------------------------------------------------------
def _make_leg_on_axle_result(axle_od: float = 3.0):
    """Trapezoid-frame leg at 43.1° landing on a horizontal axle."""
    a = math.radians(43.1)
    return calculate_cope(
        v1=(-math.cos(a), -math.sin(a), 0.0),
        od1=1.75,
        receiving_tubes=[ReceivingTube(vector=(1.0, 0.0, 0.0), od=axle_od)],
        reference_vector=(-math.sin(a), math.cos(a), 0.0),
    )


def _dashed_line_xs(svg: str) -> list[float]:
    root = ET.fromstring(svg)
    return [
        float(el.get("x1", "0"))
        for el in root.iter()
        if el.tag.endswith("line") and el.get("stroke-dasharray")
    ]


class TestChooseSeamAngle:
    """The paper seam goes in the widest gap between dashed lines."""

    def test_apex_opposite_ref_ties_resolve_toward_centered_ref(self):
        # Marks 0/90/180/270 → four 90° gaps; REF ends up 45° off center
        assert _choose_seam_angle(180) == 135

    def test_apex_on_ref_puts_ref_at_center(self):
        # Marks 0/90/270 → widest gap 90..270 → seam 180, REF centered
        assert _choose_seam_angle(0) == 180

    def test_no_apex(self):
        assert _choose_seam_angle(None) == 180

    def test_seam_never_on_a_mark(self):
        for apex in range(360):
            seam = _choose_seam_angle(apex)
            for mark in (0, 90, 270, apex):
                dist = min((seam - mark) % 360, (mark - seam) % 360)
                assert dist >= 45


class TestApexAngle:

    def test_empty(self):
        assert _apex_angle([]) is None

    def test_first_of_equal_peaks(self):
        profile = [0.0] * 360
        profile[90] = profile[270] = 2.0
        assert _apex_angle(profile) == 90


class TestTemplateLayout:
    """Printed template: dashed lines clear of paper edges, one cut line."""

    @pytest.mark.parametrize("has_bends", [True, False])
    @pytest.mark.parametrize("make", [
        _make_single_pass_result, _make_multi_pass_result, _make_leg_on_axle_result,
    ])
    def test_no_dashed_line_near_paper_edge(self, make, has_bends):
        od = 1.75
        svg = generate_cope_svg(make(), od, "Tube1", "", has_bends)
        w = math.pi * od
        left, right = 0.3, 0.3 + w  # _MARGIN
        min_clearance = w * 30.0 / 360.0
        xs = _dashed_line_xs(svg)
        assert xs
        for x in xs:
            assert x - left >= min_clearance
            assert right - x >= min_clearance

    def test_no_grey_reference_curve(self):
        svg = generate_cope_svg(_make_leg_on_axle_result(), 1.75, "Tube1", "", True)
        assert "#BBBBBB" not in svg
        root = ET.fromstring(svg)
        paths = [el for el in root.iter() if el.tag.endswith("path")]
        assert len(paths) == 1

    def test_curve_touches_tube_end_line(self):
        """Long point sits on the TUBE END edge — no extra stock cut away."""
        svg = generate_cope_svg(_make_leg_on_axle_result(), 1.75, "Tube1", "", True)
        root = ET.fromstring(svg)
        path = next(el for el in root.iter() if el.tag.endswith("path"))
        ys = [float(pt[1:].split(",")[1]) for pt in path.get("d", "").split()]
        align = next(
            el for el in root.iter()
            if el.tag.endswith("line") and el.get("stroke-width") == "0.02"
        )
        assert max(ys) == pytest.approx(float(align.get("y1", "0")), abs=1e-3)

    @pytest.mark.parametrize("waste_side", ["top", "bottom"])
    def test_depth_is_long_point_to_heel(self, waste_side):
        """3" axle under a 1.75" leg at 43.1°: heel is 1.870" behind the long point.

        The dimension, the info text and the usage steps must all agree.
        """
        svg = generate_cope_svg(
            _make_leg_on_axle_result(), 1.75, "Tube1", "", True, waste_side=waste_side,
        )
        assert 'Cope depth: 1.870"' in svg
        assert '>1.870"<' in svg
        assert "3.130" not in svg

    def test_receiver_axis_sign_does_not_change_template(self):
        a = math.radians(43.1)
        v1 = (-math.cos(a), -math.sin(a), 0.0)
        ref = (-math.sin(a), math.cos(a), 0.0)
        svgs = [
            generate_cope_svg(
                calculate_cope(v1, 1.75, [ReceivingTube(axle, 3.0)], ref),
                1.75, "Tube1", "", True,
            )
            for axle in ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0))
        ]
        assert svgs[0] == svgs[1]


class TestPageMessagesAndProcedureText:
    """Warnings/notes are printed; rotation mark and APEX are not conflated."""

    def test_calculation_warnings_printed(self):
        # Shallow 2nd receiver is excluded from the profile with a warning
        result = calculate_cope(
            v1=(0.0, 0.0, 1.0),
            od1=1.75,
            receiving_tubes=[
                ReceivingTube((1.0, 0.0, 0.0), 1.75, "Rail"),
                ReceivingTube((0.0, 0.1, 1.0), 1.75, "Brace"),
            ],
        )
        assert any("Brace" in w for w in result.warnings)
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "Brace" in svg
        assert "⚠" in svg

    def test_holesaw_warning_not_duplicated(self):
        result = _make_leg_on_axle_result()
        warning = result.passes[0].holesaw_warning
        assert warning
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True)
        assert svg.count(warning[:40]) == 1

    def test_notes_printed_and_wrapped(self):
        note = "Cut length adds 1.260\" at this end " + "x" * 120
        svg = generate_cope_svg(_make_leg_on_axle_result(), 1.75, "Tube1", "", True,
                                notes=[note])
        root = ET.fromstring(svg)
        texts = [t.text or "" for t in root.iter() if t.tag.endswith("text")]
        assert any(t.startswith("Cut length adds 1.260") for t in texts)
        width_chars = int(math.pi * 1.75 / 0.05)
        assert all(len(t) <= width_chars for t in texts if "xxx" in t)

    def test_messages_grow_the_page(self):
        result = _make_leg_on_axle_result()
        plain = ET.fromstring(generate_cope_svg(result, 1.75, "T", "", True))
        noted = ET.fromstring(generate_cope_svg(result, 1.75, "T", "", True,
                                                notes=["a", "b", "c"]))
        h = lambda el: float(el.get("height", "0in").rstrip("in"))  # noqa: E731
        assert h(noted) == pytest.approx(h(plain) + 3 * 0.13 + 0.07)

    def test_step_two_says_opposite_apex(self):
        svg = generate_cope_svg(_make_leg_on_axle_result(), 1.75, "Tube1", "", True)
        assert "directly opposite the template APEX line" in svg
        assert "align to template APEX mark" not in svg

    def test_diagram_labels_mark_and_apex_opposite(self):
        result = _make_leg_on_axle_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", True)
        root = ET.fromstring(svg)
        texts = {t.text: t for t in root.iter()
                 if t.tag.endswith("text") and not t.get("transform")}
        assert "Mark" in texts and "APEX" in texts and "0\u00b0 REF" in texts
        assert "Apex" not in texts
        # Mark at 0° (top), APEX at 180° (bottom) of the diagram circle
        assert float(texts["Mark"].get("y", "0")) < float(texts["APEX"].get("y", "0"))
        # Mark at 0° sits beside the REF label rather than on top of it
        assert float(texts["Mark"].get("x", "0")) > float(texts["0\u00b0 REF"].get("x", "0")) + 0.2

    def test_reference_description_names_bend_center(self):
        svg = generate_cope_svg(_make_leg_on_axle_result(), 1.75, "Tube1", "", True)
        assert "facing away from the bend center" in svg
        assert "holesaw center" not in svg.split("NOTCHER PROCEDURE")[0]


class TestLabelPlacement:
    """Template labels avoid the cut curve."""

    def test_tube_end_label_sits_where_curve_is_high(self):
        profile = [0.0] * 180 + [1.0] * 180
        cx = _label_center_x(profile, 0.0, 6.0, "abc", prefer_high=True)
        assert cx > 3.0

    def test_waste_label_sits_where_curve_is_low(self):
        profile = [0.0] * 180 + [1.0] * 180
        cx = _label_center_x(profile, 0.0, 6.0, "abc", prefer_high=False)
        assert cx < 3.0

    def test_flat_profile_centers_label(self):
        cx = _label_center_x([1.0] * 360, 0.3, 6.0, "abc", prefer_high=True)
        assert cx == pytest.approx(3.3, abs=0.02)

    def test_empty_or_too_wide(self):
        assert _label_center_x([], 0.0, 4.0, "abc", True) == 2.0
        assert _label_center_x([1.0] * 360, 0.0, 0.1, "x" * 50, True) == 0.05

    @pytest.mark.parametrize("waste_side", ["top", "bottom"])
    def test_tube_end_line_label_clear_of_curve(self, waste_side):
        """The label on the long-point line must not overlap the curve."""
        result = _make_leg_on_axle_result()
        svg = generate_cope_svg(result, 1.75, "T", "", True, waste_side=waste_side)
        root = ET.fromstring(svg)
        label = "TUBE END" if waste_side == "top" else "discard below"
        el = next(t for t in root.iter()
                  if t.tag.endswith("text") and label in (t.text or ""))
        cx = float(el.get("x", "0"))
        half = len(el.text or "") * 0.05 / 2
        path = next(p for p in root.iter() if p.tag.endswith("path"))
        pts = [tuple(map(float, pt[1:].split(","))) for pt in path.get("d", "").split()]
        label_y = float(el.get("y", "0"))
        under = [py for px, py in pts if cx - half <= px <= cx + half]
        assert under
        # Curve stays at least a text-height above the label baseline
        assert max(under) < label_y - 0.09
