# Fusion → Anvil Tube Export Schema (draft)

**Status:** Draft spec for review. **Version:** schema `1.0.0-draft`.
**Date:** 2026-06-04.
**Companion:** [`fusion-tube-extraction-investigation.md`](./fusion-tube-extraction-investigation.md)
(the research this is built on).
**Owners:** Fusion add-in (producer) ⇄ Rust converter (consumer).

This defines the JSON contract a Fusion add-in emits so the Rust side can ingest
a chassis as **per-tube centerline + OD + bend table + connectivity graph**,
without re-reading the B-rep. It is derived from TubeFabrication's
`BodyPathResult` / `BendData` models and validated extraction behaviour.

---

## 1. Design principles (read first)

1. **Canonical units = centimetres.** Fusion stores geometry internally in cm;
   we emit cm verbatim and let the consumer convert for display. Angles in
   **degrees**. One `units`/`angle_units` field declares this; there are no
   per-value units.
2. **Geometry is authoritative; names are advisory.** Every dimension
   (`od`, `wall`, lengths, angles) is **measured** from the B-rep. `name` is
   carried for humans only and **must not** be parsed for dimensions. (A name
   like `… 1.75` goes stale; the geometry does not.)
3. **Bend table is the primary form.** Each tube is an ordered list of straight
   and bend segments (lengths, CLR, angle, rotation). The consumer samples a
   centerline polyline from it when needed — do not invert.
4. **Visible bodies only.** The producer exports only visible tube bodies; hidden
   bodies are stale reference geometry and are omitted.
5. **Coping is per-end, never assumed.** `coped` is reported per tube-end. It is
   *not* a precondition for anything in this schema.
6. **Connectivity is endpoint-proximity, independent of coping.** A connection is
   a tube end lying within ~1.5×OD of another tube's axis. It is computed
   regardless of whether either tube is coped.
7. **Right-handed coordinates**, Fusion world frame. The vehicle-semantic mapping
   is declared in `frame` (and is fixed by the add-in: X=L/R, Y=Bottom/Top,
   Z=Front(−)/Back(+)).
8. **Nulls are explicit.** Unknown/inapplicable scalar fields are `null`, not
   omitted or zero (e.g. `id`/`wall` on a solid bar; `rotation` on the first
   bend).
9. **Forward-compatible.** Consumers must ignore unknown fields; producers must
   not repurpose existing ones. Bump `schema_version` (semver) on changes.

---

## 2. Top-level object

```jsonc
{
  "schema_version": "1.0.0-draft",
  "source": {
    "app": "anvil-fusion-addin",
    "app_version": "0.1.0",
    "design_name": "chassis v52",
    "design_id": "<Fusion document id>",   // optional
    "exported_at": "2026-06-04T22:00:00Z"  // ISO-8601 UTC
  },
  "units": "cm",                // all lengths & coordinates
  "angle_units": "degrees",
  "frame": {
    "handedness": "right",
    "centerline_axis": "X",     // lateral; vehicle centerline plane
    "centerline_plane": 0.0,    // coordinate of the L/R mirror plane (cm)
    "up_axis": "Y",
    "fore_aft_axis": "Z",
    "front_sign": -1            // front is the −Z direction  (Front(−)/Back(+))
  },
  "tubes": [ /* Tube objects, §3 */ ],
  "connections": [ /* Connection objects, §5 */ ],
  "nodes": [ /* optional, derived clusters, §6 */ ],
  "warnings": [ /* file-level Warning objects, §7 */ ]
}
```

| Field | Type | Req | Notes |
|---|---|---|---|
| `schema_version` | string (semver) | ✓ | Contract version. |
| `source` | object | ✓ | Provenance. `design_id` optional. |
| `units` | `"cm"` | ✓ | Fixed at `cm` for v1. |
| `angle_units` | `"degrees"` | ✓ | Fixed at `degrees` for v1. |
| `frame` | object | ✓ | World→vehicle axis map. `front_sign` ∈ {−1,+1}. |
| `tubes` | Tube[] | ✓ | May be empty. |
| `connections` | Connection[] | ✓ | May be empty. |
| `nodes` | Node[] | – | Optional, derived from connections. |
| `warnings` | Warning[] | ✓ | May be empty. |

