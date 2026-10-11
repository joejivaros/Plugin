# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 <Author>
"""Placement rules and path building — pure Python, no display needed."""
from __future__ import annotations

import math

import pytest


def approx_list(values, expected):
    assert len(values) == len(expected), (values, expected)
    for v, e in zip(values, expected):
        assert v == pytest.approx(e, abs=1e-9)


# ---- count mode --------------------------------------------------------------

def test_count_from_ends_includes_both_ends(geometry):
    s = geometry.positions(10.0, geometry.MODE_COUNT, count=5,
                           origin=geometry.ORIGIN_ENDS)
    approx_list(s, [0, 2.5, 5, 7.5, 10])


def test_count_from_middle_stays_off_the_ends(geometry):
    s = geometry.positions(10.0, geometry.MODE_COUNT, count=4,
                           origin=geometry.ORIGIN_MIDDLE)
    approx_list(s, [2, 4, 6, 8])


def test_count_one_point_is_the_midpoint(geometry):
    for origin in (geometry.ORIGIN_ENDS, geometry.ORIGIN_MIDDLE):
        approx_list(geometry.positions(6.0, geometry.MODE_COUNT, count=1,
                                       origin=origin), [3.0])


def test_count_closed_loop_has_n_distinct_points(geometry):
    s = geometry.positions(8.0, geometry.MODE_COUNT, count=4, closed=True)
    approx_list(s, [0, 2, 4, 6])
    s = geometry.positions(8.0, geometry.MODE_COUNT, count=4, closed=True,
                           origin=geometry.ORIGIN_MIDDLE)
    approx_list(s, [1, 3, 5, 7])


# ---- distance mode -------------------------------------------------------------

def test_distance_from_ends_leaves_remainder_in_middle(geometry):
    s = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=3.0,
                           origin=geometry.ORIGIN_ENDS)
    approx_list(s, [0, 3, 7, 10])          # 4 m left in the middle


def test_distance_from_ends_meeting_exactly_has_one_middle_point(geometry):
    s = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=2.5,
                           origin=geometry.ORIGIN_ENDS)
    approx_list(s, [0, 2.5, 5, 7.5, 10])


def test_distance_from_middle_leaves_remainder_at_ends(geometry):
    s = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=3.0,
                           origin=geometry.ORIGIN_MIDDLE)
    approx_list(s, [2, 5, 8])               # 2 m left at each end


def test_distance_from_middle_with_odd_and_even_limit(geometry):
    odd = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=1.0,
                             origin=geometry.ORIGIN_MIDDLE, limit=3)
    approx_list(odd, [4, 5, 6])
    even = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=1.0,
                              origin=geometry.ORIGIN_MIDDLE, limit=2)
    approx_list(even, [4.5, 5.5])


def test_distance_from_middle_limit_drops_what_does_not_fit(geometry):
    s = geometry.positions(2.0, geometry.MODE_DISTANCE, spacing=1.0,
                           origin=geometry.ORIGIN_MIDDLE, limit=5)
    approx_list(s, [0, 1, 2])


def test_distance_from_ends_with_limit_alternates(geometry):
    s = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=1.0,
                           origin=geometry.ORIGIN_ENDS, limit=3)
    approx_list(s, [0, 1, 10])
    s = geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=1.0,
                           origin=geometry.ORIGIN_ENDS, limit=4)
    approx_list(s, [0, 1, 9, 10])


def test_distance_on_closed_loop_does_not_double_the_seam(geometry):
    s = geometry.positions(8.0, geometry.MODE_DISTANCE, spacing=2.0,
                           origin=geometry.ORIGIN_ENDS, closed=True)
    approx_list(s, [0, 2, 4, 6])


def test_spacing_longer_than_path_gives_the_ends(geometry):
    s = geometry.positions(1.0, geometry.MODE_DISTANCE, spacing=5.0,
                           origin=geometry.ORIGIN_ENDS)
    approx_list(s, [0, 1])


