"""THROWAWAY PROBE — verify the Option D pickup-tagging convention in Fusion.

Gate for anvil docs/02-spec/fusion-api-plan.md §7 open questions Q1, Q5/Q6, Q8.
These can ONLY be answered in a live Fusion session, so this script exercises
the full attribute-tagged-SketchPoint chain end to end and writes a findings
note you can drop straight into anvil's docs/01-research/.

Run from Fusion: Scripts & Add-Ins > Scripts > + > select this file > Run
(or VS Code attach-debug via the sibling .vscode/launch.json, like anvil_probe).

It is SAFE for your real models: the SETUP run creates a brand-new scratch
design document and operates only on that — it never touches the active model.

TWO RUNS (the save/reopen item needs them):
  Run 1 (SETUP):  no SuspensionCalculator tags in the active doc yet, so the
                  script creates a scratch doc, tags points, and runs items
                  1, 2, 3, 4a (timeline rewind), 5, plus the secondary probes.
                  It then tells you to SAVE that scratch doc, CLOSE it, REOPEN
                  it, and run the script again.
  Run 2 (VERIFY): the reopened scratch doc already carries our tags, so the
                  script takes the VERIFY branch and confirms item 4b
                  (survives save + reopen), then writes the final verdict.

Output: Fusion Text Commands window (View > Show Text Commands) +
~/anvil-pickup-probe-findings.md  +  a summary message box.

Read-only in the VERIFY branch. Delete the whole scripts/anvil_pickup_probe/
folder when the convention decision is locked in.
"""

from __future__ import annotations

import json
import os
import traceback

import adsk.core
import adsk.fusion

# --- The production convention under test (anvil fusion-api-plan §4/§5) ------
GROUP = "SuspensionCalculator"
ROLE = "role"
CM_TO_IN = 1.0 / 2.54

# Scratch tags this probe writes.
ROLE_ROOT = "RUF"        # a standalone point on a root-component sketch
ROLE_OCC = "OCC_TEST"    # a point inside a TRANSLATED sub-component occurrence

# Scratch geometry coords (cm — Fusion internal units).
PT_ROOT = (2.0, 3.0, 5.0)        # root sketch point, identity transform
PT_OCC_LOCAL = (1.0, 0.0, 0.0)   # occurrence-local point coord
OCC_SHIFT = (10.0, 0.0, 0.0)     # occurrence translation (cm) along +X
# So the occurrence point's ASSEMBLY-frame position should be (11, 0, 0) cm
# IF worldGeometry/findAttributes resolve the occurrence transform.

# Scratch user parameters.
PARAM_LEN = ("susp_wheelbase", "112 in", "in")      # length param -> value in cm
PARAM_UNITLESS = ("susp_vehicle_mass", "4000", "")  # unitless -> value as typed

STATE_PATH = os.path.join(os.path.expanduser("~"), ".anvil_pickup_probe_state.json")
FINDINGS_PATH = os.path.join(os.path.expanduser("~"), "anvil-pickup-probe-findings.md")
TOL = 1e-4  # cm


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _design(app):
    return adsk.fusion.Design.cast(app.activeProduct)


def _iter_attrs(design):
    """design.findAttributes -> a plain list of Attribute (robust to either
    a Python list or a Fusion collection return)."""
    attrs = design.findAttributes(GROUP, ROLE)
    out = []
    try:
        for a in attrs:
            out.append(a)
    except TypeError:
        for i in range(attrs.count):
            out.append(attrs.item(i))
    return out


def _p3(p):
    return (round(p.x, 5), round(p.y, 5), round(p.z, 5))


def _close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=False))


def _objtype(e):
    return getattr(e, "objectType", "?")


