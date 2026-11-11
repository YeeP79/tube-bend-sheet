# Fusion Tube-Geometry Extraction — Investigation (TubeFabrication add-in)

**Status:** Research note (point-in-time). **Date:** 2026-06-04.
**Subject repo:** `~/Projects/personal/fusion/add-ins/TubeFabrication` (the
add-in is internally named *TubeFabrication*; the `…/active/TubeFabrication`
path in the original brief was stale — this is the correct tree).
**Validated against:** the live Anvil model **`chassis v52`** (Ryan ran probe
scripts in Fusion; outputs quoted below).
**Purpose:** Understand how an existing, working Fusion add-in pulls a tube's
centerline, OD, and bends out of a solid body, so Anvil can reuse the approach
to get per-tube centerline + OD for tube/link members.

> Anvil's repo was not modified. Probe scripts were added to the TubeFabrication
> repo's `scripts/` dir (uncommitted, throwaway) and run by Ryan in Fusion.

---

## 1. What TubeFabrication is and how it's structured

A Fusion add-in that turns a modeled tube into shop paperwork: a **bend sheet**
(feed lengths, bend angles, rotations) and **cope/notch templates**. Calculation
is kept strictly Fusion-free.

| Layer | Fusion API? | Role |
|-------|-------------|------|
| `commands/` | Heavy | UI command handlers + the **Fusion→model bridge** |
| `core/` | None | Pure math: geometry, bend calc, cope math, formatting, HTML |
| `models/` | None | Dataclasses (`BodyPathResult`, `BendData`, `Tube`, `UnitConfig`…) |
| `storage/` | mixed | JSON profile/tube stores (Fusion-free) + document attributes |

**Correction to the original brief:** there is **no
`commands/copeCalculator/body_extraction.py`**. The reusable BRep extractor is
**`commands/shared/body_path_extractor.py`**, orchestrated by
`commands/tubeFabrication/body_analyzer.py`. Commands present:
`tubeFabrication/` (unified: select body → bend sheet + cope), `createBendSheet/`
(legacy sketch-based path), `manageBenders/`, `manageTubes/`, `shared/`.

Core modules of interest: `core/body_path.py`
(`body_path_to_straights_and_bends`), `core/body_profile.py` (coaxial merge / OD
filter), `core/geometry.py` (`calculate_rotation` = cross-product method),
`core/geometry_extraction.py` (sketch-entity endpoints, for the legacy route).
Models: `models/body_path_data.py` (`BodyFaceSegment`, `BodyPathResult`),
`models/bend_data.py` (`StraightSection`, `BendData`, `BendSheetData`),
`models/units.py` (`UnitConfig.cm_to_unit`; Fusion stores geometry in **cm**).

---

## 2. How it extracts a tube's centerline + diameter (the reusable core)

`extract_body_path(body) -> BodyPathResult | None` reads the finished **B-rep** —
no sketch or feature history needed. A tube = a chain of **OD cylinder faces**
(straights) joined by **torus faces** (bends); it walks the face-adjacency graph.

### Fusion API calls it relies on
- `body.faces` iteration; `face.geometry.surfaceType`:
  **`1` = Cylinder** (`.radius`, `.axis`=centerline dir, `.origin`),
  **`4` = Torus** (`.majorRadius`=**CLR**, `.minorRadius`=tube OD radius, `.axis`,
  `.origin`).
- `face.area` — to pick the dominant radius.
- `face.edges` + `edge.geometry.curveType == 2` (Circle) → `edge.geometry.center`
  = centerline endpoints; `edge.tempId` — shared-edge adjacency + de-dupe.
- `face.boundingBox` — axial-extent fallback for coped ends (no circle edge).
- `body.boundingBox/entityToken/isVisible`, `root.allOccurrences` — assembly /
  receiving-tube search.

### Pipeline
1. **OD radius** = cylinder radius with the largest total `face.area`. ID =
   second largest → wall = OD − ID.
2. **Classify** OD faces into cylinders (straights) and tori (bends).
3. **Drop artifacts:** tori with bend angle `< MIN_BEND_ANGLE_DEG (3°)`
   (cope-cut slivers); for straight tubes, non-coaxial OD cylinders.
4. **Adjacency** by shared edge (`tempId`).
5. **Order — torus-anchored walk** (`_order_path_via_tori`): cylinder→torus→
   cylinder→… Anchoring on tori means cope-artifact cylinders (adjacent to path
   cylinders but never to a torus) fall out naturally. Straight tubes (no tori)
   fall back to endpoint detection.
6. **Extend terminal straights** with coaxial split faces (a cope cut can split
   the end cylinder; `_are_coaxial` re-absorbs the sliver).
