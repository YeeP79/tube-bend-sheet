"""SVG wrap template generator for tube coping.

Generates 1:1 scale SVG templates that can be printed, cut out,
and wrapped around a tube to mark the cope profile for cutting.

Zero Fusion 360 dependencies. Fully unit-testable.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from ..models.cope_data import CopeResult


# SVG units: inches (1:1 scale for printing)
_MARGIN = 0.3  # Margin around template in inches
_PROFILE_STROKE = 0.02  # Normal profile stroke width
_PROFILE_STROKE_HEAVY = 0.04  # Heavy stroke for Method C
_FONT_SIZE_LABEL = 0.12  # Label font size in inches
_FONT_SIZE_TITLE = 0.18  # Title font size
_FONT_SIZE_SMALL = 0.09  # Small text
_FONT_SIZE_INSTRUCTIONS = 0.08  # Instruction text
_SCALE_BAR_LENGTH = 1.0  # 1-inch scale bar
_REF_CIRCLE_RADIUS = 0.4  # Reference diagram circle radius
_LOBE_COLORS = ["#4488CC", "#CC7733", "#44AA44", "#AA4488"]
_WARNING_COLOR = "#CC3333"


def generate_cope_svg(
    result: CopeResult,
    od1: float,
    tube_name: str,
    node_label: str,
    has_bends: bool,
) -> str:
    """
    Generate a 1:1 scale SVG wrap template for a cope cut.

    The template unrolls the tube circumference onto a flat surface.
    Width = pi * OD1, height = max z-depth of the cope profile.

    Args:
        result: CopeResult from calculate_cope()
        od1: Incoming tube outer diameter (inches)
        tube_name: Name of the incoming tube
        node_label: User-provided node label
        has_bends: Whether the tube has bends (affects reference instructions)

    Returns:
        SVG document as a string
    """
    circumference = math.pi * od1
    max_z = max(result.z_profile) if result.z_profile else 0.0

    # Layout dimensions
    template_w = circumference
    template_h = max(max_z, 0.5)  # Minimum height for very shallow copes

    # Info block height
    info_height = _estimate_info_height(result, has_bends)

    # Total SVG size
    total_w = template_w + 2 * _MARGIN
    total_h = template_h + info_height + 3 * _MARGIN

    # Build SVG
    svg = _create_svg_root(total_w, total_h)

    # Template area
    tx = _MARGIN
    ty = _MARGIN

    # Draw template background
    _add_template_background(svg, tx, ty, template_w, template_h)

    # Draw registration marks
    _add_registration_marks(svg, tx, ty, template_w, template_h)

    # Draw profile
    stroke_width = _PROFILE_STROKE_HEAVY if result.method == "C" else _PROFILE_STROKE
    if result.is_multi_pass:
        _add_multi_pass_profile(svg, tx, ty, template_w, template_h, result)
    _add_profile_curve(svg, tx, ty, template_w, template_h, result.z_profile, stroke_width)

    # Scale bar
    _add_scale_bar(svg, tx, ty + template_h + 0.15)

    # Info section below template
    info_y = ty + template_h + _MARGIN + 0.3
    _add_info_section(svg, tx, info_y, result, od1, tube_name, node_label, has_bends)

    # Reference diagram
    ref_x = tx + template_w - _REF_CIRCLE_RADIUS - 0.1
    ref_y = info_y + 0.1
    if result.passes:
        _add_reference_diagram(svg, ref_x, ref_y, result)

    return ET.tostring(svg, encoding="unicode", xml_declaration=True)


def _create_svg_root(width: float, height: float) -> ET.Element:
    """Create the SVG root element with proper dimensions for 1:1 printing."""
    svg = ET.Element("svg")
    svg.set("xmlns", "http://www.w3.org/2000/svg")
    svg.set("width", f"{width}in")
    svg.set("height", f"{height}in")
    svg.set("viewBox", f"0 0 {width} {height}")
    return svg


def _add_template_background(
    svg: ET.Element, x: float, y: float, w: float, h: float,
) -> None:
    """Draw the template area background and border."""
    rect = ET.SubElement(svg, "rect")
    rect.set("x", f"{x}")
    rect.set("y", f"{y}")
    rect.set("width", f"{w}")
    rect.set("height", f"{h}")
    rect.set("fill", "white")
    rect.set("stroke", "#333333")
    rect.set("stroke-width", "0.01")


def _add_registration_marks(
    svg: ET.Element, x: float, y: float, w: float, h: float,
) -> None:
    """Add centerline and 90-degree registration marks."""
    center_x = x + w / 2

    # Centerline at phi=0 (apex)
    _add_dashed_line(svg, center_x, y, center_x, y + h, "#CC3333", 0.01)
    _add_text(svg, center_x, y - 0.03, "APEX", _FONT_SIZE_SMALL, "#CC3333", "middle")

    # +90 and -90 degree marks
    quarter = w / 4
    _add_dashed_line(svg, center_x - quarter, y, center_x - quarter, y + h, "#666666", 0.005)
    _add_text(svg, center_x - quarter, y - 0.03, "90\u00b0", _FONT_SIZE_SMALL, "#666666", "middle")

    _add_dashed_line(svg, center_x + quarter, y, center_x + quarter, y + h, "#666666", 0.005)
    _add_text(svg, center_x + quarter, y - 0.03, "90\u00b0", _FONT_SIZE_SMALL, "#666666", "middle")


def _add_profile_curve(
    svg: ET.Element, x: float, y: float, w: float, h: float,
    z_profile: list[float], stroke_width: float,
) -> None:
    """Draw the cope profile curve as an SVG path."""
    if not z_profile:
        return

    max_z = max(z_profile) if max(z_profile) > 0 else 1.0
    points: list[str] = []

    for i, z in enumerate(z_profile):
        px = x + (i / 360.0) * w
        py = y + h - (z / max_z) * h  # Flip Y: z=0 at bottom
        prefix = "M" if i == 0 else "L"
        points.append(f"{prefix}{px:.4f},{py:.4f}")

    path = ET.SubElement(svg, "path")
    path.set("d", " ".join(points))
    path.set("fill", "none")
    path.set("stroke", "#000000")
    path.set("stroke-width", f"{stroke_width}")
    path.set("stroke-linejoin", "round")


def _add_multi_pass_profile(
    svg: ET.Element, x: float, y: float, w: float, h: float,
    result: CopeResult,
) -> None:
    """Add color-coded lobe fills for multi-pass copes."""
    if not result.z_profile:
        return

    max_z = max(result.z_profile) if max(result.z_profile) > 0 else 1.0
    baseline_y = y + h  # z=0 line

    for pass_idx, cope_pass in enumerate(result.passes):
        color = _LOBE_COLORS[pass_idx % len(_LOBE_COLORS)]
        rotation = cope_pass.rotation_mark

        # Find the lobe region: degrees where this pass dominates
        lobe_center_deg = rotation
        half_span = cope_pass.lobe_span_degrees / 2

        points: list[str] = []
        # Build filled polygon: baseline → profile → baseline
        started = False
        for i in range(360):
            dist = abs(i - lobe_center_deg)
            if dist > 180:
                dist = 360 - dist
            if dist > half_span:
                continue

            px = x + (i / 360.0) * w
            pz = result.z_profile[i]
            py = baseline_y - (pz / max_z) * h

            if not started:
                # Start at baseline
                points.append(f"M{px:.4f},{baseline_y:.4f}")
                started = True
            points.append(f"L{px:.4f},{py:.4f}")

        if points:
            # Close back to baseline
            last_px = x + (((int(lobe_center_deg + half_span)) % 360) / 360.0) * w
            points.append(f"L{last_px:.4f},{baseline_y:.4f}")
            points.append("Z")

            fill_path = ET.SubElement(svg, "path")
            fill_path.set("d", " ".join(points))
            fill_path.set("fill", color)
            fill_path.set("fill-opacity", "0.3")
            fill_path.set("stroke", "none")

            # Pass label
            label_x = x + (lobe_center_deg / 360.0) * w
            label_y = baseline_y - (cope_pass.plunge_depth / max_z) * h - 0.05
            label = f"PASS {pass_idx + 1}"
            if cope_pass.dominant:
                label += " (PRIMARY)"
            else:
                label += " (SECONDARY)"
            _add_text(svg, label_x, label_y, label, _FONT_SIZE_SMALL, color, "middle")


def _add_scale_bar(svg: ET.Element, x: float, y: float) -> None:
    """Add a 1-inch scale bar for print verification."""
    bar_y = y
    _add_line(svg, x, bar_y, x + _SCALE_BAR_LENGTH, bar_y, "#000000", 0.015)
    # End ticks
    _add_line(svg, x, bar_y - 0.05, x, bar_y + 0.05, "#000000", 0.01)
    _add_line(svg, x + _SCALE_BAR_LENGTH, bar_y - 0.05, x + _SCALE_BAR_LENGTH, bar_y + 0.05, "#000000", 0.01)
    _add_text(svg, x + _SCALE_BAR_LENGTH / 2, bar_y + 0.12, '1" scale bar — verify before cutting',
              _FONT_SIZE_SMALL, "#000000", "middle")


def _add_info_section(
    svg: ET.Element, x: float, y: float,
    result: CopeResult, od1: float, tube_name: str,
    node_label: str, has_bends: bool,
) -> None:
    """Add the information section below the template."""
    line_y = y

    # Title
    title = f"Cope Template — {tube_name}" if tube_name else "Cope Template"
    if node_label:
        title += f" at {node_label}"
    _add_text(svg, x, line_y, title, _FONT_SIZE_TITLE, "#000000", "start")
    line_y += 0.25

    # Method recommendation
    method_colors = {"A": "#2266AA", "B": "#CC8800", "C": "#CC6600"}
    method_labels = {
        "A": "Method A — Notcher, single pass",
        "B": "Method B — Notcher, multi-pass",
        "C": "Method C — Wrap template + grinder",
    }
    _add_text(svg, x, line_y, method_labels[result.method],
              _FONT_SIZE_LABEL, method_colors[result.method], "start")
    line_y += 0.2

    # Tube OD
    _add_text(svg, x, line_y, f"Tube OD: {od1:.3f}\"", _FONT_SIZE_SMALL, "#333333", "start")
    line_y += 0.15

    # Reference
    _add_text(svg, x, line_y, f"Reference: {result.reference_description}",
              _FONT_SIZE_SMALL, "#333333", "start")
    line_y += 0.2

    # Per-pass details
    for i, cope_pass in enumerate(result.passes):
        label = f"Pass {i + 1}" if len(result.passes) > 1 else "Settings"
        if cope_pass.dominant and len(result.passes) > 1:
            label += " (PRIMARY)"
        _add_text(svg, x, line_y, label, _FONT_SIZE_LABEL, "#000000", "start")
        line_y += 0.15

        _add_text(svg, x + 0.1, line_y,
                  f"Notcher angle: {cope_pass.notcher_angle:.1f}\u00b0",
                  _FONT_SIZE_SMALL, "#333333", "start")
        line_y += 0.13

        _add_text(svg, x + 0.1, line_y,
                  f"Rotation mark: {cope_pass.rotation_mark:.1f}\u00b0 CW from reference",
                  _FONT_SIZE_SMALL, "#333333", "start")
        line_y += 0.13

        if cope_pass.is_pass_through:
            _add_text(svg, x + 0.1, line_y, "Pass type: Push through",
                      _FONT_SIZE_SMALL, "#333333", "start")
        else:
            _add_text(svg, x + 0.1, line_y,
                      f"Plunge depth: {cope_pass.plunge_depth:.3f}\" — DO NOT pass through",
                      _FONT_SIZE_SMALL, _WARNING_COLOR, "start")
        line_y += 0.13

        _add_text(svg, x + 0.1, line_y,
                  f"Min. holesaw depth: {cope_pass.holesaw_depth_required:.2f}\"",
                  _FONT_SIZE_SMALL, "#333333", "start")
        line_y += 0.13

        if cope_pass.holesaw_warning:
            _add_text(svg, x + 0.1, line_y, cope_pass.holesaw_warning,
                      _FONT_SIZE_SMALL, _WARNING_COLOR, "start")
            line_y += 0.13

        line_y += 0.05

    # Warning block for multi-pass
    if result.is_multi_pass:
        line_y += 0.1
        _add_warning_block(svg, x, line_y, result)
        line_y += 0.8

    # Method C guidance
    if result.method == "C":
        line_y += 0.05
        _add_text(svg, x, line_y, "GRINDER GUIDANCE:", _FONT_SIZE_LABEL, "#CC6600", "start")
        line_y += 0.15
        _add_text(svg, x + 0.1, line_y,
                  "Start at shallowest material, work toward deepest. Check fit frequently.",
                  _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.12
        _add_text(svg, x + 0.1, line_y,
                  'Leave 1/32" proud of scribe line — final fit with die grinder in place.',
                  _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.15

    # Print instructions
    line_y += 0.1
    _add_print_instructions(svg, x, line_y)
    line_y += 0.6

    # Bent tube procedure
    if has_bends:
        _add_bent_tube_procedure(svg, x, line_y, result)


def _add_warning_block(
    svg: ET.Element, x: float, y: float, result: CopeResult,
) -> None:
    """Add multi-pass warning block with red border."""
    # Red border box
    rect = ET.SubElement(svg, "rect")
    rect.set("x", f"{x}")
    rect.set("y", f"{y}")
    rect.set("width", "4.5")
    rect.set("height", "0.7")
    rect.set("fill", "#FFF0F0")
    rect.set("stroke", _WARNING_COLOR)
    rect.set("stroke-width", "0.02")

    _add_text(svg, x + 0.1, y + 0.15,
              "MULTI-PASS COPE REQUIRED", _FONT_SIZE_LABEL, _WARNING_COLOR, "start")
    _add_text(svg, x + 0.1, y + 0.3,
              "This cope CANNOT be made in a single pass through the notcher.",
              _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
    _add_text(svg, x + 0.1, y + 0.42,
              "Attempting a single pass-through will remove material that should remain.",
              _FONT_SIZE_INSTRUCTIONS, "#333333", "start")

    line_y = y + 0.55
    for i, cope_pass in enumerate(result.passes):
        text = (f"Pass {i + 1}: {cope_pass.notcher_angle:.1f}\u00b0, "
                f"rotate {cope_pass.rotation_mark:.1f}\u00b0, "
                f"plunge to {cope_pass.plunge_depth:.3f}\"")
        _add_text(svg, x + 0.1, line_y, text, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.1


def _add_print_instructions(svg: ET.Element, x: float, y: float) -> None:
    """Add print instruction block."""
    _add_text(svg, x, y, "PRINT INSTRUCTIONS:", _FONT_SIZE_LABEL, "#000000", "start")
    instructions = [
        "1. Print at 100% scale (no fit-to-page scaling)",
        '2. Verify 1" scale bar measures exactly 1 inch',
        "3. Cut along cope profile curve only",
        "4. Wrap around tube end, aligning template centerline to rotation mark on tube",
        "5. Tape in place and scribe along bottom edge of template",
    ]
    line_y = y + 0.15
    for inst in instructions:
        _add_text(svg, x + 0.1, line_y, inst, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.1


def _add_bent_tube_procedure(
    svg: ET.Element, x: float, y: float, result: CopeResult,
) -> None:
    """Add bent tube reference setup procedure."""
    _add_text(svg, x, y, "BENT TUBE — Reference Setup:", _FONT_SIZE_LABEL, "#000000", "start")
    rotation_text = ""
    if result.passes:
        rotation_text = f"{result.passes[0].rotation_mark:.1f}"

    steps = [
        "1. Identify the back of the last bend (outside of curve, extrados)",
        "2. Mark this point on the tube end face with a permanent marker",
        "3. This mark = 0\u00b0 reference",
        "4. In the notcher chuck, align the back-of-bend mark to the 0\u00b0 position",
        f"5. Rotate {rotation_text}\u00b0 CW (viewed from coped end) to reach cope apex",
        "6. Lock chuck and verify with a protractor before cutting",
    ]
    line_y = y + 0.15
    for step in steps:
        _add_text(svg, x + 0.1, line_y, step, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.1


def _add_reference_diagram(
    svg: ET.Element, cx: float, cy: float, result: CopeResult,
) -> None:
    """Add cross-section reference diagram showing rotation angle."""
    r = _REF_CIRCLE_RADIUS

    # Circle
    circle = ET.SubElement(svg, "circle")
    circle.set("cx", f"{cx}")
    circle.set("cy", f"{cy}")
    circle.set("r", f"{r}")
    circle.set("fill", "none")
    circle.set("stroke", "#333333")
    circle.set("stroke-width", "0.01")

    # 0-degree mark (top = back of bend)
    _add_line(svg, cx, cy - r, cx, cy - r - 0.1, "#000000", 0.015)
    _add_text(svg, cx, cy - r - 0.12, "0\u00b0", _FONT_SIZE_SMALL, "#000000", "middle")

    # Rotation mark for first pass
    if result.passes:
        angle_rad = math.radians(result.passes[0].rotation_mark)
        # CW from top in SVG coordinates (positive angle = CW)
        mark_x = cx + r * math.sin(angle_rad)
        mark_y = cy - r * math.cos(angle_rad)
        _add_line(svg, cx, cy, mark_x, mark_y, _WARNING_COLOR, 0.015)

        # Arrow label
        label_x = cx + (r + 0.15) * math.sin(angle_rad)
        label_y = cy - (r + 0.15) * math.cos(angle_rad)
        _add_text(svg, label_x, label_y, "Apex",
                  _FONT_SIZE_SMALL, _WARNING_COLOR, "middle")


def _estimate_info_height(result: CopeResult, has_bends: bool) -> float:
    """Estimate the height needed for the info section."""
    height = 1.5  # Base: title + method + OD + reference + print instructions
    height += len(result.passes) * 0.7  # Per-pass details
    if result.is_multi_pass:
        height += 0.9  # Warning block
    if result.method == "C":
        height += 0.4  # Grinder guidance
    if has_bends:
        height += 0.8  # Bent tube procedure
    return height


# --- SVG helpers ---

def _add_line(
    svg: ET.Element, x1: float, y1: float, x2: float, y2: float,
    color: str, width: float,
) -> None:
    """Add a solid line to the SVG."""
    line = ET.SubElement(svg, "line")
    line.set("x1", f"{x1}")
    line.set("y1", f"{y1}")
    line.set("x2", f"{x2}")
    line.set("y2", f"{y2}")
    line.set("stroke", color)
    line.set("stroke-width", f"{width}")


def _add_dashed_line(
    svg: ET.Element, x1: float, y1: float, x2: float, y2: float,
    color: str, width: float,
) -> None:
    """Add a dashed line to the SVG."""
    line = ET.SubElement(svg, "line")
    line.set("x1", f"{x1}")
    line.set("y1", f"{y1}")
    line.set("x2", f"{x2}")
    line.set("y2", f"{y2}")
    line.set("stroke", color)
    line.set("stroke-width", f"{width}")
    line.set("stroke-dasharray", "0.05,0.03")


def _add_text(
    svg: ET.Element, x: float, y: float, text: str,
    font_size: float, color: str, anchor: str,
) -> None:
    """Add text to the SVG."""
    elem = ET.SubElement(svg, "text")
    elem.set("x", f"{x}")
    elem.set("y", f"{y}")
    elem.set("font-family", "Arial, Helvetica, sans-serif")
    elem.set("font-size", f"{font_size}")
    elem.set("fill", color)
    elem.set("text-anchor", anchor)
    elem.text = text
