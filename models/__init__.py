"""Data models for tube bend calculator."""

from .bender import Bender, Die
from .bend_data import (
    StraightSection,
    BendData,
    PathSegment,
    MarkPosition,
    BendSheetData,
    ToolingInfo,
    GeometrySpecs,
    PathData,
    MaterialInfo,
    SheetWarnings,
)
from .compensation import CompensationDataPoint, DieMaterialCompensation
from .tube import Tube, MATERIAL_TYPES
from .types import Vector3D, Point3D, ElementType, SegmentType
from .units import UnitConfig

__all__ = [
    # Bender models
    'Bender',
    'Die',
    # Bend data models
    'StraightSection',
    'BendData',
    'PathSegment',
    'MarkPosition',
    'BendSheetData',
    # BendSheetData sub-groups
    'ToolingInfo',
    'GeometrySpecs',
    'PathData',
    'MaterialInfo',
    'SheetWarnings',
    # Compensation models
    'CompensationDataPoint',
    'DieMaterialCompensation',
    # Tube model
    'Tube',
    'MATERIAL_TYPES',
    # Type aliases
    'Vector3D',
    'Point3D',
    'ElementType',
    'SegmentType',
    # Unit config
    'UnitConfig',
]
