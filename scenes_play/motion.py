# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""How the camera gets from one scene to the next.

Plain Python (``math`` only), so it is tested without Qt.

A move takes ``travel`` seconds. It speeds up for the first part of that
time, goes at a steady speed, and slows down for the last part; ``start``
and ``stop`` (Slow / Medium / Fast) say how long those two parts are
(:data:`model.RAMP_FRACTION`). The speed curve is a "trapezoid" with
rounded (half-cosine) corners, so the camera never jerks.

The camera itself is IngeTrazo's orbit camera — a target point, a distance
from it and two angles — and a scene stores exactly those, so a move
blends them: the target in a straight line, the distance geometrically
(zooming in from 100 m to 1 m feels even), the turn the short way round.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import RAMP_FRACTION

TAU = 2.0 * math.pi


def ramp_times(travel: float, start: str, stop: str) -> tuple[float, float]:
    """Seconds spent speeding up and slowing down in a move of ``travel``."""
    travel = max(0.0, float(travel))
    return (RAMP_FRACTION.get(start, RAMP_FRACTION["medium"]) * travel,
            RAMP_FRACTION.get(stop, RAMP_FRACTION["medium"]) * travel)


def progress(t: float, travel: float, t_up: float, t_down: float) -> float:
    """Share of the way covered (0 → 1) after ``t`` seconds of a move that
    lasts ``travel`` s, speeding up for ``t_up`` s and slowing for
    ``t_down`` s. A move of no length is already there."""
    if travel <= 0.0 or t >= travel:
        return 1.0
    if t <= 0.0:
        return 0.0
    t_up = min(max(t_up, 0.0), travel)
    t_down = min(max(t_down, 0.0), travel - t_up)
    # Area under the speed curve = 1; each rounded ramp covers half of what
    # full speed would in the same time.
    v_max = 1.0 / (travel - 0.5 * t_up - 0.5 * t_down)
    if t < t_up:
        return v_max * (0.5 * t - t_up / TAU * math.sin(math.pi * t / t_up))
    if t > travel - t_down:
        u = travel - t
        return 1.0 - v_max * (0.5 * u - t_down / TAU
                              * math.sin(math.pi * u / t_down))
    return v_max * (0.5 * t_up + (t - t_up))


@dataclass(frozen=True)
class Pose:
    """An orbit-camera position: what a move blends."""
    target: tuple[float, float, float]
    distance: float
    yaw: float
    pitch: float
    fov: float

    def is_finite(self) -> bool:
        values = (*self.target, self.distance, self.yaw, self.pitch, self.fov)
        return all(math.isfinite(v) for v in values)

    def close_to(self, other: "Pose", tol: float = 1e-4) -> bool:
        """Same place within ``tol`` (metres, radians, degrees)."""
        return (all(abs(a - b) <= tol * max(1.0, abs(b))
                    for a, b in zip(self.target, other.target))
                and abs(self.distance - other.distance)
                <= tol * max(1.0, other.distance)
                and abs(_short_turn(self.yaw, other.yaw)) <= tol
                and abs(self.pitch - other.pitch) <= tol
                and abs(self.fov - other.fov) <= tol)


def _short_turn(a: float, b: float) -> float:
    """The angle from ``a`` to ``b`` the short way round, in (-π, π]."""
    d = math.fmod(b - a, TAU)
    if d > math.pi:
        d -= TAU
    elif d <= -math.pi:
        d += TAU
    return d


def _lerp(a: float, b: float, s: float) -> float:
    return a + (b - a) * s


def interpolate(a: Pose, b: Pose, s: float) -> Pose:
    """The pose a share ``s`` (0 → 1) of the way from ``a`` to ``b``."""
    if s <= 0.0:
        return a
    if s >= 1.0:
        return b
    target = tuple(_lerp(x, y, s) for x, y in zip(a.target, b.target))
    if a.distance > 0.0 and b.distance > 0.0:
        distance = a.distance * (b.distance / a.distance) ** s
    else:
        distance = _lerp(a.distance, b.distance, s)
    return Pose(target, distance, a.yaw + _short_turn(a.yaw, b.yaw) * s,
                _lerp(a.pitch, b.pitch, s), _lerp(a.fov, b.fov, s))


@dataclass(frozen=True)
class Move:
    """One move: from ``a`` to ``b`` in ``travel`` seconds."""
    a: Pose
    b: Pose
    travel: float
    t_up: float
    t_down: float

    @classmethod
    def build(cls, a: Pose, b: Pose, travel: float, start: str,
              stop: str) -> "Move":
        t_up, t_down = ramp_times(travel, start, stop)
        return cls(a, b, max(0.0, float(travel)), t_up, t_down)

    def pose_at(self, t: float) -> Pose:
        return interpolate(self.a, self.b,
                           progress(t, self.travel, self.t_up, self.t_down))