7. **Per-segment geometry:** straight axis/origin from the cylinder; length +
   endpoints from the two farthest circle-edge centers (bbox-onto-axis fallback
   for coped ends); bend CLR = `torus.majorRadius`, bend angle from the two
   circle edges projected ⟂ the torus axis.
8. Returns `BodyPathResult`: `od_radius`, `id_radius`, ordered `segments`,
   `clr_values`, `clr_consistent`, `start/end_is_coped`, `start/end_point`.

**Essence (small, reusable):** *largest cylinder = OD; cylinder faces =
straights (axis+endpoints); torus faces = bends (majorRadius=CLR,
minorRadius=OD); adjacency by shared edge; order torus-anchored.*

### Where the centerline comes from
- Direction: `end_center − start_center` (between circle-edge centers); fallback
  `geometry.axis`.
- Points: circle-edge centers; axis∩bbox extremes for coped ends.
- Diameter: `2 × od_radius`. Wall = OD − ID radius.
- A centerline polyline = `[straight.start, straight.end, (arc through
  torus.origin), …]`; bends are fillets of radius `CLR`.

---

## 3. How it represents bends (bend table)

Flat **bend table**, not a sampled centerline (`models/bend_data.py`):
- `StraightSection`: number, length, start, end, vector.
- `BendData`: number, **angle** (bend, deg), **rotation** (deg between bend
  planes; **None for first bend**), **arc_length**.
- `BendSheetData` aggregates straights/bends + tooling (bender/die), geometry
  (`tube_od`, `clr`, `die_offset`), grip/tail, warnings.

**Multi-plane rotation** (relevant to the existing skill): rotation between
consecutive bends = angle between the two bends' plane normals, each normal =
`cross(incoming_vector, outgoing_vector)` (Bend-Tech / Rogue convention).
Caveats: first bend rotation = None; `calculate_rotation` returns an **unsigned
0–180°** (no roll direction); near-straight bends → degenerate normal (guarded).

---

## 4. Modeling convention — confirmed against `chassis v52`

**Anvil models one tube per body.** Validated by a full recursive, visible-only
sweep of the chassis:
- Real structural tubes are each their own body inside a named occurrence
  (`driver shock tower`, `front main to a pillar support`, `Winch fairlead
  support`, …). The chassis is built as mirror subassemblies `passenger side` and
  `driver side` (literal `(Mirror)` copies).
- **Tube stock:** predominantly **1.75″ OD × .120″ wall** (4.4450 / 0.3050 cm);
  the **front mains** (`rebuild: … front main`) are **1.75″ × .188″**. The one
  "mixed-wall" body (lower frame rail) is a .120 rail joined to a .188 front main
  — a real weld, and it still extracts as one OD path (§5).

