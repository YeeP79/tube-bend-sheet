"""HTML bend sheet generator."""

from __future__ import annotations

import html as html_lib

from ..models.bend_data import BendSheetData
from .formatting import format_length, get_precision_label


def _escape_html(text: str | None) -> str:
    """
    Escape HTML special characters to prevent XSS.

    Args:
        text: Text to escape, or None

    Returns:
        Escaped text, or empty string if None
    """
    if text is None:
        return ""
    return html_lib.escape(str(text), quote=True)


def _generate_html_head() -> str:
    """Generate the DOCTYPE, head element, and CSS styles."""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tube Bend Sheet</title>
    <style>
        * { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
        body { max-width: 8.5in; margin: 0 auto; padding: 0.5in; font-size: 11pt; line-height: 1.4; }
        h1 { font-size: 18pt; margin-bottom: 0.1in; border-bottom: 2px solid #333; padding-bottom: 0.1in; }
        h2 { font-size: 14pt; color: #444; margin-top: 0; margin-bottom: 0.2in; }
        h3 { font-size: 12pt; margin-top: 0.3in; margin-bottom: 0.1in; color: #333; }
        .header-info { font-size: 12pt; font-weight: bold; margin-bottom: 0.2in; }
        .bender-info { font-size: 10pt; color: #666; margin-bottom: 0.15in; }
        .warning { color: #c00; font-weight: bold; margin-bottom: 0.1in; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 0.2in; font-size: 10pt; }
        th, td { border: 1px solid #333; padding: 4px 8px; text-align: left; }
        th { background-color: #f0f0f0; font-weight: bold; }
        .right { text-align: right; }
        .center { text-align: center; }
        .bend-row { background-color: #e8e8e8; }
        .grip-warning { background-color: #fff3cd; }
        .grip-warning-icon { color: #856404; }
        .procedure { margin-top: 0.2in; }
        .procedure ol { margin: 0; padding-left: 0.3in; }
        .procedure li { margin-bottom: 0.05in; }
        hr { border: none; border-top: 1px solid #999; margin: 0.2in 0; }
        .specs-table { width: auto; min-width: 3in; }
        .specs-table td:first-child { font-weight: bold; background-color: #f8f8f8; }
        .notes-section { margin-top: 0.3in; }
        .notes-box { border: 1px solid #333; padding: 10px; margin: 10px 0; min-height: 0.8in; }
        .notes-box h4 { margin: 0 0 5px 0; font-size: 11pt; color: #333; }
        .notes-box p { margin: 0; font-size: 10pt; white-space: pre-wrap; }
        .user-notes { min-height: 1.5in; background: repeating-linear-gradient(#fff, #fff 23px, #e0e0e0 24px); }
        @media print { body { padding: 0; } }
    </style>
</head>
<body>
"""


def _generate_title_section(data: BendSheetData) -> str:
    """Generate the title, component name, and bender/die info."""
    precision = data.precision
    units = data.units

    html = "<h1>TUBE BEND SHEET</h1>\n"
    if data.component_name:
        html += f"<h2>{_escape_html(data.component_name)}</h2>\n"

    # Bender/die info
    if data.bender_name or data.die_name:
        bender_parts = []
        if data.bender_name:
            bender_parts.append(f"Bender: {_escape_html(data.bender_name)}")
        if data.die_name:
            bender_parts.append(f"Die: {_escape_html(data.die_name)}")
        html += f'<div class="bender-info">{" | ".join(bender_parts)}</div>\n'

    # Header info
    html += f'<div class="header-info">Cut Length: {format_length(data.total_cut_length, precision, units)} '
    html += f'&nbsp;|&nbsp; CLR: {format_length(data.clr, precision, units)}</div>\n'

    return html


def _generate_warnings_section(data: BendSheetData) -> str:
    """Generate validation warnings (CLR mismatch, continuity errors, grip warnings)."""
    html = ""
    precision = data.precision
    units = data.units

    if data.clr_mismatch:
        clr_list = ", ".join([f"{c:.3f}{units.unit_symbol}" for c in data.clr_values])
        html += f'<div class="warning">⚠️ CLR Mismatch: {clr_list}</div>\n'
    if data.continuity_errors:
        html += f'<div class="warning">⚠️ Continuity Errors: {", ".join(data.continuity_errors)}</div>\n'
    if data.grip_violations:
        sections_list = ", ".join(f"Straight {n}" for n in data.grip_violations)
        html += f'<div class="warning">⚠️ Grip Warning: {sections_list} shorter than min grip '
        html += f'({format_length(data.min_grip, precision, units)})</div>\n'
    if data.tail_violation:
        last_straight_num = len(data.straights)
        html += f'<div class="warning">⚠️ Tail Warning: Straight {last_straight_num} shorter than min tail '
        html += f'({format_length(data.min_tail, precision, units)})</div>\n'

    if data.spring_back_warning:
        last_bend_num = len(data.bends)
        html += (
            f'<div class="warning">⚠️ Spring Back Warning: '
            f'Tail extension applied without end allowance. '
            f'Bend #{last_bend_num} may not have enough material due to spring back. '
            f'Consider adding End Allowance.</div>\n'
        )

    return html


def _generate_cut_instructions(data: BendSheetData) -> str:
    """Generate cut instructions for synthetic grip/tail material."""
    if not data.has_synthetic_grip and not data.has_synthetic_tail:
        return ""

    precision = data.precision
    units = data.units

    html = '<div class="cut-instructions" style="background-color: #d4edda; border: 1px solid #28a745; '
    html += 'border-radius: 4px; padding: 10px; margin: 10px 0;">\n'
    html += '<h3 style="margin-top: 0; color: #155724;">✂️ Cut Instructions</h3>\n'
    html += '<p style="margin-bottom: 8px;"><b>This tube requires trimming after bending:</b></p>\n'
    html += '<ul style="margin: 0; padding-left: 20px;">\n'

    if data.has_synthetic_grip and data.grip_cut_position is not None:
        html += f'<li>Cut <b>{format_length(data.grip_cut_position, precision, units)}</b> '
        html += 'from <b>START</b> of tube (grip material added because path starts with bend)</li>\n'

    if data.has_synthetic_tail and data.tail_cut_position is not None:
        tail_cut_from_end = data.total_cut_length - data.tail_cut_position
        html += f'<li>Cut <b>{format_length(tail_cut_from_end, precision, units)}</b> '
        html += 'from <b>END</b> of tube (tail material added because path ends with bend)</li>\n'

    html += '</ul>\n</div>\n'
    return html


def _generate_bend_table(data: BendSheetData) -> str:
    """Generate the main bend data table showing pure path geometry.

    This table shows the actual tube path geometry starting at 0, not the
    positions on the cut tube (which includes extra grip/tail material).
    """
    precision = data.precision
    units = data.units

    # Extra material offset to subtract for pure geometry display
    extra_offset = data.extra_material

    html = "<hr>\n<h3>Path Geometry</h3>\n<table>\n"
    html += "<tr><th class='center'>Step</th><th>Segment</th><th class='right'>Length</th>"
    html += "<th class='right'>Starts At</th><th class='right'>Ends At</th>"
    html += "<th class='right'>Bend Angle</th><th class='right'>Rotation Before</th></tr>\n"

    last_straight_num = len(data.straights)
    for i, seg in enumerate(data.segments):
        # Check if this is a straight section with grip or tail violation
        is_grip_warning = False
        is_tail_warning = False
        if seg.segment_type == 'straight':
            # Extract section number from name (e.g., "Straight 1" -> 1)
            try:
                section_num = int(seg.name.split()[-1])
                is_grip_warning = section_num in data.grip_violations
                is_tail_warning = data.tail_violation and section_num == last_straight_num
            except (ValueError, IndexError):
                pass

        # Determine row class
        if seg.segment_type == 'bend':
            row_class = ' class="bend-row"'
        elif is_grip_warning or is_tail_warning:
            row_class = ' class="grip-warning"'
        else:
            row_class = ''

        if seg.segment_type == 'bend':
            angle_str = f"{seg.bend_angle:.1f}°"
            rot_str = "—"
        else:
            angle_str = "—"
            rot_str = f"<b>{seg.rotation:.1f}°</b>" if seg.rotation is not None else "—"

        # Add warning icon to length if grip or tail warning
        length_str = format_length(seg.length, precision, units)
        if is_grip_warning or is_tail_warning:
            length_str += ' <span class="grip-warning-icon">⚠️</span>'

        # Show pure geometry (subtract extra material offset)
        geometry_starts_at = seg.starts_at - extra_offset
        geometry_ends_at = seg.ends_at - extra_offset

        html += f"<tr{row_class}><td class='center'>{i + 1}</td><td>{seg.name}</td>"
        html += f"<td class='right'>{length_str}</td>"
        html += f"<td class='right'>{format_length(geometry_starts_at, precision, units)}</td>"
        html += f"<td class='right'>{format_length(geometry_ends_at, precision, units)}</td>"
        html += f"<td class='right'>{angle_str}</td><td class='right'>{rot_str}</td></tr>\n"

    html += "</table>\n<hr>\n"
    return html


def _generate_bender_setup(data: BendSheetData) -> str:
    """Generate the bender setup section with mark positions."""
    precision = data.precision
    units = data.units

    html = "<h3>Bender Setup</h3>\n"
    if data.die_offset > 0:
        html += f"<p><b>Die Offset:</b> {format_length(data.die_offset, precision, units)} "
        html += "(bend tangent point distance from die end)</p>\n"
    else:
        html += "<p><b>Die Offset:</b> Not specified (mark positions show tangent points)</p>\n"

    html += "<table>\n"
    html += "<tr><th class='center'>Bend</th><th class='right'>Mark Position</th>"
    html += "<th>Align Mark To</th><th class='right'>Bend Angle</th><th class='right'>Rotation Before</th></tr>\n"

    for mp in data.mark_positions:
        rot_str = f"<b>{mp.rotation:.1f}°</b>" if mp.rotation is not None else "—"
        html += f"<tr><td class='center'>BEND {mp.bend_num}</td>"
        html += f"<td class='right'>{format_length(mp.mark_position, precision, units)}</td>"
        html += f"<td>Die end</td><td class='right'>{mp.bend_angle:.1f}°</td>"
        html += f"<td class='right'>{rot_str}</td></tr>\n"

    html += "</table>\n"
    return html


def _generate_procedure(data: BendSheetData) -> str:
    """Generate the step-by-step procedure section."""
    precision = data.precision
    units = data.units

    html = '<div class="procedure">\n<p><b>Procedure:</b></p>\n<ol>\n'
    html += f"<li>Cut tube to {format_length(data.total_cut_length, precision, units)}</li>\n"

    # Calculate total material to cut from start (grip + effective start allowance)
    start_cut = data.extra_material + data.effective_start_allowance

    # Calculate total material to cut from end
    # This includes: synthetic tail OR tail extension, plus effective end allowance
    end_cut = data.effective_end_allowance
    if data.has_synthetic_tail and data.tail_cut_position is not None:
        # Synthetic tail: material added because path ends with arc
        end_cut += data.total_cut_length - data.tail_cut_position
    elif data.has_tail_extension:
        # Tail extension: material added because last straight < min_tail
        end_cut += data.extra_tail_material

    if start_cut > 0:
        # Explain what's included in the start cut
        parts = []
        if data.extra_material > 0:
            parts.append(f"{format_length(data.extra_material, precision, units)} grip")
        if data.effective_start_allowance > 0:
            parts.append(f"{format_length(data.effective_start_allowance, precision, units)} allowance")
        detail = " + ".join(parts) if len(parts) > 1 else ""
        if detail:
            html += f"<li>Note: First {format_length(start_cut, precision, units)} is extra material "
            html += f"({detail} — cut off after bending)</li>\n"
        else:
            html += f"<li>Note: First {format_length(start_cut, precision, units)} "
            html += "is extra material (cut off after bending)</li>\n"

    for mp in data.mark_positions:
        if mp.rotation is not None:
            html += f"<li>Rotate tube <b>{mp.rotation:.1f}°</b></li>\n"
        html += f"<li>Mark at {format_length(mp.mark_position, precision, units)} from start "
        html += f"— align mark to die end, bend {mp.bend_angle:.1f}°</li>\n"

    if start_cut > 0:
        html += f"<li>Cut off {format_length(start_cut, precision, units)} from start of tube</li>\n"

    if end_cut > 0:
        # Explain what's included in the end cut
        parts = []
        if data.has_synthetic_tail and data.tail_cut_position is not None:
            tail_material = data.total_cut_length - data.tail_cut_position
            parts.append(f"{format_length(tail_material, precision, units)} synthetic tail")
        elif data.has_tail_extension:
            parts.append(f"{format_length(data.extra_tail_material, precision, units)} tail extension")
        if data.effective_end_allowance > 0:
            parts.append(f"{format_length(data.effective_end_allowance, precision, units)} allowance")
        detail = " + ".join(parts) if len(parts) > 1 else ""
        if detail and len(parts) > 1:
            html += f"<li>Cut off {format_length(end_cut, precision, units)} from end of tube ({detail})</li>\n"
        else:
            html += f"<li>Cut off {format_length(end_cut, precision, units)} from end of tube</li>\n"

    html += "</ol>\n</div>\n<hr>\n"
    return html


def _generate_specifications(data: BendSheetData) -> str:
    """Generate the specifications table."""
    precision = data.precision
    units = data.units

    html = "<h3>Specifications</h3>\n<table class='specs-table'>\n"

    if data.component_name:
        html += f"<tr><td>Component</td><td>{_escape_html(data.component_name)}</td></tr>\n"
    if data.bender_name:
        html += f"<tr><td>Bender</td><td>{_escape_html(data.bender_name)}</td></tr>\n"
    if data.die_name:
        html += f"<tr><td>Die</td><td>{_escape_html(data.die_name)}</td></tr>\n"
    html += f"<tr><td>Units</td><td>{units.unit_name}</td></tr>\n"
    html += f"<tr><td>Tube OD</td><td>{data.tube_od}{units.unit_symbol}</td></tr>\n"
    html += f"<tr><td>CLR</td><td>{format_length(data.clr, precision, units)}</td></tr>\n"
    html += f"<tr><td>Die Offset</td><td>{format_length(data.die_offset, precision, units) if data.die_offset > 0 else 'None'}</td></tr>\n"
    html += f"<tr><td>Min Grip</td><td>{format_length(data.min_grip, precision, units)}</td></tr>\n"
    html += f"<tr><td>Min Tail</td><td>{format_length(data.min_tail, precision, units)}</td></tr>\n"
    if data.start_allowance > 0:
        html += f"<tr><td>Start Allowance</td><td>{format_length(data.start_allowance, precision, units)}</td></tr>\n"
    if data.end_allowance > 0:
        html += f"<tr><td>End Allowance</td><td>{format_length(data.end_allowance, precision, units)}</td></tr>\n"
    html += f"<tr><td>Direction</td><td>{_escape_html(data.travel_direction)}</td></tr>\n"
    html += f"<tr><td>Precision</td><td>{get_precision_label(precision, units)}</td></tr>\n"
    html += f"<tr><td>Total Centerline</td><td>{format_length(data.total_centerline, precision, units)}</td></tr>\n"
    html += f"<tr><td>Cut Length</td><td>{format_length(data.total_cut_length, precision, units)}</td></tr>\n"

    if data.extra_material > 0:
        html += f"<tr><td>Extra Grip Material</td><td>{format_length(data.extra_material, precision, units)}</td></tr>\n"
    if data.extra_tail_material > 0:
        html += f"<tr><td>Extra Tail Material</td><td>{format_length(data.extra_tail_material, precision, units)}</td></tr>\n"
    if data.starts_with_arc:
        html += "<tr><td>Starts With</td><td>Bend</td></tr>\n"
    if data.ends_with_arc:
        html += "<tr><td>Ends With</td><td>Bend</td></tr>\n"

    html += "</table>\n"
    return html


def _generate_notes_section(data: BendSheetData) -> str:
    """Generate notes boxes for bender, die, and user notes."""
    html = '<div class="notes-section">\n'

    # Bender notes (only if present)
    if data.bender_notes:
        html += '<div class="notes-box">\n'
        html += f'<h4>Bender Notes ({_escape_html(data.bender_name)})</h4>\n'
        html += f'<p>{_escape_html(data.bender_notes)}</p>\n'
        html += '</div>\n'

    # Die notes (only if present)
    if data.die_notes:
        html += '<div class="notes-box">\n'
        html += f'<h4>Die Notes ({_escape_html(data.die_name)})</h4>\n'
        html += f'<p>{_escape_html(data.die_notes)}</p>\n'
        html += '</div>\n'

    # User notes (always present - blank lined space for handwritten notes)
    html += '<div class="notes-box user-notes">\n'
    html += '<h4>Notes</h4>\n'
    html += '</div>\n'

    html += '</div>\n'
    return html


def _generate_footer() -> str:
    """Generate the closing HTML tags."""
    return "</body>\n</html>"


def generate_html_bend_sheet(data: BendSheetData) -> str:
    """
    Generate a styled HTML bend sheet for printing.

    Args:
        data: All bend sheet data

    Returns:
        Complete HTML document as string
    """
    parts = [
        _generate_html_head(),
        _generate_title_section(data),
        _generate_warnings_section(data),
        _generate_cut_instructions(data),
        _generate_bend_table(data),
        _generate_bender_setup(data),
        _generate_procedure(data),
        _generate_specifications(data),
        _generate_notes_section(data),
        _generate_footer(),
    ]
    return "".join(parts)
