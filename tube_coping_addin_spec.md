# Fusion 360 Add-In Spec: Moon Patrol Fabrication Tools
## Claude Code Prompt Document

---

## Project Context

A working Fusion 360 bend calculation add-in already exists for the Moon Patrol rock crawler chassis build. This spec describes expanding that add-in into a unified **Moon Patrol Fabrication Add-In** that houses both the existing bend calculator and a new tube coping calculator as separate commands under one roof.

**The goal of consolidation:**

The bend and cope tools are not independent — the bend geometry determines the rotational reference for every cope on a pre-bent tube. Keeping them in the same add-in allows them to share a conventions module, share geometry utilities, and present a single coherent UI to the user rather than two separate panels that must be kept in sync manually.

**Migration approach:**

Do not rewrite the bend calculator. Refactor the existing add-in's file structure to support multiple commands, move the bend calculator into the new structure as `commands/BendCalculator/`, and add the cope calculator alongside it as `commands/CopeCalculator/`. All existing bend calculator behavior must be preserved exactly. Run the existing bend calculator tests after refactoring to confirm nothing broke before touching the cope code.

**Reference the existing codebase first — before writing any new code.** Read every existing file. Understand the command registration pattern, UI panel approach, Fusion API usage, and any utilities already written. The cope calculator must follow the same patterns. Do not introduce new architectural patterns unless the existing ones genuinely cannot support the new functionality.

---

## What the Add-In Does

**Bend Calculator (existing — preserve as-is):**
Calculates tube bend angles, rotation between bends, and outputs bend sequence instructions for the JD Squared tube bender. Already working and tested.

**Cope Calculator (new):**
Given a user-selected tube body in Fusion 360 that is about to be coped and installed at a node where other tubes already exist as solid bodies, calculates and outputs:

1. **Fabrication method recommendation** — notcher single pass, notcher multi-pass, or wrap template + grinder, based on geometry complexity
2. **Notcher wheel setting** — the angle to set on the degree wheel, per pass
3. **Holesaw depth requirement** — minimum cutting depth needed, with warnings if specialty tooling is required
4. **Rotation mark** — degrees to rotate the tube from its back-of-bend reference to align the cope apex correctly
5. **Wrap template** — a printable 1:1 scale SVG showing the cope profile, color-coded by pass if multi-pass, with a cross-section reference diagram for bent tube orientation

---

## Core Design Decision: Bodies Over Sketch Lines

The add-in uses **solid tube bodies** as its primary input source, not sketch centerlines. This is the most important architectural decision.

**Why this matters at multi-tube nodes:**

When three or more tubes meet at a node, the order in which tubes are coped and installed is significant. The tube being coped last must have its saddle cut to wrap around all previously installed tubes at that node. If the add-in used only sketch lines (centerlines), it would have no way to know which tubes have already been physically coped and installed — the user would have to manually specify order, which is error-prone.

By using solid bodies, the add-in can directly inspect what geometry exists at the node. The bodies present represent tubes that are already modeled as installed (coped) at that node. The incoming tube's cope is then calculated as the boolean union of all intersections with those present bodies. If the bodies at the node have NOT already had their own copes accounted for, the intersection math will be wrong, and the add-in must detect and error on this condition.

**Build order enforcement:**

- The add-in must validate, for each receiving body at the node, that it does not intersect the incoming tube's centerline in a way that suggests its own cope hasn't been cut. Specifically: if a receiving tube body still has full cylindrical material in the region where the incoming tube should intersect it, and the geometry of the model does not reflect a previous cope having been made, the add-in should warn the user.
- The exact detection method should be determined based on what the Fusion 360 API makes feasible. Options include: checking whether the receiving body has any non-cylindrical faces in the intersection region, or checking whether a boolean intersection between the receiving body and the incoming tube's cylinder yields a volume larger than would be expected for a proper saddle-to-saddle fit.
- If validation fails, show an error dialog stating which body at the node appears to not yet be coped, and halt calculation.

---

## User Workflow

1. User opens the add-in panel
2. User selects **the incoming tube body** (the one being coped)
3. User selects **one or more receiving bodies** at the target node (the tubes already installed there)
4. Add-in validates the receiving bodies (build order check)
5. Add-in calculates notcher settings and generates the wrap template
6. Results are shown in-panel and the template is saved as an SVG file the user can print

