# Bridge live-test log (combined branch)

Running record of what live use turns up. Every so often we stop and turn these into fixes on
the feature branches (then re-merge into `combined`). Newest first.

## Verified live
| Date | Tool | Result |
|---|---|---|
| 2026-11-04 | `capture_viewport` `clean_view` | PASS: hid 6 categories, restored all |
| 2026-11-04 | `bridge_info` | PASS: running vs disk commit, changed_since_load picks up uncommitted edits |
| 2026-11-04 | `reload_addin` | PASS: twice in a row (gen 1→2→3), edit picked up, Claude Code client reconnected on its own |
| 2026-11-04 | `document_status` | PASS: versions, read-only, folder paths, referenced_by; caught an unsaved doc after a "successful" save |
| 2026-11-04 | `fusion_dialogs` | PASS (2nd try): list in 0.5 s; opened Preferences with Cmd+, then `dismiss` sent Escape and closed it, bridge responsive after. Fusion Qt dialogs expose NO button names, so Escape is the only path |
| 2026-11-04 | `editable_files` | PASS mostly: 8 of 10 editable (from personalUseLimits), 10 projects / 49 designs in 46 s, link hints correct. BUG: `in_personal_use_list` is false for every file (matching against personalUseLimits.editableFiles fails; ids/version suffix?) |
| 2026-11-04 | `project_tree` | PASS: Buggy 43 files in 13 s (links 15 s), duplicates by name with paths/ids, empty folders, links as paths. Found 15 names duplicated by `Archive - Dec 2025`; no live file links into the Archive |
| 2026-11-04 | `tail_log` | PASS: after a self-reload (gen 4), `preset=save, since=30m` returned the knuckle upload lines in one 256 KB read |
| 2026-11-04 | `open_document` | PASS (reuse path): already-open Moon Patrol knuckle → `reused: true`, no new tab |
| 2026-11-04 | `save_document` | PASS (refusal path): unmodified doc → `not_modified`, nothing attempted. Real save + stall diagnosis still to check |
| 2026-11-04 | fixes batch 1 (gen 6) | PASS: `document_status` flags the 3 stock-knuckle instances [12, 11, 12] with the warning; `fusion_dialogs` preflight 295 ms + list 325 ms; `bridge_info.modules` short names. `list_changed` did NOT refresh Claude Code's tool list (still stale) |

## Open issues
1. **(still open after the list_changed fix) Client tool list goes stale after new tools appear** (client side, not the bridge). After the add-in restart + `/mcp`, Claude Code still only listed the older tool set; the bridge served 35 tools. Workaround: `scratchpad/mcpcall.py <tool> '<json>'` calls tools over HTTP directly. Possible bridge-side help: send `notifications/tools/list_changed` after a reload / at startup if the client supports it.
2. **FIXED (retry + preflight, gen 6): `fusion_dialogs` first call timed out** (`osascript timed out after 15s`); the next call 0.5 s. Permissions were already granted (Accessibility + Automation). Unknown cause, intermittent (user has seen timeouts before). Ideas: retry once on timeout, fast permission probe first, report timing. Also: an AX query from INSIDE `execute_python` (main thread) sees 0 windows, because Fusion can't service AX while its main thread runs the script; only the off-main-thread tool works.
3. **RESOLVED + save_document built: `Document.save()` returns True but nothing is saved** (Knuckle - SD 2005-08 stock, 2026-11-04): no new version, `isModified` stays true, 30 s+ later still v11. Happened twice. Context: the same file had been open in two tabs (one closed since), and it is linked into an open parent. Bridge help: a `save_document` tool that verifies a new version actually appeared (latestVersionNumber + isModified) and reports failure instead of trusting the return value; and `execute_python` could warn when a script called save and the doc is still modified.
4. **FIXED: `bridge_info` module list is noisy**: full synthetic package names (`__main__%2FUsers%2F...`). Show short names relative to the package.
5. **FIXED (open_document reuses; document_status flags duplicates): Opening an already-open file creates a second tab** (`documents.open(dataFile)`), which led to issue 3. A guard/helper: `open_document` that activates the existing tab if the file is already open.
   - Cause (2026-11-04): a second in-memory instance of the same file (window title `... (stock)(1)`). Fusion's log shows `Workflow start: save` with NO `[CFSUploader] Starting upload` after it. Even the UI Save command (`PLM360SaveCommand`) did nothing. Fix: close that tab without saving, reopen fresh, redo the edit, save → v12 landed in ~2 s (log: `[CFSUploader] Uploaded document`).
   - Opening a parent that links the file loads extra instances too: after reopening the Moon Patrol knuckle, `app.documents` held THREE `Knuckle - SD 2005-08 (stock)` docs (v12, v11, v12).
   - Bridge fixes to make: `save_document` that waits for the CFS upload (check `findFileById(id).latestVersionNumber` and/or tail the app log for `Uploaded document` vs a bare `Workflow start: save`) and reports failure; `document_status` should flag duplicate instances of one DataFile id (and the `(1)` title); `open_document` should reuse an open instance.
