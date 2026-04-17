# Cope Calculator — Gaps, Bugs, and Improvement Areas

**Date:** 2026-03-07
**Branch:** feature/cope-calculator
**Reviewed by:** Claude (code review session)

---

## Critical: Notcher Angle Convention is Inverted

**File:** `core/cope_math.py:124-140` (`_compute_notcher_angle`)

**Problem:** The function returns the *included angle between tube centerlines* (0-90 range), but tube notchers like the VersaNotcher use the *offset from perpendicular* convention:

- 0° on notcher = perpendicular T-joint (90° between centerlines)
- 45° on notcher = tubes at 45° to each other
- Higher notcher angle = shallower approach angle

**Current code:**
```python
def _compute_notcher_angle(v1, v2) -> float:
    cos_theta = abs(dot_product(v1, v2))
    cos_theta = min(1.0, cos_theta)
    return math.degrees(math.acos(cos_theta))  # Returns 90° for T-joint
```

**Should be:**
```python
def _compute_notcher_angle(v1, v2) -> float:
    cos_theta = abs(dot_product(v1, v2))
    cos_theta = min(1.0, cos_theta)
    included_angle = math.degrees(math.acos(cos_theta))
    return 90.0 - included_angle  # Returns 0° for T-joint
```

Or equivalently: `return math.degrees(math.asin(cos_theta))`

**Impact:** Every notcher angle output is currently wrong. A T-joint shows 90° when it should show 0°. A 45° joint shows 45° (coincidentally correct). All other angles are inverted.

**Cascading effects:**
- `ACUTE_ANGLE_LIMIT` (25°) currently triggers when the *included* angle is < 25° (tubes nearly parallel), which happens to be the right physical case to flag. But with the fix, the threshold semantics would need to flip: a *notcher angle* > 65° (= 90° - 25°) should trigger Method C. Review and update `_classify_method` accordingly.
- Holesaw depth formula `OD / sin(theta)` uses the included angle internally, which is correct for the *math* — just make sure the internal math still uses the included angle even though the *displayed* value changes to the notcher convention.
- All test assertions checking `notcher_angle` values need updating.

---

## High: `extract_bend_reference` Finds Arbitrary Torus, Not Nearest to Cope End

**File:** `commands/copeCalculator/body_extraction.py:76-98`

**Problem:** Iterates `body.faces` and returns on the *first* toroidal face found. Fusion does not guarantee face iteration order, so for a multi-bend tube, this might return a bend far from the cope end rather than the last bend before it.

**Fix:** Iterate all torus faces, compare each torus center distance to `cope_end`, and pick the closest one.

```python
best_ref = None
best_dist = float('inf')
for face in body.faces:
    geom = face.geometry
    if isinstance(geom, adsk.core.Torus):
        center = geom.origin
        dist = math.sqrt(
            (cope_end[0] - center.x)**2 +
            (cope_end[1] - center.y)**2 +
            (cope_end[2] - center.z)**2
        )
        if dist < best_dist:
            best_dist = dist
            # compute ref vector from this torus
            best_ref = ...
```

**Impact:** Wrong reference vector for multi-bend tubes → wrong rotation mark → user marks tube incorrectly → bad cope.

---

## High: `identify_cope_end` Uses Bounding Box Corners, Not Actual Tube Endpoints

**File:** `commands/copeCalculator/body_extraction.py:121-146`

**Problem:** Uses `body.boundingBox.minPoint` and `maxPoint` as endpoint candidates. These are the corners of an axis-aligned bounding box, not the actual tube endpoints. For a tube at 45° in space, the bounding box corner can be significantly displaced from the real tube end.

**Better approach:** Walk the body's cylindrical faces and find the circular end faces (planar faces with circular edges), then use their center points as the actual tube endpoints.

**Impact:** Wrong cope end identification → wrong bend reference direction → wrong rotation mark.

---

## Medium: Holesaw Depth Warnings Hardcoded in Inches

**File:** `core/cope_math.py:461-476`

**Problem:** Warning messages contain hardcoded inch values (`"exceeds 4\""`, `"depth"` in inches). The `MAX_HOLESAW_DEPTH` and `HOLESAW_CLEARANCE` constants in `tolerances.py` are documented as inches. If the user's Fusion design uses metric units, the math still works (since inputs are converted to display units before calling `calculate_cope`), but the warning thresholds assume imperial.

**Example:** A metric user with a 50mm OD tube and a perpendicular joint would see a holesaw depth of 50mm, which would not trigger the "exceeds 4"" warning — correct behavior. BUT if the caller passes metric values without converting, the 0.03" clearance becomes 0.03mm (wrong).

**Current flow:** `entry.py:279` converts to display units via `cm_to_unit`, so the values passed to `calculate_cope` are in whatever the user's design units are. If the design is metric, all values are in mm/cm. The 0.03" clearance and 4" max depth don't make sense in metric.

**Fix options:**
1. Document that `calculate_cope` always expects inches (caller must convert)
2. Accept a `UnitConfig` and convert thresholds internally
3. Make the tolerance constants unit-aware

---

## Medium: `_detect_lobes` Sets `receiver_index=0` and Never Updates It

**File:** `core/cope_math.py:338-344`

**Problem:** The `_Lobe.receiver_index` field is always set to 0 with a comment "Will be assigned below" — but it's never reassigned. The field exists in the `_Lobe` dataclass but is never used by `_build_passes` (which calls `_match_lobe_to_receiver` instead).