---

## 3. Tube object

```jsonc
{
  "id": "t-0007",                         // stable id assigned by exporter
  "entity_token": "<Fusion entityToken>", // stable Fusion identity (re-export match)
  "name": "Winch fairlead support",       // ADVISORY ONLY — never parse for dims
  "occurrence_path": ["passenger side", "Winch fairlead support"],
  "classification": "tube",               // "tube" | "ambiguous" | "non_tube"

  "geometry": {
    "od": 4.4450,            // diameter, cm (measured: 2 × largest cylinder radius)
    "id": 3.8354,            // diameter, cm; null if solid / no detectable bore
    "wall": 0.3050,          // cm; null if unknown
    "wall_consistent": true, // false ⇒ mixed-wall body (e.g. join seam) — see flags
    "clr": 13.9700,          // primary bend CLR, cm; null if no bends
    "clr_consistent": true   // false ⇒ bends disagree on CLR
  },

  "path": {
    "start_point": [0.00, 80.10, -36.00], // centerline endpoint, cm
    "end_point":   [0.00, 95.18, -49.42],
    "total_centerline": 70.92,            // cm (Σ straight lengths + bend arcs)
    "segments": [ /* ordered Segment objects, §4 */ ]
  },

  "ends": {
    "start": { "point": [0.00, 80.10, -36.00], "coped": false, "connection_ids": ["c-31"] },
    "end":   { "point": [0.00, 95.18, -49.42], "coped": true,  "connection_ids": ["c-32"] }
  },

  "flags": [],               // e.g. ["mixed_wall","ambiguous_path"]; see §7 codes
  "warnings": []             // per-tube Warning objects (§7)
}
```

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string | ✓ | Stable within a file; referenced by connections. |
| `entity_token` | string | ✓ | Fusion `entityToken`; lets a re-export re-key the same tube. |
| `name` | string | ✓ | Human label. **Advisory.** May be empty. |
| `occurrence_path` | string[] | ✓ | Root→leaf occurrence names (assembly location). |
| `classification` | enum | ✓ | `tube` (clean), `ambiguous` (multi-straight/0-tori, mixed signals), `non_tube` (cylindrical face but not a tube — gusset/plate/boss). Consumers typically use `tube` only. |
| `geometry.od` | number | ✓ | **Diameter**, cm. |
| `geometry.id` | number\|null | ✓ | Diameter, cm; `null` if solid. |
| `geometry.wall` | number\|null | ✓ | cm; `null` if unknown. |
| `geometry.wall_consistent` | bool | ✓ | `false` ⇒ multiple bore walls in one body. |
| `geometry.clr` | number\|null | ✓ | cm; `null` if straight tube. |
| `geometry.clr_consistent` | bool | ✓ | per `BodyPathResult.clr_consistent`. |
| `path.start_point`/`end_point` | number[3] | ✓ | Centerline endpoints, cm. |
| `path.total_centerline` | number | ✓ | cm. |
| `path.segments` | Segment[] | ✓ | Ordered start→end; alternating straight/bend, may start or end on either. |
| `ends.start`/`ends.end` | End | ✓ | See below. |
| `flags` | string[] | ✓ | Machine codes (§7). May be empty. |
| `warnings` | Warning[] | ✓ | May be empty. |

**End object:** `{ point:number[3], coped:bool, connection_ids:string[] }`.
`connection_ids` empty ⇒ a free/unconnected end (see `unconnected_end` warning,
§7). Multiple ids ⇒ end meets more than one tube (a node).

---

## 4. Segment objects (ordered)

A tube's `path.segments` is the bend table. Two shapes, discriminated by `type`.

**Straight:**
```jsonc
{ "type": "straight", "index": 0,
  "start": [0.00, 80.10, -36.00], "end": [0.00, 80.10, -49.79],
  "length": 13.79 }                 // cm
```

**Bend:**
```jsonc
{ "type": "bend", "index": 1,
  "angle": 36.8,                    // sweep, degrees
  "clr": 13.9700,                   // cm (torus major radius)
  "arc_length": 8.97,               // cm (clr × angle_rad)
  "center": [0.00, 86.40, -49.79],  // torus origin, cm
  "plane_normal": [1.0, 0.0, 0.0],  // unit normal = cross(incoming, outgoing)
  "rotation": null,                 // deg between this & previous bend plane; null on first bend
  "rotation_signed": null }         // reserved; null until a signed convention is fixed (§8)
```