# ---------------------------------------------------------------------------
# SETUP branch — fresh scratch doc, items 1/2/3/4a/5 + secondary probes
# ---------------------------------------------------------------------------
def run_setup(app, ui):
    results = {}  # id -> {status, detail}

    def rec(key, status, detail):
        results[key] = {"status": status, "detail": detail}

    # New scratch design so we never touch the user's real model.
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = _design(app)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType  # ensure timeline
    root = design.rootComponent

    # --- build geometry ----------------------------------------------------
    sk = root.sketches.add(root.xYConstructionPlane)
    p_root = sk.sketchPoints.add(adsk.core.Point3D.create(*PT_ROOT))
    # a line so we have a curve-endpoint SketchPoint to contrast against
    line = sk.sketchCurves.sketchLines.addByTwoPoints(
        adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(5, 0, 0)
    )

    # translated sub-component occurrence holding its own point
    mat = adsk.core.Matrix3D.create()
    mat.translation = adsk.core.Vector3D.create(*OCC_SHIFT)
    occ = root.occurrences.addNewComponent(mat)
    sub = occ.component
    sk2 = sub.sketches.add(sub.xYConstructionPlane)
    p_occ = sk2.sketchPoints.add(adsk.core.Point3D.create(*PT_OCC_LOCAL))

    # --- Q1.1: can we add an attribute to a SketchPoint at runtime? --------
    set_ok = False
    try:
        p_root.attributes.add(GROUP, ROLE, ROLE_ROOT)
        p_occ.attributes.add(GROUP, ROLE, ROLE_OCC)
        set_ok = True
        rec("q1_set", "PASS",
            f"point.attributes.add('{GROUP}','{ROLE}',...) succeeded at runtime "
            "despite the typing stub not exposing .attributes.")
    except Exception as e:  # noqa: BLE001 — probe: capture the real failure
        rec("q1_set", "FAIL",
            f"point.attributes.add raised: {type(e).__name__}: {e}. "
            "SketchPoint attributes are NOT writable -> fall back to "
            "parent-sketch attributes (key by point) or Option B "
            "(construction points).")

    # --- Q1.2: does it round-trip via itemByName? --------------------------
    if set_ok:
        try:
            got = p_root.attributes.itemByName(GROUP, ROLE).value
            if got == ROLE_ROOT:
                rec("q1_roundtrip", "PASS",
                    f"itemByName('{GROUP}','{ROLE}').value == '{got}' (exact).")
            else:
                rec("q1_roundtrip", "FAIL",
                    f"round-trip mismatch: wrote '{ROLE_ROOT}', read '{got}'.")
        except Exception as e:  # noqa: BLE001
            rec("q1_roundtrip", "FAIL",
                f"itemByName raised: {type(e).__name__}: {e}.")
    else:
        rec("q1_roundtrip", "SKIP", "set failed; round-trip not attempted.")

    # --- Q1.3: fast path findAttributes -> cast -> isValid -> worldGeometry -
    occ_world = None
    occ_native_world = None
    occ_via_attr_has_context = None
    if set_ok:
        try:
            attrs = _iter_attrs(design)
            roles_found = []
            cast_fail = []
            for a in attrs:
                sp = adsk.fusion.SketchPoint.cast(a.parent)
                if sp is None:
                    cast_fail.append(_objtype(a.parent))
                    continue
                roles_found.append({
                    "role": a.value,
                    "isValid": bool(sp.isValid),
                    "world_cm": _p3(sp.worldGeometry),
                    "world_in": tuple(round(c * CM_TO_IN, 5) for c in _p3(sp.worldGeometry)),
                    "assemblyContext": (None if sp.assemblyContext is None
                                        else sp.assemblyContext.name),
                })
                if a.value == ROLE_OCC:
                    occ_world = _p3(sp.worldGeometry)
                    occ_via_attr_has_context = sp.assemblyContext is not None
            n = len(attrs)
            root_hit = any(r["role"] == ROLE_ROOT for r in roles_found)
            if n >= 2 and root_hit and not cast_fail:
                rec("q1_findattrs", "PASS",
                    f"findAttributes returned {n} tagged point(s); every "
                    f"attr.parent cast to a valid SketchPoint. Details: "
                    f"{json.dumps(roles_found)}")
            else:
                rec("q1_findattrs", "FAIL",
                    f"findAttributes returned {n}; root_tag_found={root_hit}; "
                    f"cast_failures={cast_fail}; details={json.dumps(roles_found)}")
        except Exception as e:  # noqa: BLE001
            rec("q1_findattrs", "FAIL",
                f"findAttributes/cast chain raised: {type(e).__name__}: {e}.")
    else:
        rec("q1_findattrs", "SKIP", "set failed; fast path not attempted.")

    # --- Q5/Q8: worldGeometry units + occurrence-transform resolution ------
    # Native worldGeometry on the occurrence point (no proxy):
    try:
        occ_native_world = _p3(p_occ.worldGeometry)
    except Exception as e:  # noqa: BLE001
        occ_native_world = f"raised {type(e).__name__}: {e}"
    expected_global = tuple(PT_OCC_LOCAL[i] + OCC_SHIFT[i] for i in range(3))
    detail = (
        f"occurrence translated +{OCC_SHIFT} cm; point local coord {PT_OCC_LOCAL} cm. "
        f"Expected ASSEMBLY-frame coord = {expected_global} cm. "
        f"Native p_occ.worldGeometry = {occ_native_world}. "
        f"findAttributes(attr.parent).worldGeometry = {occ_world}. "
        f"findAttributes parent carried assemblyContext? = {occ_via_attr_has_context}."
    )
    if occ_world is not None and _close(occ_world, expected_global):
        rec("q5_occurrence", "PASS",
            "worldGeometry via the production findAttributes path resolves the "
            "occurrence transform (global frame). cm->inch boundary "
            f"`* (1/2.54)` is correct as-is. {detail}")
    elif occ_world is not None and _close(occ_world, PT_OCC_LOCAL):
        rec("q5_occurrence", "WARN",
            "worldGeometry via findAttributes returned COMPONENT-LOCAL coords, "
            "NOT assembly-global — the occurrence transform was NOT applied. "
            "Extraction (§5.3) MUST resolve assembly context "
            "(SketchPoint.createForAssemblyContext / occurrence transform) before "
            f"converting to inches, OR require Suspension placed at root origin. {detail}")
    else:
        rec("q5_occurrence", "WARN",
            "occurrence-frame worldGeometry was inconclusive — inspect the raw "
            f"numbers. {detail}")

    # --- Q1.4a: survives a timeline rewind + rebuild (in-session) ----------
    before = _p3(p_root.worldGeometry) if set_ok else None
    try:
        tl = design.timeline
        tl.moveToBeginning()
        tl.moveToEnd()
        after_attrs = _iter_attrs(design)
        survived = False
        after = None
        for a in after_attrs:
            if a.value == ROLE_ROOT:
                sp = adsk.fusion.SketchPoint.cast(a.parent)
                if sp is not None and sp.isValid:
                    survived = True
                    after = _p3(sp.worldGeometry)
        if set_ok and survived and after == before:
            rec("q4a_rewind", "PASS",
                f"after timeline moveToBeginning()+moveToEnd(), tag '{ROLE_ROOT}' "
                f"still present, point valid, worldGeometry stable ({after} cm).")
        elif set_ok and survived:
            rec("q4a_rewind", "WARN",
                f"tag survived rewind but worldGeometry changed: {before} -> {after}.")
        elif set_ok:
            rec("q4a_rewind", "FAIL",
                "tag did NOT survive timeline rewind/rebuild.")
        else:
            rec("q4a_rewind", "SKIP", "set failed; rewind not meaningful.")
    except Exception as e:  # noqa: BLE001
        rec("q4a_rewind", "WARN",
            f"timeline rewind raised: {type(e).__name__}: {e}. "
            "(Direct-modeling doc? expected parametric.)")

    # --- secondary: user parameters (value=cm? expression/unit as typed?) --
    try:
        up = design.userParameters
        up.add(PARAM_LEN[0], adsk.core.ValueInput.createByString(PARAM_LEN[1]), PARAM_LEN[2], "len probe")
        up.add(PARAM_UNITLESS[0], adsk.core.ValueInput.createByString(PARAM_UNITLESS[1]), PARAM_UNITLESS[2], "lbm per comment")
        pl = up.itemByName(PARAM_LEN[0])
        pu = up.itemByName(PARAM_UNITLESS[0])
        len_value_in = pl.value * CM_TO_IN
        detail = (
            f"{PARAM_LEN[0]}: .value={pl.value} (cm) -> {len_value_in:.4f} in, "
            f".expression='{pl.expression}', .unit='{pl.unit}'.  "
            f"{PARAM_UNITLESS[0]}: .value={pu.value}, "
            f".expression='{pu.expression}', .unit='{pu.unit}'."
        )
        len_ok = abs(pl.value - 112 * 2.54) < 1e-3
        unitless_ok = abs(pu.value - 4000.0) < 1e-6
        if len_ok and unitless_ok:
            rec("q_params", "PASS",
                "length param .value is cm (convert with *1/2.54); unitless param "
                f"reads back exactly as typed. {detail}")
        else:
            rec("q_params", "WARN",
                f"param readback unexpected (len_ok={len_ok}, "
                f"unitless_ok={unitless_ok}). {detail}")
    except Exception as e:  # noqa: BLE001
        rec("q_params", "WARN",
            f"userParameters.add/read raised: {type(e).__name__}: {e}.")

    # --- secondary: standalone vs curve-endpoint distinction ---------------
    try:
        standalone_n = p_root.connectedEntities
        standalone_count = 0 if standalone_n is None else standalone_n.count
        ep = line.startSketchPoint
        ep_n = ep.connectedEntities
        ep_count = 0 if ep_n is None else ep_n.count
        if standalone_count == 0 and ep_count >= 1:
            rec("q_standalone", "PASS",
                f"standalone point connectedEntities.count={standalone_count}; "
                f"line-endpoint connectedEntities.count={ep_count}. The tagPickup "
                "command can filter standalone points via connectedEntities. "
                "(Interactive addSelectionFilter('SketchPoints') UI behavior still "
                "to be confirmed when that command is built.)")
        else:
            rec("q_standalone", "WARN",
                f"unexpected connectedEntities counts: standalone={standalone_count}, "
                f"endpoint={ep_count}. Use the slow Python-side filter (§2.2 fallback).")
    except Exception as e:  # noqa: BLE001
        rec("q_standalone", "WARN",
            f"connectedEntities raised: {type(e).__name__}: {e}. "
            "Use the §2.2 slow filter (walk lines/arcs, exclude their points).")

    # persist setup results so the VERIFY run can assemble a complete note
    try:
        with open(STATE_PATH, "w") as f:
            json.dump({"setup": results,
                       "doc_name": doc.name,
                       "root_tag": ROLE_ROOT,
                       "expected_root_world_cm": before}, f, indent=2)
    except Exception:  # noqa: BLE001
        pass

    write_findings(app, ui, setup=results, verify=None)


