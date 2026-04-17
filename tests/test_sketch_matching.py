"""Tests for core.sketch_matching — scoring, connected path, ranking."""

from __future__ import annotations

import math

from core.sketch_matching import (
    clr_match_score,
    find_connected_path,
    graduated_direction_score,
    proximity_score,
    rank_matches,
    score_sketch_match,
)
from models.match_data import (
    BodyBend,
    BodyProfile,
    BodyStraight,
    MatchResult,
    SketchArcData,
    SketchLineData,
    TransformedSketchProfile,
)


# ── graduated_direction_score ──


class TestGraduatedDirectionScore:
    def test_exact_match(self) -> None:
        assert graduated_direction_score(0.0) == 12

    def test_under_1_degree(self) -> None:
        assert graduated_direction_score(0.5) == 12

    def test_at_1_degree(self) -> None:
        assert graduated_direction_score(1.0) == 10

    def test_under_3_degrees(self) -> None:
        assert graduated_direction_score(2.5) == 10

    def test_at_3_degrees(self) -> None:
        assert graduated_direction_score(3.0) == 7

    def test_under_5_degrees(self) -> None:
        assert graduated_direction_score(4.9) == 7

    def test_at_5_degrees(self) -> None:
        assert graduated_direction_score(5.0) == 4

    def test_under_10_degrees(self) -> None:
        assert graduated_direction_score(9.0) == 4

    def test_at_10_degrees(self) -> None:
        assert graduated_direction_score(10.0) == 2

    def test_under_15_degrees(self) -> None:
        assert graduated_direction_score(14.9) == 2

    def test_at_15_degrees(self) -> None:
        assert graduated_direction_score(15.0) == 0

    def test_large_angle(self) -> None:
        assert graduated_direction_score(90.0) == 0


# ── clr_match_score ──


class TestClrMatchScore:
    def test_exact_match(self) -> None:
        assert clr_match_score(0.0) == 12

    def test_close_match(self) -> None:
        assert clr_match_score(0.05) == 12

    def test_at_boundary_01(self) -> None:
        assert clr_match_score(0.1) == 6

    def test_marginal_match(self) -> None:
        assert clr_match_score(0.3) == 6

    def test_at_boundary_05(self) -> None:
        assert clr_match_score(0.5) == 2

    def test_poor_match(self) -> None:
        assert clr_match_score(0.9) == 2

    def test_wrong_die(self) -> None:
        assert clr_match_score(1.5) == -3

    def test_completely_wrong(self) -> None:
        assert clr_match_score(5.0) == -8


# ── proximity_score ──


class TestProximityScore:
    def test_very_close(self) -> None:
        assert proximity_score((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)) == 8

    def test_close(self) -> None:
        assert proximity_score((0.0, 0.0, 0.0), (3.0, 0.0, 0.0)) == 5

    def test_same_neighborhood(self) -> None:
        assert proximity_score((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)) == 2

    def test_same_area(self) -> None:
        assert proximity_score((0.0, 0.0, 0.0), (20.0, 0.0, 0.0)) == 0

    def test_far_away(self) -> None:
        assert proximity_score((0.0, 0.0, 0.0), (50.0, 0.0, 0.0)) == -3


# ── find_connected_path ──