| Field | Type | Req | Notes |
|---|---|---|---|
| `type` | `"straight"`\|`"bend"` | ✓ | Discriminator. |
| `index` | int | ✓ | 0-based position in `segments`. |
| straight `start`/`end` | number[3] | ✓ | Centerline endpoints, cm. |
| straight `length` | number | ✓ | cm. |
| bend `angle` | number | ✓ | Degrees, sweep of the bend. |
| bend `clr` | number | ✓ | cm. |
| bend `arc_length` | number | ✓ | cm. |
| bend `center` | number[3] | ✓ | Torus origin, cm. |
| bend `plane_normal` | number[3] | ✓ | Unit vector; `cross(incoming_straight, outgoing_straight)`. |
| bend `rotation` | number\|null | ✓ | **Unsigned** 0–180°, angle to previous bend plane. `null` for the first bend. |
| bend `rotation_signed` | number\|null | – | Reserved; `null` in v1. |

> The consumer reconstructs a polyline as straight endpoints joined by circular
> arcs of radius `clr`. `plane_normal` + `rotation` carry the multi-plane bend
> orientation; that is the only data needed to place each bend in 3D.

---

## 5. Connection object (tube-to-tube)

One edge per detected junction: a tube **end** that seats onto a **receiving
tube**. Mirrors `detect_receiving_tubes_assembly`.

```jsonc
{
  "id": "c-32",
  "tube_id": "t-0007", "tube_end": "end",     // which end of which tube
  "receiving_tube_id": "t-0019",              // tube it meets; null if receiver isn't an exported tube
  "junction_point": [0.00, 95.18, -49.42],    // the tube end point, cm
  "distance": 0.08,                           // perp dist end→receiver axis, cm
  "incidence_angle": 58.0,                    // angle between tube axes at the joint, deg (optional)
  "method": "endpoint_proximity",             // detection method
  "node_id": "n-5"                            // optional, if clustered into a node
}
```

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string | ✓ | Stable within file. |
| `tube_id` | string | ✓ | The incoming tube. |
| `tube_end` | `"start"`\|`"end"` | ✓ | Which end connects. |
| `receiving_tube_id` | string\|null | ✓ | `null` if the receiver wasn't exported (e.g. filtered non-tube). |
| `junction_point` | number[3] | ✓ | cm. |
| `distance` | number | ✓ | cm; perpendicular end→receiver-axis distance (≤ ~1.5×OD). |
| `incidence_angle` | number\|null | – | Degrees between the two tube directions. |
| `method` | string | ✓ | `endpoint_proximity` for v1. |
| `node_id` | string\|null | – | Set if `nodes` clustering is emitted. |

Connections are **directional** (incoming end → receiving tube). A typical
butt/seat joint yields one connection; a tube meeting several at a point yields
several. Plate-mediated joints produce **no** connection (a plate is not a tube)
— surface that as an `unconnected_end` warning where relevant.

---

## 6. Node object (optional, derived)

Convenience clustering of coincident `junction_point`s into chassis nodes. Purely
derived; a consumer may ignore it and cluster itself.

```jsonc
{ "id": "n-5",
  "point": [0.00, 95.18, -49.42],         // cluster centroid, cm
  "tolerance": 0.30,                       // cm clustering radius used
  "members": [                             // tube ends at this node
    { "tube_id": "t-0007", "tube_end": "end" },
    { "tube_id": "t-0019", "tube_end": "start" }
  ],
  "connection_ids": ["c-32", "c-41"] }
```

---

## 7. Warnings & flags

**`flags`** (per tube) are terse machine codes; **`warnings`** (file or tube) are
structured and human-readable.

```jsonc
{ "code": "mixed_wall", "severity": "warn",
  "tube_id": "t-0003", "tube_end": null,
  "message": "Body has 2 distinct bore walls (0.120in, 0.188in) — likely a join seam." }
```