# ---- validation ------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf, "1", None, True])
def test_bad_spacing_is_rejected(geometry, bad):
    with pytest.raises(geometry.PlacementError):
        geometry.positions(10.0, geometry.MODE_DISTANCE, spacing=bad)


@pytest.mark.parametrize("bad", [0, -2, 1.5, 10001, True])
def test_bad_count_is_rejected(geometry, bad):
    with pytest.raises(geometry.PlacementError):
        geometry.positions(10.0, geometry.MODE_COUNT, count=bad)


def test_too_many_points_is_rejected(geometry):
    with pytest.raises(geometry.PlacementError):
        geometry.positions(1000.0, geometry.MODE_DISTANCE, spacing=0.001)


def test_zero_length_path_gives_nothing(geometry):
    assert geometry.positions(0.0, geometry.MODE_COUNT, count=3) == []


# ---- paths -------------------------------------------------------------------------

def seg(a, b, pa, pb):
    return (a, b, pa, pb)


def test_connected_edges_join_into_one_path(geometry):
    # An L: (0,0,0) → (4,0,0) → (4,3,0), given out of order and reversed.
    paths = geometry.build_paths([
        seg("b", "c", (4, 0, 0), (4, 3, 0)),
        seg("b", "a", (4, 0, 0), (0, 0, 0)),
    ])
    assert len(paths) == 1
    assert not paths[0].closed
    assert paths[0].length == pytest.approx(7.0)
    # 3.5 m along the L from either end: (3.5, 0, 0) or (4, 0.5, 0).
    mid = geometry.point_at(paths[0], 3.5)
    assert any(math.dist(mid, c) < 1e-9
               for c in [(3.5, 0.0, 0.0), (4.0, 0.5, 0.0)])


def test_closed_loop_is_detected(geometry):
    sq = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    segs = [seg(i, (i + 1) % 4, sq[i], sq[(i + 1) % 4]) for i in range(4)]
    paths = geometry.build_paths(segs)
    assert len(paths) == 1 and paths[0].closed
    assert paths[0].length == pytest.approx(4.0)


def test_branch_vertex_splits_paths(geometry):
    # A T: three edges meeting at "o".
    paths = geometry.build_paths([
        seg("o", "a", (0, 0, 0), (1, 0, 0)),
        seg("o", "b", (0, 0, 0), (-1, 0, 0)),
        seg("o", "c", (0, 0, 0), (0, 1, 0)),
    ])
    assert len(paths) == 3
    assert all(p.length == pytest.approx(1.0) for p in paths)


def test_degenerate_and_duplicate_segments_are_ignored(geometry):
    paths = geometry.build_paths([
        seg("a", "b", (0, 0, 0), (2, 0, 0)),
        seg("b", "a", (2, 0, 0), (0, 0, 0)),
        seg("c", "d", (5, 5, 5), (5, 5, 5)),
    ])
    assert len(paths) == 1 and paths[0].length == pytest.approx(2.0)


def test_point_at_follows_a_curve_like_polyline(geometry):
    # A quarter "circle" of 16 segments, radius 1.
    n = 16
    pts = [(math.cos(i * math.pi / 2 / n), math.sin(i * math.pi / 2 / n), 0.0)
           for i in range(n + 1)]
    segs = [seg(i, i + 1, pts[i], pts[i + 1]) for i in range(n)]
    path = geometry.build_paths(segs)[0]
    for s in (0.0, path.length / 3, path.length):
        p = geometry.point_at(path, s)
        assert math.hypot(p[0], p[1]) == pytest.approx(1.0, abs=2e-3)


def test_place_dedupes_shared_ends(geometry):
    # Two separate paths (a branch at "o" keeps them apart) sharing "o".
    paths = geometry.build_paths([
        seg("o", "a", (0, 0, 0), (2, 0, 0)),
        seg("o", "b", (0, 0, 0), (0, 2, 0)),
        seg("o", "c", (0, 0, 0), (0, 0, 2)),
    ])
    pts = geometry.place(paths, geometry.MODE_COUNT, count=2,
                         origin=geometry.ORIGIN_ENDS)
    assert len(pts) == 4                     # o once + three far ends
