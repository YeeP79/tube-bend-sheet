"""SVG wrap template generator for tube coping.

Generates 1:1 scale SVG templates that can be printed, cut out,
and wrapped around a tube to mark the cope profile for cutting.

Zero Fusion 360 dependencies. Fully unit-testable.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Literal

from ..models.cope_data import CopeResult


# SVG units: inches (1:1 scale for printing)
_MARGIN = 0.3  # Margin around template in inches
_PROFILE_STROKE = 0.02  # Normal profile stroke width
_PROFILE_STROKE_HEAVY = 0.04  # Heavy stroke for Method C
_FONT_SIZE_LABEL = 0.12  # Label font size in inches
_FONT_SIZE_TITLE = 0.18  # Title font size
_FONT_SIZE_SMALL = 0.09  # Small text
_FONT_SIZE_INSTRUCTIONS = 0.09  # Instruction text
_SCALE_BAR_LENGTH = 1.0  # 1-inch scale bar
_REF_CIRCLE_RADIUS = 0.4  # Reference diagram circle radius
_CUTTING_MARGIN = 0.5  # Extra paper on keep side for cutting grip and labels
_LOBE_COLORS = ["#4488CC", "#CC7733", "#44AA44", "#AA4488"]
_WARNING_COLOR = "#CC3333"


def generate_cope_svg(
    result: CopeResult,
    od1: float,
    tube_name: str,
    node_label: str,
    has_bends: bool,
    ref_mark_length: float = 0.5,
    location: str = "",
    waste_side: Literal["top", "bottom"] = "top",
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
        ref_mark_length: Length of reference marks on bent tubes
        location: Optional location label
        waste_side: "top" = flush with tube end (default), "bottom" = setback
                    from cut (reusable template)

    Returns:
        SVG document as a string
    """
    circumference = math.pi * od1
    max_z = max(result.z_profile) if result.z_profile else 0.0

    # For straight tubes, rotate profile 180° so REF is at template center
    if has_bends or not result.z_profile:
        display_profile: list[float] = list(result.z_profile) if result.z_profile else []
        deg_offset = 0
    else:
        half = len(result.z_profile) // 2
        display_profile = result.z_profile[half:] + result.z_profile[:half]
        deg_offset = half

    flip = waste_side == "bottom"

    # Layout dimensions
    template_w = circumference
    profile_h = max(max_z, 0.5)  # Height for profile rendering
    template_h = profile_h + _CUTTING_MARGIN

    # Info block height
    info_height = _estimate_info_height(result, has_bends, location)

    # Total SVG size (extra 0.25 for depth dimension on right)
    dim_margin = 0.25
    total_w = template_w + 2 * _MARGIN + dim_margin
    total_h = template_h + info_height + 3 * _MARGIN

    # Build SVG
    svg = _create_svg_root(total_w, total_h)

    # Template area
    tx = _MARGIN
    ty = _MARGIN

    # Draw template background
    _add_template_background(svg, tx, ty, template_w, template_h)

    # Profile area position depends on layout mode
    if flip:
        # Setback: cutting margin (header) at top, profile below
        profile_y = ty + _CUTTING_MARGIN
    else:
        # Default: profile at top, cutting margin below
        profile_y = ty

    # Registration marks: dashed lines span the full template height
    # (profile area + cutting margin) so they extend into the header
    # where the labels are placed.
    _add_registration_marks(svg, tx, ty, template_w, template_h, display_profile,
                            ref_at_center=not has_bends, flip=flip)

    # Draw profile
    stroke_width = _PROFILE_STROKE_HEAVY if result.method == "C" else _PROFILE_STROKE
    if result.is_multi_pass:
        _add_multi_pass_profile(svg, tx, profile_y, template_w, profile_h, result,
                                display_profile, deg_offset)
    _add_profile_curve(svg, tx, profile_y, template_w, profile_h, display_profile,
                       stroke_width)

    # Edge labels on the template itself
    _add_edge_labels(svg, tx, ty, template_w, template_h, profile_y, profile_h,
                     display_profile, flip=flip)

    # Alignment line (separates profile area from cutting margin)
    if flip:
        # Setback: reference edge at top of profile
        align_y = ty + _CUTTING_MARGIN
    else:
        # Default: tube end alignment at bottom of profile
        align_y = ty + profile_h
    _add_line(svg, tx, align_y, tx + template_w, align_y, "#333333", 0.02)

    # Depth dimension on right side (spans profile area)
    _add_depth_dimension(svg, tx + template_w, profile_y, profile_h, max_z)

    # Scale bar
    _add_scale_bar(svg, tx, ty + template_h + 0.15)

    # Info section below template
    info_y = ty + template_h + _MARGIN + 0.3
    _add_info_section(svg, tx, info_y, result, od1, tube_name, node_label, has_bends,
                      ref_mark_length, location, waste_side=waste_side)

    # Reference diagram — positioned below per-pass settings to avoid title overlap
    ref_x = tx + template_w - _REF_CIRCLE_RADIUS - 0.1
    ref_y = info_y + 0.25 + len(result.passes) * 0.7 + 0.3
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
    z_profile: list[float] | None = None, ref_at_center: bool = False,
    flip: bool = False,
) -> None:
    """Add REF marks, APEX at profile peak, and 90-degree gridlines.

    Dashed lines span the full template height (profile + cutting margin).
    Labels are placed vertically in the cutting margin (header) area so
    they survive after cutting along the profile curve.

    Args:
        flip: When True (setback mode), header is at top; when False
              (default mode), header is at bottom.
    """
    # Vertical text (rotate -90) reads bottom-to-top: text-anchor "start"
    # means the text begins at (x,y) and extends upward (toward smaller y).
    # Place labels in the cutting margin area (the header/keep side).
    x_offset = 0.03
    if flip:
        # Setback: header at top — label near alignment line, text extends up
        label_y = y + _CUTTING_MARGIN - 0.05
    else:
        # Default: header at bottom — label near alignment line, text extends up
        label_y = y + h - 0.05

    if ref_at_center:
        # Single REF at center for straight tubes
        cx = x + w / 2
        _add_dashed_line(svg, cx, y, cx, y + h, "#22AA44", 0.015)
        _add_vertical_text(svg, cx + x_offset, label_y, "REF",
                           _FONT_SIZE_SMALL, "#22AA44")
    else:
        # REF at both edges for bent tubes (edges meet at back-of-bend reference)
        _add_dashed_line(svg, x, y, x, y + h, "#22AA44", 0.015)
        _add_vertical_text(svg, x + x_offset, label_y, "REF",
                           _FONT_SIZE_SMALL, "#22AA44")
        _add_dashed_line(svg, x + w, y, x + w, y + h, "#22AA44", 0.015)
        _add_vertical_text(svg, x + w + x_offset, label_y, "REF",
                           _FONT_SIZE_SMALL, "#22AA44")

    # APEX at actual profile peak position
    if z_profile:
        peak_idx = max(range(len(z_profile)), key=lambda i: z_profile[i])
    else:
        peak_idx = 180
    apex_x = x + (peak_idx / 360.0) * w
    _add_dashed_line(svg, apex_x, y, apex_x, y + h, "#CC3333", 0.01)
    _add_vertical_text(svg, apex_x + x_offset, label_y, "APEX",
                       _FONT_SIZE_SMALL, "#CC3333")

    # 90-degree and 270-degree gridlines (fixed angular positions)
    quarter = w / 4
    center_x = x + w / 2
    _add_dashed_line(svg, center_x - quarter, y, center_x - quarter, y + h, "#666666", 0.005)
    _add_vertical_text(svg, center_x - quarter + x_offset, label_y,
                       "90\u00b0", _FONT_SIZE_SMALL, "#666666")

    _add_dashed_line(svg, center_x + quarter, y, center_x + quarter, y + h, "#666666", 0.005)
    _add_vertical_text(svg, center_x + quarter + x_offset, label_y,
                       "90\u00b0", _FONT_SIZE_SMALL, "#666666")


