# Bridge primitives: design

Eight feature-building tools for the Fusion MCP bridge, each useful alone, composed into macros later. `build_recipe` stays on hold. Design only; nothing here is built.

**Sources.** `combined` branch tools; the `shared-core` worktree (`common/{results,args,api,geometry}.py` exist today, the rest are assumed); `StlToFusionBuild.py` (cited as Build + line); Fusion's API defs at `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Python/defs/adsk/`. Signatures below were read from those defs. Anything marked **live** is unproven until its check runs.

**Findings that change the plan:**
- `sketch_profile` cannot draw a single-entity circle or add a loop to an existing sketch. Without that no hole or boss is threadable. It is extra work, needed first (section 10).
- `participantBodies` is documented for cut and intersect only. Join may ignore it (section 3).
- The same getter, on a fully defined input, is documented to return the bodies the tool intersects: a real dry run for cuts with no feature added (**live**).
- `findEntityByToken` returns a *list* (a split face comes back as several), and one entity's token strings can differ between reads. Tokens are never compared as strings, and every ref also carries a point (section 1).
- `setDistanceExtent` and `ThreadFeatures.createThreadInfo` are absent from the current defs. Build calls both, and they worked on 2704.1.53. Use `setOneSideExtent` and `ThreadInfo.create`.
- Build's point-to-edge distance uses the chord for anything but circles. Cope edges are splines, so `edge_treatment` uses `measureMinimumDistance` (section 4).

---

## 1. Contract shared by every primitive

**Units.** Every tool takes `units` (`in`, `cm`, `mm`; default `in`) and echoes `unit_labels`. All points and vectors in and out are world coordinates (root assembly context).

**Values.** The schema test forbids `anyOf`, so each dimension is two keys, exactly one required: `distance` (number) or `distance_expression` (string). A number becomes `createByString("1.5 in")`, so the dialog shows real units. An expression must pass `unitsManager.isValidExpression(expr, "cm")`; a bare `"2"` is refused because it would resolve in the document's default units.

**BodyRef** is the existing shape: `{"occurrence_path": "root", "body_name": "Plate", "body_index": 0}`; `body_index` is optional, required on ambiguity. `check_solids`' ref gains `body_index` when it moves to `common.bodies`.

**EntityRef** is what `find_entities` returns and every tool accepts. `token` or `point` may be omitted, not both. `point` comes from `pointOnFace` / `pointOnEdge` (documented to lie on the entity), never `centroid`, which can fall off an annular face.
```json
{"token": "...", "kind": "face", "point": [1.0, 0.5, 1.0], "body": {"occurrence_path": "root", "body_name": "Plate"}}
```

**Resolving a ref** (`common.entity_refs.resolve`), fresh on every call:
1. `findEntityByToken(token)`. With several results keep the one `point` lies on; none or two: refuse `ambiguous_split`.
2. Verify the distance from `point` to the entity is within `ref_tolerance` (0.001 in). A mismatch means the token now names something else, or the point was cut away: go to step 3.
3. `root.findBRepUsingPoint(point, type, tolerance, False)`, filtered to `body`. Report `resolved_by: "point"` in the result's `resolved` list. Nothing found, but the token resolved to one entity on the right body: accept it with a warning.
4. A native result when `body` is in an occurrence: `createForAssemblyContext(occurrence)`. `findAttributes` is known to hand back native entities that ignore the occurrence transform; tokens are **live** (RC-1).

Wrappers are never held between calls and are compared only with `==` (Build 2563).

**Preflight** (`feature_ops.preflight`), before any write, all refusals listed together: active product is a parametric design; no timeline item in error (Fusion rolls back API edits on a broken timeline); marker at the end unless inside `timeline_insert`; `design.activeEditObject` is not a `BaseFeature`; no target in a linked occurrence. A read-only document is a warning (`document_guard`). Features land in the component stated per tool, never `design.activeComponent`, and the result says which.

**Adding a feature** (`feature_ops.add_feature`, from Build 1781, 2006, 2824). `TypeError` re-raises: our call is wrong, and retrying repeats it. `RuntimeError` is a refusal, with Fusion's words kept verbatim. A returned feature whose `healthState` is error is deleted and counted as refused, reporting `errorOrWarningMessage`. Callers get a result, never an exception, so one failed feature cannot cost a macro's earlier work.

**Measuring** (`feature_ops.snapshot`). `check_solids`' `snapshot_records` and `diff_snapshots` move to `common.bodies`. Every write snapshots the whole design before and after, hidden bodies included, using `body.volume` (not `physicalProperties`), and stores the first with `store_baseline`, so `check_solids(baseline_token=...)` needs no extra call.

**Result envelope** of every write, tool-specific keys alongside:
```json
{"status": "built", "ok": true, "dry_run": false, "units": {"length": "in", "area": "in^2", "volume": "in^3"},
 "feature": {"name": "Boss", "type": "ExtrudeFeature", "component": "root", "timeline_index": 12, "health": "healthy"},
 "bodies": {"touched": [{"ref": {}, "role": "target", "volume_before": 12.0, "volume_after": 11.2, "delta": -0.8,
                         "percent": -6.67, "faces_before": 6, "faces_after": 7}],
            "created": [], "consumed": [], "outside_target": []},
 "baseline_token": "a1b2c3", "resolved": [], "warnings": []}
```
`status` is `built`, `planned` (dry run), `partial`, `suspect` (built, but a check disagrees), `undone` or `refused`. `ok` is true only for `built` and `planned`; `isError` is `not ok`. Partial is an error on purpose: a half-chamfered part is a missing feature (Build 2455).

**Dry run.** `dry_run` (default `false`, see Q1) runs validation, preflight, ref resolution and every read, adds no feature, and returns `status: "planned"` with `plan`.

**New common modules.** `common/entity_refs.py` (describe, resolve; pure filters load without `adsk`), `common/feature_ops.py` (preflight, values, add, snapshot, undo, `temp_copy`). Needed from `shared-core`: `common.bodies` (`iter_body_entries`, `resolve_targets`, `assign_keys`, diff) and `common.timeline` (`read_rows`, marker checks). Registration follows BRIEF.

**Live fixture**, built by the lead in a new file in Default Project, removed afterward. `Block` in root: 4 x 3 x 1 in, z 0 to 1. Component `Sub` holding `SubBlock`, 2 x 2 x 1 in; occurrence `Sub:1` moved +10 in X and rotated 30 deg about Z; occurrence `Sub:2` moved -10 in X.

**Ref checks, run first, since `resolve` rests on them:**
1. RC-1. `SubBlock` top face read through `Sub:1`, token, `findEntityByToken`: is `assemblyContext` still `Sub:1`, and does `pointOnFace` read in world coordinates?
2. RC-2. Same token after an unrelated new body is added: does it still resolve?
3. RC-3. Split that face with a cut: how many results, and is the first the larger?
4. RC-4. Chamfer one edge of `Block`, then resolve tokens of its two neighbors: alive, same curve?

