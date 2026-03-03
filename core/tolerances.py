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

# Included angle (degrees) below which the cope is too acute for
# reliable notcher work and Method C (grinder) is recommended.
ACUTE_ANGLE_LIMIT: float = 25.0

# Holesaw depth (inches) above which the notcher cannot complete
# the pass and Method C is forced.
MAX_HOLESAW_DEPTH: float = 4.0

# Clearance added to plunge depth for non-pass-through cuts (inches).
HOLESAW_CLEARANCE: float = 0.03
