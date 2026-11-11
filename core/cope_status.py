"""Cope connection status text for the Tube Fabrication dialog.

Tells the user, per tube end, whether a connecting tube was detected and
therefore whether a cope template will be added to the printout.

Zero Fusion 360 dependencies. Fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

COPE_STATUS_HEADING = "<b>Cope Templates</b>"
VISIBILITY_HINT = (
    "<i>Connecting tubes must be visible to be part of the write-up.</i>"
)
NO_CONNECTION_TEXT = "⚠ No connection found — cope will not be added"


@dataclass(slots=True)
class EndConnection:
    """Detected connections at one end of the tube.

    Attributes:
        label: End label as shown on the cope page, e.g. "Left End".
        receiver_names: Names of the connecting tube bodies (may be empty).
    """
    label: str
    receiver_names: list[str]


def build_cope_status_lines(ends: list[EndConnection]) -> list[str]:
    """Build HTML lines describing cope template status for each end.

    Args:
        ends: One entry per tube end, in display order.

    Returns:
        Lines of HTML (no ``<br>`` joins): a heading, one line per end,
        and a trailing hint that connecting tubes must be visible.
    """
    lines: list[str] = [COPE_STATUS_HEADING]
    for end in ends:
        label = escape(end.label)
        names = [escape(n) for n in end.receiver_names if n]
        if names:
            lines.append(
                f"{label}: connects to {', '.join(names)} "
                f"— cope template will be added"
            )
        else:
            lines.append(f"{label}: {NO_CONNECTION_TEXT}")
    lines.append(VISIBILITY_HINT)
    return lines
