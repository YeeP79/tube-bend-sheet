"""Results display formatting for cope calculator.

Formats CopeResult data for display in the Fusion command dialog
and message boxes.
"""

from __future__ import annotations

from ...models.cope_data import CopeResult


def format_results_html(result: CopeResult) -> str:
    """
    Format cope results as HTML for display in a Fusion text box.

    Args:
        result: The cope calculation result

    Returns:
        HTML string for display
    """
    method_colors = {"A": "#2266AA", "B": "#CC8800", "C": "#CC6600"}
    method_labels = {
        "A": "Method A \u2014 Notcher, single pass",
        "B": "Method B \u2014 Notcher, multi-pass",
        "C": "Method C \u2014 Wrap template + grinder",
    }

    lines: list[str] = []
    color = method_colors[result.method]
    label = method_labels[result.method]

    lines.append(f'<b style="color:{color}">{label}</b><br/>')

    if result.is_multi_pass:
        lines.append('<b style="color:#CC3333">Read pass sequence carefully before cutting</b><br/>')

    lines.append(f'Reference: {result.reference_description}<br/><br/>')

    for i, cope_pass in enumerate(result.passes):
        if len(result.passes) > 1:
            pass_label = f"Pass {i + 1}"
            if cope_pass.dominant:
                pass_label += " (PRIMARY)"
            lines.append(f'<b>{pass_label}</b><br/>')

        lines.append(f'Notcher angle: {cope_pass.notcher_angle:.1f}\u00b0<br/>')
        lines.append(f'Rotation mark: {cope_pass.rotation_mark:.1f}\u00b0 CW from reference<br/>')

        if cope_pass.is_pass_through:
            lines.append('Pass type: Push through<br/>')
        else:
            lines.append(
                f'<b style="color:#CC3333">Plunge depth: {cope_pass.plunge_depth:.3f}" '
                f'\u2014 DO NOT pass through</b><br/>'
            )

        lines.append(f'Holesaw depth needed: {cope_pass.holesaw_depth_required:.2f}"<br/>')

        if cope_pass.holesaw_warning:
            lines.append(f'<span style="color:#CC3333">{cope_pass.holesaw_warning}</span><br/>')

        lines.append('<br/>')

    for warning in result.warnings:
        lines.append(f'<span style="color:#CC3333">\u26a0 {warning}</span><br/>')

    return ''.join(lines)


def format_results_summary(result: CopeResult) -> str:
    """
    Format a brief text summary of cope results.

    Args:
        result: The cope calculation result

    Returns:
        Plain text summary string
    """
    lines: list[str] = []
    lines.append(f"Method {result.method}: {result.method_description}")

    for i, cope_pass in enumerate(result.passes):
        prefix = f"Pass {i + 1}: " if len(result.passes) > 1 else ""
        lines.append(
            f"{prefix}{cope_pass.notcher_angle:.1f}\u00b0 notcher, "
            f"{cope_pass.rotation_mark:.1f}\u00b0 rotation"
        )

    return "\n".join(lines)
