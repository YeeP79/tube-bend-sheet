"""Scoring engine for body-to-sketch matching.

Compares a BodyProfile against candidate SketchProfiles to find the
source sketch that generated the tube body. Fusion-free — all inputs
are plain dataclasses.

Scoring is based on:
- Direction alignment between body cylinder axes and sketch line directions.
- CLR matching between body torus major radii and sketch arc radii.
- Spatial proximity between body segment centroids and sketch midpoints.
- Connected-path bonus for sketches with high line/arc connectivity.
- Penalties for unmatched body segments and extra sketch entities.
"""

from __future__ import annotations

from ..models.match_data import (
    BodyProfile,
    MatchResult,
    SketchArcData,
    SketchLineData,
    TransformedSketchProfile,
)
from .geometry import (
    ZeroVectorError,
    distance_between_points,
    unsigned_angle_between,
)
from .tolerances import SKETCH_ENDPOINT_TOLERANCE_CM


def graduated_direction_score(angle_deg: float) -> int:
    """Score based on direction match quality.

    Args:
        angle_deg: Unsigned angle between body axis and sketch direction (0-90).

    Returns:
        Integer score: 12 (<1), 10 (<3), 7 (<5), 4 (<10), 2 (<15), 0 otherwise.
    """
    if angle_deg < 1.0:
        return 12
    if angle_deg < 3.0:
        return 10
    if angle_deg < 5.0:
        return 7
    if angle_deg < 10.0:
        return 4
    if angle_deg < 15.0:
        return 2
    return 0


def clr_match_score(clr_diff_cm: float) -> int:
    """Score based on CLR difference.

    Args:
        clr_diff_cm: Absolute difference in radius (cm).

    Returns:
        Integer score: 12 (<0.1), 6 (<0.5), 2 (<1), -3 (<3), -8 otherwise.
    """
    if clr_diff_cm < 0.1:
        return 12
    if clr_diff_cm < 0.5:
        return 6
    if clr_diff_cm < 1.0:
        return 2
    if clr_diff_cm < 3.0:
        return -3
    return -8


def proximity_score(p1: tuple[float, float, float], p2: tuple[float, float, float]) -> int:
    """Score based on spatial proximity.

    Args:
        p1: First point (e.g., body centroid).
        p2: Second point (e.g., sketch midpoint).

    Returns:
        Integer score: 8 (<2cm), 5 (<5cm), 2 (<15cm), 0 (<30cm), -3 otherwise.
    """
    dist = distance_between_points(p1, p2)
    if dist < 2.0:
        return 8
    if dist < 5.0:
        return 5
    if dist < 15.0:
        return 2
    if dist < 30.0:
        return 0
    return -3