**Two real wrinkles for an auto-converter:**
1. **Mitered / multi-straight members.** Some bodies show *N disconnected
   straight legs with **0 tori*** (some frame rails/braces) — straight segments
   meeting at miters, no mandrel bend. The torus-anchored walk has nothing to
   anchor on; if such a body is multiple welded straights it won't yield a single
   path. *(Untested class — treat each leg as its own member. NB: a "spreader" is
   NOT inherently this case — a spreader validated in §5 was a clean single-bend
   tube. Don't conflate "spreader" with "mitered multi-straight.")*
2. **Non-tube bodies false-positive as tubes.** Gussets, plates, brackets, and
   driveline parts (axle, diff, wheel, knuckle, heim, bolts) have cylindrical
   faces (holes, fillets, bosses) and get read as "tubes." An auto-converter
   needs a **tube classifier** (length ≫ OD, real circular end caps) and a
   **component allowlist** (chassis only — skip `Front AxleDB`, `Winch`, rod
   ends, driveline).

**Lessons baked in (now repo memory):**
- **Only analyze visible bodies** — hidden bodies are stale reference geometry. A
  first sweep falsely reported nonexistent 1″ tubes from hidden bodies.
- **Never derive dimensions from names.** Names like `… 1.75` go stale; measure
  geometry. Name = soft cross-check at most.

---

## 5. End-to-end validation (production algorithm, real bodies)

A probe replicating the **production** torus-anchored walk was run on three
representative tubes. All three extracted correctly:

| Body | Output | Notes |
|------|--------|-------|
| `Winch fairlead support` (Body10) | 3 straights + 2× **36.8°** bends, **27.9″** CL, rotation **0°** (planar). Dropped faces 0,1,4,5 (1.9–2.6″ perpendicular slivers) | Dropped = **cope artifacts**, correctly excluded |
| `lower frame rail` (Body2, mixed-wall) | 4 straights + **90°/58°/69°** bends, **95.5″** CL, rotations **90°** then **0°** (a real 3D-bent rail). Dropped face 17 = colinear seam-split of leg 7 | Extracts as **one tube** despite mixed wall; OD path unaffected |
| **spreader** (6-face) | 1 straight + **39.1°** bend, **34.8″** CL, no drops | Clean single-bend tube — this body is a *spreader*, confirming spreaders are not inherently the "mitered multi-straight" problem |

### Coping is detected per-end, never assumed
**Not all tubes are coped, and the converter must not assume they are.** The
extractor detects coping **per tube-end** — `start_is_coped` / `end_is_coped`,
set only when a terminal straight has non-circle edges — and *only then* engages
cope handling (dropping receiving-tube slivers, bbox-axis endpoint fallback). A
plain uncoped tube has clean circle end-caps and flows through untouched, with
no faces dropped (see the spreader and simple-tube rows above: **0 drops**).
Any Anvil export schema and documentation must make clear that **coping is a
per-end property, not a blanket assumption** — treating every tube as coped, or
every dropped face as a cope artifact, would be wrong.

### Connectivity is proximity-based, NOT cope-based
**How two tubes are determined to connect does not assume coping.**
`detect_receiving_tubes_assembly` is called at *both* tube endpoints
**"regardless of whether the body already has cope geometry"** (its own comment).
It takes the tube's centerline **endpoint** and finds another tube whose axis
passes within **~1.5 × OD** of that point, with an axial-overshoot reject. By
design it runs **before** any cope is cut (the cope template is generated *from*
the detected connection), so it must — and does — work on uncoped tubes.

The modeling requirement this implies (the thing the **Fusion user must be
told**) is *geometric*, not coping:
- A tube's **end must reach the tube it joins** — centerline endpoint within
  ~1.5×OD of the receiving tube's axis, and not overshooting past that tube's
  physical extent. Floating ends / gaps / short tubes won't register as connected.
- **Plate/bracket-mediated joints are invisible** to tube-to-tube detection (a
  bracket/gusset/tab is not a tube).
- Coped or uncoped, same-OD or mixed-OD — all fine, as long as the end is
  positioned at the joint.

User-facing rule for Anvil: *"Model tube ends so they meet the tubes they join
(within ~1.5×OD); coping is optional and can come later. Joints made through
plates won't be detected as tube connections."*

**Separation to carry into Anvil:** the *add-in as a whole* is cope-centric
because its deliverable is a **cutting template** — so the end-to-end product
assumes coping. But the **connectivity layer is independent of that** and is the
reusable piece: lift the endpoint-proximity connection detection
(`detect_receiving_tubes_assembly`) and the centerline/OD extraction
(`extract_body_path`); leave the cope-template generation behind. Anvil's
"which tubes connect" question should **not** inherit the coping requirement.

The earlier "ORDERED PATH (0 faces)" came from the **old prototype**
`scripts/explore_path/explore_path.py`, which orders by degree-1 endpoints and
chokes when artifact cylinders form loops (no endpoint exists). The **production**
`_order_path_via_tori` does not have this failure. Conclusion: **the production
extractor yields a correct centerline + bend table (lengths, angles, CLR,
multi-plane rotations) on coped, mixed-wall, and multi-bend chassis tubes.**

---

## 6. Coordinate convention (for placing tubes in vehicle space)

All `origin`/`axis` values are world/assembly coordinates in **cm**. Mapping to
vehicle semantics, derived from the model:
- **Centerline = X = 0 plane** (lateral = X). Proven by 116/191 mirror pairs and
  the literal driver = mirror-of-passenger subassemblies; matches the named
  `center table verticle plane`. A tube's off-centerline distance = signed X.
- **Up = +Y** (table at Y≈0, named `table plane`; heights increase with Y).
- **Fore/aft = Z**, and **front = −Z / back = +Z** — this is **already solved in
  the add-in code**, not a guess. `core/body_path.py:detect_path_direction` and
  `core/geometry_extraction.py:determine_primary_axis` both hard-code the full
  world→vehicle map: **X** Left(−)/Right(+), **Y** Bottom(−)/Top(+), **Z**
  Front(−)/Back(+). It's the standard Fusion "Front view" orientation; the add-in
  assumes the model is built to it. (Matches the geometry — front axle/shocks/bump
  stops sit at negative Z.) *NB: a stale docstring in `geometry_extraction.py`
  lines ~132–134 contradicts the actual dict at ~143–145; the dict and
  `body_path.py` are authoritative: −Z = Front.*

---

## 7. Persistence / export schema

TubeFabrication renders to HTML/PDF; it persists only small settings
(`storage/attributes.py:TubeSettings`, JSON tube/bender stores). There is **no
geometry export to inherit** — Anvil must design one. Suggested per-tube record
(mirrors `BodyPathResult`):

```jsonc
{
  "tube_id": "string", "occurrence_path": "passenger side/front shock tower/...",
  "units": "cm",                 // emit canonical cm; convert downstream
  "od": 4.4450, "id": 3.8354, "wall": 0.3050,
  "frame": { "centerline_axis": "X", "fore_aft_axis": "Z", "up_axis": "Y",
             "front_sign": -1 },
  "segments": [
    { "type": "straight", "start": [x,y,z], "end": [x,y,z] },
    { "type": "bend", "clr": 13.97, "angle_deg": 90.0,
      "axis": [x,y,z], "origin": [x,y,z], "rotation_deg": 90.0 }
  ],
  "start_coped": false, "end_coped": false
}
```

Agree up front on: **units (canonical cm)**, diameter-vs-radius, point
order/handedness, **bend encoding (CLR+angle+axis vs sampled arc points)**, and
**rotation sign** (TubeFab's is unsigned 0–180°).

---

## 8. Options & recommendation

**A. Reuse `extract_body_path` wholesale.** Validated to work on real coped /
mixed-wall / multi-bend tubes. *Cons:* ~1400 lines with TubeFab assumptions;
inherits unsigned-rotation; needs a tube-vs-not filter wrapped around it.

**B. New, smaller exploratory command in `fusion-addin/`.** Reimplement only the
essential ~30-line core (largest cylinder=OD; cylinder→straight; torus→bend;
shared-edge adjacency; torus-anchored order) and **export** rather than render.
*Pros:* clean schema, no baggage. *Cons:* re-solve cope-artifact / ordering edges.

**C. Read a centerline sketch/sweep path directly** (if Anvil tubes are
sketch-driven). Cheapest if a reliable path exists; couples to modeling discipline.

**Form:** export the **bend table** (CLR+angle+axis per bend) — compact, exact,
fabrication-ready — and let the Rust side **sample a polyline** from it when
needed. Deriving a polyline from the table is easy; inverting is lossy.

**Recommendation:** **Reuse (A)** for the clean mandrel-bent tubes (the bulk),
wrapped with (1) a **tube classifier**, (2) a **component allowlist** (chassis
only), (3) **handling for pure-miter multi-straight bodies** (split into
per-leg members), and (4) export in the X-lateral / Y-up / Z-fore-aft frame,
**geometry-measured, names never trusted**. Graduate toward (B)'s clean core if
the wrapper grows unwieldy. Keep Fusion authoritative for geometry; the Rust
converter consumes the bend-table JSON.

**Uncertain / to verify (not asserted):**
- ~~`front = −Z` sign~~ **RESOLVED** — the add-in already encodes Front(−Z)/
  Back(+Z) (and Left/Right, Bottom/Top) in `detect_path_direction` /
  `determine_primary_axis`. Reuse that map; don't re-derive it.
- Behaviour on pure-miter multi-straight bodies (multiple straights, **0 tori**)
  — untested. (A single-bend *spreader* validated fine; "spreader" ≠ this case.)
- **Coping is per-end, not universal** — some tubes aren't coped at all; the
  export must not assume coping or treat every dropped face as a cope artifact.
- **Tube-to-tube connectivity is inferred by endpoint proximity (~1.5×OD), NOT
  by coping.** The modeling requirement to surface to the Fusion user is that
  tube ends must geometrically reach the tubes they join; plate-mediated joints
  won't register. Decide whether Anvil reuses this proximity rule or derives
  connectivity another way (shared node sketch, etc.).
- Whether Anvil ever needs **signed** rotation (TubeFab's is unsigned).

---

## 9. Open questions for Ryan
1. ~~Confirm front = −Z~~ **RESOLVED in code** (add-in encodes Front(−Z)/Back(+Z),
   Left/Right, Bottom/Top — reuse `detect_path_direction`).
2. For pure-miter "spreader" bodies — one welded member, or several tubes? (Run
   `anvil_extract` on one to decide.)
3. Does the Rust side need **signed** roll/rotation, or just lengths + OD + bend
   angles?
4. Target export schema location/spec — want a `docs/02-spec/` draft next?

---

## 10. Probe scripts run (throwaway, in `scripts/`)
- `anvil_probe/` — single body: faces, OD/ID, axes, circle-edge centers.
- `anvil_probe_all/` — recursive visible-only inventory of every body/occurrence.
- `anvil_context/` — units, extents, named planes/sketches, L/R symmetry
  (centerline finder).
- `anvil_extract/` — **production-style** torus-anchored ordering: ordered
  straights+bends, lengths, CLR, bend angles, multi-plane rotations, total
  centerline, and which faces were dropped as artifacts.

All write full output to Fusion's Text Commands window via `app.log()` plus a
`~/<name>.txt` failsafe. Results are quoted in §4–6 above.
