# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The sequencer, played with a fake camera and a fake clock."""
from __future__ import annotations

import pytest


class FakeCamera:
    def __init__(self, motion, x=-10.0):
        self.motion = motion
        self.now = motion.Pose((x, 0.0, 0.0), 10.0, 0.0, 0.3, 45.0)
        self.arrived = []
        self.gone = set()

    def pose(self):
        return self.now

    def set_pose(self, pose):
        self.now = pose

    def arrive(self, step):
        if step.view in self.gone:
            return False
        self.now = step.pose
        self.arrived.append(step.view)
        return True


def _steps(player, motion, travel=2.0, wait=3.0, names="ABC"):
    return [player.Step(n, motion.Pose((float(i), 0.0, 0.0), 10.0, 0.0, 0.3,
                                       45.0), "medium", "medium", travel, wait)
            for i, n in enumerate(names)]


def _run(seq, seconds, dt=0.05):
    for _ in range(int(round(seconds / dt))):
        seq.advance(dt)


def test_plays_every_scene_in_order_then_stops(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    assert seq.phase == player.TRAVEL
    _run(seq, 14.9)                       # 3 × (2 + 3) = 15 s
    assert cam.arrived == ["A", "B", "C"]
    assert seq.running
    _run(seq, 0.2)
    assert seq.phase == player.DONE


def test_first_move_starts_from_the_live_camera(player, motion):
    cam = FakeCamera(motion, x=-10.0)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    seq.advance(1.0)                      # half of a symmetric 2 s move
    assert cam.now.target[0] == pytest.approx(-5.0)


def test_loops(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion, names="AB"), 3, cam)
    seq.start()
    _run(seq, 31.0)
    assert cam.arrived == ["A", "B"] * 3
    assert seq.phase == player.DONE


def test_zero_loops_never_ends(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion, names="AB"), 0, cam)
    seq.start()
    _run(seq, 100.0, dt=0.5)
    assert seq.running and seq.loop == 11
    seq.stop()
    assert seq.phase == player.DONE


def test_all_zero_times_do_not_hang(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion, travel=0.0, wait=0.0), 0,
                           cam)
    seq.start()
    seq.advance(0.016)                    # returns: bounded per frame
    assert seq.running
    assert len(cam.arrived) >= 3