---

## 2. `find_entities`

**Purpose.** Replace hand-written face and edge hunts. Its output is the input of every other primitive.

**Args.** Omitted `bodies` means visible solids only (hidden bodies are stale reference geometry).
```json
{"entity": "face|edge", "bodies": ["BodyRef"], "include_hidden": false, "units": "in",
 "surface_types": ["plane","cylinder","cone","sphere","torus","nurbs"], "curve_types": ["line","circle","arc","ellipse","spline"],
 "normal": {"direction": [0,0,1], "tolerance_deg": 1, "signed": true},
 "axis": {"direction": [0,0,1], "tolerance_deg": 1, "signed": false, "through": [1,1,0], "through_tolerance": 0.001},
 "diameter": {"min": 0.9, "max": 1.1}, "area": {"min": 0}, "length": {"min": 0}, "sweep_deg": {"min": 300},
 "concavity": "concave|convex", "edge_convexity": "convex|concave|tangent",
 "near": {"point": [1,1,1], "within": 0.1}, "on_plane": {"point": [0,0,1], "normal": [0,0,1], "tolerance": 0.001},
 "in_box": {"min": [0,0,0], "max": [1,1,1]}, "of_face": "EntityRef", "of_feature": "Boss",
 "include_created_by": false, "sort_by": "distance|area|length|diameter", "max_results": 50}
```
**Result.** `label` is built from rounded geometry only, so two runs give identical labels and order. Only fields relevant to the type appear; planes carry `normal`.
```json
{"units": {}, "bodies_scanned": 3, "scanned": 212, "matched": 2, "returned": 2, "truncated": false, "scan_capped": false,
 "entities": [
  {"ref": "EntityRef", "label": "cylinder d=1.000 axis=+z len=2.000 at [1,1,0.5]", "type": "cylinder", "area": 6.28,
   "bbox": [[0,0,0],[2,2,1]], "distance": 0.0, "created_by": null, "diameter": 1.0, "axis_origin": [1,1,0],
   "axis_direction": [0,0,1], "concavity": "concave", "sweep_deg": 360.0, "length_along_axis": 2.0, "split_siblings": 0},
  {"ref": "EntityRef", "label": "circle d=1.000 at [1,1,1]", "type": "circle", "length": 3.14, "closed": true, "center": [1,1,1],
   "radius": 0.5, "normal": [0,0,1], "start": [1.5,1,1], "end": [1.5,1,1], "convexity": "convex", "faces": ["EntityRef","EntityRef"]}]}
```
- **Refusals.** `surface_types` with `edge` or `curve_types` with `face`; an inverted range; a zero direction; no filter at all on a body over 500 faces; a ref resolving to nothing.
- **Dry run.** Not applicable; read-only.
- **Common.** `common.bodies`, `common.geometry`, `common.api.safe`. New: `entity_refs.describe_face`, `describe_edge`, pure `matches_face`, `matches_edge`. Reuses `bodies._face_record`, `cylinder_concavity`, `sweep_degrees`, `feature_map`, and `probe_geometry.Budget` (90 s, sets `scan_capped`).
- **Lift.** Build 982-1038 `_face_groups_at`, plus the 200-250 constants. Change: tolerances become arguments; the component-only `_bodies()` becomes every occurrence.
- **Traps.** `face.geometry.normal` is not outward (Build 223): `signed: true` uses `face.evaluator.getNormalAtPoint` as `bodies._outward_normal` does; `signed: false` compares `abs(dot)`. Fillets pass as bores by radius: `concavity`, `sweep_deg`, `created_by` are on every cylinder, and sweep under 135 adds `bodies.TRAP_NOTE`. `split_siblings` counts coaxial equal-radius faces sharing an edge. `edge_convexity` steps from `pointOnEdge` along the summed outward normals and asks `pointContainment` (inside concave, outside convex, parallel normals tangent), computed only when asked. `of_feature` misses faces a later Combine consumed: warn when the feature is not last. Dimensions come from geometry, never names.
- **Tests.** Filter matrix over fake records; `signed` on a reversed plane; inclusive ranges; NaN never matches; `max_results` sets `truncated`, keeps order; hidden excluded; label stable under 1e-9 noise; budget sets `scan_capped`; schema rejects unknown keys.
- **Composes.** `ref.token` is `sketch_profile`'s `plane_entity_token` today; `ref.point` feeds `probe_geometry`. Rolled back, later features' faces do not exist, so find inside the `timeline_insert` window.

**Live checks.**
1. FE-1. `Block`: `normal +z` gives one face at z=1, `-z` one at z=0 (the Build 223 case).
2. FE-2. `SubBlock` through `Sub:1`: top face point is the rotated, moved world position.
3. FE-3. Ø1 hole plus an R0.5 corner fillet: `cylinder, concave, sweep_deg min 300` returns the bore only.
4. FE-4. `edge_convexity: concave` on an L-shaped body returns the inner corner only.
5. FE-5. Full scan of a 2000-face body stays inside the budget.

---

## 3. `extrude_profile`

**Purpose.** Extrude a sketch profile with explicit targets and a full account of what changed.