6. **DONE (branch tail-log, merged): a `tail_log` tool** would have found issue 3 in one call: the Fusion app log is `~/Library/Application Support/Autodesk/Autodesk Fusion 360/<id>/logs/AppLogFile*.log` (newest by mtime; the file name date is the session start). Filter by keyword and time.
7. **FIXED + LIVE PASS (gen 9): `editable_files.in_personal_use_list` always false**. Real cause: `personalUseLimits.editableFiles` is a `DataFileVector` (len/iter, no count/item); the collection helper read it as empty. Id matching was fine (see table). Fix the id match (likely `?version=N` or lineage vs version urn).
8. **FIXED + LIVE PASS: `editable_files` walk is slow-ish** (46 s → 33 s for all 10 projects, 17.5 s for Buggy; time budget 90 s) (46 s for 10 projects) and runs on the main thread; add a time budget like project_tree's, or reuse data_tree.
9. **Deleting cloud files** (2026-11-04, Buggy `Archive - Dec 2025`, 17 files): `DataFile.deleteMe()` works but raises `InternalValidationError : res` instead of returning False. `tail_log` showed the real reason: `POST 400 .../lineages/delete` → `GEN_RELATED_OBJECTS: The object being acted on has relationships.` (Warn M8000 AssemblyREV-B; `hasParentReferences` was False, so the relationship is something the API does not expose: a copy/derive/drawing link). 16 of 17 deleted fine, parents first. Tool idea: `delete_files` (dry run default, parents-first order, never open files, per-file try/except, and on failure pull the matching `lineages/delete` response body from the app log). There is no API to delete a project (`DataProject` has no `deleteMe`).
10. **Read-only toggle**: the API has no setter; UI commands `ActiveDocumentDeactivateCommand` ("Make Read-Only") / `ActiveDocumentActivateCommand` exist and act on the ACTIVE document, with a confirmation dialog. Untested path: open the file, run the command, confirm the dialog (Return key, since Qt dialogs expose no buttons). `fusion_dialogs` deliberately never confirms, so this would need its own narrow tool with an explicit dialog-title check.
11. **Make Read-Only via `ActiveDocumentDeactivateCommand` works with NO dialog** (unit bearing → read-only, editable count 8→7). Running it on 4 files back to back while Front AxleDB (big assembly) was still loading did nothing and left Fusion busy. Do it one file at a time, waiting for load to settle. Candidate tool: `set_read_only(file)` = open (reuse) → wait idle → command → verify `findFileById(id).isReadOnly` → close if we opened it.
12. **Read-only switching done live (2026-11-04)**: unit bearing, Front AxleDB, InnerC, Knuckle (old), Outer Shaft → read-only, one at a time (editable 8 → 3). The Moon Patrol knuckle keeps one stock-knuckle instance loaded (v11!) that can't be closed while the parent is open; `close(False)` returns without closing it.

