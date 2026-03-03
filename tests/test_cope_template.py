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
    """SVG width should match pi * OD1."""

    def test_width_matches_circumference(self):
        od = 1.75
        result = _make_single_pass_result(od)
        svg = generate_cope_svg(result, od, "Tube1", "", False)
        root = ET.fromstring(svg)
        width_str = root.get("width", "")
        # Width is in inches: e.g., "5.890486in"
        assert width_str.endswith("in")
        width = float(width_str.replace("in", ""))
        expected = math.pi * od + 0.6  # circumference + 2 * margin
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
        expected = math.pi * od + 0.6
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
        assert "90.0" in svg


class TestMultiPassContent:
    """Multi-pass SVGs should have warning blocks and colored fills."""

    def test_has_warning_block(self):
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
        assert "extrados" in svg

    def test_no_bent_tube_procedure_when_straight(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "BENT TUBE" not in svg


class TestPrintInstructions:
    """Print instructions should always be present."""

    def test_has_print_instructions(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "", False)
        assert "PRINT INSTRUCTIONS" in svg
        assert "100% scale" in svg

    def test_has_node_label(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "Tube1", "Front Node", False)
        assert "Front Node" in svg

    def test_has_tube_name(self):
        result = _make_single_pass_result()
        svg = generate_cope_svg(result, 1.75, "CrossBrace", "", False)
        assert "CrossBrace" in svg
