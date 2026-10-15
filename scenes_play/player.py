# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Playing an automation: which scene, which phase, how far into it.

Plain Python and driven by :meth:`Sequencer.advance` with the seconds
since the last frame, so the tests play a whole automation in a few
calls, and the MP4 export plays it frame by frame. The camera is reached
through a small adapter (the real one is in :mod:`host`):

- ``pose()`` → the camera's :class:`motion.Pose` now;
- ``set_pose(pose)`` → put the camera there (during a move);
- ``arrive(step)`` → show the scene of ``step`` exactly, as a click on it
  in the Scenes panel would (layers, style, sections…); returns False when
  the scene is gone, which stops the playback.

An optional ``audio`` adapter hears ``start(step, offset)`` when a scene's
sound should begin (``offset`` seconds into it) and ``stop()`` when it
should end: on leaving the scene, on pause and on stop.

Each step is: move from wherever the camera is to the step's scene in
``travel`` seconds, then stay ``wait`` seconds (already stretched to the
sound's length by whoever built the step). The first step of the first
loop starts from the camera as it was when Play was pressed; every next
loop starts from the last scene. The sound starts on arrival.
"""
from __future__ import annotations

from dataclasses import dataclass

from .motion import Move, Pose

IDLE, TRAVEL, WAIT, DONE = "idle", "travel", "wait", "done"


@dataclass(frozen=True)
class Step:
    """One played entry with its scene resolved."""
    view: object            # the host's scene object (a SavedView)
    pose: Pose              # where that scene puts the camera
    start: str
    stop: str
    travel: float
    wait: float             # the stay, sound included
    audio: str | None = None


class Sequencer:
    """The playback state machine."""

    def __init__(self, steps, loops: int, camera, on_change=None,
                 audio=None) -> None:
        self.steps = list(steps)
        self.loops = max(0, int(loops))       # 0 = continuously
        self.camera = camera
        self.on_change = on_change
        self.audio = audio
        self.phase = IDLE
        self.paused = False
        self.loop = 0                         # 1-based once started
        self.index = 0                        # 0-based step
        self.elapsed = 0.0                    # seconds into the phase
        self.time = 0.0                       # seconds played in all
        self._move: Move | None = None
        self._wait_left = 0.0                 # of the stay, at its start

    # ---- Where we are ------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.phase in (TRAVEL, WAIT)

    @property
    def step(self) -> Step | None:
        if 0 <= self.index < len(self.steps):
            return self.steps[self.index]
        return None

    @property
    def stay_position(self) -> float:
        """Seconds of the current stay already done (the sound's offset)."""
        step = self.step
        if step is None:
            return 0.0
        done = step.wait - self._wait_left
        return done + (self.elapsed if self.phase == WAIT else 0.0)

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def _sound(self, offset: float | None) -> None:
        """Start the step's sound at ``offset`` s, or stop (None)."""
        if self.audio is None:
            return
        step = self.step
        if offset is None or step is None or not step.audio:
            self.audio.stop()
        else:
            self.audio.start(step, offset)

    # ---- Controls ----------------------------------------------------------
    def start(self) -> None:
        """From the first scene, first loop."""
        self.paused = False
        self.time = 0.0
        if not self.steps:
            self.phase = DONE
            self._changed()
            return
        self.loop = 1
        self.index = 0
        self._begin_travel(self.steps[0].travel)
        self._changed()

    def pause(self) -> None:
        if self.running and not self.paused:
            self.paused = True
            self._sound(None)
            self._changed()

    def resume(self) -> None:
        """Go on from where the camera is now — the user may have looked
        around during the pause. A move carries on in the time it had
        left; a pause during a stay first goes back to the scene (in the
        step's travel time), then stays for what was left of the wait, and
        the sound goes on from where it was."""
        if not self.paused:
            return
        self.paused = False
        step = self.step
        if step is None:
            self.stop()
            return
        here = self.camera.pose()
        if self.phase == TRAVEL:
            left = max(0.0, self._move.travel - self.elapsed)
            self._move = Move.build(here, step.pose, left, step.start,
                                    step.stop)
            self.elapsed = 0.0
        elif self.phase == WAIT and not here.close_to(step.pose):
            self._wait_left = max(0.0, self._wait_left - self.elapsed)
            self._move = Move.build(here, step.pose, step.travel,
                                    step.start, step.stop)
            self.phase = TRAVEL
            self.elapsed = 0.0
        elif self.phase == WAIT:
            self._sound(self.stay_position)
        self._changed()

    def stop(self) -> None:
        if self.phase != DONE:
            self._sound(None)
            self.phase = DONE
            self.paused = False
            self._changed()

    # ---- Time --------------------------------------------------------------
    def advance(self, dt: float) -> None:
        """Let ``dt`` seconds go by (one frame, or many at once)."""
        if not self.running or self.paused:
            return
        left = max(0.0, float(dt))
        # Bounded: an automation whose every time is 0 would otherwise loop
        # forever inside one frame.
        for _ in range(2 * len(self.steps) + 2):
            if self.phase == TRAVEL:
                need = self._move.travel - self.elapsed
                if left < need:
                    self.elapsed += left
                    self.time += left
                    self.camera.set_pose(self._move.pose_at(self.elapsed))
                    return
                left -= need
                self.time += need
                if not self._arrive():
                    return
            elif self.phase == WAIT:
                need = self._wait_left - self.elapsed
                if left < need:
                    self.elapsed += left
                    self.time += left
                    return
                left -= need
                self.time += need
                if not self._next():
                    return
            else:
                return

    # ---- Phases ------------------------------------------------------------
    def _begin_travel(self, travel: float) -> None:
        step = self.steps[self.index]
        self._move = Move.build(self.camera.pose(), step.pose, travel,
                                step.start, step.stop)
        self._wait_left = step.wait
        self.phase = TRAVEL
        self.elapsed = 0.0

    def _arrive(self) -> bool:
        if not self.camera.arrive(self.steps[self.index]):
            self.stop()
            return False
        self.phase = WAIT
        self.elapsed = 0.0
        self._sound(self.stay_position)
        self._changed()
        return True

    def _next(self) -> bool:
        self._sound(None)
        if self.index + 1 < len(self.steps):
            self.index += 1
        elif self.loops == 0 or self.loop < self.loops:
            self.loop += 1
            self.index = 0
        else:
            self.stop()
            return False
        self._begin_travel(self.steps[self.index].travel)
        self._changed()
        return True


class NullCamera:
    """A camera that is only counted on for time: for working out when
    each sound starts before an export."""

    def __init__(self, pose: Pose) -> None:
        self._pose = pose

    def pose(self) -> Pose:
        return self._pose

    def set_pose(self, pose: Pose) -> None:
        self._pose = pose

    def arrive(self, step: Step) -> bool:
        self._pose = step.pose
        return True


class SoundLog:
    """An audio adapter that writes down when each sound starts."""

    def __init__(self) -> None:
        self.seq: Sequencer | None = None
        self.events: list[tuple[float, str, float]] = []   # time, file, offset

    def start(self, step: Step, offset: float) -> None:
        self.events.append((self.seq.time, step.audio, offset))

    def stop(self) -> None:
        pass


def timeline(steps, loops: int, start: Pose):
    """``(duration, sounds)`` of playing ``steps`` ``loops`` times (0 is
    treated as 1): the length in seconds and, for each sound, ``(time,
    file, offset)``."""
    log = SoundLog()
    seq = Sequencer(steps, loops or 1, NullCamera(start), audio=log)
    log.seq = seq
    seq.start()
    for _ in range(10 * len(steps) * max(1, loops or 1) + 10):
        if not seq.running:
            break
        seq.advance(1e9)
    return seq.time, log.events