def find_connected_path(
    lines: list[SketchLineData],
    arcs: list[SketchArcData],
    tol: float = SKETCH_ENDPOINT_TOLERANCE_CM,
) -> tuple[set[int], set[int], int]:
    """Find the longest connected chain of lines and arcs.

    Builds an adjacency graph from endpoint coincidence, then finds
    the longest path via DFS from each node.

    Args:
        lines: Sketch line data (in model space).
        arcs: Sketch arc data (in model space).
        tol: Endpoint coincidence tolerance (cm).

    Returns:
        Tuple of (connected_line_indices, connected_arc_indices, chain_length).
    """
    entities: list[tuple[str, int, tuple[float, float, float], tuple[float, float, float]]] = []
    for i, line in enumerate(lines):
        entities.append(("line", i, line.start, line.end))
    for i, arc in enumerate(arcs):
        entities.append(("arc", i, arc.start, arc.end))

    if not entities:
        return set(), set(), 0

    n = len(entities)
    adj: dict[int, list[int]] = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            ei = entities[i]
            ej = entities[j]
            if (_endpoints_match(ei[2], ej[2], tol) or
                _endpoints_match(ei[2], ej[3], tol) or
                _endpoints_match(ei[3], ej[2], tol) or
                _endpoints_match(ei[3], ej[3], tol)):
                adj[i].append(j)
                adj[j].append(i)

    best_path: list[int] = []
    for start in range(n):
        visited = {start}
        stack: list[tuple[int, list[int]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            extended = False
            for nbr in adj[node]:
                if nbr not in visited:
                    visited.add(nbr)
                    new_path = path + [nbr]
                    stack.append((nbr, new_path))
                    extended = True
            if not extended and len(path) > len(best_path):
                best_path = path

    connected_lines: set[int] = set()
    connected_arcs: set[int] = set()
    for idx in best_path:
        etype, eidx, _, _ = entities[idx]
        if etype == "line":
            connected_lines.add(eidx)
        else:
            connected_arcs.add(eidx)

    return connected_lines, connected_arcs, len(best_path)


def score_sketch_match(
    body_profile: BodyProfile,
    sketch_profile: TransformedSketchProfile,
) -> MatchResult:
    """Score how well a transformed sketch matches a body profile.

    Args:
        body_profile: Processed body geometry (OD-only segments).
        sketch_profile: Sketch with geometry transformed to model space.

    Returns:
        A MatchResult with score and breakdown details.
    """
    score = 0
    details: list[str] = []
    lines = sketch_profile.lines
    arcs = sketch_profile.arcs

    # ── Connected path bonus ──
    conn_lines, conn_arcs, chain_len = find_connected_path(lines, arcs)
    total_entities = len(lines) + len(arcs)
    conn_ratio = chain_len / total_entities if total_entities > 0 else 0.0

    if conn_ratio > 0.8 and chain_len >= 2:
        path_bonus = 10
    elif conn_ratio > 0.5 and chain_len >= 2:
        path_bonus = 5
    else:
        path_bonus = 0
    score += path_bonus
    details.append(
        f"  Path connectivity: {chain_len}/{total_entities} entities "
        f"connected (bonus: +{path_bonus})"
    )

    # ── Match body straights to sketch lines ──
    matched_body: set[int] = set()
    matched_sketch: set[int] = set()

    for bi, bseg in enumerate(body_profile.straights):
        best_total = -999
        best_si = -1
        best_angle = 999.0
        best_prox = 0
        best_dir = 0

        for si, sline in enumerate(lines):
            if si in matched_sketch:
                continue

            try:
                angle = unsigned_angle_between(bseg.axis, sline.direction)
            except ZeroVectorError:
                continue

            dir_score = graduated_direction_score(angle)
            if dir_score <= 0:
                continue

            prox = proximity_score(bseg.centroid, sline.midpoint)
            total = dir_score + prox

            if total > best_total:
                best_total = total
                best_si = si
                best_angle = angle
                best_prox = prox
                best_dir = dir_score

        if best_si >= 0 and best_total > 0:
            score += best_total
            matched_body.add(bi)
            matched_sketch.add(best_si)
            details.append(
                f"  Straight {bi}: angle={best_angle:.1f} deg (dir:+{best_dir}), "
                f"proximity (prox:+{best_prox}), total=+{best_total}"
            )

    # ── Match body bends to sketch arcs ──
    matched_body_bends: set[int] = set()
    matched_sketch_arcs: set[int] = set()

    for bi, bbend in enumerate(body_profile.bends):
        best_total = -999
        best_si = -1
        best_angle = 999.0
        best_clr_diff = 999.0
        best_clr = 0
        best_dir = 0
        best_prox = 0

        for si, sarc in enumerate(arcs):
            if si in matched_sketch_arcs:
                continue

            try:
                angle = unsigned_angle_between(bbend.axis, sarc.normal)
            except ZeroVectorError:
                continue

            dir_score = graduated_direction_score(angle)
            if dir_score <= 0:
                continue

            clr_diff = abs(bbend.major_radius - sarc.radius)
            clr = clr_match_score(clr_diff)
            prox = proximity_score(bbend.origin, sarc.center)
            total = dir_score + clr + prox

            if total > best_total:
                best_total = total
                best_si = si
                best_angle = angle
                best_clr_diff = clr_diff
                best_clr = clr
                best_dir = dir_score
                best_prox = prox

        if best_si >= 0 and best_total > 0:
            score += best_total
            matched_body_bends.add(bi)
            matched_sketch_arcs.add(best_si)
            details.append(
                f"  Bend {bi}: axis={best_angle:.1f} deg (dir:+{best_dir}), "
                f"CLR diff={best_clr_diff:.3f} cm (clr:{best_clr:+d}), "
                f"proximity (prox:{best_prox:+d}), total=+{best_total}"
            )

    # ── Penalties ──
    unmatched_body = len(body_profile.straights) - len(matched_body)
    unmatched_bends = len(body_profile.bends) - len(matched_body_bends)
    extra_lines = len(lines) - len(matched_sketch)
    extra_arcs = len(arcs) - len(matched_sketch_arcs)

    body_penalty = (unmatched_body + unmatched_bends) * -8
    extra_penalty = (extra_lines + extra_arcs) * -3
    score += body_penalty + extra_penalty

    details.append(
        f"  Summary: {len(matched_body)}/{len(body_profile.straights)} straights, "
        f"{len(matched_body_bends)}/{len(body_profile.bends)} bends matched"
    )
    details.append(
        f"  Penalties: unmatched body={body_penalty}, extra sketch={extra_penalty}"
    )

    return MatchResult(
        sketch_name=sketch_profile.name,
        score=score,
        confidence="none",
        matched_straights=len(matched_body),
        total_straights=len(body_profile.straights),
        matched_bends=len(matched_body_bends),
        total_bends=len(body_profile.bends),
        connected_line_indices=conn_lines,
        connected_arc_indices=conn_arcs,
        details=details,
    )


def rank_matches(results: list[MatchResult]) -> list[MatchResult]:
    """Sort match results by score and assign confidence levels.

    Confidence is based on the margin between first and second place:
    - "high": margin > 50% of top score.
    - "medium": margin > 25% of top score.
    - "low": positive score with small margin.
    - "none": zero or negative score.

    Args:
        results: Unordered match results.

    Returns:
        Sorted list (descending score) with confidence set.
    """
    sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

    for r in sorted_results:
        r.confidence = "none"

    if not sorted_results:
        return sorted_results

    top = sorted_results[0]
    if top.score <= 0:
        return sorted_results

    if len(sorted_results) >= 2:
        margin = top.score - sorted_results[1].score
        pct = (margin / max(1, top.score)) * 100
        if pct > 50:
            top.confidence = "high"
        elif pct > 25:
            top.confidence = "medium"
        else:
            top.confidence = "low"
    else:
        top.confidence = "high"

    return sorted_results


def _endpoints_match(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    tol: float,
) -> bool:
    """Check if two points are coincident within tolerance."""
    return distance_between_points(p1, p2) < tol
