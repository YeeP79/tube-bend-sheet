"""Handles HTML generation, file saving, and browser display.

This module is responsible for presenting the generated bend sheet
to the user via HTML and optional browser display.
"""

from __future__ import annotations

import os
import tempfile
import webbrowser

import adsk.core

from ...core import generate_html_bend_sheet, format_length
from ...models import BendSheetData


class BendSheetDisplay:
    """Displays bend sheet HTML to user.

    Responsible for:
    - Generating HTML from bend sheet data
    - Saving HTML to temporary file
    - Prompting user with summary
    - Opening browser if requested
    """

    def __init__(self, ui: adsk.core.UserInterface) -> None:
        """
        Initialize the display handler.

        Args:
            ui: Fusion UserInterface for dialogs
        """
        self._ui = ui

    def show(self, sheet_data: BendSheetData) -> bool:
        """
        Generate HTML, save to file, and prompt user to open.

        Args:
            sheet_data: Complete bend sheet data

        Returns:
            True if display was successful
        """
        # Generate HTML
        html = generate_html_bend_sheet(sheet_data)

        # Create safe filename from component name
        safe_name = self._sanitize_filename(sheet_data.component_name)

        # Save to temp file
        temp_dir = tempfile.gettempdir()
        html_path = os.path.join(temp_dir, f"{safe_name}.html")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Build summary message
        cut_length_str = format_length(
            sheet_data.total_cut_length,
            sheet_data.precision,
            sheet_data.units,
        )
        bend_count = len(sheet_data.bends)

        message = (
            f"Bend sheet created!\n\n"
            f"Component: {sheet_data.component_name or 'N/A'}\n"
            f"Cut Length: {cut_length_str}\n"
            f"Bends: {bend_count}\n"
        )

        # Add grip warning if violations exist (informational - extra material added)
        if sheet_data.grip_violations:
            violation_count = len(sheet_data.grip_violations)
            section_word = "section" if violation_count == 1 else "sections"
            sections_list = ", ".join(
                f"Straight {n}" for n in sheet_data.grip_violations
            )
            min_grip_str = format_length(
                sheet_data.min_grip, sheet_data.precision, sheet_data.units
            )
            message += (
                f"\nℹ️ NOTE: {violation_count} {section_word} shorter than "
                f"min grip ({sections_list}) - extra material added\n"
                f"Min grip: {min_grip_str}\n"
            )

        # Add tail warning if violation exists (informational - extra material added)
        if sheet_data.tail_violation:
            last_straight_num = len(sheet_data.straights)
            min_tail_str = format_length(
                sheet_data.min_tail, sheet_data.precision, sheet_data.units
            )
            message += (
                f"\nℹ️ NOTE: Straight {last_straight_num} shorter than "
                f"min tail - extra material added\n"
                f"Min tail: {min_tail_str}\n"
            )

        # Note: Spring back warning is shown earlier in the flow (in entry.py)
        # before we get here, so user has already acknowledged it

        message += "\nOpen in browser for printing?"

        # Prompt user
        result = self._ui.messageBox(
            message,
            "Bend Sheet Created",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType,
        )

        if result == adsk.core.DialogResults.DialogYes:
            webbrowser.open(f"file://{html_path}")

        return True

    def _sanitize_filename(self, name: str | None) -> str:
        """
        Create a safe filename from component name.

        Args:
            name: Original component name or None

        Returns:
            Sanitized filename string
        """
        if not name:
            return "tube_bend_sheet"

        return (
            name.replace(" ", "_")
            .replace("/", "-")
            .replace("\\", "-")
            .replace(":", "-")
            .replace("*", "-")
            .replace("?", "-")
            .replace('"', "-")
            .replace("<", "-")
            .replace(">", "-")
            .replace("|", "-")
        )
