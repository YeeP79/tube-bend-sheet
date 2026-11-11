We're continuing the Moon Patrol front axle in Fusion: next is the Mega Hi-9 third member's main case (the casting between the housing face and the pinion support), then a diff guard that fits this housing. Read these first:
1. ~/Projects/personal/fusion/front-axle-plan.md: read the END first (2026-11-07/08 entries): HOUSING BUILD SPEC, the FUDGE FACTOR REGISTER (F1-F33), conflicts #1-#20, "Third member - Ford 9 Mega Hi-9", "Diff guard / skid (planned)".
2. Photos: ~/Projects/personal/fusion/reference/diff-mega-hi9/ (08 face straight-on; 09-14 yoke; 15-17 pinion support from the right / behind / left; 18 bolt labels P1-P5; 19 bolt-hole close-up).
3. ~/Projects/personal/fusion/bridge-worktrees/LIVE-ISSUES.md: OPEN TOOL ISSUES at the end (new: #49 placement read-back, #50 re-pointing a feature's profile resets its participant bodies). Log new tool problems there and keep going unless blocked.

## Conventions (do not re-derive)
- Vehicle frame: +X = passenger, +Y = forward, +Z = up. LEFT/RIGHT ALWAYS FROM THE DRIVER'S SEAT, whichever way the user faced while measuring. Never ask.
- Front axle: the diff housing sits on the DRIVER side, face plate pointing REARWARD (toward the driveshaft), high pinion. The housing's own design frame has +Y = face direction; the axle turns it 180 deg about Z.
- Before placing anything imported, prove forward/up/driver from a confirmed feature and show the user a labeled top view; read placements back after saving (joints, not occurrence transforms).
- Don't invent geometry to fill gaps: ask how the part was made (lathe/mill/cast/formed) and for the missing number. Labeled photos (A, B, C... or numbered) + caliper numbers work best. Log every guess in the fudge register.

## State (2026-11-08)
- Bridge: add-in at ~/Projects/personal/fusion/add-ins/AutodeskFusionMCP (branch `combined`). Fallback client: ~/Projects/personal/fusion/tools/mc.py.
- Fusion Personal Use: 4/10 editable (Front Axle - Moon Patrol, Mega Hi 9 Pinion Support, Third Member - Ford 9 Mega Hi-9, chassis). Everything else read-only; keep it that way unless in use.
- Folders moved: axles now live under Buggy/Drivetrain/Axles/{Front,Shared,Rear}.
- Designs:
  - Drivetrain/Axles/Front/"Front Axle - Moon Patrol" v15: origin = axle center. Favorites: `housing_inner_end_from_center` 0.625 (front axle; housing end nearest center), `diff_offset` = -(0.625 + 8.625) = -9.25, `pinion_lateral` 1.0625, `pinion_height` 2.25, `top_bore_from_center`. Housing (v16) placed by rigid joint (face rearward). Tubes recut (tube_insert 2.8125). Yoke placed at X -10.3125, Y -11.05, Z 2.25 (pointing rearward). Pinion support placed (no rotation) with its case face at Y -6.105.
  - Drivetrain/Axles/Shared/"Diff Housing - Trail Gear Rock Assault 9" v16 (read-only): fully measured shell (bowtie band, faceted side shells), face plate (studs A-J, opening, ring gear notches, recess, wings), tube support walls.
  - "Mega Hi 9 Pinion Yoke - 1410 Billet" v10 (read-only): origin = U-joint center, +Y away from the diff.
  - "Mega Hi 9 Pinion Support" v2 (editable): installed, world-aligned frame (X passenger, Y forward, Z up), origin on the pinion axis at the case face; 5 bolts 3/8-16 on R 2.886 at 111.1 / 35.7 / 323.8 / 251.7 / 175.5 deg (seen from behind, counterclockwise from the passenger side).
  - "Third Member - Ford 9 Mega Hi-9" v1: EMPTY placeholder: the main case goes here.
- Mega Hi-9 numbers already measured (diff bolted into the housing, axle on the stand parallel to the fixture table):
  - Table heights: tube center (scribed marks) 16 1/4; pinion center 18 1/2 (2 1/4 above the tube center). Pinion 1 1/16 LEFT (driver) of the housing's scribed center line; pinion square to the face (flat).
  - Third member flange face (on the housing face) to the yoke U-joint center: 9 3/8. Yoke flat end to the support's front face: 2.8. Support case face to its front face: 2.145. So the MAIN CASE pinion boss face is 4.43 behind the flange face.
  - Housing machined face is 1.675 behind the axle centerline (front axle, face rearward).
  - It's a custom casting (True Hi 9), not Ford parts; the support bolt pattern matches the Ford-style supports the WFO guard fits.
  - User doesn't want gear teeth modeled: a motion link (yoke -> axle shafts) at the ring and pinion ratio instead (ratio not given yet).

## Task 1: Mega Hi-9 main case (enough to build around; pictures for the look)
The user takes these off the table (heights are easy). Measure from the third member's flange face (against the housing face) back along the pinion:
1. Flange thickness at its edge.
2. Flange outline vs the housing's machined ring: same, bigger or smaller? Photo of the joint from behind.
3. Pinion boss diameter at its face (where the support bolts on; face is 4.43 back).
4. Casting envelope at about 1", 2 1/2" and 4" back from the flange face. At each: table height to the top and to the bottom of the casting, and its left and right edges (from the scribed line or the pinion center).
5. The case's highest and lowest points (table heights) and how far back they are.
6. Photos with a tape along the pinion: from above, from each side, from behind.
Build it in "Third Member - Ford 9 Mega Hi-9" in the installed, world-aligned frame (like the support) so it drops into the axle without rotation; the flange carries the housing's 10-stud pattern; the main case is mostly an envelope + look-alike detail from the photos (log made-up shapes as fudges).

## Task 2 (after): diff guard / skid
User owns a WFO 9"/10" High Pinion Diff Guard (doesn't fit the Trail Gear housing smoothly). Goal: design one that bolts to the pinion support's 5-bolt pattern, protects the yoke and driveshaft, and blends smoothly from the housing bottom. Needs: the main case envelope (Task 1), the 1410 U-joint swing at the yoke, and from the WFO part: plate thickness, mounting details, photos with a tape, where it doesn't fit. Also later: stud-mounted skid notes in the plan.

## Rules for working with the user
- Plain language, American spelling. Measurement asks as simple numbered steps or small diagrams, never formulas. Use the table for heights.
- One change at a time, verified (check_solids, timeline health, a labeled capture), then saved.
- When numbers disagree: flag it, rank suspects (least accurate first), the user decides; log in the plan's conflict table. Every adjustment to fit is a fudge in the register with where to change it.
- Fusion: edit a design ON ITS OWN (close any parent that links it); check `document_status` warnings are empty before saving. Throwaway designs only for tool tests. Ask before opening big assemblies if the user may be working in Fusion (they sometimes drag parts while the API runs: wait for Fusion to go idle).

Start by reading those files, then tell me briefly that you're ready and give me the main case measurement list in the order you want it.
