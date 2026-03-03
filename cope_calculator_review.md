# Cope Calculator Feature - Code Robustness Review

**Date:** 2026-02-22
**Review Type:** DIFF REVIEW (uncommitted changes, new feature branch)
**Branch:** feature/cope-calculator
**Reviewer:** Claude Opus 4.6

---

## Review Scope

### Files Changed (Modified)
- `Makefile` (14 lines changed)
- `TubeFabrication.manifest` (renamed, 4 lines changed)
- `TubeFabrication.py` (renamed)
- `TubeFabrication.svg` (renamed)
- `__init__.py` (4 lines changed)
- `commands/__init__.py` (2 lines added)
- `config.py` (2 lines changed)
- `core/__init__.py` (32 lines added)
- `core/geometry.py` (40 lines added)
- `core/tolerances.py` (21 lines added)
- `models/__init__.py` (5 lines added)
- `models/types.py` (2 lines changed)
- `pyproject.toml` (5 lines changed)
- `pyrightconfig.json` (1 line added)
- `storage/attributes.py` (2 lines changed)
- `tests/__init__.py` (2 lines changed)
- `tests/conftest.py` (40 lines changed)
- `tests/helpers.py` (2 lines changed)
- `tests/test_geometry.py` (84 lines added)

### New Files
- `commands/copeCalculator/__init__.py` (1 line)
- `commands/copeCalculator/body_extraction.py` (146 lines)
- `commands/copeCalculator/build_order.py` (82 lines)
- `commands/copeCalculator/dialog_builder.py` (47 lines)
- `commands/copeCalculator/entry.py` (298 lines)
- `commands/copeCalculator/results_display.py` (91 lines)
- `core/conventions.py` (22 lines)
- `core/cope_math.py` (516 lines)
- `core/cope_template.py` (509 lines)
- `models/cope_data.py` (42 lines)
- `tests/test_conventions.py` (28 lines)
- `tests/test_cope_math.py` (507 lines)
- `tests/test_cope_template.py` (199 lines)

### Validation Status
- `make validate`: PASS (609 tests, 0 failures)
- `make typecheck`: PASS (0 errors, 0 warnings)

---

## Layer Compliance

| Layer | Fusion API Imports | Status |
|-------|-------------------|--------|
| `core/` | None at runtime (TYPE_CHECKING only in pre-existing files) | COMPLIANT |
| `models/` | None at runtime (TYPE_CHECKING only in pre-existing files) | COMPLIANT |
| `core/cope_math.py` | None | COMPLIANT |
| `core/cope_template.py` | None | COMPLIANT |
| `core/conventions.py` | None | COMPLIANT |
| `models/cope_data.py` | None | COMPLIANT |

The new cope calculator core logic is properly isolated from Fusion API dependencies.

---

## SOLID Adherence Score

- SRP: 8/10 (weight: 30%)
- OCP: 8/10 (weight: 20%)
- LSP: 9/10 (weight: 15%)
- ISP: 9/10 (weight: 15%)
- DIP: 7/10 (weight: 20%)

**Overall SOLID Score: 8.0/10**

---

## CRITICAL Issues (Must Fix)

### C1. No validation of `od1` or `ReceivingTube.od` for zero/negative values

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 41-67
**Severity:** CRITICAL -- will produce incorrect output silently or crash

The `calculate_cope()` function validates that vectors are non-zero and non-parallel, but never validates that tube outer diameters are positive. A zero or negative OD will silently produce a meaningless z-profile (all zeros, or negative amplitudes), and zero OD causes division issues downstream.

```python
# Current code at line 41:
def calculate_cope(
    v1: Vector3D,
    od1: float,
    receiving_tubes: list[ReceivingTube],
    reference_vector: Vector3D | None = None,
) -> CopeResult:
    if not receiving_tubes:
        raise ValueError("At least one receiving tube is required")

    v1_norm = normalize(v1)
    # ... no validation of od1 or rt.od
```

**Recommended fix:**

```python
def calculate_cope(
    v1: Vector3D,
    od1: float,
    receiving_tubes: list[ReceivingTube],
    reference_vector: Vector3D | None = None,
) -> CopeResult:
    if not receiving_tubes:
        raise ValueError("At least one receiving tube is required")

    if od1 <= 0:
        raise ValueError(f"Incoming tube OD must be positive, got {od1}")

    for i, rt in enumerate(receiving_tubes):
        if rt.od <= 0:
            name = rt.name or f"tube {i + 1}"
            raise ValueError(f"Receiving {name} OD must be positive, got {rt.od}")

    v1_norm = normalize(v1)
    # ... rest of function
```

**Why it matters:** A fabricator entering "0" into a UI field, or a unit conversion producing a negative value, would generate a template with no visible cope profile. The tube gets cut incorrectly.

---

