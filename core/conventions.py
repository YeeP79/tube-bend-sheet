"""Rotation reference conventions shared by bend and cope commands.

This is the single source of truth for the back-of-bend reference convention.
Both the bend calculator and cope calculator import from here.
"""

# Rotation reference convention
ROTATION_REFERENCE = "back_of_last_bend_extrados"
ROTATION_DIRECTION = "clockwise_from_coped_end"
ROTATION_ZERO_DESCRIPTION = (
    "Outside of last curve (extrados), facing away from holesaw center"
)

# Fallback label for straight tubes (no bends)
ROTATION_ZERO_STRAIGHT_DESCRIPTION = (
    "User-scribed reference line (tube has no bends)"
)

# Minimum straight length before tube end, as a ratio of tube OD.
# Below this threshold the back-of-bend reference is hard to identify
# and the add-in should offer the second-to-last bend as an alternative.
MIN_STRAIGHT_BEFORE_END_OD_RATIO: float = 1.0