# ---------------------------------------------------------------------------
# VERIFY branch — runs on the reopened doc, confirms Q1.4b (save+reopen)
# ---------------------------------------------------------------------------
def run_verify(app, ui, design, attrs):
    verify = {}

    def rec(key, status, detail):
        verify[key] = {"status": status, "detail": detail}

    found = []
    cast_fail = []
    root_world = None
    for a in attrs:
        sp = adsk.fusion.SketchPoint.cast(a.parent)
        if sp is None:
            cast_fail.append(_objtype(a.parent))
            continue
        w = _p3(sp.worldGeometry)
        found.append({"role": a.value, "isValid": bool(sp.isValid),
                      "world_cm": w,
                      "assemblyContext": (None if sp.assemblyContext is None
                                          else sp.assemblyContext.name)})
        if a.value == ROLE_ROOT:
            root_world = w

    # compare against the value recorded at setup, if available
    expected = None
    try:
        with open(STATE_PATH) as f:
            expected = json.load(f).get("expected_root_world_cm")
        if expected is not None:
            expected = tuple(expected)
    except Exception:  # noqa: BLE001
        expected = None

    if found and not cast_fail and root_world is not None:
        same = (expected is None) or _close(root_world, expected)
        if same:
            rec("q4b_reopen", "PASS",
                f"after save+reopen the {len(found)} tag(s) are still present, "
                f"cast to valid SketchPoints, worldGeometry stable "
                f"(root '{ROLE_ROOT}' at {root_world} cm"
                + (f", matches pre-save {expected}" if expected else "")
                + f"). Found: {json.dumps(found)}")
        else:
            rec("q4b_reopen", "WARN",
                f"tags survived reopen but root worldGeometry shifted: "
                f"{expected} -> {root_world} cm. Found: {json.dumps(found)}")
    else:
        rec("q4b_reopen", "FAIL",
            f"after reopen: tags={len(found)}, cast_failures={cast_fail}, "
            f"root_world={root_world}. Found: {json.dumps(found)}")

    # re-read a user parameter post-reopen as a bonus persistence check
    try:
        pl = design.userParameters.itemByName(PARAM_LEN[0])
        if pl is not None:
            rec("q_params_reopen", "PASS",
                f"{PARAM_LEN[0]} persisted: .value={pl.value} cm "
                f"({pl.value * CM_TO_IN:.4f} in), .expression='{pl.expression}'.")
        else:
            rec("q_params_reopen", "WARN",
                f"{PARAM_LEN[0]} not found post-reopen (was this the scratch doc?).")
    except Exception as e:  # noqa: BLE001
        rec("q_params_reopen", "WARN", f"param re-read raised: {type(e).__name__}: {e}.")

    setup = None
    try:
        with open(STATE_PATH) as f:
            setup = json.load(f).get("setup")
    except Exception:  # noqa: BLE001
        setup = None

    write_findings(app, ui, setup=setup, verify=verify)