| Code | Severity | Meaning / producer action |
|---|---|---|
| `mixed_wall` | warn | >1 bore wall in one body (join seam). OD path still valid; `wall` is the dominant one. |
| `unconnected_end` | warn | A tube end found no receiving tube. May be a legit free end OR a misplaced/short tube — **surface to the Fusion user**. |
| `ambiguous_path` | warn | Multiple straight legs, **0 tori** (mitered/multi-straight). Path may not be a single chain; consider per-leg export. |
| `possible_non_tube` | info | Cylindrical face(s) but tube-likeness is low (length≈OD, no clean end caps) — gusset/plate/boss. Usually `classification:"non_tube"`. |
| `clr_mismatch` | warn | Bends disagree on CLR beyond tolerance. |
| `overshoot_reject` | info | A near-axis receiver was rejected because the body was far along the axis (false-positive guard). |
| `coped_no_receiver` | info | End is coped but no receiver detected (receiver may be hidden/non-tube). |

Severity ∈ `{info, warn, error}`. `error` means the tube's geometry could not be
trusted and the consumer should skip it.

---

## 8. Open decisions (flag before freezing v1)

1. **Signed rotation — RESOLVED for v1: not needed.** TubeFabrication's
   `calculate_rotation` is unsigned 0–180°. Anvil's goal is to **replicate and
   render** the chassis (Fusion → Rust object graph → three.js), and rendering is
   fully determined by the **absolute centerline coordinates** already in the
   schema — roll direction is a *fabrication* concern, not a rendering input. So
   `rotation_signed` stays `null` in v1. Revisit only if Anvil later emits
   bend/fabrication instructions; then define the sign (reference vector +
   right-hand rule about the tube axis).
2. **Receiver that isn't a tube.** A tube can seat onto a plate or a filtered
   body. v1 sets `receiving_tube_id: null` + `coped_no_receiver`/`unconnected_end`.
   Decide if Anvil wants plate receivers modelled at all.
3. **Mitered multi-straight bodies.** Export as one `ambiguous` tube, or split
   into N per-leg tubes? (Depends on how Anvil treats welded multi-segment members.)
4. **Connectivity tolerance.** v1 inherits ~1.5×OD proximity + axial-overshoot.
   Confirm that matches Anvil's modeling discipline, or parameterize it.
5. **`nodes` clustering** ownership — produce in Fusion, or derive in Rust?

---

## 9. Producer contract (Fusion add-in must)

- Enumerate **visible** bodies across the full occurrence tree; skip hidden.
- Classify tube vs non-tube; never derive dimensions from names.
- Run centerline/OD/bend extraction (`extract_body_path`) and emit the bend table.
- Run connectivity at **both** ends of every tube **regardless of coping**.
- Emit `coped` per end (true iff terminal straight has non-circle edges).
- Emit warnings for `mixed_wall`, `unconnected_end`, `ambiguous_path`, etc.
- Use the fixed vehicle-axis map (Front=−Z …) from `detect_path_direction`.

## 10. Consumer contract (Rust converter may assume)

- All lengths/coords are **cm**; angles **degrees**; coordinates right-handed.
- The **bend table is authoritative**; sample a polyline from it as needed.
- Honour `null` semantics; do not treat `null` as `0`.
- Treat `name` as advisory; trust measured geometry.
- Ignore unknown fields; check `schema_version` major for compatibility.
- Filter to `classification:"tube"` unless it explicitly wants the rest.

### 10.1 Rendering / replica use case (three.js)

Anvil's primary use is to **replicate and render** the chassis. The load-bearing
fields for that are the absolute centerline coordinates and `od`; the bend-table
angles/rotation are fabrication-flavored extras and are **not** needed to draw a
faithful tube.

- **Per tube:** sweep a circle of radius `od/2` along the centerline. Vertices =
  each straight's `start`/`end`; tessellate each bend into arc points from
  `center`, radius `clr`, `plane_normal`, and `angle` (rotate the entering
  direction about `plane_normal` by `angle`, stepping in small increments).
- **Placement** is already absolute (world cm) — no per-tube transform needed.
- **The chassis graph** Rust builds = `tubes` as nodes-of-objects + `connections`
  (edges) + optional `nodes` (junction clusters). That *is* the object model;
  three.js just renders the tubes and (optionally) highlights nodes.
- **Roll/`rotation` can be ignored** for rendering — the absolute geometry is
  unambiguous without it.

