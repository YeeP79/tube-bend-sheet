"""Tests for SVG cope template generator.

Run with: pytest tests/test_cope_template.py -v
"""
import math
import xml.etree.ElementTree as ET

from core.cope_math import calculate_cope
from core.cope_template import generate_cope_svg
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
        assert "PASS 1" in svg
        assert "PASS 2" in svg

    def test_has_colored_fills(self):
        result = _make_multi_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        # Check for lobe fill colors
        assert "#4488CC" in svg or "#CC7733" in svg

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

    def test_ref_marks_at_edges_for_bent_tubes(self):
        """Bent tubes: REF marks at both template edges (back-of-bend reference)."""
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", True)
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}

        ref_texts = [
            t for t in root.findall(".//svg:text", ns)
            if t.text == "REF"
        ]
        assert len(ref_texts) == 2

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

        # Find APEX text element
        apex_texts = [
            t for t in root.findall(".//svg:text", ns)
            if t.text == "APEX"
        ]
        assert len(apex_texts) == 1
        apex_x = float(apex_texts[0].get("x", "0"))

        # Calculate expected position (small x-offset nudges label right of dashed line)
        circumference = math.pi * od
        margin = 0.3  # _MARGIN
        peak_idx = max(range(len(result.z_profile)), key=lambda i: result.z_profile[i])
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