# ---------------------------------------------------------------------------
# findings note (markdown) + emit
# ---------------------------------------------------------------------------
ITEM_TITLES = {
    "q1_set": "Q1.1 — set attribute on SketchPoint",
    "q1_roundtrip": "Q1.2 — round-trips via itemByName",
    "q1_findattrs": "Q1.3 — findAttributes → cast → isValid → worldGeometry",
    "q4a_rewind": "Q1.4a — survives timeline rewind + rebuild",
    "q4b_reopen": "Q1.4b — survives save + reopen",
    "q5_occurrence": "Q5/Q8 — worldGeometry units + occurrence transform",
    "q_params": "Secondary — user parameters (cm value / expression / unit)",
    "q_params_reopen": "Secondary — user parameter persists across reopen",
    "q_standalone": "Secondary — standalone vs curve-endpoint point",
}
ITEM_ORDER = ["q1_set", "q1_roundtrip", "q1_findattrs", "q4a_rewind",
              "q4b_reopen", "q5_occurrence", "q_params", "q_params_reopen",
              "q_standalone"]


def _verdict(setup, verify):
    merged = {}
    if setup:
        merged.update(setup)
    if verify:
        merged.update(verify)

    def st(k):
        return merged.get(k, {}).get("status")

    if st("q1_set") == "FAIL":
        return ("**FALL BACK** — `SketchPoint.attributes.add` failed at runtime. "
                "Option D is not viable. Use parent-sketch attributes keyed by "
                "point, or Option B (named construction points). See Q1.1 detail.")
    core_ok = all(st(k) == "PASS" for k in ("q1_set", "q1_roundtrip", "q1_findattrs"))
    if not core_ok:
        return ("**INCONCLUSIVE** — core attribute chain (set/round-trip/"
                "findAttributes) not all green. Inspect the items above before "
                "committing to Option D.")
    rewind_ok = st("q4a_rewind") in ("PASS", "WARN")
    if verify is None:
        return ("**PROVISIONAL: Option D looks confirmed in-session** "
                "(set + round-trip + findAttributes fast path all pass"
                + (", survives timeline rewind" if rewind_ok else "")
                + "). ⏳ Pending the save+reopen check — SAVE the scratch doc, "
                "CLOSE it, REOPEN it, and run this script again to finalize Q1.4b.")
    reopen_ok = st("q4b_reopen") == "PASS"
    if reopen_ok:
        adj = ""
        if st("q5_occurrence") == "WARN":
            adj = (" **Extraction adjustment required:** worldGeometry did NOT "
                   "resolve the occurrence transform via findAttributes — §5.3 "
                   "must apply the occurrence/assembly-context transform (or the "
                   "Suspension component must sit at the root origin). See Q5 detail.")
        return ("**OPTION D CONFIRMED** — attribute-tagged SketchPoints set, "
                "round-trip, are discoverable via `design.findAttributes` "
                "(`attr.parent` casts to a valid SketchPoint), survive a timeline "
                "rewind/rebuild, and survive save + reopen. The cm→inch boundary "
                "`* (1/2.54)` is correct." + adj)
    return ("**OPTION D AT RISK** — the chain works in-session but the save+reopen "
            "check did not pass. See Q1.4b detail before committing.")


