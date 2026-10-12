# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Pure geometry for Divide Points: no Qt, no IngeTrazo imports.

Two jobs:

* :func:`build_paths` joins selected edges into paths — chains of points,
  open or closed — splitting at vertices where more than two selected
  edges meet;
* :func:`positions` decides WHERE along a path of a given length the points
  go (arc-length parameters), for every spacing mode and origin;
  :func:`point_at` turns a parameter back into a 3D point.

All lengths are in metres (IngeTrazo's internal unit).
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

#: Spacing modes.
MODE_COUNT = "count"
MODE_DISTANCE = "distance"
#: Where the placement starts.
ORIGIN_ENDS = "ends"
ORIGIN_MIDDLE = "middle"

#: Two parameters (or points) closer than this are the same one, in metres.
EPS = 1e-7
#: The smallest spacing accepted, in metres (a tenth of a millimetre).
MIN_SPACING = 1e-4
#: Hard cap on the points one action may create, so a typo cannot hang the app.
MAX_POINTS = 10000


class PlacementError(ValueError):
    """Invalid placement settings; ``str(exc)`` is an English UI message
    (translated by the caller), ``kwargs`` its format arguments."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(message)
        self.message = message
        self.kwargs = kwargs


Point = tuple[float, float, float]


@dataclass
class Path:
    """A chain of points; ``closed`` paths end where they start (the last
    point is NOT repeated)."""

    points: list[Point]
    closed: bool = False
    _cum: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        pts = self.points + ([self.points[0]] if self.closed else [])
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        self._cum = cum

    @property
    def length(self) -> float:
        return self._cum[-1]


def _chain_from(start, first_edge, adj, used, edges):
    """Walk from vertex ``start`` along ``first_edge`` until a vertex whose
    degree is not 2 (or back to ``start``). Returns the list of vertex keys."""
    keys = [start]
    cur, e = start, first_edge
    while True:
        used.add(e)
        a, b = edges[e]
        nxt = b if a == cur else a
        keys.append(nxt)
        if nxt == start or len(adj[nxt]) != 2:
            return keys
        e = next((x for x in adj[nxt] if x not in used), None)
        if e is None:
            return keys
        cur = nxt


def build_paths(segments) -> list[Path]:
    """Join segments into paths.

    ``segments`` is an iterable of ``(key_a, key_b, point_a, point_b)``:
    the keys say which segments share a vertex (any hashable — vertex
    identity), the points are ``(x, y, z)``. Connected segments become one
    path; a vertex where more than two segments meet ends the paths there.
    A loop with no such vertex is a closed path. Zero-length segments and
    duplicates are ignored.
    """
    edges: list[tuple] = []
    pos: dict = {}
    seen = set()
    for ka, kb, pa, pb in segments:
        if ka == kb or math.dist(pa, pb) <= EPS:
            continue
        k = frozenset((ka, kb))
        if k in seen:
            continue
        seen.add(k)
        pos[ka] = tuple(float(c) for c in pa)
        pos[kb] = tuple(float(c) for c in pb)
        edges.append((ka, kb))
    adj: dict = {}
    for i, (a, b) in enumerate(edges):
        adj.setdefault(a, []).append(i)
        adj.setdefault(b, []).append(i)

    used: set[int] = set()
    paths: list[Path] = []
    # Open chains first: they start at ends and branch vertices.
    for v in adj:
        if len(adj[v]) == 2:
            continue
        for e in adj[v]:
            if e not in used:
                keys = _chain_from(v, e, adj, used, edges)
                closed = len(keys) > 2 and keys[0] == keys[-1]
                if closed:
                    keys = keys[:-1]
                paths.append(Path([pos[k] for k in keys], closed))
    # What is left are loops where every vertex has degree 2.
    for e in range(len(edges)):
        if e in used:
            continue
        start = edges[e][0]
        keys = _chain_from(start, e, adj, used, edges)
        if keys[0] == keys[-1]:
            keys = keys[:-1]
        paths.append(Path([pos[k] for k in keys], len(keys) > 2))
    return paths


def point_at(path: Path, s: float) -> Point:
    """The point at arc length ``s`` along ``path`` (clamped)."""
    pts = path.points + ([path.points[0]] if path.closed else [])
    cum = path._cum
    if s <= 0.0:
        return pts[0]
    if s >= cum[-1]:
        return pts[-1]
    i = bisect.bisect_right(cum, s) - 1
    i = min(max(i, 0), len(pts) - 2)
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg <= 0.0 else (s - cum[i]) / seg
    a, b = pts[i], pts[i + 1]
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def _check_count(n) -> int:
    if not isinstance(n, int) or isinstance(n, bool):
        raise PlacementError("The number of points must be a whole number.")
    if n < 1 or n > MAX_POINTS:
        raise PlacementError("The number of points must be between 1 and {max}.",
                             max=MAX_POINTS)
    return n


def _check_spacing(d) -> float:
    if isinstance(d, bool) or not isinstance(d, (int, float)) \
            or not math.isfinite(d):
        raise PlacementError("The distance between points must be a number.")
    if d < MIN_SPACING:
        raise PlacementError("The distance between points is too small.")
    return float(d)


def _dedupe(values, length: float, closed: bool) -> list[float]:
    """Sorted, inside ``[0, length]``, without near-duplicates; on a closed
    path ``length`` is the same place as 0."""
    out: list[float] = []
    for v in sorted(values):
        if v < -EPS or v > length + EPS:
            continue
        v = min(max(v, 0.0), length)
        if out and v - out[-1] <= EPS:
            continue
        out.append(v)
    if closed and len(out) > 1 and length - out[-1] <= EPS and out[0] <= EPS:
        out.pop()
    return out


def _too_many(n: float) -> None:
    if n > MAX_POINTS:
        raise PlacementError("That would place more than {max} points — use a "
                             "larger distance.", max=MAX_POINTS)


def positions(length: float, mode: str, *, count: int | None = None,
              spacing: float | None = None, origin: str = ORIGIN_ENDS,
              limit: int | None = None, closed: bool = False) -> list[float]:
    """Arc-length parameters (sorted, metres) of the points on a path.

    * ``mode == MODE_COUNT``: ``count`` points, equal gaps.
      ``ORIGIN_ENDS`` puts the first and last point ON the ends
      (gap ``L/(N-1)``); ``ORIGIN_MIDDLE`` keeps them off the ends,
      centred (gap ``L/(N+1)``). A closed path gets ``N`` equal gaps
      ``L/N``, starting at its seam (ends) or half a gap after it (middle).
    * ``mode == MODE_DISTANCE``: a point every ``spacing``.
      ``ORIGIN_ENDS`` walks in from both ends and leaves the remainder in
      the middle; ``ORIGIN_MIDDLE`` walks out from the midpoint and leaves
      the remainder at both ends. ``limit`` (optional) caps the number of
      points: from the ends they alternate start/end; from the middle they
      are centred on the midpoint (odd: one ON it, even: it lies between
      two). A closed path is opened at its seam.
    """
    if not math.isfinite(length) or length <= EPS:
        return []
    L = float(length)
    if mode == MODE_COUNT:
        n = _check_count(count)
        if closed:
            step = L / n
            shift = step / 2.0 if origin == ORIGIN_MIDDLE else 0.0
            return _dedupe([shift + i * step for i in range(n)], L, True)
        if origin == ORIGIN_MIDDLE:
            return _dedupe([L * (i + 1) / (n + 1) for i in range(n)], L, False)
        if n == 1:
            return [L / 2.0]
        return _dedupe([L * i / (n - 1) for i in range(n)], L, False)

    if mode != MODE_DISTANCE:
        raise PlacementError("Unknown spacing mode.")
    d = _check_spacing(spacing)
    if limit is not None:
        limit = _check_count(limit)
    half = L / 2.0
    vals: list[float] = []
    if origin == ORIGIN_MIDDLE:
        if limit is None:
            k = int(math.floor(half / d + EPS))
            _too_many(2 * k + 1)
            vals = [half + i * d for i in range(-k, k + 1)]
        else:
            vals = [half + (i - (limit - 1) / 2.0) * d for i in range(limit)]
    else:
        k = int(math.floor(half / d + EPS))       # steps that stay in a half
        _too_many(2 * (k + 1))
        left = [i * d for i in range(k + 1)]
        right = [L - i * d for i in range(k + 1)]
        if limit is None:
            vals = left + right
        else:
            for i in range(k + 1):
                vals.append(left[i])
                vals.append(right[i])
            vals = _first_distinct(vals, limit, L, closed)
    return _dedupe(vals, L, closed)


def _first_distinct(vals, limit: int, length: float, closed: bool) -> list[float]:
    """The first ``limit`` values of ``vals`` (in order) that are not
    duplicates of an earlier one (the two halves can meet at the middle; a
    closed path's two ends are one place)."""
    out: list[float] = []
    for v in vals:
        w = 0.0 if closed and abs(v - length) <= EPS else v
        if any(abs(w - o) <= EPS for o in out):
            continue
        out.append(w)
        if len(out) == limit:
            break
    return out


def place(paths, mode: str, **kwargs) -> list[Point]:
    """All points for ``paths``, without duplicates (two paths sharing an
    end put one point there)."""
    out: list[Point] = []
    keys = set()
    for p in paths:
        for s in positions(p.length, mode, closed=p.closed, **kwargs):
            q = point_at(p, s)
            k = point_key(q)
            if k in keys:
                continue
            keys.add(k)
            out.append(q)
            if len(out) > MAX_POINTS:
                _too_many(len(out))
    return out


def point_key(p, digits: int = 6) -> tuple:
    """A hashable key for a point, rounded to ``digits`` (a micrometre)."""
    return (round(float(p[0]), digits), round(float(p[1]), digits),
            round(float(p[2]), digits))


def gaps(params: list[float]) -> list[float]:
    """The distances between consecutive parameters."""
    return [b - a for a, b in zip(params, params[1:])]