def test_one_big_frame_crosses_several_steps(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    seq.advance(11.0)                     # A and B done, 1 s into C's move
    assert cam.arrived == ["A", "B"]
    assert seq.index == 2 and seq.phase == player.TRAVEL


def test_pause_holds_time(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    seq.advance(1.0)
    seq.pause()
    before = cam.now
    seq.advance(50.0)
    assert cam.now == before and seq.paused


def test_resume_in_a_move_goes_on_from_the_camera(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    seq.advance(1.0)
    seq.pause()
    cam.now = motion.Pose((40.0, 0.0, 0.0), 10.0, 0.0, 0.3, 45.0)  # looked
    seq.resume()
    seq.advance(0.999)                    # the second it had left
    assert cam.arrived == []
    seq.advance(0.002)
    assert cam.arrived == ["A"]


def test_resume_in_a_stay_goes_back_then_waits_what_was_left(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    seq.advance(3.0)                      # arrived at A, 1 s into its stay
    seq.pause()
    cam.now = motion.Pose((40.0, 0.0, 0.0), 10.0, 0.0, 0.3, 45.0)
    seq.resume()
    assert seq.phase == player.TRAVEL
    seq.advance(2.0)                      # the way back (A's travel)
    assert cam.arrived == ["A", "A"]
    seq.advance(1.9)                      # 2 s of stay were left
    assert seq.index == 0
    seq.advance(0.2)
    assert seq.index == 1


def test_resume_in_a_stay_without_moving_just_goes_on(player, motion):
    cam = FakeCamera(motion)
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    seq.advance(3.0)
    seq.pause()
    seq.resume()
    assert seq.phase == player.WAIT
    seq.advance(2.1)
    assert seq.index == 1


def test_a_scene_gone_stops_the_playback(player, motion):
    cam = FakeCamera(motion)
    cam.gone.add("B")
    seq = player.Sequencer(_steps(player, motion), 1, cam)
    seq.start()
    _run(seq, 10.0)
    assert cam.arrived == ["A"]
    assert seq.phase == player.DONE


def test_nothing_to_play_is_done_at_once(player, motion):
    changes = []
    seq = player.Sequencer([], 1, FakeCamera(motion),
                           lambda: changes.append(1))
    seq.start()
    assert seq.phase == player.DONE and changes


# ---- Time and sounds ------------------------------------------------------------
class FakeSound:
    def __init__(self):
        self.seq = None
        self.calls = []

    def start(self, step, offset):
        self.calls.append(("start", step.view, round(offset, 6),
                           round(self.seq.time, 6)))

    def stop(self):
        self.calls.append(("stop",))


def _with_sound(player, motion, cam, loops=1):
    steps = _steps(player, motion)
    steps[1] = player.Step(steps[1].view, steps[1].pose, "medium", "medium",
                           2.0, 3.0, audio="C:\\b.mp3")
    sound = FakeSound()
    seq = player.Sequencer(steps, loops, cam, audio=sound)
    sound.seq = seq
    return seq, sound


def test_time_is_counted_exactly(player, motion):
    seq = player.Sequencer(_steps(player, motion), 2, FakeCamera(motion))
    seq.start()
    seq.advance(7.3)
    assert seq.time == pytest.approx(7.3)
    _run(seq, 40.0, dt=0.7)
    assert seq.phase == player.DONE
    assert seq.time == pytest.approx(30.0)     # 2 × 3 × (2 + 3)


def test_sound_starts_on_arrival_and_stops_on_leaving(player, motion):
    seq, sound = _with_sound(player, motion, FakeCamera(motion))
    seq.start()
    seq.advance(7.5)                          # A: 0-5, B arrives at 7
    starts = [c for c in sound.calls if c[0] == "start"]
    assert starts == [("start", "B", 0.0, 7.0)]
    seq.advance(3.0)                          # B left at 10
    assert sound.calls[-1] == ("stop",)


def test_pause_stops_the_sound_and_resume_goes_on(player, motion):
    seq, sound = _with_sound(player, motion, FakeCamera(motion))
    seq.start()
    seq.advance(8.0)                          # 1 s into B's stay
    seq.pause()
    assert sound.calls[-1] == ("stop",)
    seq.resume()                              # camera did not move
    assert sound.calls[-1][:3] == ("start", "B", 1.0)


def test_resume_after_looking_around_plays_on_from_the_rest(player, motion):
    cam = FakeCamera(motion)
    seq, sound = _with_sound(player, motion, cam)
    seq.start()
    seq.advance(8.0)
    seq.pause()
    cam.now = motion.Pose((40.0, 0.0, 0.0), 10.0, 0.0, 0.3, 45.0)
    seq.resume()                              # goes back first: 2 s
    seq.advance(2.0)
    assert sound.calls[-1][:3] == ("start", "B", 1.0)


def test_timeline_gives_the_length_and_when_sounds_start(player, motion):
    steps = _steps(player, motion)
    steps[2] = player.Step("C", steps[2].pose, "fast", "slow", 2.0, 3.0,
                           audio="C:\\c.mp3")
    start = motion.Pose((-10.0, 0.0, 0.0), 10.0, 0.0, 0.3, 45.0)
    duration, sounds = player.timeline(steps, 2, start)
    assert duration == pytest.approx(30.0)
    assert [(round(t, 6), f, o) for t, f, o in sounds] == \
        [(12.0, "C:\\c.mp3", 0.0), (27.0, "C:\\c.mp3", 0.0)]
    assert player.timeline(steps, 0, start)[0] == pytest.approx(15.0)
