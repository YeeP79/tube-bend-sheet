# Robustness Review: Cope Calculator Multi-Receiver Lobe Merging Fix

**Review Type:** DIFF REVIEW
**Date:** 2026-04-11
**Branch:** feature/cope-calculator
**Reviewer:** Claude Opus 4.6 (Automated)

---

## Review Scope

**Files Changed (in scope):** 16 modified, 28 untracked
**Primary focus (per user request):**
- `core/cope_math.py` -- +383/-109 lines (multi-receiver lobe merging bug fix, new functions)
- `tests/test_cope_math.py` -- +747/-17 lines (new test classes and expanded coverage)

**Supporting changes reviewed for context:**
- `core/tolerances.py` -- New constants: `MIN_COPE_INCLINATION_DEG`, `MAX_NOTCHER_ANGLE`
- `core/conventions.py` -- Reference description strings
- `models/cope_data.py` -- Data models (unchanged, reviewed for context)

**Test Status:** All 101 tests in `test_cope_math.py` pass.

---

## Changes Summary

This diff implements three significant improvements to the cope calculator:

1. **Notcher angle convention fix**: Changed from reporting the raw included/inclination angle to reporting `90 - inclination_angle`, matching VersaNotcher degree wheel convention (0 = perpendicular T-joint).

2. **Exact cylinder-cylinder intersection formula**: Replaced the simplified `z = (R_receive / sin(theta)) * cos(phi)` with the exact formula `z = [sqrt(R2^2 - R1^2*sin^2(phi)) - R1*cos(alpha)*cos(phi)] / sin(alpha)`, which correctly handles same-OD tubes.

3. **Multi-receiver merged lobe fix (primary bug fix)**: When two receivers' saddles merge into a single detected lobe (valley too shallow to split), the old code produced only one pass. The fix detects merged receivers and creates separate passes with individual notcher/rotation/depth settings.

4. **Shallow angle filtering**: Receivers below `MIN_COPE_INCLINATION_DEG` (5 degrees) are filtered out before z-profile computation, preventing impractically deep profiles from near-parallel false-positive detections.

---

## CRITICAL Issues (Must Fix)

### C1. `_build_passes` exceeds 180 lines -- Severe SRP violation

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 402-588
**Severity:** CRITICAL (maintainability)

The `_build_passes` function has grown to approximately 186 lines and now handles at least 5 distinct responsibilities:

```
Current Responsibilities:
  1. Front/back lobe classification -- Lines 438-453
  2. Lobe-to-receiver assignment (deduplication) -- Lines 455-465
  3. Merged receiver detection and notcher angle comparison -- Lines 472-509
  4. CopePass construction for unique lobes -- Lines 518-550
  5. CopePass construction for merged receivers -- Lines 552-579
  6. Post-hoc dominant pass reassignment -- Lines 581-587
```

**SRP Assessment:** SEVERE VIOLATION -- 6 responsibilities in one function.

**Recommended split:**

```python
def _classify_lobes_front_back(
    lobes: list[_Lobe], azimuths: list[float]
) -> tuple[list[_Lobe], list[_Lobe]]:
    """Separate lobes into front (within 90 deg of a receiver) and back."""
    ...

def _assign_lobes_to_receivers(
    front_lobes: list[_Lobe],
    back_lobes: list[_Lobe],
    azimuths: list[float],
    inclination_angles: list[float],
) -> tuple[list[_Lobe], dict[int, int], list[int]]:
    """Assign unique lobes to receivers, identify merged receivers."""
    ...

def _build_passes(
    lobes: list[_Lobe],
    inclination_angles: list[float],
    azimuths: list[float],
    receiving_tubes: list[ReceivingTube],
    od1: float,
    unit_label: str = '"',
) -> list[CopePass]:
    """Orchestrate: classify, assign, build CopePass entries."""
    front, back = _classify_lobes_front_back(lobes, azimuths)
    unique, lobe_map, merged = _assign_lobes_to_receivers(...)
    passes = _create_lobe_passes(unique, lobe_map, ...)
    passes += _create_merged_passes(merged, ...)
    return _sort_and_mark_dominant(passes)
```