### C2. Hardcoded unit assumptions in holesaw warnings and tolerances

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/tolerances.py`, lines 55-60
**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 460-476

The cope tolerance constants `MAX_HOLESAW_DEPTH`, `HOLESAW_CLEARANCE`, and the holesaw warning thresholds (2.0, 3.0) are all hardcoded in inches. The warning messages explicitly include the `"` inch symbol. However, `calculate_cope()` receives `od1` in "display units" which could be millimeters if the user's design is metric.

```python
# tolerances.py line 57:
MAX_HOLESAW_DEPTH: float = 4.0  # inches

# cope_math.py line 465:
if depth > 3.0:
    warning = (
        f"Requires extra-deep holesaw ({depth:.1f}\" cutting depth). "
        # ...
    )
elif depth > 2.0:
    warning = (
        f"Requires deep holesaw ({depth:.1f}\" cutting depth). "
        # ...
    )
```

If `od1` is passed in mm (e.g., 44.45 for 1.75"), the depth calculation `od1 / sin(theta)` will be in mm, and the threshold comparisons against 2.0/3.0/4.0 (inches) will be meaningless -- nearly every cope would trigger a "depth exceeds" warning.

**Recommended fix:**

Either (a) document and enforce that `calculate_cope()` always receives values in inches, or (b) pass a unit label parameter and scale thresholds accordingly:

```python
# Option A: Document the contract explicitly in the docstring and add
# a unit assertion or at least a clear comment at the call site.
# In entry.py, the call already converts to display units, which for
# imperial IS inches -- but for metric would be mm or cm.

# Option B (preferred): Make tolerances unit-aware
def _compute_holesaw_depth(
    od1: float,
    notcher_angle: float,
    is_pass_through: bool,
    plunge_depth: float,
    unit_label: str = "in",
) -> tuple[float, str | None]:
    """..."""
    # Scale thresholds based on unit system
    if unit_label == "mm":
        max_depth = MAX_HOLESAW_DEPTH * 25.4
        deep_threshold = 3.0 * 25.4
        moderate_threshold = 2.0 * 25.4
    else:
        max_depth = MAX_HOLESAW_DEPTH
        deep_threshold = 3.0
        moderate_threshold = 2.0
    # ... use scaled thresholds
```

**Why it matters:** A metric user would get nonsensical holesaw warnings and incorrect Method C recommendations. This could cause them to disregard valid warnings in the future (cry-wolf effect) or use the wrong fabrication method.

---

### C3. `_compute_notcher_angle` only returns 0-90 range, discarding obtuse angles

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 124-140

The spec document (line 99) states the notcher reads **included angles** and explicitly mentions 110 degrees as a valid setting (20 degrees off perpendicular, obtuse side). However, `_compute_notcher_angle` uses `abs(dot_product)`, which folds all angles into the 0-90 range and discards the distinction between acute and obtuse.

```python
# Current code:
def _compute_notcher_angle(v1: Vector3D, v2: Vector3D) -> float:
    cos_theta = abs(dot_product(v1, v2))  # abs() folds 90-180 into 0-90
    cos_theta = min(1.0, cos_theta)
    return math.degrees(math.acos(cos_theta))
```

If two tubes meet at 110 degrees (included), this function returns 70 degrees. For certain notcher degree wheels that read the included angle directly, this would cause the wrong setting.

**Recommended fix:**

```python
def _compute_notcher_angle(v1: Vector3D, v2: Vector3D) -> float:
    """Compute the included angle between two tube centerlines.

    Returns the full included angle (0-180). The notcher degree wheel
    may read either the acute or obtuse angle depending on setup.
    """
    cos_theta = dot_product(v1, v2)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))
```

However, this requires careful review of how the angle is used downstream (z-profile computation, acute angle limit check). The `abs()` may be intentional for the z-profile formula but incorrect for the displayed notcher angle. At minimum, the docstring must clarify which convention is used and why.

---

## HIGH Priority Issues

### H1. `_compute_notcher_angle` does not clamp lower bound of `cos_theta`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, line 139

```python
cos_theta = abs(dot_product(v1, v2))
cos_theta = min(1.0, cos_theta)  # Only upper bound clamped
return math.degrees(math.acos(cos_theta))
```

Since `abs()` makes `cos_theta` non-negative, and `min(1.0, ...)` caps the upper bound, the lower bound of 0.0 is guaranteed. So this is technically safe because `acos(0..1)` is always valid. However, the pattern is inconsistent with every other `acos` call in the codebase which uses `max(-1.0, min(1.0, ...))`. This inconsistency makes the code harder to review and more fragile if the `abs()` is ever removed (per C3 above).

**Recommended fix:**

```python
cos_theta = max(-1.0, min(1.0, dot_product(v1, v2)))
# or if keeping abs():
cos_theta = max(0.0, min(1.0, abs(dot_product(v1, v2))))
```

---

### H2. `body_extraction.py` -- `extract_bend_reference` finds first torus face, not nearest to cope end

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/commands/copeCalculator/body_extraction.py`, lines 76-97

The function iterates `body.faces` and returns the first toroidal face found. The Fusion API does not guarantee face iteration order, so on a tube with multiple bends, this may return a bend far from the cope end rather than the "last bend before the cope end" as the docstring claims.

```python
# Current: returns FIRST torus found, not nearest to cope_end
for face in body.faces:
    geom = face.geometry
    if isinstance(geom, adsk.core.Torus):
        center = geom.origin
        # ... immediately returns
```

**Recommended fix:**

```python
def extract_bend_reference(
    body: adsk.fusion.BRepBody,
    cope_end: Point3D,
) -> tuple[Vector3D | None, str]:
    import adsk.core

    best_torus: adsk.core.Torus | None = None
    best_dist: float = float('inf')

    for face in body.faces:
        geom = face.geometry
        if isinstance(geom, adsk.core.Torus):
            center = geom.origin
            dist = (
                (cope_end[0] - center.x) ** 2
                + (cope_end[1] - center.y) ** 2
                + (cope_end[2] - center.z) ** 2
            )
            if dist < best_dist:
                best_dist = dist
                best_torus = geom

    if best_torus is not None:
        center = best_torus.origin
        cope_x, cope_y, cope_z = cope_end
        ref_x = cope_x - center.x
        ref_y = cope_y - center.y
        ref_z = cope_z - center.z
        mag = math.sqrt(ref_x**2 + ref_y**2 + ref_z**2)
        if mag > 1e-10:
            ref_vector: Vector3D = (ref_x / mag, ref_y / mag, ref_z / mag)
            return ref_vector, "Back of last bend (extrados)"

    return None, "Straight tube -- use scribed reference line"
```

**Why it matters:** On a tube with 3 bends, the wrong bend reference direction means the rotation mark is calculated from the wrong datum. The fabricator cuts the cope rotated to the wrong position.

---

### H3. `body_extraction.py` -- `identify_cope_end` uses bounding box corners, not tube centerline endpoints

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/commands/copeCalculator/body_extraction.py`, lines 101-146

Bounding box min/max points are the corners of the axis-aligned bounding box, not the endpoints of the tube's centerline. For a tube oriented at a 45-degree angle, the bounding box corners can be significantly offset from the actual tube ends.

```python
# Current: uses bounding box corners as "endpoints"
bbox = body.boundingBox
min_pt = bbox.minPoint
max_pt = bbox.maxPoint
end1: Point3D = (min_pt.x, min_pt.y, min_pt.z)
end2: Point3D = (max_pt.x, max_pt.y, max_pt.z)
```

This will produce the wrong "cope end" determination for tubes not aligned with coordinate axes. The centroid-proximity heuristic may still yield the correct answer in many cases (whichever bounding box corner is closer to the node is likely on the cope-end side), but it is geometrically incorrect.

**Recommended fix:** Use the cylinder axis direction and body centroid to compute the two endpoints along the axis, or walk the cylindrical face edges to find the actual end circles.

```python
def identify_cope_end(
    body: adsk.fusion.BRepBody,
    receiving_bodies: list[adsk.fusion.BRepBody],
) -> Point3D:
    import adsk.core

    # Find the cylinder axis
    axis_vector: adsk.core.Vector3D | None = None
    axis_origin: adsk.core.Point3D | None = None

    for face in body.faces:
        geom = face.geometry
        if isinstance(geom, adsk.core.Cylinder):
            axis_vector = geom.axis
            axis_origin = geom.origin
            break

    if axis_vector is None or axis_origin is None:
        # Fallback to bounding box if no cylinder found
        bbox = body.boundingBox
        return (bbox.minPoint.x, bbox.minPoint.y, bbox.minPoint.z)

    # Project bounding box extents onto the axis to find endpoints
    bbox = body.boundingBox
    min_pt = bbox.minPoint
    max_pt = bbox.maxPoint

    # Use 8 corners of bbox, project each onto axis, find min/max projections
    corners = [
        (min_pt.x, min_pt.y, min_pt.z), (max_pt.x, min_pt.y, min_pt.z),
        (min_pt.x, max_pt.y, min_pt.z), (min_pt.x, min_pt.y, max_pt.z),
        (max_pt.x, max_pt.y, min_pt.z), (max_pt.x, min_pt.y, max_pt.z),
        (min_pt.x, max_pt.y, max_pt.z), (max_pt.x, max_pt.y, max_pt.z),
    ]
    ax = (axis_vector.x, axis_vector.y, axis_vector.z)
    ox = (axis_origin.x, axis_origin.y, axis_origin.z)

    projections = []
    for c in corners:
        diff = (c[0] - ox[0], c[1] - ox[1], c[2] - ox[2])
        t = diff[0]*ax[0] + diff[1]*ax[1] + diff[2]*ax[2]
        projections.append(t)

    t_min = min(projections)
    t_max = max(projections)
    end1 = (ox[0] + t_min*ax[0], ox[1] + t_min*ax[1], ox[2] + t_min*ax[2])
    end2 = (ox[0] + t_max*ax[0], ox[1] + t_max*ax[1], ox[2] + t_max*ax[2])

    # ... then proceed with centroid comparison as before
```

---

### H4. `cope_template.py` is 509 lines -- moderate SRP concern

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_template.py`

**SRP Assessment:**

| Responsibility | Lines |
|---------------|-------|
| SVG document structure and dimensions | 103-110, 453-463 |
| Template area drawing (background, registration) | 113-143 |
| Profile curve rendering | 146-230 |
| Scale bar rendering | 233-241 |
| Info section text layout | 244-346 |
| Warning blocks | 348-377 |
| Print/procedure instructions | 380-416 |
| Reference diagram (cross-section circle) | 419-450 |
| SVG primitive helpers (line, text, etc.) | 466-509 |

**Assessment:** The module has a single public function (`generate_cope_svg`) and all helpers are private. The file is long but has a clear single purpose (SVG generation). The internal helpers are well-decomposed. This is a MINOR SRP concern at most -- splitting would increase file count without clear benefit given there is one entry point.

**Recommendation:** No immediate split needed. If the template grows to support additional features (e.g., metric templates, different SVG styles), consider extracting the SVG primitive helpers into a `_svg_helpers.py` module.

---

### H5. `cope_math.py` `_detect_lobes` assigns `receiver_index=0` as placeholder but never assigns correctly

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 338-343

```python
lobes.append(_Lobe(
    apex_phi=apex_phi,
    apex_z=apex_z,
    start_phi=start,
    end_phi=end,
    receiver_index=0,  # Will be assigned below  <-- NEVER ASSIGNED
))
```

The comment says "Will be assigned below" but no code after this point updates `receiver_index`. The `_Lobe` dataclass has a `receiver_index` field but it is never used after `_detect_lobes` returns -- `_build_passes` uses `_match_lobe_to_receiver` instead. This is dead code / misleading comment.

**Recommended fix:** Either remove the `receiver_index` field from `_Lobe` entirely, or assign it correctly in `_detect_lobes`. Since `_match_lobe_to_receiver` handles this responsibility, removing the field is cleaner:

```python
@dataclass(slots=True)
class _Lobe:
    """A peak region in the z-profile."""
    apex_phi: int
    apex_z: float
    start_phi: int
    end_phi: int
```

---

### H6. `_detect_lobes` single-lobe fallback hardcodes `receiver_index=0`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 286-295, 312-323

When the entire profile is above the valley threshold (line 286-295) or no significant regions are found (312-323), the fallback creates a lobe with `receiver_index=0`. While this field is unused (per H5), if it were used, the hardcoded `0` would be incorrect when the dominant receiver is not the first one.

This is a code smell indicating the `receiver_index` field should be removed (per H5 recommendation).

---

## MEDIUM Priority Issues

### M1. Duplicate method color/label maps in `results_display.py` and `cope_template.py`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/commands/copeCalculator/results_display.py`, lines 22-27
**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_template.py`, lines 260-265

Both files define:
```python
method_colors = {"A": "#2266AA", "B": "#CC8800", "C": "#CC6600"}
method_labels = {"A": "Method A ...", "B": "Method B ...", "C": "Method C ..."}
```

This is a DRY violation. If a method label changes, it must be updated in two places.

**Recommended fix:** Move the method display metadata to a shared location, either in `models/cope_data.py` as class attributes or in a small constants module:

```python
# In models/cope_data.py or a new cope_constants.py:
METHOD_COLORS: dict[str, str] = {"A": "#2266AA", "B": "#CC8800", "C": "#CC6600"}
METHOD_LABELS: dict[str, str] = {
    "A": "Method A -- Notcher, single pass",
    "B": "Method B -- Notcher, multi-pass",
    "C": "Method C -- Wrap template + grinder",
}
```

---

### M2. `_add_profile_curve` calls `max(z_profile)` twice

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_template.py`, line 154

```python
max_z = max(z_profile) if max(z_profile) > 0 else 1.0
```

This iterates `z_profile` (360 elements) twice. Minor performance issue but also a readability concern.

**Recommended fix:**

```python
max_z = max(z_profile)
if max_z <= 0:
    max_z = 1.0
```

Similarly at line 179:
```python
max_z = max(result.z_profile) if max(result.z_profile) > 0 else 1.0
```
Should be:
```python
max_z = max(result.z_profile)
if max_z <= 0:
    max_z = 1.0
```

---

### M3. `_add_multi_pass_profile` calculates `max_z` independently from `_add_profile_curve`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_template.py`, lines 154 and 179

Both `_add_profile_curve` and `_add_multi_pass_profile` independently compute `max_z` from the z-profile. If the values ever diverge (due to data mutation or floating point), the colored lobe fills and the profile curve would be drawn at different scales. They should share the same `max_z` value.

**Recommended fix:** Compute `max_z` once in `generate_cope_svg()` and pass it as a parameter to both functions.

---

### M4. `_add_warning_block` has hardcoded width `"4.5"` inches

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_template.py`, line 357

```python
rect.set("width", "4.5")
```

The warning block width is hardcoded at 4.5 inches regardless of the template width (`circumference = pi * od1`). For a small tube (e.g., 0.5" OD, circumference ~1.57"), the warning block extends far beyond the template. For a large tube (e.g., 4" OD, circumference ~12.57"), the warning block is relatively small.

**Recommended fix:** Base the warning block width on the template width:

```python
warn_width = min(template_w, 4.5)
rect.set("width", f"{warn_width}")
```

Or pass `template_w` to `_add_warning_block`.

---

### M5. No test for `NaN` or `Inf` tube OD values

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/tests/test_cope_math.py`

Tests cover zero vectors, parallel tubes, and empty receiver lists, but do not test:
- `od1 = 0.0`
- `od1 = -1.0`
- `od1 = float('nan')`
- `od1 = float('inf')`
- `ReceivingTube.od = 0.0`

These should raise `ValueError` after implementing C1.

**Recommended tests:**

```python
class TestInvalidOD:
    """Invalid tube OD values should raise ValueError."""

    def test_zero_od_raises(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=0.0,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            )

    def test_negative_od_raises(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=-1.0,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            )

    def test_nan_od_raises(self):
        with pytest.raises(ValueError):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=float('nan'),
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
            )

    def test_zero_receiving_od_raises(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_cope(
                v1=(1.0, 0.0, 0.0),
                od1=1.75,
                receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=0.0)],
            )
```

---

### M6. `entry.py` saves SVG to `~/Desktop` without checking directory exists

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/commands/copeCalculator/entry.py`, lines 273-277

```python
save_dir = os.path.expanduser('~/Desktop')
svg_path = os.path.join(save_dir, svg_filename)

with open(svg_path, 'w', encoding='utf-8') as f:
    f.write(svg_content)
```

On some Linux systems or custom configurations, `~/Desktop` may not exist. The `open()` call would raise `FileNotFoundError`, which would be caught by the outer `except:` but with a confusing error message.

**Recommended fix:**

```python
save_dir = os.path.expanduser('~/Desktop')
if not os.path.isdir(save_dir):
    save_dir = os.path.expanduser('~')

svg_path = os.path.join(save_dir, svg_filename)
```

---

### M7. `entry.py` does not sanitize filenames

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/commands/copeCalculator/entry.py`, lines 268-270

```python
doc_name = doc.name if doc else 'untitled'
svg_filename = f'{doc_name}_cope_{incoming_body.name}_{timestamp}.svg'
```

Fusion document names and body names can contain characters that are invalid in filenames on various operating systems (e.g., `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` on Windows). This would cause the `open()` call to fail.

**Recommended fix:**

```python
import re

def _sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

doc_name = _sanitize_filename(doc.name) if doc else 'untitled'
body_name = _sanitize_filename(incoming_body.name)
svg_filename = f'{doc_name}_cope_{body_name}_{timestamp}.svg'
```

---

### M8. `cope_math.py` -- `_compute_z_profile` silently skips receivers with near-zero `sin_theta`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 238-241

```python
sin_theta = math.sin(theta_rad)
if sin_theta < 1e-10:
    continue
```

When `sin_theta` is near zero, the tubes are nearly parallel. This case is already validated in `calculate_cope()` (lines 70-78), so the `continue` should be unreachable. However, if the validation threshold (`1.0 - 1e-8`) and the z-profile threshold (`1e-10`) ever drift apart, a receiver could pass validation but be silently skipped in the profile.

**Recommended fix:** Use the same tolerance constant, or add a comment explaining the relationship:

```python
# NOTE: Parallel tubes are rejected in calculate_cope() with a stricter
# threshold (dot > 1 - 1e-8). This guard is a safety net for numerical
# edge cases only and should never trigger during normal operation.
if sin_theta < 1e-10:
    continue
```

---

### M9. `_classify_method` lobe separation check accesses `lobes[0]` and `lobes[1]` without bounds check

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 505-511

```python
if len(lobes) == 2:
    sep = abs(lobes[0].apex_phi - lobes[1].apex_phi)
```

This is actually safe because the `len(lobes) == 2` guard ensures both indices exist. However, the function also checks `len(lobes) >= 3` (line 501) before this block, meaning the flow is:
1. `>= 3 lobes` -> Method C
2. `== 2 lobes` -> check separation
3. `== 1 lobe` -> falls through to single/multi pass check
4. `== 0 lobes` -> falls through (but `passes` would be empty)

When `lobes` is empty and `passes` is empty, `len(passes) == 1` is False, so it returns Method B. This is incorrect -- an empty passes list should probably not reach this code path at all.

**Recommended fix:** Add an early return for the empty case:

```python
def _classify_method(
    passes: list[CopePass],
    lobes: list[_Lobe],
) -> tuple[Literal["A", "B", "C"], str]:
    if not passes:
        return ("C", "Wrap template + grinder -- no cope geometry could be determined")
    # ... rest of function
```

---

## LOW Priority Issues

### L1. `conventions.py` constants are only used in cope_template.py, not in bend calculator

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/conventions.py`

The module docstring says "Both the bend calculator and cope calculator import from here" but `ROTATION_REFERENCE` and related constants are not imported by the bend calculator. This is forward-looking design (the spec mentions unifying the reference convention), not a current issue.

**Recommendation:** Add a TODO comment noting the bend calculator integration is pending, to avoid confusion during review.

---

### L2. `_Lobe` dataclass could use `frozen=True` for immutability

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_math.py`, lines 31-38

`_Lobe` instances are created once and never modified. Adding `frozen=True` would prevent accidental mutation:

```python
@dataclass(slots=True, frozen=True)
class _Lobe:
    """A peak region in the z-profile."""
    apex_phi: int
    apex_z: float
    start_phi: int
    end_phi: int
```

---

### L3. Magic numbers in `_add_info_section` and `_add_warning_block`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/core/cope_template.py`

Multiple hardcoded vertical spacing values: `0.25`, `0.2`, `0.15`, `0.13`, `0.05`, `0.1`, `0.12`, etc. These could be named constants for consistency:

```python
_LINE_SPACING_LARGE = 0.25
_LINE_SPACING_NORMAL = 0.15
_LINE_SPACING_SMALL = 0.13
_LINE_SPACING_TIGHT = 0.10
_SECTION_GAP = 0.20
```

This is a minor readability concern and low priority.

---

### L4. Test helper `_make_single_pass_result` and `_make_multi_pass_result` repeat `calculate_cope` setup

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/tests/test_cope_template.py`, lines 13-31
**File:** `/home/yeep/Projects/personal/active/TubeFabrication/tests/test_cope_math.py`

Multiple test classes in `test_cope_math.py` repeat the same `calculate_cope` call with identical parameters. This is acceptable for test readability but could be reduced with class-level fixtures:

```python
class TestCase1Perpendicular:
    @pytest.fixture(autouse=True)
    def setup_result(self):
        self.result = calculate_cope(
            v1=(1.0, 0.0, 0.0),
            od1=1.75,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=1.75)],
        )

    def test_notcher_angle_90(self):
        assert abs(self.result.passes[0].notcher_angle - 90.0) < 0.1

    def test_rotation_mark_0(self):
        assert 0.0 <= self.result.passes[0].rotation_mark < 360.0