---

## Geometry Extraction

From the selected incoming tube body:
- Extract the cylindrical body's axis to get the centerline unit vector **v₁**
- Extract the outer diameter OD₁
- Identify the end of the tube closest to the node (the end being coped)

From each receiving body at the node:
- Extract centerline unit vector **v₂, v₃, ...** for each
- Extract outer diameter OD₂, OD₃, ... for each
- Identify the approximate node center point (the centroid of all body axes' closest approach)

All geometry extraction should be done through the Fusion 360 API's BRepBody and BRepFace interfaces. Cylindrical faces have a well-defined axis accessible via the `geometry` property of a `BRepFace` when its surface type is `SurfaceTypes.CylinderSurfaceType`.

---

## Core Math Module: `cope_math.py`

This module must have **zero Fusion 360 API dependencies**. It takes plain Python vectors and numbers and returns results. This makes it fully unit-testable without the Fusion environment.

### Inputs
```python
def calculate_cope(
    v1: tuple[float, float, float],        # incoming tube centerline unit vector
    od1: float,                             # incoming tube outer diameter (inches)
    receiving_tubes: list[dict],            # list of {vector, od} for each receiving tube
    node_point: tuple[float, float, float]  # 3D point of node center
) -> CopeResult
```

### Notcher Angle

The notcher degree wheel on this build reads the **included angle between the two tube centerlines**. At 90° the tubes are perpendicular (straight cope). At 70° the included angle is 70° (20° off perpendicular, acute side). At 110° the included angle is 110° (20° off perpendicular, obtuse side).

For a single receiving tube, the included angle is:
```
θ = arccos(|v1 · v2|)
```

For a multi-tube node, calculate θ separately for each receiving tube. Report all angles. The user will make the primary notch at the dominant (largest) receiving tube angle and hand-finish for the others.

### Rotation Mark

The rotation mark tells the user where to orient the tube in the notcher chuck so the cope apex lands correctly.

1. Find the plane containing both centerlines (v1 and v2). Its normal is `n = v1 × v2`.
2. The cope apex (deepest point) lies in this plane on the side facing the receiving tube. Project this direction onto the cross-sectional circle of the incoming tube.
3. The resulting clock position (in degrees around the tube circumference, measured from a reference flat the user scribes before clamping) is the rotation mark.
4. Convention: 0° = reference mark faces directly toward the receiving tube axis. Report the rotation in degrees clockwise when viewed from the coped end.

### Wrap Template Profile

For a single receiving tube:

At each angular position φ around the incoming tube (0° to 360°, in 1° increments):
```
z(φ) = (R_receive / sin θ) × cos(φ - φ_offset)
```
Where:
- `R_receive` = receiving tube outer radius
- `θ` = included angle between centerlines  
- `φ_offset` = angular position of the cope apex (from rotation mark calculation)

Negative values of z(φ) are clamped to 0 (the cope only removes material, never adds).

For a multi-tube node:

Calculate `z_n(φ)` for each receiving tube independently using the formula above (each has its own θ and φ_offset). The final template profile is:
```
z_final(φ) = max(z₁(φ), z₂(φ), z₃(φ), ...)
```
This envelope represents the minimum material that must be removed to fit the cluster.

### Multi-Pass Detection

After computing z_final(φ), analyze the profile for **multiple distinct lobes**. A lobe is a local maximum in z_final(φ) that is separated from another local maximum by a valley where z_final drops significantly (threshold: the valley depth should be at least 15% of the tube OD to be considered a true separation, not just profile noise).

**What a multi-pass cope means physically:**

If z_final(φ) has a single dominant peak, the user can make one clean pass through the notcher at the calculated angle and rotation. The tube enters the notcher, passes through, and exits — one motion.

If z_final(φ) has two distinct lobes separated by a valley, the user cannot make a single clean pass. The two lobes correspond to two different receiving tubes at different angular positions around the circumference. A single pass at one angle would correctly cut lobe 1 but would either miss lobe 2 entirely or remove material that belongs to the un-cut valley between the lobes (which may need to remain for structural reasons or simply doesn't need to be removed).

In this case the notcher must be used in two separate operations:
- **Pass 1:** Set notcher to θ₁, rotate tube to rotation mark 1, plunge only until the lobe 1 apex depth is reached — do NOT push all the way through
- **Pass 2:** Rotate tube to rotation mark 2, set notcher to θ₂, plunge for lobe 2

The `CopeResult` object must include:

```python
@dataclass
class CopePass:
    notcher_angle: float        # degree wheel setting for this pass
    rotation_mark: float        # degrees CW from reference mark
    plunge_depth: float         # how far to push tube into notcher (inches), NOT pass-through
    is_pass_through: bool       # True = push all the way through; False = plunge to depth only
    lobe_span_degrees: float    # angular width of this lobe on the tube (for template annotation)
    dominant: bool              # True if this is the primary/deepest pass

@dataclass 
class CopeResult:
    passes: list[CopePass]      # one entry per required notcher pass
    is_multi_pass: bool         # True if more than one pass is required
    z_profile: list[float]      # z_final(φ) at 1° increments, 360 values
    template_svg_path: str | None
```

The plunge depth for a non-pass-through cut is the z value at the lobe apex plus a small clearance (0.03"). The user must stop the notcher at this depth and back out before repositioning for the next pass.

---

## Output Module: `template.py`

Generates an SVG file of the wrap template at **true 1:1 scale**.

### SVG Layout

The template is an unrolled cylinder surface. The horizontal axis represents the tube circumference (width = π × OD₁). The vertical axis represents the axial cope depth.

- X axis: angular position φ mapped to linear distance along tube circumference. Total width = π × OD₁ (half-wrap is sufficient since the cope is symmetric — output a half-template from -90° to +90° relative to the dominant apex, clearly labeled).
- Y axis: cope depth z(φ). Scale matches real inches 1:1.
- The profile curve is the locus of z_final(φ) points.
- The bottom edge of the template (z=0) is a straight line representing the uncut tube end.

### Multi-Pass Visual Annotation

When `CopeResult.is_multi_pass` is True, the template SVG must make this unmistakably clear. A user unfamiliar with compound copes might look at the profile and assume it's a single pass — the template must prevent this misunderstanding.

**Visual treatment for multi-pass templates:**

- Each lobe must be **filled with a distinct color** (e.g., lobe 1 = blue fill, lobe 2 = orange fill). The fills share the same baseline (z=0) and show the material being removed by each pass separately.
- The valley region between the lobes (where z_final drops back toward zero) must be clearly visible as a gap or transition between the colored fills — do not blend the lobes together.
- Each lobe must be annotated with a label directly on the fill: **"PASS 1"** and **"PASS 2"**, with the notcher angle for that pass: e.g., `"PASS 1 — Set notcher to 73.2°"`.
- A dashed vertical line must mark the apex of each lobe, extending from the profile curve down to the baseline.
- The dominant (deepest) pass must be labeled **"PRIMARY"** and the secondary labeled **"SECONDARY"**.

**Warning block — multi-pass copes:**

Include a prominent warning text block on the SVG, visually distinct from the instruction block (use a red border box):

```
⚠ MULTI-PASS COPE REQUIRED

This cope profile has two separate lobes. It CANNOT be made in a single 
pass through the notcher. Attempting a single pass-through will remove 
material from the valley between the lobes that should remain, ruining the fit.

PASS 1 (PRIMARY — Blue):
  Notcher angle: XX.X°
  Rotation: XX.X° CW from reference mark
  ⚠ Do NOT pass through — plunge to X.XXX" depth only, then back out

PASS 2 (SECONDARY — Orange):  
  Notcher angle: XX.X°
  Rotation: XX.X° CW from reference mark
  ⚠ Do NOT pass through — plunge to X.XXX" depth only, then back out

Sequence: Complete Pass 1 fully, then reposition for Pass 2.
Hand-file the valley transition between passes for final fit.
```

For single-pass copes, no warning block is shown. The instruction block simply reads "Single pass — push through at XX.X°."

### Registration Marks

Print the following on the template:
- Vertical centerline at φ=0° labeled "APEX — align to rotation mark"
- Vertical lines at φ=±90° labeled "90°"
- Horizontal scale bar (1 inch reference)
- Tube OD, wall thickness if known, date
- Node name/label if the user provides one

### Print Instructions Block

Include a text block on the SVG:
```
1. Print at 100% scale (no fit-to-page scaling)
2. Verify 1" scale bar before cutting
3. Cut along cope profile curve only
4. Wrap around tube end, aligning centerline of template to rotation mark scribed on tube
5. Tape in place and scribe along bottom edge of template
```

### File Output

Save the SVG to the same directory as the active Fusion document, named:
```
[document_name]_cope_[incoming_tube_name]_[timestamp].svg
```

Notify the user of the save path in the results panel.

---

## UI Panel

Build a palette-style panel (non-modal, dockable) consistent with how the existing add-in handles its UI.

### Inputs Section
- Button: "Select Incoming Tube" → activates selection filter for BRepBody
- Button: "Select Receiving Tubes at Node" → activates multi-select for BRepBody
- Text field: "Node Label" (optional, used in template filename and printout)

### Validation Section
- Status indicator for each selected receiving body: green checkmark (passed validation) or red warning (build order issue detected)
- Warning message text if validation fails

### Results Section
Display after successful calculation:

**Single-pass cope:**
- **Notcher Setting:** `XX.X°` (with note: "included angle between tube centerlines")
- **Rotation Mark:** `XX.X° clockwise from reference mark` (when viewed from coped end)
- **Pass type:** `Single pass — push through`
- **Template saved to:** `[path]`

**Multi-pass cope — show a prominent warning banner at the top of the results section in red/amber:**
```
⚠ MULTI-PASS COPE — Read carefully before cutting
```
Then for each pass:
- **Pass N (Primary / Secondary):**
  - Notcher angle: `XX.X°`
  - Rotation mark: `XX.X° CW from reference`
  - Plunge depth: `X.XXX" — DO NOT pass through`
- **Template saved to:** `[path]` (with note that template is color-coded by pass)

### Action Buttons
- "Calculate & Generate Template" — runs calculation and saves SVG
- "Clear Selection" — resets all inputs

---

## Unified Add-In Module Structure

```
moon_patrol_fab/
├── commands/
│   ├── BendCalculator/            # EXISTING — migrated from current add-in, no behavior changes
│   │   ├── entry.py
│   │   ├── bend_math.py           # existing bend math, untouched
│   │   ├── ui_panel.py
│   │   └── handlers.py
│   └── CopeCalculator/            # NEW
│       ├── entry.py               # command registration
│       ├── geometry.py            # Fusion API: centerline/OD/bend extraction from BRepBody
│       ├── validation.py          # build order checks on receiving bodies
│       ├── ui_panel.py            # palette panel, input/results UI
│       └── handlers.py            # Fusion event handlers
├── shared/
│   ├── conventions.py             # rotation reference constants shared by both commands
│   ├── fusion_utils.py            # common Fusion API helpers (body walking, face type checks)
│   │                              # — extract any duplicated Fusion API code from bend calculator here
│   └── geometry_utils.py         # common pure-Python geometry (vector math, projections)
│                                  # — no Fusion deps, usable in tests
├── lib/
│   ├── cope_math.py               # cope-specific pure math, no Fusion deps
│   └── template.py                # SVG wrap template generation, no Fusion deps
├── tests/
│   ├── test_bend_math.py          # existing bend tests — must still pass after refactor
│   ├── test_cope_math.py          # cope unit tests (Cases 1–5)
│   └── test_geometry_utils.py     # shared geometry utility tests
└── manifest.json                  # updated to register both commands
```

**Key structural rules:**

- `shared/conventions.py` is the single source of truth for the back-of-bend reference convention. Neither command defines its own convention — both import from here.
- `shared/fusion_utils.py` must not grow into a dumping ground. It contains only code that is genuinely used by both commands. If something is cope-specific, it stays in `commands/CopeCalculator/geometry.py`.
- `lib/cope_math.py` and `lib/template.py` have zero Fusion dependencies. They must be importable and fully testable in a plain Python environment with no Fusion installation.
- The bend calculator's `bend_math.py` should likewise remain Fusion-free if it currently is. If it has mixed Fusion and pure-math code, separate them during the refactor.

---

---

## Unit Test Cases

The following known cases must be validated before any Fusion integration work begins:

**Case 1 — Simple perpendicular cope:**
- v1 = (1, 0, 0), v2 = (0, 1, 0), both 1.75" OD
- Expected notcher angle: 90°
- Expected rotation mark: 0° (apex points directly toward receiving tube axis)

**Case 2 — The Moon Patrol front cross-brace tube:**
- Tube rises at 19.3° elevation in the side plane, runs perpendicular to frame rails in plan view (no lateral sweep)
- v1 = (0, cos(19.3°), sin(19.3°)) = (0, 0.9435, 0.3305)
- Receiving tube v2 = (1, 0, 0) (frame rail, running fore-aft)
- Both 1.75" OD
- Compute and record expected notcher angle and rotation mark. These become the ground-truth regression values.

**Case 3 — Compound angle tube:**
- v1 at 19.3° elevation AND 12° lateral sweep
- Single receiving tube, 1.75" OD
- Verify that notcher angle changes appropriately vs Case 2

**Case 4 — Multi-tube node, two receiving tubes, single-pass result:**
- v1 = incoming at slight angle, v2 and v3 nearly co-planar with v1
- The two lobe apexes are close enough in angle that z_final has one broad peak, no valley deep enough to trigger multi-pass detection
- Verify z_final(φ) = max(z2, z3) at each φ
- Verify `is_multi_pass = False`

**Case 5 — Multi-pass cope (the key new case):**
- Two receiving tubes at the node are in significantly different planes relative to the incoming tube — e.g., one is roughly in the same horizontal plane as the incoming tube, the other rises steeply out of plane
- Their lobe apexes are separated by ~90° or more around the tube circumference
- Verify `is_multi_pass = True`
- Verify two `CopePass` entries are returned, each with correct notcher angle and rotation mark
- Verify plunge depths are correct (lobe apex z value + 0.03" clearance)
- Verify the valley between lobes meets the 15% OD threshold
- Visually inspect the generated SVG to confirm the two-color lobe rendering and warning block are present and legible

All tests must pass before moving to Fusion API integration.

---

## Implementation Order

**Phase 0 — Refactor (touch nothing functionally, restructure only)**
1. Create the new `moon_patrol_fab/` directory structure
2. Move all existing bend calculator files into `commands/BendCalculator/`
3. Create `shared/conventions.py` with the rotation reference constants
4. Extract any Fusion API utilities used by the bend calculator into `shared/fusion_utils.py`
5. Extract any pure-math geometry code into `shared/geometry_utils.py`
6. Update `manifest.json` to register both commands (bend calculator re-registered at its existing entry point)
7. Run all existing bend calculator tests — **they must pass before Phase 1 begins**

**Phase 1 — Cope math, no Fusion**
8. Write `lib/cope_math.py` with all five unit test cases passing
9. Write `lib/template.py` generating correct SVG for Case 1 and Case 2 — print and physically verify scale
10. Visually inspect Case 5 (multi-pass) SVG to confirm color coding, warning block, and cross-section reference diagram

**Phase 2 — Fusion integration**
11. Write `commands/CopeCalculator/geometry.py` — centerline and bend extraction from BRepBody
12. Write `commands/CopeCalculator/validation.py` — build order checking
13. Write `commands/CopeCalculator/ui_panel.py` and `handlers.py`
14. Write `commands/CopeCalculator/entry.py` to register the command alongside the bend calculator

**Phase 3 — Integration test**
15. Load the unified add-in in Fusion with the Moon Patrol model
16. Verify bend calculator still works identically to before the refactor
17. Run cope calculator on the Case 2 tube (front cross-brace, 19.3° elevation) and verify output matches Phase 1 unit test values
18. Run cope calculator on a known multi-pass node and verify Method B classification and two-pass SVG output

---

## Rotational Reference for Pre-Bent Tubes

This section addresses the most practically critical problem in the entire add-in: when a tube has already been bent before coping, the rotational orientation of the coped end is not free — it is fully determined by the bend geometry. The rotation mark for the notcher or grinder setup must be expressed relative to a physical feature that already exists on the tube, not an arbitrary scribe made at the notcher.

### The Problem

For a straight tube, the user scribes a reference line before clamping in the notcher, and the rotation mark is an angle from that line. The line can be anywhere.

For a bent tube, the user cannot freely rotate the tube end in the notcher without also rotating the bends — the whole tube moves as a rigid body. The tube has a specific orientation in 3D space determined by its bends, and the cope must land correctly in that orientation. If the rotation reference is arbitrary, the user has no way to align the notcher setup to match the Fusion model's geometry.

### The Solution: Back-of-Bend as Universal Reference

The **back of the last bend before the coped end** (the outside of the curve, the extrados) is the correct zero reference. It is:
- Physically identifiable on any bent tube with a straightedge or square
- Already tracked by the bend add-in — it is the reference from which inter-bend rotation angles are measured
- Consistent: every tube that goes through the bend process has this mark available

**Convention (must be identical in both add-ins):**
- 0° = back of last bend (extrados, outside of curve), facing away from the notcher holesaw center
- Angles increase clockwise when viewed from the coped end toward the tube
- If the tube has no bends (straight tube), the user scribes an arbitrary reference line and marks it as 0° before clamping — the add-in outputs the rotation from that mark as usual

### Integration with the Bend Add-In

The cope add-in cannot work correctly for bent tubes without knowing the bend geometry. This requires a formal integration point between the two add-ins.

**What the bend add-in must provide (or what the cope add-in must extract from the Fusion body):**

1. The centerline direction at the coped end: **v₁** (already extracted from body geometry)
2. The bend plane of the last bend before the coped end: specifically, the **back-of-bend direction vector** at that end — the vector pointing from the bend center toward the outside of the curve, projected into the tube's cross-sectional plane at the coped end
3. The angular offset between that back-of-bend direction and the cope apex direction — this is the rotation mark the user physically sets

**Extraction from Fusion body geometry:**

A bent tube body in Fusion has curved (toroidal) faces at each bend and cylindrical faces on the straight segments. The cope add-in should:

1. Walk the BRepFaces of the selected body from the coped end inward
2. Find the first non-cylindrical face (the nearest bend's toroidal section)
3. Extract the torus geometry: the torus axis gives the bend plane normal, and the center of the torus gives the bend center point
4. Compute the back-of-bend direction: the vector from the torus center to the tube centerline at the start of the bend, projected into the cross-section at the coped end
5. This vector becomes the 0° reference

If no toroidal face is found (straight tube), fall back to arbitrary reference with a UI note instructing the user to scribe a reference line before clamping.

### Communicating the Reference to the User

**In the UI panel results**, the rotation mark section must clearly state what it is relative to:

```
Rotation mark: 34.5° CW from back-of-bend
(viewed from coped end; 0° = outside of last curve)
```

Never report just a number without the reference. A number without a reference is useless on a bent tube.

**On the SVG template**, add a reference diagram — a small cross-section circle of the tube showing:
- A bold mark at 0° labeled "Back of last bend (extrados)"
- An arrow at the rotation mark angle labeled "Cope apex — align to notcher"
- The angular value labeled on the arc between them

This diagram is more valuable than the number alone because the user can hold the template next to the tube end, visually align the 0° mark to the back of the bend, and directly see where the cope apex should land.

### Physical Workflow for Bent Tube Coping

Add this as a step-by-step procedure block on the SVG template when the tube is detected as having bends:

```
BENT TUBE — Reference Setup Procedure:

1. Identify the back of the last bend (outside of curve, extrados)
2. Use a permanent marker to mark this point on the tube end face 
   and extend a short line (~1") along the tube's outside surface
3. This mark = 0° reference
4. In the notcher chuck, rotate tube until the back-of-bend mark 
   aligns with the 0° position shown in the reference diagram above
5. From that position, rotate an additional XX.X° clockwise 
   (viewed from coped end) to reach the cope apex position
6. Lock chuck and verify with a protractor or angle finder before cutting
```

### Edge Case: Multiple Bends, Last Bend Is Very Short

If the last bend before the coped end is a very short segment (less than 1× OD in straight length between the bend and the tube end), the back-of-bend mark may be hard to identify clearly on the physical tube. In this case:

- The add-in should detect this condition (check straight segment length between last toroidal face and tube end)
- Offer the user an alternative reference: back of the **second-to-last** bend, with the rotation mark recomputed relative to that reference
- Note this clearly: "Last bend is very close to tube end — using second-to-last bend as reference. Rotation mark: XX.X° from back of second bend."

### Shared Convention Module

The reference convention must live in `shared/conventions.py` — the single source of truth imported by both commands:

```python
# shared/conventions.py

# Rotation reference convention — shared by BendCalculator and CopeCalculator
# Any change here must be reflected in both commands and all printed output
ROTATION_REFERENCE = "back_of_last_bend_extrados"
ROTATION_DIRECTION = "clockwise_from_coped_end"
ROTATION_ZERO_DESCRIPTION = "Outside of last curve (extrados), facing away from holesaw center"

# Fallback label for straight tubes (no bends)
ROTATION_ZERO_STRAIGHT_DESCRIPTION = "User-scribed reference line (tube has no bends)"
```

---

The add-in must recommend a fabrication method based on the complexity of the cope profile. The notcher is a precision tool but it has a narrow envelope of usefulness — outside that envelope, the wrap template + angle grinder is faster and more accurate than trying to force the notcher to do something it isn't designed for.

### Method Classification Logic

After computing `CopeResult`, classify the cope into one of three methods:

**Method A — Notcher (single pass, push-through)**
Conditions:
- `is_multi_pass = False`
- All lobes have apex separation < 30° from each other (or only one lobe)
- No included angle is < 25°

This is the clean, repeatable notcher case. Set angle, set rotation, push through.

**Method B — Notcher (controlled plunge, multi-pass)**
Conditions:
- `is_multi_pass = True`
- Lobe apexes are separated enough to require distinct passes
- But each individual pass still has an included angle ≥ 25°

The notcher is still usable but requires discipline — the user must stop at the plunge depth on each pass and not push through. The template and warning block are critical here.

**Method C — Wrap template + grinder**
Conditions (any one of these triggers Method C):
- Any included angle < 25° (cope is so elongated the notcher holesaw would need to travel further than the tube OD allows cleanly)
- Three or more distinct lobes detected
- Two lobes with apex separation < 30° where collapsing to a single pass would require an intermediate angle not achievable on the notcher
- Receiving tube OD significantly larger than incoming tube OD (the saddle wraps more than 180° around the receiving tube, exceeding the notcher's geometry)

For Method C, the notcher settings are still computed and reported (they may be useful for a rough first cut), but the primary guidance shifts to the wrap template.

### Holesaw Depth Requirement

For each notcher pass, calculate the minimum holesaw cutting depth required to complete that pass. This tells the user whether their current holesaw is long enough before they start cutting.

**The geometry:**

For a tube of outer diameter OD₁ being notched at included angle θ (the notcher wheel setting), the holesaw must travel axially from first contact on the near wall to last contact on the far wall. The required cutting depth is:

```
depth_required = OD₁ / sin(θ)
```

Where θ is the included angle in radians. At 90° (perpendicular) this reduces to exactly OD₁ — the holesaw only needs to be as deep as the tube is wide. As θ decreases toward acute angles, depth_required increases rapidly. At 45° it's OD₁ × √2. At 25° it's over 2× OD₁.

For a 1.75" tube:

| Notcher Angle | Depth Required |
|---------------|---------------|
| 90° | 1.75" |
| 70° | 1.86" |
| 60° | 2.02" |
| 45° | 2.47" |
| 30° | 3.50" |
| 25° | 4.14" |

For Method B (multi-pass, plunge only), use the plunge depth from `CopePass.plunge_depth` instead of the full formula — the user only needs the holesaw to reach that depth, not the full pass-through depth.

**Add to `CopePass`:**

```python
@dataclass
class CopePass:
    notcher_angle: float
    rotation_mark: float
    plunge_depth: float
    is_pass_through: bool
    lobe_span_degrees: float
    dominant: bool
    holesaw_depth_required: float   # minimum cutting depth needed for this pass (inches)
    holesaw_warning: str | None     # populated if depth exceeds common holesaw sizes
```

**Warning thresholds:**

- Standard bi-metal holesaws: ~1" cutting depth — sufficient for perpendicular and slightly angled cuts
- Deep holesaws (readily available): ~2" cutting depth  
- Extra-deep holesaws (specialty, expensive): ~3–4" cutting depth

Populate `holesaw_warning` based on `holesaw_depth_required`:
- `< 2.0"` → `None` (standard deep holesaw handles this)
- `2.0" – 3.0"` → `"Requires deep holesaw (2"+ cutting depth). Verify your holesaw before starting."`
- `3.0" – 4.0"` → `"Requires extra-deep holesaw (3"+ cutting depth). These are specialty items — confirm you have the right tool. Consider Method C (grinder) instead."`
- `> 4.0"` → `"Holesaw depth exceeds 4". A standard notcher setup cannot complete this pass. Use Method C (wrap template + grinder)."`

The `> 4.0"` condition should also **force a Method C reclassification** regardless of other criteria. Update the method classification logic accordingly: if any pass has `holesaw_depth_required > 4.0"`, escalate to Method C automatically.

### Reporting Holesaw Requirements

**In the UI panel results**, add under each pass:
```
Holesaw depth needed: X.XX"
⚠ Requires extra-deep holesaw — verify before cutting
```

**On the SVG template**, add to the per-pass annotation box:
```
Min. holesaw depth: X.XX"
```

This should be prominent enough that a user can check it before even getting to the notcher — ideally they're reading the template printout at the parts bench, not discovering the problem mid-cut.

When Method C is recommended:

**UI panel banner** (yellow/amber, not red — this is guidance not an error):
```
📋 RECOMMENDED METHOD: Wrap Template + Grinder

This cope profile is too complex for reliable notcher work alone.
The wrap template is your primary tool. Print it, scribe it onto
the tube, and use an angle grinder with a flap disc to rough in
the profile. Finish with a die grinder or hand files to final fit.

Notcher angles are shown below for reference — a rough first pass
on the notcher can save grinding time, but do not rely on it for
final fit.
```

**Template SVG changes for Method C:**
- The template is now the **primary deliverable**, not a secondary check
- Print instructions become the top-level heading, not a footnote
- Add a "ROUGH GRIND GUIDANCE" annotation on the template indicating the order to work around the profile — typically start at the shallowest material and work toward the deepest, checking fit frequently
- The profile curve is drawn heavier/bolder than in Methods A/B
- Add a note: "Leave 1/32\" proud of scribe line — final fit with die grinder in place"

### Reporting in Results Panel

Always show the recommended method prominently at the top of results, before the angle numbers:

- 🔵 **Method A — Notcher, single pass** — straightforward, proceed with angles below
- 🟡 **Method B — Notcher, multi-pass** — read pass sequence carefully before cutting  
- 🟠 **Method C — Wrap template + grinder** — notcher angles shown for reference only

This ensures the user's first read of the output is "what tool do I reach for" not "what numbers do I dial in."

---

## Known Constraints and Edge Cases

- **Multi-pass cope — three or more lobes:** Theoretically possible at a very complex node. The same logic applies — each lobe gets its own pass entry. The template must render all lobes in distinct colors (cycle through a palette). The warning block must list all passes in sequence. The implementation order matters: the deepest lobe should typically be Pass 1, as it sets the primary orientation, but this may be overridden by geometric considerations. Document the ordering logic used.
- **Multi-pass cope — overlapping lobes:** If two lobe apexes are within ~30° of each other, it may be possible to make a single wider-angle pass that covers both. Detect this condition and offer the user a note: "Lobes are close — a single pass at the intermediate angle XX.X° may be feasible with slight hand-finishing." Do not automatically collapse them; leave it as two passes with the note.
- **Parallel tubes:** If v1 and v2 are parallel (or anti-parallel), the included angle is 0° or 180°, and a saddle cope is not meaningful. Detect this and show an error.
- **Very acute angles (< 20°):** The cope becomes extremely elongated. The template SVG must still render correctly even for long profiles. Warn the user that hand-finishing will be significant.
- **Tube OD mismatch:** If the incoming tube OD differs from the receiving tube OD, the math still works — OD₁ affects the template width, OD₂ affects the cope depth profile. Ensure the formula uses the correct OD for each role.
- **Node point precision:** The node center is an approximation from body axis intersections. Small errors here do not affect the cope angle or rotation mark, only the template's z-axis offset. This is acceptable.
