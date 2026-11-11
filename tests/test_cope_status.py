"""Tests for core/cope_status.py — dialog cope connection status text."""

from core.cope_status import (
    COPE_STATUS_HEADING,
    NO_CONNECTION_TEXT,
    VISIBILITY_HINT,
    EndConnection,
    build_cope_status_lines,
)


class TestBuildCopeStatusLines:
    """Per-end status lines for the Tube Fabrication dialog."""

    def test_both_ends_connected(self) -> None:
        lines = build_cope_status_lines([
            EndConnection("Left End", ["Main Rail"]),
            EndConnection("Right End", ["Cross Bar"]),
        ])
        assert lines == [
            COPE_STATUS_HEADING,
            "Left End: connects to Main Rail — cope template will be added",
            "Right End: connects to Cross Bar — cope template will be added",
            VISIBILITY_HINT,
        ]

    def test_no_connection_at_either_end(self) -> None:
        lines = build_cope_status_lines([
            EndConnection("Left End", []),
            EndConnection("Right End", []),
        ])
        assert lines[1] == f"Left End: {NO_CONNECTION_TEXT}"
        assert lines[2] == f"Right End: {NO_CONNECTION_TEXT}"
        assert "cope will not be added" in NO_CONNECTION_TEXT

    def test_one_end_connected(self) -> None:
        lines = build_cope_status_lines([
            EndConnection("Front End", ["Rail"]),
            EndConnection("Back End", []),
        ])
        assert "connects to Rail" in lines[1]
        assert lines[2] == f"Back End: {NO_CONNECTION_TEXT}"

    def test_multiple_receivers_listed(self) -> None:
        lines = build_cope_status_lines([
            EndConnection("Left End", ["Rail A", "Rail B"]),
        ])
        assert "connects to Rail A, Rail B" in lines[1]

    def test_visibility_hint_always_last(self) -> None:
        for ends in ([], [EndConnection("Left End", ["X"])]):
            assert build_cope_status_lines(ends)[-1] == VISIBILITY_HINT
        assert "visible" in VISIBILITY_HINT

    def test_empty_ends_gives_heading_and_hint_only(self) -> None:
        assert build_cope_status_lines([]) == [COPE_STATUS_HEADING, VISIBILITY_HINT]

    def test_blank_receiver_names_treated_as_no_connection(self) -> None:
        lines = build_cope_status_lines([EndConnection("Left End", ["", ""])])
        assert lines[1] == f"Left End: {NO_CONNECTION_TEXT}"

    def test_html_in_names_is_escaped(self) -> None:
        lines = build_cope_status_lines([
            EndConnection("<Left> End", ["Tube <b>1</b> & 2"]),
        ])
        assert "&lt;Left&gt; End" in lines[1]
        assert "Tube &lt;b&gt;1&lt;/b&gt; &amp; 2" in lines[1]
        assert "<b>1</b>" not in lines[1]