This refactoring would make each piece independently testable and reduce cognitive load.

---

### C2. `object.__setattr__` used on non-frozen dataclass

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 584-586

```python
for p in passes:
    object.__setattr__(p, 'dominant', False)
object.__setattr__(passes[0], 'dominant', True)
```

`CopePass` is decorated with `@dataclass(slots=True)` but **not** `frozen=True`. Direct attribute assignment works fine:

```python
p.dominant = False  # This works on a non-frozen dataclass
```

Using `object.__setattr__` is misleading -- it suggests the dataclass is frozen when it is not. If the intent is to eventually freeze `CopePass`, then freeze it and keep `object.__setattr__`. Otherwise, use direct assignment.

**Impact:** Readability and future maintainability. A developer may assume `CopePass` is frozen and make incorrect assumptions.

**Recommendation:** Either:
- (A) Use direct assignment: `p.dominant = False`
- (B) Make `CopePass` frozen: `@dataclass(slots=True, frozen=True)` (and keep `object.__setattr__`)

---

## HIGH Priority Issues

### H1. `_compute_receiver_peak_depth` docstring claims phi=180 back-of-saddle but formula evaluates the front peak

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 613-643

The docstring states:
> The maximum occurs at the back of the saddle (phi=180 from the receiver azimuth), where sin(phi) = 0 and cos(phi) = -1

But if cos(phi) = -1 (at phi=180), then the z-profile formula gives:
```
z(180) = [sqrt(R2^2 - R1^2*0) - R1*cos(alpha)*(-1)] / sin(alpha)
       = [R2 + R1*cos(alpha)] / sin(alpha)
```

This is indeed a valid local maximum (the back peak). However, **this is the correct maximum for same-OD tubes at non-perpendicular angles** -- the back peak is deeper than the front peak. The formula itself is correct; the docstring is actually accurate. No code change needed, but I flag this for clarity since the naming "peak depth" could be confused with the front-facing cope apex.

**Recommendation:** Add a clarifying note in the docstring that this is the deepest point (back peak), not the cope apex (front peak). This distinction matters for fabricators.

### H2. Duplicate azimuth distance calculation -- violates DRY

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`

The azimuth wraparound distance pattern appears in 4 separate locations:

1. `_match_lobe_to_receiver` (line 597): `dist = abs(lobe.apex_azimuth - az); if dist > 180: dist = 360 - dist`
2. `_build_passes` front lobe classification (line 444): same pattern
3. `_build_passes` merged receiver check (line 481): same pattern
4. `_azimuth_dist` function (line 607-610): extracted helper

The `_azimuth_dist` helper was created but is only used in ONE place (line 492). The other three locations still use inline azimuth distance calculations.

**Recommendation:** Use `_azimuth_dist` consistently everywhere:

```python
# In _match_lobe_to_receiver:
dist = _azimuth_dist(lobe.apex_azimuth, az)

# In _build_passes front lobe check:
if _azimuth_dist(lobe.apex_azimuth, az) <= 90:

# In _build_passes merged receiver check:
if _azimuth_dist(lobe.apex_azimuth, azimuths[recv_idx]) <= 90:
```

### H3. `ACUTE_ANGLE_LIMIT` constant is now dead code but still exported

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/tolerances.py`, line 54
**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/__init__.py`, lines 69 and 166

The `ACUTE_ANGLE_LIMIT` constant was replaced by `MAX_NOTCHER_ANGLE` in all usage sites, but the original constant is still defined in `tolerances.py` and still exported from `core/__init__.py`. The comment on `MAX_NOTCHER_ANGLE` (line 63) even references it:

```python
# This is the complement of ACUTE_ANGLE_LIMIT: 90 - 25 = 65.
```

**Recommendation:** Either remove `ACUTE_ANGLE_LIMIT` if no external code depends on it, or mark it with a deprecation comment. Keeping both constants in sync is a maintenance burden and a source of potential confusion.

### H4. `_build_passes` owner-finding logic has a fragile conditional expression

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 490-493

```python
owner_idx = _match_lobe_to_receiver(
    unique_lobes[0] if len(unique_lobes) == 1 else
    min(unique_lobes, key=lambda lb: _azimuth_dist(lb.apex_azimuth, azimuths[recv_idx])),
    azimuths,
)
```

This ternary expression is hard to read and has a subtle behavior: when `len(unique_lobes) == 1`, it just uses that lobe. When there are multiple, it finds the closest lobe by azimuth. But the `_match_lobe_to_receiver` call then re-matches to receivers, which could return a **different receiver** than the one that "owns" the closest lobe.

**Potential issue:** The `lobe_to_receiver` dict is built earlier but not used here. Instead, the code recomputes the owner via `_match_lobe_to_receiver`, which is an approximation (nearest-azimuth) and could disagree with the earlier assignment in edge cases with closely-spaced receivers.

**Recommendation:** Use the `lobe_to_receiver` dict directly:

```python
closest_lobe_idx = min(
    range(len(unique_lobes)),
    key=lambda j: _azimuth_dist(unique_lobes[j].apex_azimuth, azimuths[recv_idx]),
)
owner_idx = lobe_to_receiver[closest_lobe_idx]
```

However, note that `lobe_to_receiver` is indexed by the **pre-sort** lobe position. After `unique_lobes.sort(...)` on line 512, the indices shift. This is a bug: the `lobe_to_receiver` dict becomes stale after the sort.

**Resolution:** Either:
- Do not re-sort `unique_lobes` until after all lobe-to-receiver mappings are resolved
- Store receiver index directly on the lobe (add a field to `_Lobe`)

---

## MEDIUM Priority Issues

### M1. `_build_passes` lobe_to_receiver dict is invalidated by re-sort

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 458, 465, 512

The `lobe_to_receiver` dictionary maps lobe index to receiver index:
```python
lobe_idx = len(unique_lobes)
unique_lobes.append(lobe)
lobe_to_receiver[lobe_idx] = receiver_idx
```

Then on line 512:
```python
unique_lobes.sort(key=lambda lobe: lobe.apex_z, reverse=True)
```

After sorting, the indices in `lobe_to_receiver` no longer correspond to the actual positions in `unique_lobes`. The dict is not used after the sort in the current code (the for-loop on line 519 calls `_match_lobe_to_receiver` to re-derive the mapping), but it is dead code that could mislead future developers.

**Recommendation:** Either remove `lobe_to_receiver` entirely (it is unused in the current iteration loop) or restructure to keep it valid.

### M2. Hardcoded holesaw depth warning thresholds (2.0 and 3.0 inches)

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 686-697

```python
elif depth > 3.0:
    warning = (
        f"Requires extra-deep holesaw ({depth:.1f}{unit_label} cutting depth). "
        ...
    )
elif depth > 2.0:
    warning = (
        f"Requires deep holesaw ({depth:.1f}{unit_label} cutting depth). "
        ...
    )