```

---

### L5. `test_conventions.py` tests are trivially simple

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/tests/test_conventions.py`

The tests only verify constants are non-empty and have expected values. They serve as documentation more than as robustness tests. This is fine for a constants module but worth noting.

---

### L6. `cope_data.py` dataclasses could benefit from `frozen=True`

**File:** `/home/yeep/Projects/personal/active/TubeFabrication/models/cope_data.py`

`ReceivingTube`, `CopePass`, and `CopeResult` are created by the calculation engine and consumed by the template generator. They are never modified after creation. Adding `frozen=True` would prevent accidental mutation and make the data flow clearer:

```python
@dataclass(slots=True, frozen=True)
class CopePass:
    """Settings for a single notcher pass."""
    notcher_angle: float
    # ...
```

Note: `CopeResult` uses `field(default_factory=list)` for `warnings`, which works with `frozen=True` as long as the list is not modified after construction (it isn't).

---

## SOLID Analysis - Detailed

### Module: `core/cope_math.py` (516 lines)

**Current Responsibilities:**
1. Input validation (lines 64-78)
2. Notcher angle calculation (lines 124-140)
3. Rotation mark calculation (lines 143-213)
4. Z-profile computation (lines 216-253)
5. Lobe detection (lines 256-349)
6. Pass construction (lines 352-409)
7. Lobe-to-receiver matching (lines 412-425)
8. Holesaw depth computation (lines 428-477)
9. Method classification (lines 480-516)

**SRP Assessment:** MODERATE concern. The module has one public function (`calculate_cope`) that orchestrates 8+ internal steps. Each step is a separate private function, which is good decomposition. However, at 516 lines, the module is approaching the threshold where splitting makes sense.

**Recommended split if it grows further:**
- `cope_math.py` -- `calculate_cope()` orchestration + notcher angle + rotation mark
- `cope_profile.py` -- `_compute_z_profile()` + `_detect_lobes()` + `_Lobe`
- `cope_passes.py` -- `_build_passes()` + `_match_lobe_to_receiver()` + `_compute_holesaw_depth()` + `_classify_method()`

**Current verdict:** Acceptable for now. The single public API and clear internal decomposition make this manageable. Re-evaluate if the module grows past 600 lines.

### Module: `core/cope_template.py` (509 lines)

**Current Responsibilities:**
1. SVG structure creation (lines 103-110)
2. Template area rendering (lines 113-143)
3. Profile curve rendering (lines 146-230)
4. Info section layout (lines 244-416)
5. Reference diagram (lines 419-450)
6. SVG primitive helpers (lines 466-509)

**SRP Assessment:** MINOR concern. Single public function, clear purpose (SVG generation). The helpers are well-organized. See H4 above.

### Module: `commands/copeCalculator/entry.py` (298 lines)

**Current Responsibilities:**
1. Command registration/deregistration (lines 49-97)
2. Dialog creation and handler wiring (lines 100-124)
3. Input change validation (lines 127-168)
4. Cope calculation orchestration (lines 171-291)
5. File I/O for SVG output (lines 267-277)
6. Results display (lines 280-286)

**SRP Assessment:** MODERATE concern. The `command_execute` function (lines 171-291) at 120 lines is doing too much: selection validation, geometry extraction, cope calculation, SVG generation, file saving, and results display.

**Recommended refactoring:** Extract the core orchestration into a helper function:

```python
def _execute_cope_calculation(
    inputs: adsk.core.CommandInputs,
    design: adsk.fusion.Design,
    units: UnitConfig,
) -> tuple[CopeResult, str, str]:
    """Extract inputs, calculate cope, generate SVG.

    Returns (result, svg_content, svg_path)
    Raises ValueError for validation failures.
    """
    # ... selection extraction, validation, geometry extraction,
    # cope calculation, SVG generation
    return result, svg_content, svg_path
```

This would reduce `command_execute` to: get design, get units, call helper, display results.

### Module: `commands/copeCalculator/body_extraction.py` (146 lines)

**Current Responsibilities:**
1. Cylinder axis extraction (lines 19-53)
2. Bend reference extraction (lines 56-98)
3. Cope end identification (lines 101-146)

**SRP Assessment:** GOOD. Three focused functions, each with a single purpose. The module handles "geometry extraction from Fusion BRepBody objects" which is a cohesive responsibility.

### Module: `models/cope_data.py` (42 lines)

**SRP Assessment:** GOOD. Pure data structures with no behavior. Clean separation.

---

## Test Coverage Analysis

### Coverage by Category

| Category | Covered | Missing |
|----------|---------|---------|
| Happy path (spec cases 1-5) | YES (5 test classes) | -- |
| Zero vectors | YES | -- |
| Parallel tubes | YES | -- |
| Empty receivers | YES | -- |
| Acute angle Method C | YES | -- |
| Holesaw warnings | YES | -- |
| Z-profile properties | YES | -- |
| Reference vector presence | YES | -- |
| SVG well-formedness | YES | -- |
| SVG dimensions | YES | -- |
| SVG content (single/multi pass) | YES | -- |
| Invalid OD values (0, negative, NaN) | NO | See M5 |
| Very large OD values | NO | Edge case |
| Many receivers (5+) | NO | Load test |
| Floating point edge cases in rotation | PARTIAL | Near-axis reference vectors |
| `_detect_lobes` edge cases | NO | All-zero profile, single-degree lobes |
| `_arbitrary_perpendicular` coverage | INDIRECT | Called through rotation |
| `generate_cope_svg` with empty passes | NO | Edge case |
| `_add_multi_pass_profile` wrap-around lobes | NO | Lobe spanning 0/360 boundary |

### Recommended Additional Tests

```python
class TestDetectLobesEdgeCases:
    """Edge cases for lobe detection."""

    def test_all_zero_profile(self):
        """All-zero z_profile should return empty lobes."""
        from core.cope_math import _detect_lobes
        lobes = _detect_lobes([0.0] * 360, 1.75)
        assert lobes == []

    def test_single_point_lobe(self):
        """A single non-zero point should still produce a lobe."""
        from core.cope_math import _detect_lobes
        profile = [0.0] * 360
        profile[90] = 1.0
        lobes = _detect_lobes(profile, 1.75)
        assert len(lobes) >= 1

    def test_wrap_around_lobe(self):
        """A lobe spanning the 0/360 boundary."""
        from core.cope_math import _detect_lobes
        profile = [0.0] * 360
        for i in range(350, 360):
            profile[i] = 1.0
        for i in range(0, 10):
            profile[i] = 1.0
        lobes = _detect_lobes(profile, 1.75)
        assert len(lobes) == 1


class TestSvgEmptyEdgeCases:
    """SVG generation with edge case inputs."""

    def test_empty_z_profile(self):
        """SVG generation with empty z_profile should not crash."""
        result = CopeResult(
            passes=[], is_multi_pass=False, method="A",
            method_description="test", z_profile=[],
        )
        svg = generate_cope_svg(result, 1.75, "Test", "", False)
        ET.fromstring(svg)  # Should produce valid XML

    def test_very_small_od(self):
        """Very small OD should produce a valid template."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0), od1=0.25,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=0.25)],
        )
        svg = generate_cope_svg(result, 0.25, "SmallTube", "", False)
        ET.fromstring(svg)

    def test_very_large_od(self):
        """Large OD should produce a valid template."""
        result = calculate_cope(
            v1=(1.0, 0.0, 0.0), od1=12.0,
            receiving_tubes=[ReceivingTube(vector=(0.0, 1.0, 0.0), od=12.0)],
        )
        svg = generate_cope_svg(result, 12.0, "LargeTube", "", False)
        ET.fromstring(svg)
```

---

## Positive Findings

### Architecture
1. **Clean layer separation.** The new cope calculator follows the established pattern precisely: `core/` has zero Fusion imports, `models/` are pure dataclasses, `commands/` handles all Fusion API interaction.
2. **Single public API per module.** `calculate_cope()` is the one entry point for cope math, `generate_cope_svg()` is the one entry point for templates. This makes the API surface small and well-defined.
3. **Consistent with existing codebase patterns.** Handler registration uses `futil.add_handler()`, error handling uses `futil.handle_error()`, command lifecycle follows `start()`/`stop()`/`command_created()`/`command_execute()`/`command_destroy()`.

### Type Safety
4. **All functions have complete type hints.** Parameters, return types, and intermediate variables are typed throughout.
5. **No `Any` types used anywhere** in the new code. This is exemplary adherence to the project's type safety requirements.
6. **Proper use of `Literal` types** for method classification (`"A" | "B" | "C"`).
7. **`Vector3D` type alias** used consistently for all vector parameters.
8. **`TYPE_CHECKING` guards** properly used in command files that need Fusion types.

### Defensive Programming
9. **Floating point clamping** for `acos()` in `_compute_rotation_mark` (line 188): `max(-1.0, min(1.0, ...))`.
10. **Zero vector checks** via `normalize()` which raises `ZeroVectorError`.
11. **Parallel tube detection** with clear error messages (lines 70-78).
12. **Empty input validation** for `receiving_tubes` (line 64).
13. **Null-safe Fusion API access** throughout `entry.py` -- `design`, `incoming_sel`, `receiving_sel`, `incoming_body` all checked before use.

### Testing
14. **Comprehensive spec coverage.** All 5 spec test cases have dedicated test classes with multiple assertions per case.
15. **Defensive tests present.** Parallel tubes, zero vectors, empty receivers, and acute angles are all tested.
16. **SVG well-formedness validated.** Tests parse generated SVG as XML to ensure valid output.
17. **Symmetry test** for perpendicular cope z-profile (test_cope_math.py line 480-493) -- this is an excellent mathematical invariant test.
18. **609 tests pass** with zero failures, zero pyright errors. The codebase is in excellent shape.

### Code Quality
19. **Thorough docstrings** on all public and private functions, with Args/Returns/Raises sections.
20. **Named constants** for all tolerance values, centralized in `core/tolerances.py`.
21. **Clear separation of concerns** in the command layer: `dialog_builder.py`, `body_extraction.py`, `build_order.py`, `results_display.py` are each focused on one task.
22. **SVG template design** includes real fabrication-aware features: scale bar, print instructions, multi-pass warnings, bent tube reference setup procedure. These show deep domain understanding.

---

## Summary of Findings by Priority

| Priority | Count | Key Themes |
|----------|-------|------------|
| CRITICAL | 3 | Missing OD validation, hardcoded inch units, notcher angle range |
| HIGH | 6 | Incorrect bend reference selection, bounding box vs axis endpoints, dead receiver_index field, empty passes edge case |
| MEDIUM | 9 | DRY violations, double max(), magic numbers, missing tests for invalid ODs, filename sanitization |
| LOW | 6 | Immutability suggestions, test organization, minor cleanup |

---

## Recommended Validation Commands

```bash
make validate  # Run all checks before committing
make check     # Syntax only
make lint      # Ruff linter
make typecheck # Pyright
make test      # Unit tests
```

All currently pass. After implementing the recommended fixes, run these again to verify no regressions.