**Args.** One of `sketch_token` / `sketch_name`. One of `direction` / `side` for one-sided extents.
```json
{"sketch_token": "...", "sketch_name": "S1", "component": "root",
 "profile_select": "only|containing_point|containing_points|most_loops|largest", "containing_point": [1,1,0], "containing_points": [[1,1,0]],
 "operation": "new_body|join|cut|intersect", "target_bodies": ["BodyRef"],
 "extent": {"type": "distance|symmetric|two_sides|through_all|to_entity", "distance": 1.0, "distance_expression": "wall*2",
            "side_two_distance": 0.5, "full_length": true, "both_sides": false, "to": "EntityRef", "to_offset": 0.0, "chained": false},
 "direction": [0,0,1], "side": "positive|negative", "taper_deg": 0, "taper_expression": "", "start_offset": 0.0,
 "body_name": "Boss", "feature_name": "Boss extrude", "on_collateral": "undo|keep", "units": "in", "dry_run": false}
```
**Result**, beyond the envelope. `faces` come from `startFaces` / `endFaces` / `sideFaces` right after the add, so a macro rarely needs a find.
```json
{"profile": {"count": 1, "area": 4.0, "loop_count": 2, "plane_normal_world": [0,0,1]},
 "extrude": {"side_used": "positive", "direction_world": [0,0,1], "requested_depth": 1.0, "measured_depth": 1.0,
             "expected_volume": 4.0, "volume_check": "ok|mismatch|not_applicable"},
 "faces": {"start": ["EntityRef"], "end": ["EntityRef"], "side": ["EntityRef"]}, "targets_unchanged": [], "in_path_not_targeted": ["BodyRef"]}
```
- **Refusals.** `cut`, `join` or `intersect` with no `target_bodies`, naming the implicit behavior; `new_body` with them. A surface, linked or missing target. `profile_select: only` with several profiles (lists area, centroid, loops); integer indices are not accepted at all. `direction` more than 1 degree off the sketch normal: an extrude runs along the normal, so a tilted direction is a wrong answer. Taper with `two_sides` or `through_all`. A `distance` cut whose end plane lies within 0.001 in of a parallel target face without touching it (`abutment_gap`): "use `through_all` or `to_entity`; abutting cuts leave a floor." Owner rule: the feature lives in `sketch.parentComponent`; if that is not root and a target sits in another component, refuse (EP-7).
- **Dry run.** Build the input, set the extent, read `input.participantBodies` before setting it, never call `add`. Returns `would_intersect`, `in_path_not_targeted`, `expected_volume` (area x depth, no taper), side, abutment result. If the getter gives nothing (EP-3), `plan_basis: "bbox"`: swept profile box against body boxes.
- **After the add.** Diff snapshots. A body outside the targets lost volume or vanished: with `on_collateral: undo` (default), `feature.deleteMe()`, verify volumes returned, `status: "undone"`, name the bodies. Other occurrences of the same component are classed `other_instance`, not collateral (EP-6, Q5). A target unchanged or `measured_depth` off: `suspect`. Measured depth is the new body's extent along `direction_world`; a wrong side there is deleted and rebuilt once with the other side, and reported.
- **Common.** `feature_ops`, `entity_refs`, `common.bodies`. New pure: `extrude_sign`, `abutment_gap`, `swept_box`. `sketch_profile.describe_profiles` and `choose_profile` are imported.
- **Lift.** Build 1159-1200 `_set_extent`, 1201-1253 `_to_face_or_distance`, 741-765 `_towards`, 1369-1407 `_region`, `_area_of`, 1820-1885 `_extrude_profile`. Change: `participantBodies = self._bodies()` becomes the caller's list, since Build's every-body policy is the bug to refuse here; drop `_adopt` naming and recipe parameters; drop the never-Join rule (1112); drop the fallback from a missing face to a distance, as `to_entity` either resolves or refuses.
- **Traps.** Name every body a cut passes through (1122), and report those not named. Build's comment says an implicit cut takes only the body under the profile, the defs say all intersected, and live use saw other components cut: implicit is unreliable, so it is unavailable. `setDistanceExtent` takes no angle or direction (1159): every path uses `setOneSideExtent`. Never pick by index (1369); `areaProperties` is a method (1383); the sign is asked of `profile.plane`, never assumed (741), and a native plane is mapped with `occurrence.transform2`. Join: if EP-4 shows `participantBodies` ignored, implement join as `new_body` plus `combine_bodies`, same result shape. Drill-then-chamfer order is the macro's job (1595); `abutment_gap` is the net.
- **Tests.** `extrude_sign` at the 1 degree limits; `abutment_gap` at 0, tolerance, just over; refusal matrix (targets per operation, taper with `through_all`, `direction` and `side` together, `distance` and `distance_expression` together, bare-number expression); `profile_select` over fakes returned smallest first; `add_feature` paths; collateral classifier (target loss, outside loss, other_instance, target unchanged); undo that fails verification stays `refused` with a warning.
- **Composes.** `sketch_profile` first; its `sketch.entity_token` is `sketch_token`. Profile tokens are not trusted across calls: re-select by point. `baseline_token` into `check_solids` with `edited_component`. Under `timeline_insert`, call through `primitives` (section 11).

**Live checks.**
1. EP-1. New body on XY, `direction +z` then `-z`: depth and bbox right both ways.
2. EP-2. Cut through `Block` naming it, with `SubBlock` under the profile: `SubBlock` unchanged.
3. EP-3. Dry run of EP-2 first: does `participantBodies` list both?
4. EP-4. Two overlapping bodies, join naming one: are both consumed? Decides the join implementation.
5. EP-5. Tilted plane from `construction_plane`, `direction` along its normal: right side, no retry.
6. EP-6. Root sketch cuts `SubBlock` via the `Sub:1` proxy: does `Sub:2` change? Does the feature land in root?
7. EP-7. Sketch in `Sub`, new body with `creationOccurrence` = `Sub:1`: where does it land?
8. EP-8. Taper +5 and -5 deg: which widens? Record the sign in the tool description.
9. EP-9. Unset `participantBodies` via `execute_python` to force collateral, then confirm the classifier fires.
10. EP-10. `to_entity` with a body rather than a face (G5).

---

## 4. `edge_treatment`

**Purpose.** Chamfer or fillet named edges, retry the way Fusion's own refusal suggests, then measure the result.

