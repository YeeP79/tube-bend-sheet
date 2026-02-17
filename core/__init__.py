"""Core calculation and geometry utilities."""

from .geometry import (
    cross_product,
    dot_product,
    magnitude,
    angle_between_vectors,
    calculate_rotation,
    distance_between_points,
    points_are_close,
    vectors_are_collinear,
)
from .protocols import (
    ArcLike,
    UnitConfigLike,
    PathElementLike,
)
from .geometry_extraction import (
    PathElement,
    get_sketch_entity_endpoints,
    get_component_name,
    get_free_endpoint,
    determine_primary_axis,
    should_reverse_path_direction,
)
from .path_ordering import (
    build_ordered_path,
    merge_collinear_lines,
    validate_path_alternation,
)
from .calculations import (
    validate_clr_consistency,
    calculate_straights_and_bends,
    build_segments_and_marks,
)
from .formatting import (
    format_length,
    get_precision_label,
)
from .html_generator import generate_html_bend_sheet
from .direction_validation import (
    GripValidationResult,
    DirectionValidationResult,
    validate_grip_for_direction,
    validate_direction_aware,
)
from .grip_tail import (
    MaterialCalculation,
    calculate_material_requirements,
)
from .tolerances import (
    CONNECTIVITY_CM,
    ZERO_MAGNITUDE,
    CLR_RATIO,
    CLR_MIN_FLOOR,
    DIE_CLR_MATCH_DEFAULT,
    CLR_MATCH_DISPLAY,
    TUBE_OD_MATCH_CM,
    COLLINEAR_ANGLE_DEG,
)

__all__ = [
    # Geometry
    'cross_product',
    'dot_product',
    'magnitude',
    'angle_between_vectors',
    'calculate_rotation',
    'distance_between_points',
    'points_are_close',
    'vectors_are_collinear',
    # Protocols
    'ArcLike',
    'UnitConfigLike',
    'PathElementLike',
    # Path analysis
    'PathElement',
    'get_sketch_entity_endpoints',
    'get_component_name',
    'build_ordered_path',
    'merge_collinear_lines',
    'validate_path_alternation',
    'get_free_endpoint',
    'determine_primary_axis',
    'should_reverse_path_direction',
    # Calculations
    'validate_clr_consistency',
    'calculate_straights_and_bends',
    'build_segments_and_marks',
    # Formatting
    'format_length',
    'get_precision_label',
    # HTML
    'generate_html_bend_sheet',
    # Direction validation
    'GripValidationResult',
    'DirectionValidationResult',
    'validate_grip_for_direction',
    'validate_direction_aware',
    # Grip/tail calculations
    'MaterialCalculation',
    'calculate_material_requirements',
    # Tolerances
    'CONNECTIVITY_CM',
    'ZERO_MAGNITUDE',
    'CLR_RATIO',
    'CLR_MIN_FLOOR',
    'DIE_CLR_MATCH_DEFAULT',
    'CLR_MATCH_DISPLAY',
    'TUBE_OD_MATCH_CM',
    'COLLINEAR_ANGLE_DEG',
]