def _add_profile_curve(
    svg: ET.Element, x: float, y: float, w: float, h: float,
    z_profile: list[float], stroke_width: float,
) -> None:
    """Draw the cope profile curve as an SVG path.

    z=0 (tube end) maps to the bottom of the profile area,
    z=max (APEX) maps to the top. This mapping is the same
    regardless of template layout mode.
    """
    if not z_profile:
        return

    max_z = max(z_profile) if max(z_profile) > 0 else 1.0
    points: list[str] = []

    for i, z in enumerate(z_profile):
        px = x + (i / 360.0) * w
        py = y + h - (z / max_z) * h  # z=0 at bottom, z=max at top
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
    result: CopeResult, z_profile: list[float], deg_offset: int = 0,
) -> None:
    """Add color-coded lobe fills for multi-pass copes.

    Baseline (z=0) is always at the bottom of the profile area,
    fills extend upward toward z=max. Same in both layout modes.
    """
    if not z_profile:
        return

    max_z = max(z_profile) if max(z_profile) > 0 else 1.0
    baseline_y = y + h  # z=0 line at bottom

    for pass_idx, cope_pass in enumerate(result.passes):
        color = _LOBE_COLORS[pass_idx % len(_LOBE_COLORS)]
        rotation = cope_pass.rotation_mark

        # Shift lobe center for display profile rotation
        lobe_center_deg = (rotation - deg_offset) % 360
        half_span = cope_pass.lobe_span_degrees / 2

        # Collect degree indices in the lobe, sorted by degree
        lobe_degrees: list[int] = []
        for i in range(360):
            dist = abs(i - lobe_center_deg)
            if dist > 180:
                dist = 360 - dist
            if dist <= half_span:
                lobe_degrees.append(i)

        if not lobe_degrees:
            continue

        # Detect wrap-around: if degree indices jump (e.g., 358,359,0,1)
        # split into contiguous segments for proper SVG rendering
        segments: list[list[int]] = []
        current_seg: list[int] = [lobe_degrees[0]]
        for j in range(1, len(lobe_degrees)):
            if lobe_degrees[j] - lobe_degrees[j - 1] > 1:
                segments.append(current_seg)
                current_seg = []
            current_seg.append(lobe_degrees[j])
        segments.append(current_seg)

        # Draw each contiguous segment as a filled polygon
        for seg in segments:
            points: list[str] = []
            first_px = x + (seg[0] / 360.0) * w
            points.append(f"M{first_px:.4f},{baseline_y:.4f}")

            for i in seg:
                px = x + (i / 360.0) * w
                pz = z_profile[i]
                py_val = baseline_y - (pz / max_z) * h  # Extend upward
                points.append(f"L{px:.4f},{py_val:.4f}")

            # Close back to baseline
            last_px = x + (seg[-1] / 360.0) * w
            points.append(f"L{last_px:.4f},{baseline_y:.4f}")
            points.append("Z")

            fill_path = ET.SubElement(svg, "path")
            fill_path.set("d", " ".join(points))
            fill_path.set("fill", color)
            fill_path.set("fill-opacity", "0.3")
            fill_path.set("stroke", "none")

        # Pass label (placed at lobe center, clamped to template bounds)
        label_x = x + (lobe_center_deg / 360.0) * w
        label_x = max(x + 0.3, min(label_x, x + w - 0.3))
        label_y = baseline_y - (cope_pass.plunge_depth / max_z) * h - 0.05
        label = f"PASS {pass_idx + 1}"
        if cope_pass.dominant:
            label += " (PRIMARY)"
        else:
            label += " (SECONDARY)"
        _add_text(svg, label_x, label_y, label, _FONT_SIZE_SMALL, color, "middle")