class TestFindConnectedPath:
    def test_empty_inputs(self) -> None:
        lines_idx, arcs_idx, chain = find_connected_path([], [])
        assert lines_idx == set()
        assert arcs_idx == set()
        assert chain == 0

    def test_single_line(self) -> None:
        line = SketchLineData(
            direction=(1.0, 0.0, 0.0),
            start=(0.0, 0.0, 0.0),
            end=(5.0, 0.0, 0.0),
            midpoint=(2.5, 0.0, 0.0),
            length=5.0,
        )
        lines_idx, arcs_idx, chain = find_connected_path([line], [])
        assert lines_idx == {0}
        assert chain == 1

    def test_two_connected_lines(self) -> None:
        l1 = SketchLineData(
            direction=(1.0, 0.0, 0.0),
            start=(0.0, 0.0, 0.0), end=(5.0, 0.0, 0.0),
            midpoint=(2.5, 0.0, 0.0), length=5.0,
        )
        l2 = SketchLineData(
            direction=(0.0, 1.0, 0.0),
            start=(5.0, 0.0, 0.0), end=(5.0, 5.0, 0.0),
            midpoint=(5.0, 2.5, 0.0), length=5.0,
        )
        lines_idx, arcs_idx, chain = find_connected_path([l1, l2], [])
        assert lines_idx == {0, 1}
        assert chain == 2

    def test_disconnected_lines(self) -> None:
        l1 = SketchLineData(
            direction=(1.0, 0.0, 0.0),
            start=(0.0, 0.0, 0.0), end=(5.0, 0.0, 0.0),
            midpoint=(2.5, 0.0, 0.0), length=5.0,
        )
        l2 = SketchLineData(
            direction=(0.0, 1.0, 0.0),
            start=(50.0, 0.0, 0.0), end=(50.0, 5.0, 0.0),
            midpoint=(50.0, 2.5, 0.0), length=5.0,
        )
        lines_idx, arcs_idx, chain = find_connected_path([l1, l2], [])
        assert chain == 1

    def test_line_arc_line_chain(self) -> None:
        l1 = SketchLineData(
            direction=(1.0, 0.0, 0.0),
            start=(0.0, 0.0, 0.0), end=(5.0, 0.0, 0.0),
            midpoint=(2.5, 0.0, 0.0), length=5.0,
        )
        arc = SketchArcData(
            center=(5.0, 1.0, 0.0), radius=1.0,
            normal=(0.0, 0.0, 1.0), sweep=math.pi / 2,
            start=(5.0, 0.0, 0.0), end=(6.0, 1.0, 0.0),
        )
        l2 = SketchLineData(
            direction=(0.0, 1.0, 0.0),
            start=(6.0, 1.0, 0.0), end=(6.0, 8.0, 0.0),
            midpoint=(6.0, 4.5, 0.0), length=7.0,
        )
        lines_idx, arcs_idx, chain = find_connected_path([l1, l2], [arc])
        assert lines_idx == {0, 1}
        assert arcs_idx == {0}
        assert chain == 3

    def test_tolerance_respected(self) -> None:
        l1 = SketchLineData(
            direction=(1.0, 0.0, 0.0),
            start=(0.0, 0.0, 0.0), end=(5.0, 0.0, 0.0),
            midpoint=(2.5, 0.0, 0.0), length=5.0,
        )
        l2 = SketchLineData(
            direction=(0.0, 1.0, 0.0),
            start=(5.04, 0.0, 0.0), end=(5.04, 5.0, 0.0),
            midpoint=(5.04, 2.5, 0.0), length=5.0,
        )
        # Within default 0.05 tolerance
        _, _, chain = find_connected_path([l1, l2], [])
        assert chain == 2

        # Outside tight tolerance
        _, _, chain_tight = find_connected_path([l1, l2], [], tol=0.01)
        assert chain_tight == 1


# ── score_sketch_match ──


def _make_body_profile(
    straights: list[BodyStraight] | None = None,
    bends: list[BodyBend] | None = None,
    od_radius: float = 1.905,
) -> BodyProfile:
    return BodyProfile(
        straights=straights or [],
        bends=bends or [],
        od_radius=od_radius,
    )


def _make_sketch_profile(
    name: str = "Sketch1",
    lines: list[SketchLineData] | None = None,
    arcs: list[SketchArcData] | None = None,
) -> TransformedSketchProfile:
    return TransformedSketchProfile(
        name=name,
        lines=lines or [],
        arcs=arcs or [],
    )


