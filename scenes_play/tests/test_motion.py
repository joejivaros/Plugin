# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The move: speed curve and pose blending."""
from __future__ import annotations

import math

import pytest


@pytest.mark.parametrize("start", ["slow", "medium", "fast"])
@pytest.mark.parametrize("stop", ["slow", "medium", "fast"])
def test_progress_runs_from_0_to_1_smoothly(motion, start, stop):
    T = 4.0
    up, down = motion.ramp_times(T, start, stop)
    samples = [motion.progress(T * i / 400, T, up, down) for i in range(401)]
    assert samples[0] == 0.0 and samples[-1] == pytest.approx(1.0)
    steps = [b - a for a, b in zip(samples, samples[1:])]
    assert all(s >= -1e-12 for s in steps)            # never goes back
    # No jumps: the speed changes gradually between samples.
    assert max(abs(b - a) for a, b in zip(steps, steps[1:])) < 1e-3


def test_ramps_follow_the_fractions(motion, model):
    up, down = motion.ramp_times(10.0, "slow", "fast")
    assert up == pytest.approx(10.0 * model.RAMP_FRACTION["slow"])
    assert down == pytest.approx(10.0 * model.RAMP_FRACTION["fast"])


def test_slow_start_covers_less_ground_early(motion):
    T = 5.0
    slow = motion.progress(1.0, T, *motion.ramp_times(T, "slow", "medium"))
    fast = motion.progress(1.0, T, *motion.ramp_times(T, "fast", "medium"))
    assert slow < fast


def test_speed_is_zero_at_both_ends(motion):
    T = 3.0
    up, down = motion.ramp_times(T, "medium", "medium")
    eps = 1e-4
    assert motion.progress(eps, T, up, down) / eps < 1e-2
    assert (1.0 - motion.progress(T - eps, T, up, down)) / eps < 1e-2


def test_zero_travel_is_a_cut(motion):
    assert motion.progress(0.0, 0.0, 0.0, 0.0) == 1.0


def _pose(motion, x=0.0, d=10.0, yaw=0.0, pitch=0.3, fov=45.0):
    return motion.Pose((x, 0.0, 0.0), d, yaw, pitch, fov)


def test_interpolate_ends_and_middle(motion):
    a = _pose(motion, x=0.0, d=1.0, pitch=0.0, fov=40.0)
    b = _pose(motion, x=10.0, d=100.0, pitch=1.0, fov=60.0)
    assert motion.interpolate(a, b, 0.0) == a
    assert motion.interpolate(a, b, 1.0) == b
    mid = motion.interpolate(a, b, 0.5)
    assert mid.target[0] == pytest.approx(5.0)
    assert mid.distance == pytest.approx(10.0)        # geometric
    assert mid.pitch == pytest.approx(0.5)
    assert mid.fov == pytest.approx(50.0)


def test_yaw_turns_the_short_way(motion):
    a = _pose(motion, yaw=math.radians(170))
    b = _pose(motion, yaw=math.radians(-170))
    mid = motion.interpolate(a, b, 0.5)
    assert math.cos(mid.yaw) == pytest.approx(-1.0)   # through 180°, not 0°


def test_close_to(motion):
    a = _pose(motion, yaw=math.pi)
    b = _pose(motion, yaw=-math.pi)
    assert a.close_to(b)
    assert not a.close_to(_pose(motion, x=0.1, yaw=math.pi))


def test_move_pose_at(motion):
    a, b = _pose(motion, x=0.0), _pose(motion, x=8.0)
    move = motion.Move.build(a, b, 2.0, "medium", "medium")
    assert move.pose_at(0.0) == a
    assert move.pose_at(2.0) == b
    assert move.pose_at(1.0).target[0] == pytest.approx(4.0)  # symmetric
