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
DIE_CLR_MATCH_DEFAULT: float = 0.01

# CLR match tolerance for dropdown display (in display units)
# More lenient tolerance for showing checkmark in die dropdown
CLR_MATCH_DISPLAY: float = 0.1