---

## Appendix A — Worked example (Body10 = `Winch fairlead support`)

Real measured values (lengths converted to cm; coordinates illustrative):
OD 1.75″ (4.4450 cm), ID 1.51″ (3.8354 cm), wall .120″ (0.3050 cm),
CLR 5.5″ (13.97 cm), two 36.8° bends, 0° rotation between them (planar),
total centerline 27.92″ (70.92 cm).

```jsonc
{
  "id": "t-0007", "entity_token": "…", "name": "Winch fairlead support",
  "occurrence_path": ["passenger side", "Winch fairlead support"],
  "classification": "tube",
  "geometry": { "od": 4.4450, "id": 3.8354, "wall": 0.3050,
                "wall_consistent": true, "clr": 13.9700, "clr_consistent": true },
  "path": {
    "start_point": [0.00, 80.10, -36.00], "end_point": [0.00, 95.18, -49.42],
    "total_centerline": 70.92,
    "segments": [
      { "type": "straight", "index": 0, "start": [0.00,80.10,-36.00], "end": [0.00,80.10,-49.79], "length": 13.79 },
      { "type": "bend", "index": 1, "angle": 36.8, "clr": 13.9700, "arc_length": 8.97,
        "center": [0.00,86.40,-49.79], "plane_normal": [1.0,0.0,0.0], "rotation": null, "rotation_signed": null },
      { "type": "straight", "index": 2, "start": [0.00,86.40,-43.10], "end": [0.00,86.40,-17.70], "length": 25.40 },
      { "type": "bend", "index": 3, "angle": 36.8, "clr": 13.9700, "arc_length": 8.97,
        "center": [0.00,92.70,-17.70], "plane_normal": [1.0,0.0,0.0], "rotation": 0.0, "rotation_signed": null },
      { "type": "straight", "index": 4, "start": [0.00,95.18,-23.99], "end": [0.00,95.18,-49.42], "length": 13.79 }
    ]
  },
  "ends": {
    "start": { "point": [0.00,80.10,-36.00], "coped": false, "connection_ids": [] },
    "end":   { "point": [0.00,95.18,-49.42], "coped": false, "connection_ids": [] }
  },
  "flags": [], "warnings": []
}
```
*(In Body10 the production walk dropped 4 short perpendicular cylinder faces as
cope artifacts; an uncoped end like the two above drops nothing.)*

---

