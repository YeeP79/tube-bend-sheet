"""Extract geometry from Fusion UI selections.

This module handles the single responsibility of extracting lines and arcs
from user selections in the Fusion UI.
"""

from __future__ import annotations

from dataclasses import dataclass

import adsk.core
import adsk.fusion


@dataclass(slots=True)
class ExtractedGeometry:
    """Result of geometry extraction from selections.

    Attributes:
        lines: List of sketch lines extracted from selection
        arcs: List of sketch arcs extracted from selection
        first_entity: First entity in selection order (for attribute storage)
    """

    lines: list[adsk.fusion.SketchLine]
    arcs: list[adsk.fusion.SketchArc]
    first_entity: adsk.fusion.SketchEntity | None


def extract_geometry(
    selections: adsk.core.Selections,
) -> ExtractedGeometry:
    """Extract lines and arcs from Fusion selections.

    Separates sketch entities into lines and arcs, preserving the first
    entity for document attribute storage.

    Args:
        selections: Active selections from the UI

    Returns:
        ExtractedGeometry with separated lines, arcs, and first entity
    """
    lines: list[adsk.fusion.SketchLine] = []
    arcs: list[adsk.fusion.SketchArc] = []
    first_entity: adsk.fusion.SketchEntity | None = None

    for i in range(selections.count):
        entity = selections.item(i).entity
        if first_entity is None:
            first_entity = entity

        line = adsk.fusion.SketchLine.cast(entity)
        if line:
            lines.append(line)
            continue

        arc = adsk.fusion.SketchArc.cast(entity)
        if arc:
            arcs.append(arc)

    return ExtractedGeometry(lines=lines, arcs=arcs, first_entity=first_entity)