**Args.** `points` name edges by any point on them; `body` is then required. `size_two` makes a two-distance chamfer and requires `size_on_face`, the face `size` is measured on. All sets go to one feature first, one feature per body.
```json
{"kind": "chamfer|fillet", "strategy": "split_on_refusal|together_only", "tolerance": 0.001, "feature_name": "Top chamfer", "units": "in", "dry_run": false,
 "sets": [{"edges": ["EntityRef"], "points": [[1,0,1]], "body": "BodyRef", "size": 0.06, "size_expression": "",
           "size_two": 0.1, "size_two_expression": "", "size_on_face": "EntityRef", "tangent_chain": false}]}
```
**Result**, beyond the envelope (`feature` becomes `features`). Points and edges are counted apart: "4 of 132" reads as failure when Fusion holds the outline as 4 edges.
```json
{"edges": {"requested": 6, "built": 5, "points_named": 8, "points_matched": 8, "searched": 14, "lost": [],
           "refused": [{"point": [1,0,1], "attempt": "edge", "refusal": "ASM_BL_CAP_COMPLEX ..."}]},
 "attempts": [{"scope": "together", "edges": 6, "outcome": "refused", "refusal": "..."}, {"scope": "loop", "edges": 4, "outcome": "built"}],
 "measured": [{"set": 0, "method": "inset|radius", "expected": [0.06,0.1], "found": [0.06,0.1], "flipped": false,
               "verdict": "ok|flipped_fixed|mismatch|not_measured"}],
 "suspects": [{"point": [1,0,1], "why": "neighbor edge 0.004 long is shorter than size 0.06"}]}
```
- **Refusals.** No edges resolved; `size <= 0`; fillet with `size_two`; `size_two` without `size_on_face`, or that face not adjacent to the edges; chamfer and fillet mixed (they cannot share a feature; macros run fillets first); one point within `tolerance` of two edges. A point near no edge is not a refusal if others matched: it goes in `lost` and the status is `partial`.
- **Dry run.** Planning only. Returns edges with length and adjacent faces, chains, and `suspects`: edges or vertex-sharing neighbors shorter than `size`, sliver faces beside the edge, high face counts from layered unions.
- **Ladder** on refusal: (1) all sets, one feature per body; (2) each set alone; (3) each chain alone, if there are several; (4) each edge of a refused chain. Every step re-finds its edges by **anchor**, the `pointOnEdge` captured before step 1, because a treated edge changes its neighbors (RC-4). Anchors that find nothing are `lost`.
- **Measured check.** Chamfer: for each anchor, the distance to the nearest edge of `size_on_face` is the inset on that face; classify as `size`, `size_two` or neither, within a quarter of their gap, when they differ by at least 2%, otherwise `not_measured`. Any anchor the wrong way fails the set. Two-distance is built `isFlipped=False`; if swapped, delete, rebuild flipped, measure again; still wrong, delete and refuse. Equal chamfers check both adjacent faces. Fillet: `feature.faces` must hold a cylinder or torus of radius `size`.
- **Common.** `feature_ops`, `entity_refs`. New pure: `chains`, `classify_inset`, `point_to_segment`. New: `edge_distance(edge, point)`, bbox prefilter then `app.measureManager.measureMinimumDistance`.
- **Lift.** Build 2559-2593 `_chains`, 2440-2529 `_break_edge_by_edge`, 2530-2558 `_break_once`, 2642-2705 `_edges_near`, 2706-2780 `_off_edge`, `_off_arc`, 2793-2891 chamfer and fillet builders, 2365-2439 `_two_distances`, `_inset`, 2109-2167 `_chamfer_together`, 2299-2317 `_shortfall`. Change: `extent_mm`-scaled tolerance becomes `tolerance`; plane lookup by recipe becomes refs. `_on_sketch_plane` (2080-2108) is **not** lifted: it is a rule measured on block end caps, and flip-and-measure replaces it for every shape. `_off_edge` stays only as fallback: its chord is wrong on cope splines, and `_off_arc` ignores arc extent. The older chamfer input stays equal-distance only, so it can never build a two-distance chamfer square (2831).
- **Traps.** Distance to the curve (2642, 2706, 2744). Two-distance takes 5 args (2865). Swapped distances (2080, 2382). Chamfers on one plane in one feature (2017). Closed loops first, since a tangent arc alone cannot cap (2440). Per-attempt compute failures (1781). `==` for vertices (2563). Fillets failing on layered unions and at sliver edges: `suspects` names why, and nothing substitutes another shape. `addDistanceAndAngleChamferEdgeSet` is unused because which face the angle starts from is unmeasured; macros turn an angle into two distances.
- **Tests.** `chains` on a square, two squares, an open path, unreadable vertices; `classify_inset` at gap/4 and the 2% line; ladder order with a fake refusing by scope, including skipped rungs; `TypeError` stops the ladder; lost anchors; partial on one failed edge; `suspects` thresholds; flip path swapped-then-fixed and swapped-twice.
- **Composes.** `find_entities` supplies edges; `check_solids` with `slivers` after. Inside `timeline_insert`, find edges in the same window.

**Live checks.**
1. ET-1. Equal chamfer on `Block`'s 4 top edges by token: `ok`.
2. ET-2. Two-distance 0.1 / 0.2, `size_on_face` = top: verdict, flipped or not. Repeat with the side face.
3. ET-3. Hole rim two-distance (the case unmeasured at Build 2098).
4. ET-4. Slot (2 lines, 2 tangent arcs) plus a square loop in one call with one slot edge left out: loops build on step 3.
5. ET-5. Name edges by points after a fillet trimmed them: still found (the Build 2642 case).
6. ET-6. A point on a tube cope spline edge: `measureMinimumDistance` finds it through a proxy; time it.
7. ET-7. R0.25 fillet beside a 0.01 edge: refusal verbatim, `suspects` names the neighbor.

---

## 5. `pattern_features`

**Purpose.** Repeat features, bodies or faces and prove how many instances were made.

**Args.** A negative spacing reverses (per the defs). `axis: x|y|z` is the owning component's axis; the result always gives the world direction.
```json
{"type": "rectangular|circular", "entities": [{"feature": "Hole extrude"}, {"feature_token": "..."}, {"body": "BodyRef"}, {"face": "EntityRef"}],
 "direction_one": {"axis": "x|y|z", "edge": "EntityRef", "sketch_line_token": "..."}, "count_one": 4, "spacing_one": 1.5, "spacing_one_expression": "",
 "direction_two": {"axis": "y"}, "count_two": 2, "spacing_two": 1.0, "spacing_two_expression": "",
 "axis": {"axis": "z", "edge": "EntityRef", "face": "EntityRef"}, "count": 6, "total_angle_deg": 360, "total_angle_expression": "", "symmetric": false,
 "compute": "adjust|identical|optimized", "seed_point": [1,0,0], "seed_volume_delta": -0.2,
 "feature_name": "Bolt pattern", "on_collateral": "undo", "units": "in", "dry_run": false}
```
**Result**, beyond the envelope. `elements` is `patternElements.count`. `instances_reached` is `volume_change / seed_volume_delta + 1`, null without a seed delta. `positions` needs `seed_point`.
```json
{"pattern": {"type": "circular", "asked_for": 6, "elements": 6, "bodies_made": 0, "volume_change": -1.0, "instances_reached": 6,
             "direction_world": [[0,0,1]], "direction_two_set": "explicit|placeholder"}, "positions": [[1,0,0],[0.5,0.866,0]]}
```
- **Refusals.** Mixed entity kinds; seeds in different components; `count < 1`; keys from the other pattern type; `direction_two` parallel to `direction_one`; a non-linear direction entity; `total_angle_deg` of 0; duplicate feature names (as `timeline_insert.resolve_target`).
- **Dry run.** Planning only: seeds, world directions, predicted `positions`, and a warning for any position outside the target's bbox (it would cut nothing).
- **Common.** `feature_ops`, `common.timeline`. New pure: `rectangular_positions`, `circular_positions` (360 divides by `n`, a partial total by `n - 1`; PF-3), `unused_axis`.
- **Lift.** Build 1487-1574 `_pattern`, `ONLY_ONE_DIRECTION` (292). Change: the placeholder is `unused_axis`, not a fixed `z`, since Build would pass z twice for a pattern along z; `_share_out` naming dropped, bodies go in `bodies.created`. Circular adds `circularPatternFeatures.createInput(entities, axis)` with `quantity`, `totalAngle` and `isSymmetric` set explicitly: about 30 lines more, so it is in.
- **Traps.** Always set direction two; unset, quantity 2 built 6 (1516). Set `patternComputeOption` too rather than rely on a default. A cut makes no bodies, and volume alone cannot tell a missed instance from a short pattern, hence `elements` and `instances_reached` together. A boss and its bore pattern together in one call (1487).
- **Tests.** Positions for rectangular, full and partial circular, negative spacing; `unused_axis` for x, y, z, oblique; direction two always set, by a fake input recording calls; `instances_reached` rounding and null; refusal matrix.
- **Composes.** Seeds from `extrude_profile.feature.name`. After it, `find_entities(cylinder, diameter)` should return the instance count. A pattern before a mirror needs `timeline_insert`.

