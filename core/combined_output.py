"""Combined HTML document: bend sheet + cope templates on one printout.

Generates a single printable HTML with bend sheet page(s) followed by
cope template page(s). When no cope pages are requested, the output is
identical to generate_html_bend_sheet().

Zero Fusion 360 dependencies. Fully unit-testable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from ..models.bend_data import BendSheetData
from ..models.cope_data import CopeResult
from .cope_template import generate_cope_svg
from .html_generator import generate_html_bend_sheet


# Width thresholds for print-orientation hints (inches)
_PORTRAIT_MAX_WIDTH = 7.5
_LANDSCAPE_MAX_WIDTH = 10.0


@dataclass(slots=True)
class CopePageData:
    """Data needed to render one cope template page.

    Attributes:
        end_label: Page heading, e.g. "Start End" or "End — Front Node".
        cope_result: The CopeResult from calculate_cope().
        od1: Tube OD in display units (inches).
        tube_name: Name of the incoming tube.
        has_bends: Whether the tube has bends (affects SVG instructions).
    """
    end_label: str
    cope_result: CopeResult
    od1: float
    tube_name: str
    has_bends: bool
    location: str = ""
    waste_side: Literal["top", "bottom"] = "top"


def generate_combined_document(
    bend_sheet_data: BendSheetData,
    cope_pages: list[CopePageData],
) -> str:
    """Generate a single printable HTML with bend sheet + cope templates.

    If cope_pages is empty, returns exactly ``generate_html_bend_sheet(data)``
    with zero behaviour change for existing callers.

    Args:
        bend_sheet_data: All data needed for the bend sheet.
        cope_pages: Zero or more cope template pages to append.

    Returns:
        Complete HTML document as a string.
    """
    bend_html = generate_html_bend_sheet(bend_sheet_data)

    if not cope_pages:
        return bend_html

    # Split the bend sheet HTML at </body> so we can insert cope pages
    body_close = "</body>"
    parts = bend_html.rsplit(body_close, 1)
    if len(parts) != 2:
        return bend_html

    content = parts[0]
    closing = body_close + parts[1]

    # Inject cope-page CSS into the existing <style> block
    cope_css = _cope_page_css()
    content = _inject_css(content, cope_css)

    # Append cope pages
    cope_html_parts: list[str] = []
    for page in cope_pages:
        cope_html_parts.append(_render_cope_page(page))

    return content + "\n".join(cope_html_parts) + "\n" + closing


def _cope_page_css() -> str:
    """CSS rules for cope template pages."""
    return (
        "\n        .cope-page { page-break-before: always; margin-top: 0.5in; }"
        "\n        .cope-svg-container { margin: 0.2in 0; }"
        "\n        .cope-page h2 { font-size: 16pt; margin-bottom: 0.15in; }"
        "\n        .landscape-hint { color: #666; font-style: italic; margin-bottom: 0.1in; }"
        "\n        .wide-format-warning {"
        " color: #c00; font-weight: bold; margin-bottom: 0.1in; }"
    )


def _inject_css(html: str, css: str) -> str:
    """Insert additional CSS rules before the closing </style> tag."""
    style_close = "</style>"
    if style_close in html:
        return html.replace(style_close, css + "\n    " + style_close, 1)
    return html


def _render_cope_page(page: CopePageData) -> str:
    """Render a single cope template page as an HTML fragment."""
    svg_raw = generate_cope_svg(
        result=page.cope_result,
        od1=page.od1,
        tube_name=page.tube_name,
        node_label=page.end_label,
        has_bends=page.has_bends,
        location=page.location,
        waste_side=page.waste_side,
    )

    # Strip XML declaration — not valid inside HTML
    svg_clean = re.sub(r'<\?xml[^?]*\?>\s*', '', svg_raw)

    # Determine print-orientation hints
    circumference = math.pi * page.od1
    orientation_hint = _orientation_hint(circumference)

    parts = [
        '<div class="cope-page">',
        f'  <h2>Cope Template &mdash; {page.end_label}</h2>',
    ]
    if orientation_hint:
        parts.append(f'  {orientation_hint}')
    parts.append('  <div class="cope-svg-container">')
    parts.append(f'    {svg_clean}')
    parts.append('  </div>')
    parts.append('</div>')

    return "\n".join(parts)


def _orientation_hint(svg_width_inches: float) -> str:
    """Return an HTML hint/warning based on SVG width."""
    if svg_width_inches <= _PORTRAIT_MAX_WIDTH:
        return ""
    if svg_width_inches <= _LANDSCAPE_MAX_WIDTH:
        return '<p class="landscape-hint">Print this page in landscape orientation.</p>'
    return (
        '<p class="wide-format-warning">'
        'Wide-format printer required for 1:1 scale printing.</p>'
    )