def _add_edge_labels(
    svg: ET.Element, x: float, y: float, w: float, template_h: float,
    profile_y: float, profile_h: float,
    z_profile: list[float], flip: bool = False,
) -> None:
    """Add orientation labels to the template: alignment edge, CUT LINE, and WASTE.

    Args:
        x: Template left x.
        y: Template top y.
        w: Template width.
        template_h: Total template height (profile + cutting margin).
        profile_y: Top y of the profile area.
        profile_h: Height of the profile area.
        z_profile: Profile depth values.
        flip: When True, waste is at bottom (setback mode).
    """
    if flip:
        # Setback mode: straight reference edge at top, waste at bottom
        # Top label (above alignment line): straight edge sits at cope depth from tube end
        _add_text(svg, x + w / 2, y + 0.12,
                  "\u2190 REFERENCE EDGE \u2014 place at cope depth from tube end \u2192",
                  _FONT_SIZE_SMALL, "#666666", "middle")
        # Bottom label: waste below the profile curve
        _add_text(svg, x + w / 2, y + template_h - 0.04,
                  "WASTE \u2014 discard below curve",
                  _FONT_SIZE_SMALL, "#AAAAAA", "middle")
    else:
        # Default mode: waste at top, tube end at bottom
        # Bottom label: "TUBE END — align flush"
        bottom_y = profile_y + profile_h
        _add_text(svg, x + w / 2, bottom_y - 0.04,
                  "\u2190 TUBE END \u2014 align flush \u2192",
                  _FONT_SIZE_SMALL, "#666666", "middle")
        # Top label: "WASTE — discard after cutting"
        _add_text(svg, x + w / 2, y + 0.12,
                  "WASTE \u2014 discard above curve",
                  _FONT_SIZE_SMALL, "#AAAAAA", "middle")

    # Scissors + "CUT LINE" near the profile curve start
    if z_profile:
        max_z = max(z_profile) if max(z_profile) > 0 else 1.0
        start_z = z_profile[0]
        start_py = profile_y + profile_h - (start_z / max_z) * profile_h
        _add_text(svg, x + 0.05, start_py - 0.04,
                  "\u2702 CUT LINE", _FONT_SIZE_SMALL, "#000000", "start")