class TestScoreSketchMatch:
    def test_empty_body_and_sketch(self) -> None:
        result = score_sketch_match(
            _make_body_profile(), _make_sketch_profile()
        )
        assert result.score == 0
        assert result.matched_straights == 0
        assert result.matched_bends == 0

    def test_perfect_straight_match(self) -> None:
        body = _make_body_profile(
            straights=[BodyStraight(
                axis=(1.0, 0.0, 0.0), origin=(0.0, 0.0, 0.0),
                radius=1.905, length=10.0, centroid=(5.0, 0.0, 0.0),
            )]
        )
        sketch = _make_sketch_profile(
            lines=[SketchLineData(
                direction=(1.0, 0.0, 0.0),
                start=(0.0, 0.0, 0.0), end=(10.0, 0.0, 0.0),
                midpoint=(5.0, 0.0, 0.0), length=10.0,
            )]
        )
        result = score_sketch_match(body, sketch)
        assert result.matched_straights == 1
        assert result.score > 0

    def test_perpendicular_no_match(self) -> None:
        body = _make_body_profile(
            straights=[BodyStraight(
                axis=(1.0, 0.0, 0.0), origin=(0.0, 0.0, 0.0),
                radius=1.905, length=10.0, centroid=(5.0, 0.0, 0.0),
            )]
        )
        sketch = _make_sketch_profile(
            lines=[SketchLineData(
                direction=(0.0, 1.0, 0.0),
                start=(0.0, 0.0, 0.0), end=(0.0, 10.0, 0.0),
                midpoint=(0.0, 5.0, 0.0), length=10.0,
            )]
        )
        result = score_sketch_match(body, sketch)
        assert result.matched_straights == 0

    def test_bend_match_with_clr(self) -> None:
        body = _make_body_profile(
            bends=[BodyBend(
                axis=(0.0, 0.0, 1.0), origin=(5.0, 0.0, 0.0),
                major_radius=5.0, minor_radius=1.905,
            )]
        )
        sketch = _make_sketch_profile(
            arcs=[SketchArcData(
                center=(5.0, 0.0, 0.0), radius=5.0,
                normal=(0.0, 0.0, 1.0), sweep=math.pi / 2,
                start=(5.0, -5.0, 0.0), end=(10.0, 0.0, 0.0),
            )]
        )
        result = score_sketch_match(body, sketch)
        assert result.matched_bends == 1
        assert result.score > 0

    def test_unmatched_body_penalty(self) -> None:
        body = _make_body_profile(
            straights=[
                BodyStraight(
                    axis=(1.0, 0.0, 0.0), origin=(0.0, 0.0, 0.0),
                    radius=1.905, length=10.0, centroid=(5.0, 0.0, 0.0),
                ),
                BodyStraight(
                    axis=(0.0, 1.0, 0.0), origin=(0.0, 0.0, 0.0),
                    radius=1.905, length=10.0, centroid=(0.0, 5.0, 0.0),
                ),
            ]
        )
        sketch = _make_sketch_profile()  # empty sketch
        result = score_sketch_match(body, sketch)
        assert result.score < 0

    def test_extra_sketch_penalty(self) -> None:
        body = _make_body_profile()  # empty body
        sketch = _make_sketch_profile(
            lines=[
                SketchLineData(
                    direction=(1.0, 0.0, 0.0),
                    start=(0.0, 0.0, 0.0), end=(5.0, 0.0, 0.0),
                    midpoint=(2.5, 0.0, 0.0), length=5.0,
                ),
                SketchLineData(
                    direction=(0.0, 1.0, 0.0),
                    start=(50.0, 50.0, 0.0), end=(50.0, 55.0, 0.0),
                    midpoint=(50.0, 52.5, 0.0), length=5.0,
                ),
            ]
        )
        result = score_sketch_match(body, sketch)
        assert result.score < 0

    def test_connected_path_bonus(self) -> None:
        body = _make_body_profile(
            straights=[
                BodyStraight(
                    axis=(1.0, 0.0, 0.0), origin=(0.0, 0.0, 0.0),
                    radius=1.905, length=5.0, centroid=(2.5, 0.0, 0.0),
                ),
                BodyStraight(
                    axis=(0.0, 1.0, 0.0), origin=(6.0, 1.0, 0.0),
                    radius=1.905, length=7.0, centroid=(6.0, 4.5, 0.0),
                ),
            ]
        )
        sketch = _make_sketch_profile(
            lines=[
                SketchLineData(
                    direction=(1.0, 0.0, 0.0),
                    start=(0.0, 0.0, 0.0), end=(5.0, 0.0, 0.0),
                    midpoint=(2.5, 0.0, 0.0), length=5.0,
                ),
                SketchLineData(
                    direction=(0.0, 1.0, 0.0),
                    start=(6.0, 1.0, 0.0), end=(6.0, 8.0, 0.0),
                    midpoint=(6.0, 4.5, 0.0), length=7.0,
                ),
            ],
            arcs=[
                SketchArcData(
                    center=(5.0, 1.0, 0.0), radius=1.0,
                    normal=(0.0, 0.0, 1.0), sweep=math.pi / 2,
                    start=(5.0, 0.0, 0.0), end=(6.0, 1.0, 0.0),
                ),
            ],
        )
        result = score_sketch_match(body, sketch)
        # The connected chain should give a bonus
        assert any("connectivity" in d.lower() for d in result.details)
        assert result.score > 0

    def test_result_has_sketch_name(self) -> None:
        result = score_sketch_match(
            _make_body_profile(),
            _make_sketch_profile(name="TestSketch42"),
        )
        assert result.sketch_name == "TestSketch42"


# ── rank_matches ──


class TestRankMatches:
    def _make_result(self, name: str, score: int) -> MatchResult:
        return MatchResult(
            sketch_name=name, score=score, confidence="none",
            matched_straights=0, total_straights=0,
            matched_bends=0, total_bends=0,
            connected_line_indices=set(), connected_arc_indices=set(),
        )

    def test_empty_list(self) -> None:
        assert rank_matches([]) == []

    def test_sorted_by_score(self) -> None:
        results = [
            self._make_result("A", 10),
            self._make_result("B", 50),
            self._make_result("C", 30),
        ]
        ranked = rank_matches(results)
        assert [r.sketch_name for r in ranked] == ["B", "C", "A"]

    def test_high_confidence(self) -> None:
        results = [
            self._make_result("Best", 100),
            self._make_result("Distant", 20),
        ]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "high"

    def test_medium_confidence(self) -> None:
        results = [
            self._make_result("Best", 100),
            self._make_result("Close", 60),
        ]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "medium"

    def test_low_confidence(self) -> None:
        results = [
            self._make_result("Best", 100),
            self._make_result("VeryClose", 90),
        ]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "low"

    def test_none_confidence_for_negative(self) -> None:
        results = [self._make_result("Bad", -5)]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "none"

    def test_single_positive_is_high(self) -> None:
        results = [self._make_result("Only", 50)]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "high"

    def test_all_negative_none_confidence(self) -> None:
        results = [
            self._make_result("A", -10),
            self._make_result("B", -5),
        ]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "none"
        assert ranked[1].confidence == "none"

    def test_non_top_results_are_none(self) -> None:
        results = [
            self._make_result("Best", 100),
            self._make_result("Second", 20),
            self._make_result("Third", 10),
        ]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "high"
        assert ranked[1].confidence == "none"
        assert ranked[2].confidence == "none"

    def test_zero_score_is_none(self) -> None:
        results = [self._make_result("Zero", 0)]
        ranked = rank_matches(results)
        assert ranked[0].confidence == "none"