**Live checks.**
1. PF-1. One-direction new-body pattern, quantity 2: exactly 2 (Build's 6 case).
2. PF-2. Cut seed, one direction, quantity 3: `elements` 3, two seed volumes removed (the question left open at Build 1524).
3. PF-3. Circular, 6 over 360 and 4 over 90: positions match.
4. PF-4. Pattern along z with the placeholder on x: accepted?
5. PF-5. Patterned cut with participants on its seed, bystander body in an instance's path: is it cut?
6. PF-6. Cylindrical face as circular `axis` (the defs allow an entity with an axis).

---

## 6. `combine_bodies`

**Purpose.** Boolean existing bodies with an explicit target and tools, and hand back fresh references.

**Args.** `keep_tools` is **required**: Fusion's default silently consumes the tools.
```json
{"target": "BodyRef", "tools": ["BodyRef"], "operation": "join|cut|intersect", "keep_tools": false,
 "feature_name": "", "result_name": "", "on_collateral": "undo", "units": "in", "dry_run": false}
```
**Result**, beyond the envelope. A cut can leave several bodies. `stale_refs` lists refs the caller must drop.
```json
{"result": {"bodies": [{"ref": "BodyRef", "token": "...", "volume": 8.0, "lumps": 1, "faces": 12}], "preview_volume": 8.0, "preview_matched": true},
 "tools_kept": ["BodyRef"], "stale_refs": ["BodyRef"]}
```
- **Refusals.** Target among the tools; duplicates; surface or linked body; bodies in different components (Q4); `cut` or `intersect` where the preview finds no overlap.
- **Dry run.** A real preview. `TemporaryBRepManager.copy` target and tools, `booleanOperation`, report `preview_volume`, lumps, overlap per tool. Warn `disjoint_join` when a join gains lumps. The non-dry path runs the same preview and compares.
- **Common.** `feature_ops` (`temp_copy`, shared with `compare_bodies`), `common.bodies`.
- **Lift.** Build 3195-3205 (`createInput`, `operation`, `isKeepToolBodies`). Change: the suppressed print-ready policy (3180-3227) stays behind; this tool combines only what it is given and is not suppressed.
- **Re-fetch rules.** (1) Bodies resolve from refs immediately before `createInput`, in one main-thread call. (2) Wrappers from before a base feature's `finishEdit` are dead and combine fails on them; tokens are tried, checked with `isValid`, then path + name + index, with `resolved_by` reported. (3) After the add read `feature.bodies`, never the target wrapper. (4) Consumed tools go in `bodies.consumed` and `stale_refs`. (5) Any `EntityRef` on the target may be stale; a warning says so.
- **Traps.** Combine failing on pre-`finishEdit` references; `==`; lump count catches a join that made a disjoint body.
- **Tests.** `keep_tools` missing; target in tools; old wrappers raise on a fake; result refs come from `feature.bodies`; consumed vs kept; preview mismatch gives `suspect`; several bodies from a cut; collateral undo.
- **Composes.** The route for `join` if EP-4 fails, and for copes: an oversize plate cut by tubes with `keep_tools: true`. `check_solids` with `lumps` after. `timeline_insert` reports dropped participants on later features.

**Live checks.**
1. CB-1. Cut, `keep_tools: true`: tool stays, same volume, visibility unchanged?
2. CB-2. Join, `keep_tools: false`: `stale_refs` right, target ref fresh.
3. CB-3. Base feature: edit, add a body, `finishEdit`, combine using a token taken before `finishEdit`.
4. CB-4. Cut splitting a bar: two result bodies reported.
5. CB-5. `preview_volume` equals built volume to 1e-6.
6. CB-6. Combine in `Sub` via `Sub:1` proxies: native or proxy input? Does `Sub:2` follow?

---

## 7. `construction_plane`

**Purpose.** Make a plane at a stated place and report where it really is, normal sign included.

**Args.** `toward` (offset) fixes the side whatever the parent's normal does. `point_normal` is Build's `_oblique_plane`: a three-point plane from a position and a normal. Added because the gusset macro needs it.
```json
{"mode": "offset|three_point|angle|point_normal", "component": "root", "name": "Boss plane",
 "from": "xy|xz|yz", "from_ref": "EntityRef", "from_plane_token": "...", "offset": 1.0, "offset_expression": "", "toward": [0,0,1],
 "points": [{"point": [0,0,0]}, {"ref": "EntityRef"}, {"sketch_point_token": "..."}],
 "axis": {"axis": "x|y|z", "edge": "EntityRef"}, "angle_deg": 30, "angle_expression": "", "point": [0,0,0], "normal": [0,0.5,0.866],
 "reuse_existing": true, "show_anchors": false, "units": "in", "dry_run": false}
```
**Result.** `normal` is whatever Fusion built; consumers must read it. Anchors and parents are never deleted, since that takes the plane and everything sketched on it.
```json
{"status": "built", "ok": true, "plane": {"token": "...", "name": "Boss plane", "component": "root", "origin": [0,0,1], "normal": [0,0,1], "u": [1,0,0], "v": [0,1,0]},
 "parent": {"kind": "root_plane|face|plane|anchors", "name": "XY", "token": "...", "visible": true},
 "anchors": [{"sketch": "Boss plane_anchors", "token": "...", "point": [0,0,0], "visible": false}],
 "sign": {"asked_normal": [0,0.5,0.866], "built_normal": [0,-0.5,-0.866], "flipped_vs_asked": true}, "reused": false, "warnings": []}
```
- **Refusals.** Collinear or coincident points; a `from_ref` that is not planar; an `axis` entity that is not linear; zero normal; a name already used (unless reusing); a direct design (`setByPlane` is direct-only and not offered).
- **Dry run.** Planning only: predicted origin, normal up to sign, `reused` if a coincident plane exists, anchors it would add.
- **Common.** `feature_ops`, `entity_refs`, `common.geometry`. New pure: `perpendicular_pair`, `rotate_about`, `collinear`, `same_plane`. New: `feature_ops.anchor_points`.
- **Lift.** Build 670-678 `_sketch_plane_for`, 679-740 `_oblique_plane`, 741-765 `_towards`, 766-791 `_anchor`, 301-331 `_perpendicular_pair`, 2062-2079 `_same_plane`. Change: `reach` from `recipe.extent_mm` (728) becomes the owning body's bbox diagonal with a floor; the `_oblique_planes` cache (721) becomes `reuse_existing`, a scan of the component's planes; anchors are reported, not just labeled. Try all three anchors in **one** sketch keeping sketch-space z (CP-3), falling back to Build's plane and sketch per point.
- **Traps.** Three-point planes need sketch points; construction points at fixed coordinates raise "Environment is not supported" (679); a ref's vertex is used directly. Query the normal sign (741). Hide anchors, never delete (783): 15 loose points was the first complaint at the machine. Hiding uses `isLightBulbOn` on sketches (the defs say so; Build wrote `isVisible`). `setByAngle(linearEntity, angle, planarEntity)` has an unmeasured sign: predict the normal with `rotate_about`, and if the built plane matches -angle, delete and rebuild, so `angle_deg` always means right-hand about the axis given. `toward` gets the same measure-and-rebuild. In a sub-component, `geometry` is in the plane's own context, so read through a proxy; set `creationOccurrence` when the parent is in another component.
- **Tests.** `perpendicular_pair` for axes and oblique; `rotate_about` at 0, 90, 180; `collinear` threshold; `same_plane` with reversed normals; reach floor; `reuse_existing` hit and miss; angle and `toward` rebuild paths on a fake returning the wrong sign.
- **Composes.** `plane.token` is `sketch_profile`'s `plane_entity_token`, and `to` for `to_entity`. `normal` becomes `extrude_profile.direction`. `delete_features` sees anchors as dependencies.

**Live checks.**
1. CP-1. `offset` 1 from XY, `toward -z`: origin at z=-1.
2. CP-2. `offset` from a side face of `Block`, `toward` outward: right side.
3. CP-3. `point_normal` tilted 30 deg: one-sketch anchors accepted? Normal abs-matches? Plane alive with anchors hidden.
4. CP-4. `angle` 30 about a `Block` edge from its top face: right-hand rule held; record the raw sign.
5. CP-5. Plane on `SubBlock` via `Sub:1`: world origin correct.
6. CP-6. `delete_features` dry run on an anchor sketch lists the plane as dependent.

---

## 8. `apply_thread`

**Purpose.** Catalog lookup and thread application, refusing the cases that silently cut the wrong solid.

**Args.** `modeled` is required for `apply`: the two differ by one flag and 9.8% of a rod.
```json
{"action": "catalog|recommend|apply", "family": "ANSI Unified Screw Threads", "size": "0.25", "designation": "1/4-20 UNC", "internal": false,
 "face": "EntityRef", "diameter": 0.25, "thread_class": "2B", "modeled": false, "right_handed": true, "full_length": true,
 "length": 0.5, "offset": 0.0, "measured_from": "low|high", "units": "in", "dry_run": false}
```
**Result.** `catalog` narrows by what is given: `{"families": []}`, `{"sizes": []}`, `{"designations": []}`, then `{"classes": [{"class": "2A", "major": 0.2489, "minor": 0.2, "pitch": 0.05}]}`. `recommend`: `{"designation": "12-24 UNC", "thread_class": "3A", "nearest_only": true}`, warning that it is the nearest size, not what the part is. `apply`, beyond the envelope:
```json
{"thread": {"family": "...", "designation": "1/4-20 UNC", "thread_class": "2B", "internal": true, "modeled": false, "pitch": 0.05, "major": 0.25, "minor": 0.2, "class_defaulted": false},
 "face": {"diameter": 0.2, "sweep_deg": 360.0, "split_siblings": 0, "diameter_check": "ok"}, "volume_delta": 0.0}
```
- **Refusals.** Face not cylindrical. `sweep_deg` under 355 or `split_siblings > 0`: "split shafts cut 2.57x too much, or fail; measured." Other cylinders on the body are fine; Build's `len(found) != 1` is too strict for a plate of holes. `internal` contradicting concavity. Unknown family or designation, with near matches. A tapered family. Face diameter more than 5% from `major` (external) or `minor` (internal), read for the class in use. `length` without `full_length: false`. After the add, `modeled` with zero delta or cosmetic with nonzero: `suspect`.
- **Dry run.** Planning only: designation, class, face checks, diameters. `catalog` and `recommend` are read-only.
- **Common.** `feature_ops`, `entity_refs`. New pure, in this module: `normalize_size` (`1/4` to `0.25`, `#10` to `0.19(#10)`, `6 mm` to `6.0`, checked against `allSizes`), `pick_class`, `is_split`. Per-family cache.
- **Lift.** Build 517-580 `_faces_of`, 3299-3354 `_thread_face`, 3431-3505 `_apply_thread`; StlToFusionProbe 4109-4170 (catalog walk). Change: body-name lookup becomes a face ref; dialogs (3228-3430) dropped; `classes[0]` (the loosest, `1A`) becomes `pick_class`: `2A`/`2B` for Unified, `6g`/`6H` for ISO if offered, else first, with `class_defaulted: true`. Use `ThreadInfo.create(False, internal, family, designation, cls, right_handed)`, falling back to `threads.createThreadInfo`.
- **Traps.** One whole face (1296, 3299); never two through `inputCylindricalFaces`. API sizes are decimals; `1/4` raises. `allClasses(isInternal, type, designation)` argument order. Class cannot be None. `allThreadTypes` is a property. Pitch cannot be set: designation only. Catalog diameters are class-dependent, so compare like with like. `SurfaceTypes` is in `adsk.core`.
- **Tests.** `normalize_size` table with a miss; `pick_class` per family; `is_split` on whole, two halves, two separate same-size bores; diameter boundaries; `modeled` required; concavity contradiction; tapered refused; catalog narrowing.
- **Composes.** Needs G1 circles. `find_entities` gives the face and `split_siblings`. Thread after the chamfer: the chamfer adds a cone and the cylinder stays whole.

**Live checks.**
1. AT-1. `catalog` walk: the 18 public families; `0.25` under Unified.
2. AT-2. `ThreadInfo.create` on a Ø0.25 rod, cosmetic: delta 0. New rod, modeled: delta about 10%.
3. AT-3. Rod from a two-arc `closed_polyline`: refused, nothing added.
4. AT-4. Ø0.2 hole, internal `1/4-20 UNC`: check passes against the class minor. Ø0.5 hole refused.
5. AT-5. Partial length, `measured_from` low then high: which end, relative to the reported axis?
6. AT-6. Thread a hole, then pattern it: does `pattern_features` carry the thread?

---

## 9. `compare_bodies`

**Purpose.** Answer "are these the same solid, and where do they differ", with no timeline change.

**Args.** `translate_b` compares against a copy sitting elsewhere.
```json
{"a": "BodyRef", "b": "BodyRef", "units": "in", "volume_tolerance": 0.0001, "length_tolerance": 0.001, "max_lumps": 20, "sample_fallback": true, "translate_b": [0,0,0]}
```
**Result.** `same` requires symmetric difference within `volume_tolerance` *and* `bbox_max_shift` within `length_tolerance`. Equal volume alone proves nothing: a split shaft has the volume of a whole one.
```json
{"verdict": "same|different|unknown", "units": {}, "method": "temporary_brep|sampled",
 "a": {"volume": 8.0, "area": 28.0, "faces": 12, "lumps": 1, "bbox": [[0,0,0],[2,2,2]]}, "b": {"volume": 8.0, "area": 28.0, "faces": 12, "lumps": 1, "bbox": [[0,0,0],[2,2,2]]},
 "delta": {"volume": 0.0, "percent": 0.0, "bbox_max_shift": 0.0}, "overlap": {"volume": 7.9, "percent_of_a": 98.75, "percent_of_b": 98.75},
 "symmetric_difference": {"volume": 0.2, "a_only": {"volume": 0.1, "lumps": [{"volume": 0.1, "bbox": [[0,0,0],[1,1,1]]}]}, "b_only": {"volume": 0.1, "lumps": []}},
 "consistency": {"a_minus_overlap_vs_a_only": 0.0, "ok": true}, "warnings": []}
```
- **Refusals.** `a` and `b` the same body; a surface body; a missing ref, with candidates; a negative tolerance. Linked bodies are allowed: this writes nothing.
- **Dry run.** Not applicable; read-only, and temporary bodies never enter the design.
- **Method.** Three booleans, each on fresh copies since `booleanOperation` modifies its target: `A∩B`, `A-B`, `B-A`. `V(A) - V(A-B)` must match the intersection. Lumps of each difference locate *where* they differ. An empty result is zero volume, not an error. A failed or inconsistent boolean with `sample_fallback`: `method: "sampled"`, a `pointContainment` grid over the union bbox under `probe_geometry`'s budget, uncertainty in `warnings`. Neither works: `unknown`, never `same`.
- **Common.** `common.bodies`, `common.geometry`, `feature_ops.temp_copy`. New pure: `verdict`, `consistent`, `grid_estimate`; `bbox_overlap` moves from `solid_check`.
- **Lift.** No Build code; `self_check` (3506-3738) compares against a recipe. Take the copy-and-intersect shape from `solid_check._boolean_interference` (631-647). Change: `temp_copy` applies `occurrence.transform2` if proxy copies come back in component space (CM-2).
- **Traps.** Near-identical bodies have coincident faces, where booleans are weakest, and they are this tool's main job: hence the consistency check, fallback and `unknown`. `translate_b` uses `manager.transform` on the copy.
- **Tests.** `verdict` matrix (same, equal volume but shifted, over tolerance, unknown); `consistent` boundary; empty difference; lumps capped; sampled path with a fake; same-body refusal; `translate_b` applied to `b` only.
- **Composes.** The check after a macro: compare a built candidate with the hand-modeled body. `check_solids` asks whether a body is sane; this asks whether it is the right one.

**Live checks.**
1. CM-1. `Block` vs an identical copy in place: `same`, no fallback (the coincident case).
2. CM-2. `SubBlock` via `Sub:1` vs `Sub:2`: `different`, and the copies' bboxes read in world coordinates.
3. CM-3. `Block` vs `Block` with a Ø0.25 hole: `a_only` equals the hole and its bbox locates it.
4. CM-4. Disjoint bodies: overlap 0, no exception.
5. CM-5. Time two large bodies from Warn M8000; decide whether it needs a budget.

---

## 10. Gaps the macros exposed

- **G1, blocking: single-entity circles.** `closed_polyline` draws a circle as two arcs, so the wall is two faces: unthreadable (Build 1296). Add `sketch_profile` action `circles`: `{"circles": [{"center": [x,y], "diameter": d}], ...plane or sketch args}` via `addByCenterRadius` (Build 1335-1355) with the z flatten (1275). Many per sketch.
- **G2, blocking: add to an existing sketch.** `closed_polyline` always makes a new sketch. Accept `sketch_entity_token`, so a plate outline and its holes share a sketch and `profile_select: most_loops` applies.
- **G3: `sketch_profile` in a sub-component is not world.** `modelToSketchSpace` is "sensitive to the assembly context" and `component.sketches.add` returns a native sketch, so `space: "model"` means component space under a moved occurrence. Add `occurrence_path`, map through `transform2`. Live: repeat a model-space outline on `Sub:1`.
- **G4: `construction_axis`.** Circular patterns and angle planes about a kingpin need an axis not on an edge. Same module and anchors as `construction_plane`: `setByCircularFace`, `setByTwoPoints`, `setByNormalToFaceAtPoint`. Build it if PF-6 fails or the knuckle macro needs it.
- **G5: bosses on curved faces.** Sketch on an offset plane, then `to_entity` the body. The defs say "construction plane or face", so a body is EP-10.

---

## 11. Build order

```
shared-core ──┬─ A entity_refs + find_entities ──┬─ extrude_profile ───┬─ edge_treatment ────┐
 (common/*)   ├─ B feature_ops                   ├─ construction_plane ├─ pattern_features ──┼─ primitives namespace, macros
              ├─ C sketch_profile G1, G2, G3     └─ combine_bodies     └─ apply_thread apply ┘
              ├─ D compare_bodies
              └─ E apply_thread catalog, recommend
```
- **Gate 0.** Run RC-1 to RC-4 through `execute_python` before A finishes. Everything downstream rests on them.
- **Stage 1, parallel:** A, B, C, D, E. `find_entities` is first on the critical path. B needs only a ref type from A. D needs only `common.bodies` and `temp_copy`.
- **Stage 2, parallel after A and B:** `extrude_profile` (needs C to test holes), `construction_plane`, `combine_bodies`. If EP-4 says join ignores participants, `extrude_profile` depends on `combine_bodies`.
- **Stage 3, parallel after `extrude_profile`:** `edge_treatment` (the largest; its pure code can start in stage 1), `pattern_features`, `apply_thread` apply.
- **Stage 4.** `_build_runtime_globals` gains `primitives`, one method per tool taking kwargs and returning the parsed payload, so `execute_python` and `timeline_insert(code=...)` use the same handlers. `run_rolled_back` sets a flag in `common.timeline` that relaxes preflight's marker rule. Macros live in `fusion_bridge/macros/`, plain functions over the handlers, each a thin tool later.

One branch per primitive, stacked on `shared-core`. Each branch's report lists its live checks for the lead.

---

## 12. Example macros

Pseudo-arguments only. Each ends with whether the interfaces held.

**12.1 Bored boss on a face (knuckle ear).**
```
f   = find_entities(face, surface_types=[plane], near={point: P, within: .05}, bodies=[B])
s   = sketch_profile(circles, plane_entity_token=f.ref.token, space=model, circles=[{center: P, diameter: OD}])
e   = extrude_profile(s, profile_select=only, operation=join, target_bodies=[B], extent={distance: H}, direction=f.normal)
s2  = sketch_profile(circles, plane_entity_token=e.faces.end[0].token, circles=[{center: P+H*n, diameter: ID}])
c   = extrude_profile(s2, operation=cut, target_bodies=[B], extent={through_all}, direction=-f.normal)
rim = find_entities(edge, curve_types=[circle], near={point: P+H*n, within: ID}, diameter={min: ID, max: ID}, bodies=[B])
edge_treatment(chamfer, sets=[{edges: rim, size: .03}])
check_solids(baseline_token=e.baseline_token, edited_component=...)
```
Holds with G1. `e.faces.end` saves a find. Read `B` back from `e.bodies.touched`. Join depends on EP-4. A curved ear goes through `construction_plane` and G5.

**12.2 Flanged plate with a bolt pattern (axle bracket, hub flange).**
```
s = sketch_profile(closed_polyline, sketch_plane=xy, points=[...], arcs=[corner radii])
sketch_profile(circles, sketch_entity_token=s, circles=[{center: C, diameter: pilot}])
p = extrude_profile(s, profile_select=most_loops, operation=new_body, extent={distance: T}, direction=+z, body_name="Flange")
h = sketch_profile(circles, plane_entity_token=p.faces.end[0].token, circles=[{center: bolt1, diameter: D}])
c = extrude_profile(h, operation=cut, target_bodies=[Flange], extent={through_all}, direction=-z)
pattern_features(circular, entities=[{feature: c.feature.name}], axis={face: pilot_bore}, count=6, total_angle_deg=360,
                 seed_point=bolt1, seed_volume_delta=c.bodies.touched[0].delta)
e = find_entities(edge, curve_types=[circle], on_plane=top, diameter={min: D, max: D}, bodies=[Flange])
edge_treatment(chamfer, sets=[{edges: e.entities, size: .03}])
```
Holds with G1, G2. If PF-6 fails, `axis: z` only works at the origin and G4 becomes blocking. A rotated rectangular flange uses `direction_one: {edge: ...}`, which is why edges are direction entities. All the holes chamfer in one feature from one find.

**12.3 Gusset between two faces (tube-fab).** Legs L1, L2, thickness T.
```
a, b = find_entities(... near={point: Pa}), find_entities(... near={point: Pb})
# macro math: corner C on both faces, in-plane directions da, db, normal n = cross(da, db)
m = construction_plane(point_normal, point=C, normal=n, name="Gusset plane")
s = sketch_profile(closed_polyline, plane_entity_token=m.plane.token, space=model, points=[C-overlap, C+L1*da, C+L2*db])
g = extrude_profile(s, operation=new_body, extent={type: symmetric, distance: T, full_length: true}, body_name="Gusset")
combine_bodies(target=Gusset, tools=[TubeA, TubeB], operation=cut, keep_tools=true)   # coped to the tubes
edge_treatment(fillet, sets=[{points: [free corner], body: Gusset, size: R}])
check_solids(checks=[slivers, lumps, interference], interference_pairs=[[Gusset, TubeA]])
```
Holds, and shows why `keep_tools` is required: an oversize plate cut by the tube gives an exact cope with no spline sketching. It needed `point_normal`. The cut may leave a stray lump; `result.bodies` lists every piece and the macro keeps the largest.

**12.4 Drilled and chamfered hole (countersink).**
```
f = find_entities(face, surface_types=[plane], near={point: P}, normal={direction: n, signed: true}, bodies=[B])
s = sketch_profile(circles, plane_entity_token=f.ref.token, space=model, circles=[{center: P, diameter: D}])
c = extrude_profile(s, operation=cut, target_bodies=[B], extent={through_all}, direction=-n)
f2 = find_entities(face, surface_types=[plane], on_plane={point: P, normal: n}, bodies=[B])
rim = find_entities(edge, curve_types=[circle], of_face=f2.ref, diameter={min: D, max: D})
# macro math, 82 deg: d1 = (CSK-D)/2 on the top face, d2 = d1/tan(41 deg) down the bore
edge_treatment(chamfer, sets=[{edges: rim, size: d1, size_two: d2, size_on_face: f2.ref}])
apply_thread(apply, face=<bore from find_entities>, designation=..., modeled=false)   # if tapped
```
Holds. This is the Build 1595 order: drill through, then chamfer, so nothing abuts. `f.ref` may not survive the cut (its `pointOnFace` can land in the hole), so the macro re-finds by plane. A blind hole uses `extent={distance: depth}`, and `abutment_gap` refuses a depth that leaves a skin at the far face.

**Result.** The eight interfaces hold. The exercise added G1, G2, `point_normal`, and `faces` on the extrude result.

---

## 13. Open questions

1. **`dry_run` default.** This design says `false`: a feature undoes with one delete, refusals run either way, and a macro would otherwise double every call. Existing destructive tools default `true`. Keep the split?
2. **"Visible parent and anchors."** Read here as visible to the modeler: named in the browser, listed in the result, light bulb off by default, `show_anchors` to turn on. That respects "hide, never delete". If you meant shown in the viewport, flip the default.
3. **Collateral default.** `on_collateral: undo` deletes the feature when an outside body lost volume. Right default, or report and keep?
4. **Cross-component combine.** Refused in v1. Assemblies may need root-level combines of proxies (CB-6 tells us what Fusion does). Allow after that?
5. **Component instances.** If a root cut via `Sub:1` also changes `Sub:2` (EP-6), that is correct CAD and a surprise. Warn, or refuse unless `allow_all_instances: true`?
6. **Participant repair.** `timeline_insert` reports dropped participants but cannot restore them. Tag each cut with a `fusion_bridge/participants` attribute so a later tool can? Cheap now, hard later.
7. **Trial mode.** Add, measure, delete, for an exact delta on a treatment or pattern. Useful, or does build plus undo cover it?
8. **`compare_bodies` across files.** A `compare_to_target` for stl_to_fusion needs a body from another document or a STEP file (`TemporaryBRepManager.createFromFile`). Add `b_file` now, or wait for the recipe work?
9. **Fillet fallback** (backlog #11). This design reports and never substitutes. Should `edge_treatment` offer `min_size`, or leave retries to macros?
10. **`build_recipe`.** When it resumes it should be a macro over these handlers. Does the improved recipe need anything this drops? Named parameters are covered by `*_expression`.

## Decisions (user, 2026-11-05)
- Build tools do NOT default to a dry run. File and delete tools keep their dry-run default. Cuts must name their target bodies.
- Helper geometry: make as much as needed, but never on in the view by default: named and listed in the result, light bulb off.

## Gate 0 results (live, 2026-11-05, throwaway design; occurrence moved +10 in X, rotated 30 deg)
- RC-1 PASS: token through `Sub:1` resolves to one BRepFace, `assemblyContext` Sub:1, `pointOnFace` world coordinates (10.366, 1.366, 1.0).
- RC-2 PASS: still one result after an unrelated new body.
- RC-3: after a cut splits the face, `findEntityByToken` returns 2 results, both in Sub:1, areas 2.0 then 1.4 in^2 (larger first here; don't rely on order, use `point`).
- RC-4 PASS: chamfering one edge leaves neighbor tokens alive; lengths trimmed (1.0 → 0.9, 3.0 → 2.9), the unrelated 4.0 unchanged.

## Stage 1 landed (2026-11-05)
On `combined`: `common.entity_refs`, `common.feature_ops`, `find_entities`, `compare_bodies`, `apply_thread` catalog/recommend, sketch_profile circles / add to sketch / world space. Differences from this doc: `temp_copy` lives at `common.bodies.temp_copy(manager, body)` (no `feature_ops.temp_copy`); `body_label` is `label`. Read the module docstrings for exact signatures.

## Stage 2 landed (2026-11-05)
On `combined`: `extrude_profile`, `combine_bodies`, `construction_plane`. Stage 3 next. Live: `participantBodies` read before add returns nothing, so plans use `plan_basis: bbox`.