**Fix:** Either remove the `receiver_index` field from `_Lobe` (dead code), or populate it properly and use it instead of `_match_lobe_to_receiver`.

**Impact:** No functional bug — just misleading dead code.

---

## Medium: `conventions.py` Not Used by `cope_math.py`

**File:** `core/cope_math.py:102-104` vs `core/conventions.py`

**Problem:** `cope_math.py` hardcodes its own description strings:
```python
ref_desc = "Back of last bend (extrados)"
ref_desc = "User-scribed reference line"
```

These should reference `conventions.py` constants (`ROTATION_ZERO_DESCRIPTION`, `ROTATION_ZERO_STRAIGHT_DESCRIPTION`) to maintain single source of truth.

**Impact:** If conventions change, `cope_math.py` will be out of sync with the bend calculator.

---

## Medium: SVG Lobe Fill Doesn't Handle 0/360 Wrap-Around

**File:** `core/cope_template.py:193-198`

**Problem:** In `_add_multi_pass_profile`, the distance calculation:
```python
dist = abs(i - lobe_center_deg)
if dist > 180:
    dist = 360 - dist
if dist > half_span:
    continue
```

This correctly computes circular distance, but the resulting polygon points are added in raw degree order. If a lobe spans across the 0°/360° boundary (e.g., lobe center at 350° with span 40°), the fill polygon will jump from x-position near the right edge to x-position near the left edge, creating a discontinuous shape.

**Fix:** For wrap-around lobes, split the fill into two polygons: one at the right edge and one at the left edge of the template.

**Impact:** Visual artifact in the SVG template for copes where a lobe wraps around the 0° mark. Doesn't affect notcher settings or calculations.

---

## Medium: `_build_passes` Pass-Through Logic Only Checks Lobe Count

**File:** `core/cope_math.py:392`

**Problem:** `is_pass_through = single_pass` means any single-lobe cope is marked as pass-through regardless of depth or geometry. This is generally correct (a single saddle can be made by pushing through), but there's no consideration of extreme depths or very shallow receiving tubes where a controlled plunge might be preferable.

**Impact:** Minor — the single-pass push-through recommendation is standard practice. But could add a depth-based override for edge cases.

---

## Low: `_compute_notcher_angle` Doesn't Clamp Lower Bound of `cos_theta`

**File:** `core/cope_math.py:138-139`

**Problem:** Only clamps `cos_theta` to `min(1.0, cos_theta)` but not `max(0.0, cos_theta)`. Since `cos_theta = abs(dot_product(...))`, it's always >= 0, but floating point edge cases with non-unit vectors could theoretically produce values slightly below 0 after abs().

**Fix:** `cos_theta = max(0.0, min(1.0, cos_theta))`

**Impact:** Extremely unlikely to trigger; defensive hardening.

---

## Test Coverage Gaps

### Missing Direct Tests for `_detect_lobes`
Complex logic with circular wrapping, valley detection, and edge cases. Only tested indirectly through `calculate_cope`. Should have direct tests for:
- Single lobe at various positions
- Two lobes with clear valley
- Two lobes with valley below threshold (should merge)
- Lobe wrapping across 0°/360°
- Entire profile above valley threshold
- Empty/zero profile

### Missing Direct Tests for `_match_lobe_to_receiver`
Wrap-around distance calculation is tricky. Should test:
- Exact match (lobe at same angle as receiver)
- Closest of two receivers
- Wrap-around: lobe at 350°, receivers at 10° and 170°

### Missing Direct Tests for `_classify_method`
Should test each classification path:
- Method A: single pass (standard)
- Method A: two close lobes that collapse
- Method B: two distinct lobes
- Method C: acute angle trigger
- Method C: excessive holesaw depth
- Method C: three or more lobes

### Missing Tests for `results_display.py`
`format_results_html` and `format_results_summary` are completely untested. Should verify:
- Method A/B/C labels appear
- Pass details are correctly formatted
- Warnings appear in output
- Multi-pass warning appears
- HTML is well-formed

### Missing Tests for `_arbitrary_perpendicular`
Edge cases with axis-aligned vectors:
- v along X axis
- v along Y axis
- v along Z axis
- v along negative axes
- v at 45° to all axes

### Missing Tests for `_compute_z_profile`
Should verify:
- Profile shape for single perpendicular receiver
- Profile shape for single angled receiver
- Envelope (max) behavior with multiple receivers
- All-zero profile when sin(theta) ≈ 0

### Missing Tests for SVG Wrap-Around Edge Cases
- Lobe centered near 0° or 360°
- Very shallow cope (max_z ≈ 0)
- Very deep cope
- Empty tube name / node label

---

## Architecture Notes (Not Bugs)

### Separation of Display Units from Math Units
The `calculate_cope` function receives values in display units (inches or mm) and returns results in display units. The tolerance constants (`HOLESAW_CLEARANCE`, `MAX_HOLESAW_DEPTH`) are in inches. This works only because the current caller converts to display units first. A future metric user could hit bugs. Consider either:
- Documenting the unit contract explicitly
- Making `calculate_cope` accept a `UnitConfig` parameter

### SVG Template Hardcoded to Inches
The SVG template uses `"in"` for dimensions and prints measurements with `"` (inch) marks. A metric user would need a separate code path or unit-aware formatting.

### `build_order.py` Validation is Heuristic
The check for "has this tube been coped already?" relies on counting non-cylindrical/non-planar faces. This is a reasonable heuristic but could give false positives (e.g., a tube with chamfered edges) or false negatives (e.g., a cope that happens to produce only cylindrical/planar surfaces).
