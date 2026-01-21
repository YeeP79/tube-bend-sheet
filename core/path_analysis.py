"""Path analysis for tube bend geometry.

DEPRECATED: This module re-exports from geometry_extraction and path_ordering
for backward compatibility. New code should import directly from those modules.
"""

from typing import TYPE_CHECKING

from .geometry_extraction import (
    get_sketch_entity_endpoints,
    get_component_name,
    PathElement,
    PathElementLike,
    get_free_endpoint,
    determine_primary_axis,
    should_reverse_path_direction,
)
from .path_ordering import (
    elements_are_connected,
    build_ordered_path,
    validate_path_alternation,
)

if TYPE_CHECKING:
    from .geometry_extraction import SketchEntity as SketchEntity  # noqa: F401

__all__ = [
    # Geometry extraction
    'SketchEntity',
    'get_sketch_entity_endpoints',
    'get_component_name',
    'PathElement',
    'PathElementLike',
    'get_free_endpoint',
    'determine_primary_axis',
    'should_reverse_path_direction',
    # Path ordering
    'elements_are_connected',
    'build_ordered_path',
    'validate_path_alternation',
]
