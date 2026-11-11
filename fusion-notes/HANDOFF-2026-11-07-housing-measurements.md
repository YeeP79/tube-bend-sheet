We're continuing the Moon Patrol front axle in Fusion, starting a measurement session for the diff housing (third member next). Read these first:
1. ~/Projects/personal/fusion/front-axle-plan.md: read the end first. It has the FUDGE FACTOR REGISTER (F1-F19), conflicts #1-#14, the "Front Axle - Moon Patrol" section, and the diff housing notes ("Derived from the carried-over housing", photos, renames).
2. ~/Projects/personal/fusion/reference/trail-gear-9in-housing-research.md (published Trail Gear and Ford 9" values; no public CAD or stud coordinates exist).
3. Photos: ~/Projects/personal/fusion/reference/diff-mega-hi9/ (01 Mega Hi-9 in the housing, 02 housing rear, 03 face plate from above, 04 face plate side with the tube end inside, 05 face plate edge close-up).
4. ~/Projects/personal/fusion/bridge-worktrees/LIVE-ISSUES.md: the OPEN TOOL ISSUES table at the end. Log any new tool problem there and keep going unless it blocks the work.

## State (2026-11-07)
- Bridge: add-in at ~/Projects/personal/fusion/add-ins/AutodeskFusionMCP, branch `combined` at 7fc8f7e, 3223 tests passing. If the Fusion MCP tools are disconnected, call the bridge with ~/Projects/personal/fusion/tools/mc.py (`from mc import call`).
- Designs (Buggy project):
  - Axles/Front/"Front Axle - Moon Patrol" v5: origin = axle center, X along the axle, driver side -X, +Y forward, +Z up. The left steering corner is linked with its top-bore center at X = -26.125 and 8.5 deg caster. The housing is linked at `diff_offset` 9.5 (+X, the user's placement for driveshaft clearance). Tubes: Ø3.5 x 3/8, driver -23.75 to +0.24, passenger +18.76 to +23.75, `tube_insert` 0 (estimate).
  - Axles/Shared/"Diff Housing - Trail Gear Rock Assault 9" v3: center section only, centered on its own origin, same axes. Four plates (Face plate, Center band, Side plate driver/passenger) carried over as a base feature from the friend's model (Front AxleDB v6), so they are not parametric. Parameter `housing_tube_end_half` 9.26.
  - Axles/Shared/"Third Member - Ford 9 Mega Hi-9" v1: empty placeholder. High pinion; 1410 billet yoke (matches the 1410 driveshafts: Drivetrain/"UJoint - Spicer 1410", "DSYoke").
  - Front AxleDB is the old, broken axle; keep it read-only and do not edit it.
- Steering corner chain is done and verified (Inner C v7, Moon Patrol knuckle v31, Steering Corner v12): KPI 12.2 confirmed assembled (gauge 12.3 with caster), stop at 42.4 out.

## Rules for working with the user
- Plain language, American spelling. Ask for measurements as simple numbered steps or a small diagram, never formulas.
- One change at a time, verified, then saved.
- When numbers disagree in 3D: flag it, rank the suspects (least accurate first), and let the user decide. Log the decision in the plan's conflict table.
- Every adjustment made to fit is a "fudge": add it to the FUDGE FACTOR REGISTER with where to adjust it.
- Fusion: open a design ON ITS OWN before editing it (close any parent that links it). Check that `document_status` warnings are empty (the "linked by open document" warning means the save will stall), not just the active name. Throwaway designs only for tool tests. Ask before opening big assemblies if the user may be in Fusion. Keep designs read-only unless in use (chassis exception).

## Task: housing measurements, then rebuild the housing to match
The user takes these with the third member OUT. The expected values in [brackets] come from the carried-over plates; use them as checks, not inputs.
1. Stud template: cardboard pressed over the 10 studs, opening edge traced, photographed flat with a ruler. Calibrate the photo, and extract the stud coordinates and the opening outline.
2. Face ring outside: width [13.5] x height [11.0].
3. Opening: width [10.0] x height [9.5].
4. Face plate thickness [1/2; the model reads 0.49].
5. Machined face straight back to the tube center [1.75 ahead of the axle centerline].
6. Overall width, end to end where the tubes enter [18.5].
7. Overall height at the center band [11.5].
8. Center band width at the back: top, middle, bottom [model 5.0 front to about 3.0 back; the rear photo suggests about 6, so this is the likely conflict].
9. Depth: machined face to the back of the center band [7.25].
10. Stud length out of the face.
11. Tube insertion on each side: where the tube enters the housing to the tube's inner end, seen through the opening (photos 04/05 show it well inside). This sets `tube_insert` in the axle.
Plan for applying them: build a parametric housing in the same design from these measurements: face plate from the stud template, ring and opening; the side shells and center band to the measured envelope. Keep the old base-feature plates hidden for comparison, and log fudges. Keep the housing's frame and origin unchanged so the axle link still lines up.

## After the housing: third member (Mega Hi-9), flange face down on the table
12. Pinion center height off the table, at the yoke.
13. Face to the U-joint center of the 1410 yoke.
14. Pinion sideways: to the nearest stud hole and to the flange edge.
15. Casting size: how far it sticks out past the face; width and height at the widest point.
16. Photos with a tape: straight down onto the yoke, and from each side.
Its flange shares the housing's 10-stud pattern. Build it in "Third Member - Ford 9 Mega Hi-9"; it joins the housing later.

## Still open (not this session's focus)
Right knuckle: MB4082-01 rod numbers and a steering-side photo. Branik washer seating. Ram mount trapezoid tube (needs the inside faces at 43.75). Open tool issues in LIVE-ISSUES.md (top: #42 hollow tube gussets read as suspect, #46 save_document should refuse when a parent holds the file).

Start by reading those files, then tell me briefly that you're ready and which measurement you want first.