```

The thresholds 2.0 and 3.0 are magic numbers that should be named constants in `tolerances.py`. The `MAX_HOLESAW_DEPTH` (4.0) is already a constant, but these intermediate thresholds are inline.

Additionally, these thresholds are in **inches** but the `unit_label` parameter now supports metric. A metric user would see warnings at 2.0mm and 3.0mm, which are nonsensical thresholds for millimeters (a 2mm holesaw depth is trivial). The thresholds need to be unit-aware or the constants should document that they assume imperial units.

**Recommendation:** Extract to constants and document the unit assumption:

```python
# In tolerances.py:
HOLESAW_DEEP_WARNING: float = 2.0     # inches
HOLESAW_EXTRA_DEEP_WARNING: float = 3.0  # inches
```

Or, better, accept the thresholds as parameters when unit_label is metric, applying appropriate conversion.

### M3. Hardcoded `lobe_span_degrees=180.0` for merged receiver passes

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, line 575

```python
passes.append(CopePass(
    ...
    lobe_span_degrees=180.0,  # Hardcoded
    ...
))
```

For merged receivers, the lobe span is hardcoded to 180 degrees. This is a reasonable approximation (a full saddle spans ~180 degrees), but it does not match the actual span of the merged receiver's portion of the lobe. A more accurate value could be computed from the receiver's intersection profile.

**Impact:** Low -- this value is mainly informational in the output. But it could mislead a fabricator into thinking the lobe always spans exactly half the tube.

### M4. `_Lobe` dataclass removed `receiver_index` field but assignment logic grew

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 36-42

The `_Lobe` dataclass previously had a `receiver_index` field. It was removed in this diff, and the receiver assignment logic was moved into `_build_passes`. This creates a tension: the lobe-to-receiver assignment is now computed in multiple places via `_match_lobe_to_receiver` calls, rather than being determined once and stored.

**Recommendation:** Consider adding a `receiver_index: int | None = None` field back to `_Lobe` and populating it once during the assignment phase. This would eliminate redundant `_match_lobe_to_receiver` calls in `_build_passes` (there are currently 3 separate calls to this function within `_build_passes`).

### M5. Missing test: negative or zero `od1` input

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/tests/test_cope_math.py`

Neither `calculate_cope` nor `_compute_z_profile` validates that `od1` (incoming tube OD) is positive. If a caller passes `od1=0.0`, the code computes `r1 = 0.0`, which would not crash but would produce meaningless results. If `od1 < 0`, the code computes a negative radius, which would also produce incorrect geometry.

**Recommendation:** Add input validation in `calculate_cope`:

```python
if od1 <= 0.0:
    raise ValueError(f"Incoming tube OD must be positive, got {od1}")
```

And add a corresponding test:

```python
def test_zero_od_raises(self):
    with pytest.raises(ValueError, match="positive"):
        calculate_cope(v1=(1,0,0), od1=0.0,
            receiving_tubes=[ReceivingTube(vector=(0,1,0), od=1.75)])
```

### M6. Missing test: negative or zero receiving tube OD

Similar to M5, `ReceivingTube.od` is never validated. A receiver with `od=0.0` would produce `r2=0.0`, making `discriminant = -r1_sq * sin^2(phi)` which is always <= 0, so the profile would be all zeros. This is a silent failure.

---

## LOW Priority Issues

### L1. `_compute_holesaw_depth` variable naming inconsistency

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, lines 670-677

```python
theta_rad = math.radians(inclination_angle)
sin_theta = math.sin(theta_rad)
```

The parameter is now named `inclination_angle` but the local variables still use `theta_rad` and `sin_theta`. The rest of the file consistently uses `alpha` for inclination angle.

**Recommendation:** Rename to `alpha_rad` and `sin_alpha` for consistency.

### L2. Comment in `TestComputeReceiverPeakDepth::test_near_zero_angle_returns_zero` is misleading

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/tests/test_cope_math.py`, lines 1179-1186

The test name says "returns_zero" but the comment acknowledges it returns a large number, not zero:

```python
def test_near_zero_angle_returns_zero(self):
    """Very small inclination (sin ~= 0) -> guarded, returns 0."""
    depth = _compute_receiver_peak_depth(0.0001, 0.875, 0.875)
    # sin(0.0001) ~= 1.7e-6 which is above the 1e-10 guard, so the
    # formula runs. Result is a large number, not zero.
    assert depth >= 0.0
    assert math.isfinite(depth)
