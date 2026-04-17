"""Tolerance constants for geometric calculations.

Centralizes all tolerance values used throughout the codebase for
consistency and easy tuning.
"""

# Point connectivity tolerance (in cm, Fusion internal units)
# Used to determine if two sketch points are "connected"
CONNECTIVITY_CM: float = 0.1

# Zero vector detection threshold
# Vectors with magnitude below this are considered zero-length
ZERO_MAGNITUDE: float = 1e-10

# CLR matching ratio tolerance (0.2%)
# Two CLR values match if they differ by less than this ratio
# For example: 5.5" CLR with 0.2% tolerance allows ±0.011" variance
CLR_RATIO: float = 0.002

# Minimum tolerance floor for CLR matching (in display units)
# Prevents false mismatches with very small CLR values
CLR_MIN_FLOOR: float = 0.001

# Default tolerance for die CLR matching (in display units)
# Used when comparing detected CLR against die specifications
# Re-exported from models.constants (single source of truth)
from ..models.constants import DIE_CLR_MATCH_DEFAULT as DIE_CLR_MATCH_DEFAULT

# CLR match tolerance for dropdown display (in display units)
# More lenient tolerance for showing checkmark in die dropdown
CLR_MATCH_DISPLAY: float = 0.1

# Tube OD matching tolerance (in cm, Fusion internal units)
# Used to find tubes/dies with matching outer diameters
TUBE_OD_MATCH_CM: float = 0.01

# Collinearity angle tolerance (in degrees)
# Lines within this angle are considered truly collinear (floating point tolerance only)
COLLINEAR_ANGLE_DEG: float = 0.01

# --- Cope calculation tolerances ---

# Valley depth as fraction of OD that triggers multi-pass detection.
# Below this threshold, valleys between lobes are considered noise.
VALLEY_DEPTH_OD_RATIO: float = 0.15

# Angular separation (degrees) below which two close lobes could
# potentially be handled as a single pass.
LOBE_COLLAPSE_DEGREES: float = 30.0

# Minimum inclination angle (degrees) for a receiver to be included in the
# z-profile computation.  Below this threshold, the saddle formula produces
# impractically deep profiles (z ∝ 1/sin(α)), and the "receiver" is most
# likely a same-direction tube at a shared junction (e.g., a Y-branch off
# the actual receiving tube) rather than a tube that crosses the incoming path.
MIN_COPE_INCLINATION_DEG: float = 10.0

# Maximum notcher degree wheel setting above which Method C is recommended.
# 90 - 25 = 65: inclination angles below 25° are too acute for reliable
# notcher work.
# On a VersaNotcher-style wheel, 0° = perpendicular T-joint, higher = steeper.
MAX_NOTCHER_ANGLE: float = 65.0

# Holesaw depth (inches) above which the notcher cannot complete
# the pass and Method C is forced.
MAX_HOLESAW_DEPTH: float = 4.0

# Clearance added to plunge depth for non-pass-through cuts (inches).
HOLESAW_CLEARANCE: float = 0.03

# Holesaw cutting depth (display units, typically inches) above which
# a "deep holesaw" warning is issued.
HOLESAW_DEEP_THRESHOLD: float = 2.0

# Holesaw cutting depth (display units, typically inches) above which
# an "extra-deep holesaw" warning is issued.
HOLESAW_EXTRA_DEEP_THRESHOLD: float = 3.0

# Minimum torus bend angle (degrees) to be considered a real bend.
# Torus faces with a smaller angle are likely cope artifacts from tube
# intersections and should be excluded from the tube path.
MIN_BEND_ANGLE_DEG: float = 3.0

# Maximum ratio of receiving tube OD to incoming tube OD for detection.
# Bodies with OD larger than this ratio × incoming OD are rejected as
# non-tube bodies (e.g., sheet metal panels with large-radius bends).
MAX_RECEIVING_OD_RATIO: float = 5.0

# --- Body-to-sketch matching tolerances ---

# Angle tolerance (degrees) for merging coaxial cylinder faces that were
# split by boolean operations (e.g., cope cuts).
COAXIAL_MERGE_ANGLE_DEG: float = 2.0

# Maximum perpendicular distance (cm) between cylinder axes to still
# consider them coaxial and merge them.
COAXIAL_MERGE_DISTANCE_CM: float = 0.5

# Radius tolerance (cm) when filtering cylinder/torus faces to OD-only.
OD_FILTER_TOLERANCE_CM: float = 0.01

# Endpoint tolerance (cm) for sketch entity connectivity detection
# (line-to-line, line-to-arc, arc-to-arc endpoint coincidence).
SKETCH_ENDPOINT_TOLERANCE_CM: float = 0.05
