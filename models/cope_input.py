"""Data model for specifying cope operations at tube path ends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .cope_data import ReceivingTube


@dataclass(slots=True)
class CopeEndSpec:
    """Declares what the user wants to cope at one end of a tube path.

    The incoming tube OD comes from GeometrySpecs.tube_od on the bend
    sheet side, so it is not duplicated here.
    """
    end: Literal["start", "end"]
    receiving_tubes: list[ReceivingTube]
    label: str = ""