## Appendix B — JSON Schema (draft 2020-12, abridged)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://anvil/schemas/tube-export-1.0.0.json",
  "title": "AnvilTubeExport",
  "type": "object",
  "required": ["schema_version","source","units","angle_units","frame","tubes","connections","warnings"],
  "properties": {
    "schema_version": { "type": "string" },
    "source": {
      "type": "object",
      "required": ["app","design_name","exported_at"],
      "properties": {
        "app": {"type":"string"}, "app_version": {"type":"string"},
        "design_name": {"type":"string"}, "design_id": {"type":"string"},
        "exported_at": {"type":"string","format":"date-time"}
      }
    },
    "units": { "const": "cm" },
    "angle_units": { "const": "degrees" },
    "frame": {
      "type": "object",
      "required": ["handedness","centerline_axis","centerline_plane","up_axis","fore_aft_axis","front_sign"],
      "properties": {
        "handedness": {"const":"right"},
        "centerline_axis": {"enum":["X","Y","Z"]},
        "centerline_plane": {"type":"number"},
        "up_axis": {"enum":["X","Y","Z"]},
        "fore_aft_axis": {"enum":["X","Y","Z"]},
        "front_sign": {"enum":[-1,1]}
      }
    },
    "tubes": { "type":"array", "items": { "$ref": "#/$defs/tube" } },
    "connections": { "type":"array", "items": { "$ref": "#/$defs/connection" } },
    "nodes": { "type":"array", "items": { "$ref": "#/$defs/node" } },
    "warnings": { "type":"array", "items": { "$ref": "#/$defs/warning" } }
  },
  "$defs": {
    "vec3": { "type":"array", "items":{"type":"number"}, "minItems":3, "maxItems":3 },
    "tube": {
      "type":"object",
      "required": ["id","entity_token","name","occurrence_path","classification","geometry","path","ends","flags","warnings"],
      "properties": {
        "id": {"type":"string"}, "entity_token": {"type":"string"},
        "name": {"type":"string"},
        "occurrence_path": {"type":"array","items":{"type":"string"}},
        "classification": {"enum":["tube","ambiguous","non_tube"]},
        "geometry": {
          "type":"object",
          "required": ["od","id","wall","wall_consistent","clr","clr_consistent"],
          "properties": {
            "od": {"type":"number","exclusiveMinimum":0},
            "id": {"type":["number","null"]},
            "wall": {"type":["number","null"]},
            "wall_consistent": {"type":"boolean"},
            "clr": {"type":["number","null"]},
            "clr_consistent": {"type":"boolean"}
          }
        },
        "path": {
          "type":"object",
          "required": ["start_point","end_point","total_centerline","segments"],
          "properties": {
            "start_point": {"$ref":"#/$defs/vec3"},
            "end_point": {"$ref":"#/$defs/vec3"},
            "total_centerline": {"type":"number","minimum":0},
            "segments": {"type":"array","items":{"$ref":"#/$defs/segment"}}
          }
        },
        "ends": {
          "type":"object",
          "required": ["start","end"],
          "properties": { "start": {"$ref":"#/$defs/end"}, "end": {"$ref":"#/$defs/end"} }
        },
        "flags": {"type":"array","items":{"type":"string"}},
        "warnings": {"type":"array","items":{"$ref":"#/$defs/warning"}}
      }
    },
    "end": {
      "type":"object",
      "required": ["point","coped","connection_ids"],
      "properties": {
        "point": {"$ref":"#/$defs/vec3"},
        "coped": {"type":"boolean"},
        "connection_ids": {"type":"array","items":{"type":"string"}}
      }
    },
    "segment": {
      "oneOf": [
        {
          "type":"object",
          "required": ["type","index","start","end","length"],
          "properties": {
            "type": {"const":"straight"}, "index": {"type":"integer","minimum":0},
            "start": {"$ref":"#/$defs/vec3"}, "end": {"$ref":"#/$defs/vec3"},
            "length": {"type":"number","minimum":0}
          }
        },
        {
          "type":"object",
          "required": ["type","index","angle","clr","arc_length","center","plane_normal","rotation"],
          "properties": {
            "type": {"const":"bend"}, "index": {"type":"integer","minimum":0},
            "angle": {"type":"number"}, "clr": {"type":"number","exclusiveMinimum":0},
            "arc_length": {"type":"number","minimum":0},
            "center": {"$ref":"#/$defs/vec3"}, "plane_normal": {"$ref":"#/$defs/vec3"},
            "rotation": {"type":["number","null"]},
            "rotation_signed": {"type":["number","null"]}
          }
        }
      ]
    },
    "connection": {
      "type":"object",
      "required": ["id","tube_id","tube_end","receiving_tube_id","junction_point","distance","method"],
      "properties": {
        "id": {"type":"string"}, "tube_id": {"type":"string"},
        "tube_end": {"enum":["start","end"]},
        "receiving_tube_id": {"type":["string","null"]},
        "junction_point": {"$ref":"#/$defs/vec3"},
        "distance": {"type":"number","minimum":0},
        "incidence_angle": {"type":["number","null"]},
        "method": {"type":"string"},
        "node_id": {"type":["string","null"]}
      }
    },
    "node": {
      "type":"object",
      "required": ["id","point","members"],
      "properties": {
        "id": {"type":"string"}, "point": {"$ref":"#/$defs/vec3"},
        "tolerance": {"type":"number"},
        "members": {"type":"array","items":{
          "type":"object","required":["tube_id","tube_end"],
          "properties": {"tube_id":{"type":"string"},"tube_end":{"enum":["start","end"]}}
        }},
        "connection_ids": {"type":"array","items":{"type":"string"}}
      }
    },
    "warning": {
      "type":"object",
      "required": ["code","severity","message"],
      "properties": {
        "code": {"type":"string"}, "severity": {"enum":["info","warn","error"]},
        "tube_id": {"type":["string","null"]},
        "tube_end": {"enum":["start","end",null]},
        "message": {"type":"string"}
      }
    }
  }
}
```