def _add_depth_dimension(
    svg: ET.Element, template_right: float, y: float,
    h: float, max_z: float,
) -> None:
    """Draw a vertical depth dimension on the right side of the template."""
    if max_z <= 0:
        return

    dim_x = template_right + 0.08  # Offset right from template edge
    top_y = y
    bottom_y = y + h

    # Vertical dimension line
    _add_line(svg, dim_x, top_y, dim_x, bottom_y, "#555555", 0.008)

    # Tick marks (horizontal)
    tick_len = 0.04
    _add_line(svg, dim_x - tick_len, top_y, dim_x + tick_len, top_y, "#555555", 0.008)
    _add_line(svg, dim_x - tick_len, bottom_y, dim_x + tick_len, bottom_y, "#555555", 0.008)

    # Dimension label (rotated text via transform)
    label_x = dim_x + 0.06
    label_y = y + h / 2
    text = ET.SubElement(svg, "text")
    text.set("x", f"{label_x}")
    text.set("y", f"{label_y}")
    text.set("font-family", "Arial, Helvetica, sans-serif")
    text.set("font-size", f"{_FONT_SIZE_SMALL}")
    text.set("fill", "#555555")
    text.set("text-anchor", "middle")
    text.set("transform", f"rotate(90,{label_x},{label_y})")
    text.text = f"{max_z:.3f}\""


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
    ref_mark_length: float = 0.5,
    location: str = "",
    waste_side: Literal["top", "bottom"] = "top",
) -> None:
    """Add the information section below the template."""
    line_y = y

    # Title
    title = f"Cope Template — {tube_name}" if tube_name else "Cope Template"
    if node_label:
        title += f" at {node_label}"
    _add_text(svg, x, line_y, title, _FONT_SIZE_TITLE, "#000000", "start")
    line_y += 0.25

    # Location (when provided)
    if location:
        _add_text(svg, x, line_y, f"Location: {location}",
                  _FONT_SIZE_LABEL, "#555555", "start")
        line_y += 0.2

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

    # Receiving tube names (use all_receiver_names to include merged receivers)
    receiver_names = result.all_receiver_names or [
        p.receiver_name for p in result.passes if p.receiver_name
    ]
    if receiver_names:
        names_str = ", ".join(dict.fromkeys(receiver_names))  # dedupe, preserve order
        _add_text(svg, x, line_y, f"Receiving: {names_str}",
                  _FONT_SIZE_SMALL, "#333333", "start")
        line_y += 0.15

    # Cope depth
    max_z = max(result.z_profile) if result.z_profile else 0.0
    _add_text(svg, x, line_y, f"Cope depth: {max_z:.3f}\" from tube end",
              _FONT_SIZE_SMALL, "#333333", "start")
    line_y += 0.15

    # Reference
    _add_text(svg, x, line_y, f"Reference: {result.reference_description}",
              _FONT_SIZE_SMALL, "#333333", "start")
    line_y += 0.2

    # Per-pass details
    for i, cope_pass in enumerate(result.passes):
        label = f"Pass {i + 1}" if len(result.passes) > 1 else "Settings"
        if cope_pass.receiver_name:
            label += f" \u2014 {cope_pass.receiver_name}"
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

    # Print verification
    circumference = math.pi * od1
    max_z = max(result.z_profile) if result.z_profile else 0.0
    line_y += 0.1
    line_y = _add_print_verification(svg, x, line_y, circumference)
    line_y += 0.1

    # Template usage
    line_y = _add_template_usage(svg, x, line_y, max_z, waste_side=waste_side)
    line_y += 0.1

    # Method-specific procedure
    if result.method == "C":
        _add_text(svg, x, line_y, "GRINDER GUIDANCE:", _FONT_SIZE_LABEL, "#CC6600", "start")
        line_y += 0.15
        _add_text(svg, x + 0.1, line_y,
                  "Start at shallowest material, work toward deepest. Check fit frequently.",
                  _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.12
        _add_text(svg, x + 0.1, line_y,
                  'Leave 1/32" proud of scribe line \u2014 final fit with die grinder in place.',
                  _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.15
    else:
        line_y = _add_notcher_procedure(svg, x, line_y, result)
        line_y += 0.1

    # Bent tube procedure
    if has_bends:
        _add_bent_tube_procedure(svg, x, line_y, result, ref_mark_length)


def _add_print_verification(
    svg: ET.Element, x: float, y: float, circumference: float,
) -> float:
    """Add print scale verification steps. Returns y after last line."""
    _add_text(svg, x, y, "PRINT VERIFICATION:", _FONT_SIZE_LABEL, "#000000", "start")
    steps = [
        "1. Print at 100% scale (no fit-to-page scaling)",
        '2. Verify 1" scale bar measures exactly 1 inch',
        f'3. Template width should measure {circumference:.3f}" (\u03c0 \u00d7 OD) \u2014 adjust print scale if not',
    ]
    line_y = y + 0.18
    for step in steps:
        _add_text(svg, x + 0.1, line_y, step, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.13
    return line_y


def _add_template_usage(
    svg: ET.Element, x: float, y: float, max_z: float,
    waste_side: Literal["top", "bottom"] = "top",
) -> float:
    """Add physical template application steps. Returns y after last line."""
    _add_text(svg, x, y, "TEMPLATE USAGE:", _FONT_SIZE_LABEL, "#000000", "start")
    if waste_side == "bottom":
        steps = [
            "1. Cut out along the cope profile curve (\u2702 CUT LINE)",
            "2. Discard the WASTE piece below the curve; keep the piece with the straight REFERENCE EDGE",
            f"3. Mark the tube {max_z:.3f}\" from the end (the cope depth)",
            "4. Wrap template around tube with the straight REFERENCE EDGE at the cope-depth mark",
            "5. Align green REF marks on template to reference marks on tube",
            "6. Tape in place, then scribe along the profile curve (the cut edge)",
            "7. Remove template \u2014 rough-cut near the scribe line",
            "8. Re-wrap template (the reference edge and mark are still intact) and re-scribe for a precise cut",
        ]
    else:
        steps = [
            "1. Cut out along the cope profile curve (\u2702 CUT LINE)",
            "2. Discard the WASTE piece above the curve; keep the piece with the straight TUBE END edge",
            "3. Wrap around tube with the straight TUBE END edge flush against the tube end",
            "4. Align green REF marks on template to reference marks on tube",
            "5. Tape in place, then scribe along the profile curve (the cut edge)",
            "6. Remove template \u2014 cut/grind away material between the scribe line and tube end",
        ]
    line_y = y + 0.18
    for step in steps:
        _add_text(svg, x + 0.1, line_y, step, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.13
    # Note about cope depth
    _add_text(svg, x + 0.1, line_y,
              f"Cope depth: {max_z:.3f}\" from tube end at the deepest point (apex).",
              _FONT_SIZE_INSTRUCTIONS, "#555555", "start")
    line_y += 0.13
    return line_y


def _add_notcher_procedure(
    svg: ET.Element, x: float, y: float, result: CopeResult,
) -> float:
    """Add method-specific notcher cutting procedure. Returns y after last line."""
    if result.method == "A":
        return _add_notcher_procedure_a(svg, x, y, result)
    elif result.method == "B":
        return _add_notcher_procedure_b(svg, x, y, result)
    # Method C uses grinder guidance instead — no notcher procedure
    return y


def _add_notcher_procedure_a(
    svg: ET.Element, x: float, y: float, result: CopeResult,
) -> float:
    """Add single-pass notcher procedure (Method A). Returns y after last line."""
    cope_pass = result.passes[0]
    _add_text(svg, x, y, "NOTCHER PROCEDURE:", _FONT_SIZE_LABEL, "#2266AA", "start")
    steps = [
        f"1. Set notcher degree wheel to {cope_pass.notcher_angle:.1f}\u00b0",
        f"2. Mark tube at {cope_pass.rotation_mark:.1f}\u00b0 CW from reference (or align to template APEX mark)",
        "3. Align the rotation mark with the center of the holesaw",
        "4. Push tube through the holesaw in a single continuous pass",
        "5. Compare cut profile against the printed template to verify",
    ]
    line_y = y + 0.18
    for step in steps:
        _add_text(svg, x + 0.1, line_y, step, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.13
    return line_y


def _add_notcher_procedure_b(
    svg: ET.Element, x: float, y: float, result: CopeResult,
) -> float:
    """Add multi-pass notcher procedure (Method B). Returns y after last line."""
    _add_text(svg, x, y, "NOTCHER PROCEDURE \u2014 MULTI-PASS:",
              _FONT_SIZE_LABEL, _WARNING_COLOR, "start")
    line_y = y + 0.18
    _add_text(svg, x + 0.1, line_y,
              "\u26a0 DO NOT push tube through the holesaw on any pass.",
              _FONT_SIZE_INSTRUCTIONS, _WARNING_COLOR, "start")
    line_y += 0.13
    _add_text(svg, x + 0.1, line_y,
              "Each pass is a controlled plunge to a specific depth.",
              _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
    line_y += 0.18

    for i, cope_pass in enumerate(result.passes):
        label = f"Pass {i + 1}"
        if cope_pass.dominant:
            label += " (PRIMARY)"
        _add_text(svg, x + 0.1, line_y, f"{label}:", _FONT_SIZE_LABEL, "#000000", "start")
        line_y += 0.15
        _add_text(svg, x + 0.2, line_y,
                  f"a. Set notcher degree wheel to {cope_pass.notcher_angle:.1f}\u00b0",
                  _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.13
        _add_text(svg, x + 0.2, line_y,
                  f"b. Rotate tube {cope_pass.rotation_mark:.1f}\u00b0 CW from reference",
                  _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.13
        _add_text(svg, x + 0.2, line_y,
                  f"c. Plunge to {cope_pass.plunge_depth:.3f}\" depth \u2014 STOP and withdraw",
                  _FONT_SIZE_INSTRUCTIONS, _WARNING_COLOR, "start")
        line_y += 0.18

    _add_text(svg, x + 0.1, line_y,
              "After all passes, compare cut profile against the printed template.",
              _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
    line_y += 0.13
    return line_y


def _add_bent_tube_procedure(
    svg: ET.Element, x: float, y: float, result: CopeResult,
    ref_mark_length: float = 0.5,
) -> None:
    """Add bent tube reference setup procedure."""
    _add_text(svg, x, y, "BENT TUBE \u2014 Reference Mark Alignment:",
              _FONT_SIZE_LABEL, "#000000", "start")
    rotation_text = ""
    if result.passes:
        rotation_text = f"{result.passes[0].rotation_mark:.1f}"

    # Format mark length as fraction if applicable
    mark_text = f'{ref_mark_length:.2g}"'

    steps = [
        f"1. Locate the {mark_text} reference marks at each tube end (marked before bending)",
        "2. Wrap template around tube end with REF marks aligned to reference marks",
        "3. Tape in place and scribe along the cope profile curve (the cut edge of template)",
        f"4. Rotation mark: {rotation_text}\u00b0 CW from reference \u2014 use for verification only",
    ]
    line_y = y + 0.18
    for step in steps:
        _add_text(svg, x + 0.1, line_y, step, _FONT_SIZE_INSTRUCTIONS, "#333333", "start")
        line_y += 0.13


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


def _estimate_info_height(result: CopeResult, has_bends: bool, location: str = "") -> float:
    """Estimate the height needed for the info section."""
    # Base: title + method + OD + cope depth + reference
    height = 0.95
    if location:
        height += 0.2
    # Receiving tube names line
    if result.all_receiver_names or any(p.receiver_name for p in result.passes):
        height += 0.15
    # Per-pass settings
    height += len(result.passes) * 0.7
    # Print verification (header + 3 lines)
    height += 0.55
    # Template usage (header + up to 8 lines + note)
    height += 1.4
    # Method-specific procedure
    if result.method == "C":
        height += 0.4  # Grinder guidance
    elif result.method == "A":
        height += 0.9  # Notcher procedure (header + 5 lines)
    elif result.method == "B":
        height += 0.6 + len(result.passes) * 0.4  # Multi-pass procedure
    if has_bends:
        height += 0.75  # Bent tube procedure
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


def _add_vertical_text(
    svg: ET.Element, x: float, y: float, text: str,
    font_size: float, color: str,
) -> None:
    """Add vertically rotated text (reads bottom-to-top)."""
    elem = ET.SubElement(svg, "text")
    elem.set("x", f"{x}")
    elem.set("y", f"{y}")
    elem.set("font-family", "Arial, Helvetica, sans-serif")
    elem.set("font-size", f"{font_size}")
    elem.set("fill", color)
    elem.set("text-anchor", "start")
    elem.set("transform", f"rotate(-90,{x},{y})")
    elem.text = text