```

**Recommendation:** Rename to `test_near_zero_angle_finite` and update the docstring.

### L3. Test class docstring on `TestCase1Perpendicular` is stale

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/tests/test_cope_math.py`, line 31

```python
class TestCase1Perpendicular:
    """v1=(1,0,0), v2=(0,1,0), both 1.75" OD -> 90 deg notcher, 0 deg rotation."""
```

The docstring says "90 deg notcher" but the convention was changed so perpendicular = 0 deg notcher. The test itself was updated (`test_notcher_angle_0`), but the class docstring was not.

### L4. Minor: `_detect_lobes` lambda variable shadowing

**File:** `/Users/ryanhartman/Projects/personal/fusion/add-ins/TubeFabrication/core/cope_math.py`, line 341

```python
apex_azimuth = max(range(360), key=lambda i: z_profile[i])
```

The lambda parameter `i` shadows the loop variable `i` from the outer scope (if any). In this particular context there is no outer `i` in scope, but the same pattern on line 386 does occur inside a `for start, end in regions:` loop. Not currently a bug but could become one if the surrounding code changes.

---

## SOLID Adherence Analysis

### `_build_passes` function -- Detailed SRP Analysis

**Current Responsibilities:**
1. **Front/back lobe classification** (lines 438-453) -- Geometry concern
2. **Lobe-to-receiver assignment** (lines 455-465) -- Matching/assignment concern
3. **Merged receiver detection** (lines 472-509) -- Comparison/threshold concern
4. **CopePass construction from lobes** (lines 518-550) -- Data transformation
5. **CopePass construction from merged receivers** (lines 552-579) -- Data transformation
6. **Dominant pass reassignment** (lines 581-587) -- Post-processing concern

**SRP Assessment:** SEVERE -- 6 distinct responsibilities.

**OCP Assessment:** MODERATE VIOLATION -- Adding a new lobe classification strategy (e.g., three-way merge) would require modifying the deeply nested if/else logic inside this function.

**DIP Assessment:** GOOD -- The function depends on data types (`_Lobe`, `CopePass`) not concrete implementations.

### `calculate_cope` function -- SRP Analysis

**Current Responsibilities:**
1. **Input validation** (lines 70-84) -- Validation concern
2. **Inclination/azimuth computation** (lines 86-93) -- Calculation concern
3. **Shallow angle filtering** (lines 95-122) -- Filtering concern
4. **Z-profile computation orchestration** (lines 124-129) -- Orchestration
5. **Result assembly** (lines 131-156) -- Assembly concern

**SRP Assessment:** MODERATE -- This is an orchestration function, and 5 concerns is borderline. The shallow angle filtering (30 lines) could be extracted.

### Overall SOLID Score for Changed Code

| Principle | Score | Notes |
|-----------|-------|-------|
| SRP | 5/10 | `_build_passes` has too many responsibilities |
| OCP | 7/10 | Tolerance constants are configurable; method classification is extensible |
| LSP | 9/10 | No inheritance issues; data models are well-structured |
| ISP | 8/10 | `_Lobe` and `CopePass` are focused, small dataclasses |
| DIP | 8/10 | Pure functions with injected parameters; no global state |

**Weighted SOLID Score:** 7.0/10

---

## Test Coverage Analysis

### Positive Test Coverage

The new tests are excellent. The diff adds 672 net new test lines organized into 9 new test classes:

| Test Class | Tests | Category |
|------------|-------|----------|
| `TestDetectLobes` | 7 | Unit test of internal function |
| `TestMatchLobeToReceiver` | 5 | Unit test with wrap-around edge cases |
| `TestClassifyMethod` | 6 | Unit test covering all method paths |
| `TestArbitraryPerpendicular` | 5 | Geometry edge cases |
| `TestComputeZProfile` | 8 | Exact formula verification |
| `TestExactFormulaAccuracy` | 6 | Formula accuracy vs. simplified |
| `TestShallowAngleFiltering` | 5 | New filtering feature |
| `TestMergedLobeMultiReceiver` | 8 | Primary bug fix validation |
| `TestComputeReceiverPeakDepth` | 6 | New function unit tests |