## Next batch (proposed 2026-11-05)
Issue 1 update: a fresh `/mcp` after the last reloads DID refresh the client's tool list (all new tools visible). So: reconnect is the working step; `list_changed` alone is not.
- A. `set_read_only` / `set_editable` (issue 11): open or reuse, wait for idle, run the command, verify, close if we opened it.
- B. `delete_files` (issue 9): dry run default, parents first, per-file errors, server reason pulled from the app log.
- C. `execute_python` keeps imports and functions between calls (only plain values persist now: `P3`, `math`, lambdas vanished on nearly every call).
- D. `fusion_status` (direct tool): is the main thread responsive, is a load/compute running. Would have shown the Front AxleDB overload; lets batches wait instead of piling up.
- E. `close_document`: verifies the close. `Document.close(False)` on an instance held by a parent "succeeds" and nothing closes (30 no-op closes in one loop); should report which parent holds it.
- F. `update_references`: Get Latest on links, per reference, then verified save (needed for stock v12 → Moon Patrol).
- G. `probe_geometry`: point-in-body, ray hits, radial/axial section sampling in world coords and chosen units (hand-written ~8 times for arm, eye, dish).
- H. `insert_before` helper: roll the marker before a named feature, run edits, roll to end, report health (the "before the mirror" pattern), and restore the marker on failure.
- I. `capture_viewport` camera args (eye/target/up in model units; this model is Z-up, Fusion's views are Y-up) and a warning on a blank image (blank capture seen right after a document close).
- J. `compare_files`: occurrences, bodies, volume, timeline length of two DataFiles, closing what it opened (the winch check).
- K. Older backlog still unbuilt: Edit Joint gap (#2), fillet-with-fallback (#11), identify by entityToken across linked designs (#12).

## Live check round 2 (2026-11-05, throwaway file in Default Project, removed afterward)
PASS: sketch_profile (refusal, arcs, XZ), parameters (list, tree, dry run, cycle, apply), compute, list_bodies, describe_body (fillet hint, created_by), check_solids (baseline diff with outside_edited_component, interference via analyzeInterference), timeline_health, document_versions, restore_version (after fix), save_document (after fix), set_editable_state both ways with no dialog, move_files + link check, rename_file, delete_files, execute_python sessions, open_document.
13. **FIXED: modern protocol (2026-07-28) tools/call all failed `-32603`** once Fusion passed 1024 open files: `select.select` raises ValueError. Branch `fix-select-fd-limit`. Upstream-worthy.
14. **FIXED: `restore_version` looked up the fs.file versionId form** ("Invalid Version URI"); now DataFile.id.
15. **FIXED: `save_document` false failure on a first-save file** (id is a local path until the upload lands); re-reads the id each poll.
16. **FIXED + LIVE PASS (plan listed all 4, `also_removed` empty, 6 → 2): `delete_features` plan understated.** Deleting `sq` + dependent `Box1`: plan listed 2, timeline went 8 → 4; Fusion also removed `Fillet1` and `Cut1`, unreported (`new_errors` empty). Needs dependents through bodies/edge sets, and an after-delete timeline diff that reports `also_removed`.
17. **FIXED + LIVE PASS (server lock 423, now waits and retries): `rename_folder` case-only rename failed** at step 2 (`InternalValidationError`); it restored the original name correctly. Find the server reason in the log; maybe a delay is needed, or say it isn't supported.
18. **FIXED + LIVE PASS (`mismatch_count` 0): `parameters` `dependents` included transitive items**: API `dependentParameters` returned d7 for `od` though d7 depends on idia. Labeled "direct"; `dependency_check` shows it as mismatches. Use parsing to split direct vs transitive.
19. `fusion_status` merged (gen 12): idle 47 ms, 1203 open files. Busy check below in session notes.

## Macro tool candidates from stl_to_fusion (survey 2026-11-05, nothing built yet)
Source: `fusion/StlToFusionBuild/StlToFusionBuild.py` and `docs/06-reference/fusion-api-not-the-dialog.md`. The bridge has no feature-building tool today.
Ranked for hand modeling: `extrude_profile` (extent, participants, volume delta; pairs with sketch_profile), `break_edges` (chamfer/fillet edges named by points, retry, measured post-check), `pattern_features`, `compare_to_target`, `build_recipe`, `apply_thread`. Later or not at all: `describe_as_recipe` (large, new code, no read-back exists to lift), `recover_body` (needs the whole mesh stack as a sidecar).
Does not transfer: mesh recovery (numpy/trimesh), one-component-per-part policies, 25%/1% tolerances, StlToFusionBatch.
Traps worth reusing: see the survey list (name every body a cut passes through; always set pattern direction two; face normals aren't outward; pick profiles by loop count; chamfer distances can swap, so measure).

## Direction (user, 2026-11-05)
Hold `build_recipe`: the recipe in stl_to_fusion is being improved first. Build the primitives the macros need, each usable on its own, then compose macros from them in code. Shared code goes in one place: upstream has no shared layer, and our self-contained branches duplicated helpers (`_error` x16, `_safe` x11, `_ok` x9, `_items` x7, log lookup x4, timeline health x3, plus `data_tree` copies). Order: `shared-core` (branch off combined: `fusion_bridge/common/`, every tool migrated), then primitive branches stack on it.
Primitives planned: `find_entities` (faces/edges by location, tokens out), `extrude_profile`, `edge_treatment` (chamfer/fillet), `pattern_features`, `combine_bodies`, `construction_plane`, `apply_thread`, `compare_bodies`.

## Live round 3 (2026-11-05)
PASS: `timeline_insert` (dry run, insert before Mirror1, marker restored after a raised error, partial work reported), `compare_files` (Warn M8000 copies: same, 13.5 s, 23 bodies, 4226.188 cm3, 32 steps, nothing left open), `capture_viewport` `model_view` after the extents fix, `probe_geometry` on the knuckle, `fusion_status` idle and busy.
Not yet live: blank-image warning, `close_document`, `update_references` apply, `activate_document`, `timeline_health` suppress + rollback message, `reload_addin` fallback, `remove_empty_folders` real run. Small: `timeline_health` fallback enum has unknown=3 but 3 is Suppressed (only if the enum lookup fails).

## Idea: `audit_design` (user, 2026-11-05; proposal, not built)
From Anvil's "Audit Tube Joints" command (`fusion_addin/commands/auditJoints/entry.py`, `core/tube_joints.py`): read-only, classifies everything into named categories, flags the worst first, Fusion-free core. Adapt as one read-only health report for a design: checks in groups (file, timeline, links, bodies, joints, sketches, parameters), each finding with severity, location, why it matters, and the tool that fixes it. Profiles choose the rules (general, assembly, export-ready); packs add domain rules (Anvil tube joints). Baseline token to show what got worse. Optional per-design expectations (measured facts) as a later phase.
Anvil-side review (Anvil's agent, via the user, 2026-11-05): classifier in `fusion_addin/core/tube_joints.py` is Fusion-free, but it reads a tube EXPORT document, and building that uses Fusion. It's tube-only, with tolerances tuned to this chassis's coped ends; untried elsewhere. No route from outside the add-in yet, so a pack is real (small) work. Plan: build `audit_design` here, independent of Anvil; first read Anvil's tube export as a FILE; real pack later. Per-design expectations must stay compatible with Anvil's recorded measurements, so measured facts live in one place. Severity per profile fits the user's configurability rule. 98/44/0/8 came from `chassis v54-joint-audit.txt`, not re-run.
Scope rule (user, 2026-11-05): the bridge stays GENERIC; nothing Anvil-specific goes in it. It's MIT (Frank Hommers). Anvil-specific behavior lives in Anvil, combining bridge tools with what Anvil needs. So no tube pack in `audit_design`: a generic way to add checks at most, with Anvil supplying its own.

## State at restart (2026-11-05)
`combined` f3655e2, 1608 tests, live add-in gen 19. shared-core merged; every tool on `fusion_bridge/common/` (README "Shared code"). Smoke test after merge passed: list_bodies, check_solids, probe_geometry, timeline_health, tail_log, fusion_status, delete_files refusal, parameters. `check_solids` on the Moon Patrol knuckle reports one `tiny_faces`: look at it.
Next: primitives per `PRIMITIVES.md` (stack on `combined`/shared-core, build order there, RC checks first; decisions at the end of that file). `audit_design` alongside them, generic only. Nub measurements (conflict #6) pending from the user. Mesh: repo opted in at local scope; after restart check `daemon_status`, `list_peers`, and how to reach the Anvil session.
20. `check_solids` on the Moon Patrol knuckle: `face_count_outlier` is a false alarm (a 92-face casting beside 3-face bolts, median 3). Severity per profile in `audit_design` should handle it, or compare only like bodies. `tiny_faces`: one 0.000025 in^2 face on the stock knuckle, harmless modeling leftover, no action.

## Anvil measurement shape (Anvil orchestrator anvil-9ac9e410 on monsoon-pc, via mesh, 2026-11-05)
Garage SQLite per ADR-0008: `observation` row = quantity (text), value (real), unit (text), optional method, provenance reference; `observation_target` links to parts by id. Values are never on the part. Vehicle-level targets planned (sprung mass, CG). No shared file format yet, so not a contract. For `audit_design` expectations: one record per fact, beside the design; draft a format and post it on repo/tube-bend-sheet/announce for checking.

## Live round 4 (2026-11-05, gen 21, throwaway closed afterward)
PASS: `compare_bodies` same / different on a rotated pair (temporary_brep, 0.01 s), `apply_thread` catalog + designation + recommend (12-24 UNC 3A as expected), `sketch_profile` circles (`whole: true`), add to existing sketch (profiles 1 → 3), world space in moved+rotated `Sub:1` (hand-checked).

## Live round 5 (2026-11-05, gen 22)
PASS `find_entities`: FE-1 normals, FE-2 world point through rotated Sub:1, FE-3 bore vs an equal-diameter fillet (concavity + sweep), FE-4 concave edge through Sub:1 at the hand-computed world position. Not yet: FE-5 timing, FE-6, FE-7, RS-1/2, FO-1/2/4.

## Live round 6 (2026-11-05, gen 23ish): `audit_design` on the Moon Patrol knuckle
PASS: 0.8 s, 86 findings, baseline re-run 0 new / 0 resolved / 86 unchanged, no false `face_count_outlier`, tiny face is info, flagged the duplicate stock instances.
21. **`audit_design` noise:** 75 `unused_user_parameter` rows (measured facts kept as parameters, used by scripts) and 6 `unheld_occurrence` rows drown the rest. Collapse repeats into one row with a count, keep details on request; consider `unused_user_parameter` off in `general`.
22. **Document reads as modified after read-only work** (Moon Patrol knuckle: `isModified` true, v21 = latest, timeline unchanged). Suspect `capture_viewport` `clean_view` or camera changes dirty the document even though flags are restored. Unproven: test on a saved throwaway (is `isModified` false, run clean_view, read it again). If true, the tool should say so, and a read-only tool shouldn't leave a document dirty.
Chassis audit (read-only, 2026-11-05): full report saved at `~/Projects/personal/fusion/chassis-audit-2026-11-05.json`. 5.2 s on a 1476-step design, complete. Update on 22: a LINKED stock knuckle instance also read modified with content identical to its saved v12, consistent with `clean_view` toggling light bulbs on linked components; still to prove on a throwaway. `save_document` real save PASS (v21 → v22, 3.6 s); `close_document` refusal + discard + also_closed PASS.

## Chassis goals (user, 2026-11-05; after the front axle)
Work earliest issue forward, together. Suppress only what blocks an edit, log it, restore it in turn (no blanket suppress). Refactor: (1) look at splitting sections of the chassis into separate linked designs; (2) make the left and right sides a TRUE mirror. History: built mostly passenger side intending to mirror; tight suspension-flex spots by the engine forced building from the driver side. Tool ideas: `symmetry_report` (pair bodies across a plane, report per-pair deviation, unmatched bodies), `compare_bodies` mirror option.

## Live round 7 (2026-11-05, gen ~26, combined 022bf02, 2508 tests)
PASS `extrude_profile`: EP-1 both directions, EP-2 cut names Block and leaves Tool alone with a warning, no-target cut refused, EP-3 dry run reads `plan_basis: bbox` (participants getter gives nothing; plan still lists both bodies). PASS `combine_bodies` (cut, keep tools, preview vs built after fix: Fusion lists a kept tool among feature.bodies), `construction_plane` offset + point_normal (anchors hidden, reuse works). Not yet: EP-4 join route, EP-5..EP-16, CB-3/4/6-9, CP-2/4-8.

## Live round 8 (2026-11-05, gen 26, combined c543015, 2660 tests)
`edge_treatment`: ET-1 equal chamfer on 4 edges ok (measured 0.1/0.1), rim fillet ok (0.05). Full chain with no raw scripts: sketch_profile -> circles -> extrude_profile -> find_entities -> edge_treatment; volume 11.2146 = 12 - pi/4. ET-2 results in the session; rest of ET-3..11 open.

## Live round 9 (2026-11-05, combined e95e018, 2876 tests)
`pattern_features` circular built 6 correct holes; `patternElement.transform` is unreliable on circular patterns (0,120,180,240,300,0), so position check read a false `suspect`. `apply_thread` apply: cosmetic thread RESIZES the cylinder to the thread (Ø0.2 → Ø0.2015 minor), volume changes by that amount; refusals for wrong side + diameter work. Fixes sent to the agent.

## Live round 10 (2026-11-05, gen 28, combined 6b25d55, 3039 tests)
PASS: `audit_design` folding (knuckle 86 → 4 rows, ok true), `symmetry_report` on a Mirror-feature pair (`true_mirror`, temporary_brep, reflection works) and a one-side hole (near, symmetric difference 0.0314 in^3 exact).
23. **`symmetry_report` disables all confirmation if one reflected copy fails its check**: on the chassis one body read 79.4947 vs 79.5218 in^3 (0.03%), so 30 pairs fell to numbers after 14 had confirmed. Make the copy check per body, relative tolerance, skip that pair only.
Chassis symmetry saved at `~/Projects/personal/fusion/chassis-symmetry-2026-11-05.json`.

## Stage 3 complete (2026-11-05, combined 0ef5a34, 3065 tests, 56 tools served)
PASS after fixes: circular pattern (`positions_basis: faces`, 6 correct positions), thread resize reported (0.2 → 0.2015, status built). Open: issue 23; stage 4 (primitives namespace), macros; a few rarer live checks per tool listed above.

## Issue 23 fixed (2026-11-05, combined 7676478, 3072 tests)
`symmetry_report`: a failed reflection costs only its pair (`confirmation.reflection_failed`, pair stays on numbers); `available` is false only when no pair reflected. Copy volume limit 0.01% -> 0.1%. Not yet live on the chassis. Expect the 0.034% body may read `unknown`, not confirmed: `boolean_parts` checks against the source volume, so that drift can exceed the pair's limit. Also moved ahead of macros (user OK): EP-4, PF-6, ET-2/ET-3.

## Live round 11 (2026-11-05, gen 30, combined 7676478; throwaway discarded afterward)
PASS issue 23 on the chassis (v55, plane yz): 44 checked, 40 same, 1 different, 3 unknown, 0 reflection_failed, 0 not_reached, 3.0 s, no warnings. Summary 41 true_mirror / 3 near / 1 different / 1 unmatched. The 0.034% body no longer trips the limit. New finding: `Y tube` pair read true_mirror on numbers, booleans moved it to near. 3 unknown: 2 are ASM_EDGECOIN_PROBLEM (shock tower pair stays true_mirror on numbers; shock hoop pair near), 1 is Body3/Body1 (near). Saved `chassis-symmetry-2026-11-05-rerun.json`.
PASS issue 22: capture with model_view, clean_view, and both on the saved chassis (16 open documents, 53 linked components left alone): nothing marked modified. `clean_view_linked` not tested; its description states the price.
PASS EP-4: join honors participants. Bar through A and B, join naming A: A 4.0 -> 6.5 (+2.5, hand-checked), B unchanged, join_route participants, warning names B. Macro 12.1 can use join directly.
PASS PF-6: cylinder face as circular axis: 6 elements, 6 reached, volume -0.31416 = 5 seed holes, positions on R2 about the bore, positions_basis faces. G4 `construction_axis` not needed for the flange macro.
PASS ET-2: size_on_face top: built unflipped (`ok`), top edge at y 10.1. size_on_face side: `flipped_fixed`, so isFlipped really swaps; 0.2 lands on top, edge at y 12.8.
PASS ET-3: hole rim 0.1 on top / 0.2 down the bore: rim d 1.2, cylinder 1.0 -> 0.8 long, cone half angle 26.565 = atan(0.1/0.2). Bore survives as one face.

## Live round 12 (2026-11-05, gen 31, combined bba35d9, 3116 tests; throwaway discarded)
PASS `primitives`: PN-1 10 names; PN-2 `done True 2`; PN-3 `from_` plane at z=1; PN-4 refused with the marker text, moveToEnd after; PN-5 plane, sketch, extrude all built right before X, `timeline_index` 7 = landed slot, marker restored, 10 healthy; PN-7 raise reported, rule refuses again afterward; PN-8 find then chamfer in one window, measured ok, and a ref taken inside the window resolves after the restore (`resolved_by: token`).
Partly tested PN-6: `deleteMe` on an extrude inside the window is clean (timeline healthy, marker restored). A real `on_collateral: undo` could not be triggered, since participants are honored; still open.
Open small: `sketch_profile` has no preflight (marker rule never applied to it). `close_document` listed UniversalJoint in also_closed yet UniCross, DSYoke, UniversalJoint stayed open after closing the chassis: maybe a second instance; check.
24. **Editing a stock file through a tab loaded by its parent stalls the save again (issue 3 pattern, 2026-11-05).** Stock knuckle activated while Moon Patrol held it: `save_document` correctly reported `nothing_happened` after 60 s; log shows `Workflow start: save` and no upload. `document_status` showed one instance and no warning, so nothing warned before the edit. Fix that worked: close the parent, close the instance (discard), open the file on its own, redo, save (v13 in 2.2 s). Tool ideas: flag an instance loaded through a parent in `document_status`, refuse up front in `save_document`, warn in `activate_document`. Also `document_status` entries can have `data_file: null` (the empty Untitled Fusion makes when nothing is open).
25. **FIXED + LIVE PASS (combined d85b3cf, 3117 tests, gen 32): `extrude_profile` read the plane in sketch space.** `Profile.plane` is sketch space: normal always +z, origin ignores the plane offset. A correct direction was refused on any sketch off XY, and a join on an offset plane read `suspect` (depth from z=0). Now mapped through sketchToModelSpace. Live: +y sketch reads [0,1,0], wrong direction refused, join on the offset plane 1.1 deep, cut on a +y-facing sketch built. EP-5 proper (tilted plane) still to run, with the gusset macro.
26. **`capture_viewport` `camera` with `perspective` and `extents` threw the eye to about 1500 cm away** (blank image; the blank warning caught it). Orthographic is right. Looks like extents acts as a zoom on perspective.
27. First client call after `reload_addin` can answer 503 `MCP server restarting` even though the add-in is up; a retry works. Seen three times.
Light bulb in a link: `BRepBody.isLightBulbOn = False` on a body in a linked occurrence marks the linked instance modified, but saving the PARENT keeps it: after a true close and reopen the body stays hidden and nothing is modified. The linked file itself still shows the body. To close afterward use discard_unsaved (it only drops that flag).

## Live round 13 (2026-11-05, gen 34, combined 2476cdb, 3214 tests; throwaways discarded)
PASS macros, hand-checked: M-1 boss (12 -> 12.2198); M-2 stops on "not whole", `partial`, sketch kept; M-3 flange (15.8357, 6 reached, one chamfer); M-4 on xz and on a 30 deg tilted plane (closes EP-5); M-5 countersink (0.125 / 0.1438); M-6 thread, resize 0.2 -> 0.2015, bad designation adds nothing; M-7 blind; M-8 gusset after the fix below (0.25 in^3 exact, Floor and Wall untouched); M-11 inside `timeline_insert`; M-12 marker rule, `partial`, sketches kept.
M-7 note: depth equal to the thickness builds a clean through hole, no floor. The agent's expected refusal was wrong; `abutment_gap` only fires when the end misses the far face.
28. **FIXED + LIVE PASS: `combine_bodies` kept tools counted as results.** Filter read `tool["body"]`, a name string; fake tests hid it. `result_name` renamed Floor and Wall, built volume 48.25 vs preview 0.25.

## OPEN TOOL ISSUES (user 2026-11-05: keep tracking these; improve as we go). Worst first.
| # | Tool | Issue | Impact |
|---|---|---|---|
| 29 | `extrude_profile` | **FIXED + LIVE PASS (see round 14).** `through_all` cut in a moved, rotated sub-component refused: "body not found to extrude through" (bored_boss, drilled_hole, flanged_plate all stopped there; new-body and join built at the right world positions). Blind cuts there untested. | HIGH: real designs are mostly sub-components, so macros stop partway |
| 30 | `gusset` macro | **FIXED + LIVE PASS (round 15).** Second gusset refused: default plane name 'Gusset plane' already exists. Needs a unique default. | Medium: M-9 never reached the tube cope, so that is unproven |
| 31 | document tools | **FIXED (round 15; `save_document` still does not refuse up front).** Stall of issue 24: an instance loaded through a parent cannot save, and nothing warns. Flag in `document_status`, refuse in `save_document`, warn in `activate_document`. | Medium: cost a 60 s failure and a redo |
| 32 | `sketch_profile` | No preflight: macros leave sketches behind before the extrude refuses (M-2, M-12). | Medium |
| 33 | macros | `partial` keeps what it built; no undo option. | Medium |
| 34 | `close_document` | Two 'Untitled' docs can't be told apart (no id), so the throwaway needed raw execute_python. | Low |
| 35 | `close_document` | Listed UniversalJoint in also_closed, yet it stayed open with UniCross and DSYoke (issue noted in round 12). Check. | Low |
| 36 | `capture_viewport` | Issue 26: perspective with `extents` throws the eye about 1500 cm away. | Low |
| 37 | client/reload | Issue 27: first client call after a reload can 503; a retry works. | Low |
| 38 | `document_status` | `data_file` can be null; scripts must allow for it. | Low |
| 39 | `extrude_profile` | Proved by delete only: real `on_collateral: undo` inside `timeline_insert` (PN-6). | Check |
| 40 | fake tests | Issues 25 and 28 both passed fakes that did not match real Fusion shapes. Worth a pass over fakes for `entries` and API spaces. | Process |
Still unproven: M-9 tube cope and stray pieces, M-10 after 29, FE-5/6/7, EP-6 to EP-10, ET-4 to ET-7, PF-1/2/4/5, CB-3/4/6-9, CP-2/4-8, AT-5/6.
Backlog unchanged: `audit_design` expectations format for the Anvil agent; update `github-issue-draft.md`; `build_recipe` on hold.
| 41 | Front AxleDB reads | `rootComponent.allOccurrences` raises `InternalValidationError : occ`, and some as-built joints raise on `occurrenceOne/Two`, in Front AxleDB v17 (76 timeline items read health unknown, likely the suppressed ones). Any tool walking all occurrences (`list_bodies`, `find_entities`, `audit_design`, `symmetry_report`) may fail or come up short on it: check. | Medium |

## Live round 14 (2026-11-05, gen 35, combined 3a3ef6e, 3219 tests; throwaway discarded)
Issue 29: Fusion refuses `through_all` in a moved sub-component however it is built: native, proxy or no participants, component active or not, from root with a proxy profile, either direction. A 2 in blind cut works. Not tested: an unmoved sub-component. Fix: on that exact refusal, retry a measured distance past the targets (both ways for both_sides), with a warning and `through_all_route: measured`. A root through_all that finds nothing stays refused. The measured cut will not follow a body that grows later.
PASS M-10 through rotated Sub:1, hand-checked: boss 16 -> 16.0723, countersunk hole through (bore 0.856 long), flange 15.8402 with 6 bolts at the right world positions.
Process slip: a chained command merged `sub-through-all` with one failing test (a wrong count in the new test); fixed before any reload. Gate merges on the test result.

## Live round 15 (2026-11-05, combined 7fc8f7e, 3223 tests; throwaway discarded)
PASS issue 30: second gusset builds on its own plane (`unique_name`); a name the caller gives still refuses. Its body comes out 'Gusset (1)' with a warning.
PASS M-9: tube on plate and tube to tube cope cleanly, both tools unchanged, legs measured from the axis. On hollow tubes the plate continues inside the bore, so pieces are left there: 1 and 2 `stray_bodies`, status `suspect`, as designed.
| 42 | `gusset` macro | Hollow tubes always leave stray pieces in the bore, so a good gusset reads `suspect`. Add `remove_strays`, or cope against the tube's outer solid. | Medium |
| 43 | `gusset` macro | The default body name collides on a second gusset ('Gusset (1)'); give it `unique_name` treatment too. | Low |
| 44 | Fusion trap / move tools | Setting `occurrence.transform2` then `snapshots.add()` in a parametric design did not hold: after compute and save the bodies were back (left an empty "Position1" snapshot). A Move feature on the bodies worked. Worth a `move_bodies` primitive that uses Move features and checks the bodies landed. | Medium |
| 45 | `delete_features` | Cannot delete a Snapshot ("Position1"): nothing deleted, no reason given. | Low |
| 46 | `save_document` | Proven predictive (2026-11-07): an edit made in a tab that `document_status` warned was held by an open parent stalled (`nothing_happened`, 45 s). Make `save_document` refuse up front when the target is linked by an open document, naming the parent. Process: scripts that edit must check `warnings` empty, not just the active name. | Medium |
| 47 | `construction_plane` | `offset_expression: "-tube_end_from_center"` with `toward: [-1,0,0]` built at +23.75 with expression `-( -tube_end_from_center )`: the toward flip double-negated a negative expression, so the plane landed on the wrong side. Expected toward to decide the side and the expression's own sign to be respected or refused. | Medium |
| 48 | document tools | Right after `saveAs`, `document_status` read the new file as read-only; `set_editable_state` then said "already editable". The read-only flag lags a fresh save. | Low |
| 49 | placement / verification | Recurrence of #44 found 2026-11-08: "Front Axle - Moon Patrol" v5 was logged as housing "placed at diff_offset 9.5", but the occurrence transform is identity (housing centered). The placement was never read back after save. Need: a placement primitive that uses a joint or Move feature and verifies the occurrence's world position after save. | Medium: a wrong assembly position went unnoticed for a day |
| 50 | feature edits | Re-pointing an extrude to a new profile via API (`feature.profile = ...`) silently reset its participant bodies to all bodies, so a trim cut wiped out an unrelated body (2026-11-08). Editing the original sketch's curves in place made `profile` unsettable ("InternalValidationError: curProfile"). ShellFeature has no setter for its faces; a lost face reference means delete and recreate. A safe "replace profile" primitive should keep participants and verify body volumes before/after. | Medium |
| 51 | `check_solids` | `interference_pairs` given as a list of 14 pairs, each `[{occurrence_path, body_name}, {occurrence_path, body_name}]`, was refused: "'interference_pairs' must be 'all' or a non-empty list of body-reference pairs" (2026-11-08, Front Axle - Moon Patrol). Worked around with the default 'all' over a `bodies` list. Pair parsing looks broken, or the error should say what was wrong. | Low |
| 52 | `capture_viewport` | `camera.extents` is documented as a radius around the target, but the reported extents width equals the value given (9 in -> 22.86 cm wide), so it behaves as the full width. Doc or code mismatch. | Low |
