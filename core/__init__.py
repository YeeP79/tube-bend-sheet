"""Core calculation and geometry utilities."""

from .geometry import (
    cross_product,
    dot_product,
    magnitude,
    normalize,
    project_onto_plane,
    angle_between_vectors,
    calculate_rotation,
    distance_between_points,
    points_are_close,
    vectors_are_collinear,
    subtract_vectors,
    add_vectors,
    scale_vector,
    point_to_line_distance,
    unsigned_angle_between,
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
    VALLEY_DEPTH_OD_RATIO,
    LOBE_COLLAPSE_DEGREES,
    MAX_NOTCHER_ANGLE,
    MAX_HOLESAW_DEPTH,
    HOLESAW_CLEARANCE,
    MIN_COPE_INCLINATION_DEG,
    COAXIAL_MERGE_ANGLE_DEG,
    COAXIAL_MERGE_DISTANCE_CM,
    OD_FILTER_TOLERANCE_CM,
    SKETCH_ENDPOINT_TOLERANCE_CM,
)
from .body_profile import (
    merge_coaxial_straights,
    determine_od_radius,
    filter_od_straights,
    filter_od_bends,
    build_body_profile,
)
from .sketch_matching import (
    graduated_direction_score,
    clr_match_score,
    proximity_score,
    find_connected_path,
    score_sketch_match,
    rank_matches,
)
from .body_path import body_path_to_straights_and_bends, detect_path_direction
from .cope_math import calculate_cope
from .cope_template import generate_cope_svg
from .cope_path import EndReference, compute_end_reference
from .combined_output import CopePageData, generate_combined_document
from .conventions import (
    ROTATION_REFERENCE,
    ROTATION_DIRECTION,
    ROTATION_ZERO_DESCRIPTION,
    ROTATION_ZERO_STRAIGHT_DESCRIPTION,
    MIN_STRAIGHT_BEFORE_END_OD_RATIO,
)

__all__ = [
    # Geometry
    'cross_product',
    'dot_product',
    'magnitude',
    'normalize',
    'project_onto_plane',
    'angle_between_vectors',
    'calculate_rotation',
    'distance_between_points',
    'points_are_close',
    'vectors_are_collinear',
    'subtract_vectors',
    'add_vectors',
    'scale_vector',
    'point_to_line_distance',
    'unsigned_angle_between',
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
    'VALLEY_DEPTH_OD_RATIO',
    'LOBE_COLLAPSE_DEGREES',
    'MAX_NOTCHER_ANGLE',
    'MAX_HOLESAW_DEPTH',
    'HOLESAW_CLEARANCE',
    'MIN_COPE_INCLINATION_DEG',
    'COAXIAL_MERGE_ANGLE_DEG',
    'COAXIAL_MERGE_DISTANCE_CM',
    'OD_FILTER_TOLERANCE_CM',
    'SKETCH_ENDPOINT_TOLERANCE_CM',
    # Body profile
    'merge_coaxial_straights',
    'determine_od_radius',
    'filter_od_straights',
    'filter_od_bends',
    'build_body_profile',
    # Sketch matching
    'graduated_direction_score',
    'clr_match_score',
    'proximity_score',
    'find_connected_path',
    'score_sketch_match',
    'rank_matches',
    # Body path conversion
    'body_path_to_straights_and_bends',
    'detect_path_direction',
    # Cope math
    'calculate_cope',
    'generate_cope_svg',
    # Cope path extraction
    'EndReference',
    'compute_end_reference',
    # Combined output
    'CopePageData',
    'generate_combined_document',
    # Conventions
    'ROTATION_REFERENCE',
    'ROTATION_DIRECTION',
    'ROTATION_ZERO_DESCRIPTION',
    'ROTATION_ZERO_STRAIGHT_DESCRIPTION',
    'MIN_STRAIGHT_BEFORE_END_OD_RATIO',
]