### Defensive Test Quality

Strong points:
- Boundary testing at `MIN_COPE_INCLINATION_DEG` threshold (both sides)
- Negative discriminant handling tested
- Wrap-around azimuth distance tested
- Near-zero angle guards verified
- All-zero profile edge case tested
- Non-negativity invariants checked

### Missing Test Categories

1. **Negative/zero OD inputs** -- No tests for `od1 <= 0` or `ReceivingTube.od <= 0` (see M5, M6)
2. **Three receivers with merged lobes** -- Only two-receiver merging is tested. A three-receiver scenario where two merge and one is separate is not covered.
3. **`_build_passes` with empty azimuths** -- What happens if `azimuths` is empty? The function guard checks `lobes` but not `azimuths`.
4. **`_azimuth_dist` edge cases** -- The new helper function has no direct tests (it is tested indirectly through `_build_passes`).
5. **Unit label edge cases** -- What if `unit_label` is empty string? Should be harmless but not tested.

---

## Positive Findings

1. **Excellent formula documentation**: The z-profile formula, peak depth formula, and their derivations are thoroughly documented in docstrings with mathematical explanations. This is critical for fabrication code.

2. **Strong defensive programming in `_compute_z_profile`**: The `discriminant < 0.0` guard (line 300) correctly handles the case where the incoming tube is larger than the receiver -- a real-world scenario that would have crashed the old simplified formula.

3. **Shallow angle filtering is well-designed**: The filtering at `calculate_cope` level (before z-profile computation) with clear warnings is the right approach. The error messages include the receiver name, making debugging straightforward.

4. **The `_compute_inclination_angle` clamping improvement**: Adding `max(0.0, ...)` to the lower bound of `cos_theta` (line 177) is correct -- while `abs()` ensures non-negative in theory, floating point arithmetic could produce a tiny negative value. Good defensive practice.

5. **Test organization**: The new test classes are well-organized with clear docstrings explaining the physical scenario being tested. `TestMergedLobeMultiReceiver` includes a detailed class-level docstring explaining the real-world bug being reproduced.

6. **Convention fix**: Changing notcher angle from included angle to `90 - included_angle` aligns with VersaNotcher convention. The tests were all updated consistently.

7. **The `unit_label` parameterization**: Moving from hardcoded `"` to a configurable `unit_label` parameter follows OCP and prepares for metric support.

---

## Recommended Actions Summary

| Priority | Issue | Action |
|----------|-------|--------|
| CRITICAL | C1. `_build_passes` 186 lines / 6 responsibilities | Extract into 3-4 smaller functions |
| CRITICAL | C2. `object.__setattr__` on non-frozen dataclass | Use direct assignment or freeze the dataclass |
| HIGH | H2. DRY violation: azimuth distance duplicated 4x | Use `_azimuth_dist` helper everywhere |
| HIGH | H3. Dead constant `ACUTE_ANGLE_LIMIT` still exported | Remove or deprecate |
| HIGH | H4. `lobe_to_receiver` dict invalidated by sort | Use dict directly or add field to `_Lobe` |
| MEDIUM | M2. Hardcoded warning thresholds assume inches | Extract to constants, document unit assumption |
| MEDIUM | M3. Hardcoded 180 lobe span for merged passes | Compute from actual intersection profile |
| MEDIUM | M5-M6. No validation on OD inputs | Add validation + tests |
| LOW | L1-L4. Naming, comments, docstrings | Cleanup pass |

---

## Validation Commands

After addressing issues, run:

```bash
make validate  # Run all checks before committing
make typecheck # Pyright
pytest tests/test_cope_math.py -v  # Run focused tests
```