def write_findings(app, ui, setup, verify):
    merged = {}
    if setup:
        merged.update(setup)
    if verify:
        merged.update(verify)

    lines = []
    lines.append("# Fusion runtime probe — Option D pickup-tagging convention")
    lines.append("")
    lines.append("Gate for anvil `docs/02-spec/fusion-api-plan.md` §7 (Q1, Q5/Q6, Q8). "
                 "Generated by `scripts/anvil_pickup_probe/` run inside a live Fusion "
                 "session on a throwaway scratch design.")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(_verdict(setup, verify))
    lines.append("")
    lines.append("## Per-item results")
    lines.append("")
    lines.append("| Item | Status | Finding |")
    lines.append("|------|--------|---------|")
    for k in ITEM_ORDER:
        r = merged.get(k)
        title = ITEM_TITLES[k]
        if r is None:
            status, detail = "—", "(not run yet)"
        else:
            status, detail = r["status"], r["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {title} | {status} | {detail} |")
    lines.append("")
    if verify is None:
        lines.append("> ⏳ **Run 2 still needed for Q1.4b.** Save this scratch doc "
                     "(`Ctrl/Cmd+S` → any name), close it, reopen it from the Data "
                     "panel, then run the script again.")
    lines.append("")

    text = "\n".join(lines)
    try:
        app.log(text)
    except Exception:  # noqa: BLE001
        pass
    print(text)
    saved = None
    try:
        with open(FINDINGS_PATH, "w") as f:
            f.write(text)
        saved = FINDINGS_PATH
    except Exception:  # noqa: BLE001
        saved = None

    phase = "VERIFY (post-reopen)" if verify is not None else "SETUP (in-session)"
    msg = f"Anvil pickup probe — {phase} done.\n\n{_verdict(setup, verify)}"
    if saved:
        msg += f"\n\nFindings note written to:\n{saved}"
    msg += "\n\nFull table is in the Text Commands window (View > Show Text Commands)."
    ui.messageBox(msg, "Anvil Pickup Probe")


# ---------------------------------------------------------------------------
# entry point — branch on whether the active doc already carries our tags
# ---------------------------------------------------------------------------
def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = _design(app)
        if design is None:
            ui.messageBox("Open or let Fusion create a Design first, then run again.")
            return

        existing = _iter_attrs(design)
        if existing:
            # Reopened scratch doc (or any doc already carrying tags) -> verify.
            run_verify(app, ui, design, existing)
        else:
            # No tags yet -> build a fresh scratch doc and run the setup probes.
            run_setup(app, ui)

    except:  # noqa: E722 — probe: surface any failure verbatim
        ui.messageBox(f"anvil_pickup_probe failed:\n{traceback.format_exc()}")
