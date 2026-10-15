# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The automation itself: an ordered list of scene entries and a loop count.

Plain Python, no Qt and no IngeTrazo: the dialog edits it, the player plays
it, and it is saved as JSON (in a file the user picks, or in the model's
document data). Scenes are referred to by NAME — IngeTrazo keeps scene
names unique — so an automation file can be loaded onto another model
that has scenes with the same names.

An entry may carry a sound: a file path and its length, measured with
ffprobe when it was attached. The scene then stays at least as long as the
sound plays.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath, PureWindowsPath

#: How fast a move gets going (``start``) or comes to rest (``stop``).
EASES = ("slow", "medium", "fast")

#: Share of the travel time spent speeding up (start) or slowing down
#: (stop). Slow + Slow leaves 10 % of the move at full speed.
RAMP_FRACTION = {"slow": 0.45, "medium": 0.30, "fast": 0.12}

TRAVEL_MAX = 600.0          # seconds
WAIT_MAX = 3600.0           # seconds
LOOPS_MAX = 999             # 0 = continuously
MAX_ENTRIES = 500
MAX_NAME_LENGTH = 200

DEFAULT_TRAVEL = 3.0
DEFAULT_WAIT = 5.0

#: Sound files that can be attached to a scene.
AUDIO_SUFFIXES = (".wav", ".mp3", ".ogg", ".oga", ".flac", ".m4a", ".aac",
                  ".opus", ".wma")
MAX_PATH_LENGTH = 1024

#: What a saved automation says it is, and the newest layout this code reads.
#: Version 2 added a sound per entry; version 1 files still load.
FORMAT = "scenes_play.automation"
FORMAT_VERSION = 2


class AutomationError(ValueError):
    """Saved data that cannot be used. ``message`` is the English source of
    the text to show (translated by the caller), ``fields`` its values."""

    def __init__(self, message: str, **fields) -> None:
        super().__init__(message.format(**fields) if fields else message)
        self.message = message
        self.fields = fields


@dataclass
class Entry:
    """One scene of the sequence and how the camera reaches it."""
    scene: str
    enabled: bool = True
    start: str = "medium"
    stop: str = "medium"
    travel: float = DEFAULT_TRAVEL
    wait: float = DEFAULT_WAIT
    audio: str | None = None        # absolute path of a sound file
    audio_length: float = 0.0       # its length in seconds

    def copy(self) -> "Entry":
        return replace(self)

    def stay(self, sound: bool = True) -> float:
        """Seconds the scene stays: Wait, or the sound's length when that
        is longer. ``sound`` False: the sound cannot be played (its file is
        missing), so it does not count."""
        if sound and self.audio:
            return max(self.wait, self.audio_length)
        return self.wait

    def to_dict(self) -> dict:
        out = {"scene": self.scene, "enabled": self.enabled,
               "start": self.start, "stop": self.stop,
               "travel": self.travel, "wait": self.wait}
        if self.audio:
            out["audio"] = self.audio
            out["audio_length"] = self.audio_length
        return out

    @classmethod
    def from_dict(cls, raw, index: int) -> "Entry":
        if not isinstance(raw, dict):
            raise AutomationError("Entry {n} is not valid.", n=index + 1)
        scene = raw.get("scene")
        if (not isinstance(scene, str) or not scene.strip()
                or len(scene) > MAX_NAME_LENGTH):
            raise AutomationError("Entry {n} has no valid scene name.",
                                  n=index + 1)
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise AutomationError("Entry {n} is not valid.", n=index + 1)
        eases = []
        for key in ("start", "stop"):
            value = raw.get(key, "medium")
            if value not in EASES:
                raise AutomationError("Entry {n} has an unknown speed.",
                                      n=index + 1)
            eases.append(value)
        times = []
        for key, top, default in (("travel", TRAVEL_MAX, DEFAULT_TRAVEL),
                                  ("wait", WAIT_MAX, DEFAULT_WAIT)):
            times.append(_seconds(raw.get(key, default), top, index))
        audio, length = raw.get("audio"), 0.0
        if audio is not None:
            if safe_audio_path(audio) is None:
                raise AutomationError("Entry {n} has a sound file that cannot "
                                      "be used.", n=index + 1)
            length = _seconds(raw.get("audio_length", 0.0), WAIT_MAX, index)
        return cls(scene, enabled, eases[0], eases[1], times[0], times[1],
                   audio, length)


def safe_audio_path(text) -> str | None:
    """``text`` when it is a local, absolute path to a sound file, else
    None. Network paths (two leading slashes or backslashes), URLs and
    relative paths are refused: an automation file from someone else must
    not make IngeTrazo contact a server or open an unexpected file."""
    if (not isinstance(text, str) or not text or len(text) > MAX_PATH_LENGTH
            or "\0" in text or "://" in text):
        return None
    if text[:2] in ("\\\\", "//", "\\/", "/\\") or text.startswith("-"):
        return None
    win, posix = PureWindowsPath(text), PurePosixPath(text)
    if not (win.drive and win.root) and not posix.is_absolute():
        return None
    if win.suffix.lower() not in AUDIO_SUFFIXES:
        return None
    return text


def _seconds(value, top: float, index: int) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0.0 <= value <= top):
        raise AutomationError("Entry {n} has a time out of range.",
                              n=index + 1)
    return float(value)


@dataclass
class Automation:
    """The sequence of scenes and how many times it is played."""
    entries: list[Entry] = field(default_factory=list)
    loops: int = 1

    def copy(self) -> "Automation":
        return Automation([e.copy() for e in self.entries], self.loops)

    # ---- What will be played ---------------------------------------------
    def played(self, available) -> list[Entry]:
        """The checked entries whose scene exists in the model, in order."""
        names = set(available)
        return [e for e in self.entries if e.enabled and e.scene in names]

    def single_runtime(self, available, sound_ok=None) -> float:
        """Seconds for one pass: every played entry's travel plus stay.
        ``sound_ok(entry)`` says whether its sound can be played (default:
        yes); a sound that cannot does not stretch the stay."""
        ok = sound_ok or (lambda _e: True)
        return sum(e.travel + e.stay(ok(e)) for e in self.played(available))

    def total_runtime(self, available, sound_ok=None) -> float | None:
        """Seconds for every loop; ``None`` when it plays continuously."""
        if self.loops == 0:
            return None
        return self.single_runtime(available, sound_ok) * self.loops

    # ---- JSON --------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"format": FORMAT, "version": FORMAT_VERSION,
                "loops": self.loops,
                "entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, raw) -> "Automation":
        """Read saved data, checking every field; raises AutomationError."""
        if not isinstance(raw, dict) or raw.get("format") != FORMAT:
            raise AutomationError("This is not a scene automation.")
        version = raw.get("version")
        if isinstance(version, bool) or not isinstance(version, int) \
                or version < 1:
            raise AutomationError("This is not a scene automation.")
        if version > FORMAT_VERSION:
            raise AutomationError(
                "This automation was made by a newer version of the plugin.")
        loops = raw.get("loops", 1)
        if isinstance(loops, bool) or not isinstance(loops, int) \
                or not 0 <= loops <= LOOPS_MAX:
            raise AutomationError("The number of loops is out of range.")
        entries = raw.get("entries", [])
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
            raise AutomationError("The list of scenes is not valid.")
        return cls([Entry.from_dict(e, i) for i, e in enumerate(entries)],
                   loops)


def split_duration(seconds: float) -> tuple[bool, str]:
    """``(clock, text)`` for showing a duration: up to 120 s it is plain
    seconds (``clock`` False, ``"95.5"``), above it ``m:ss`` or ``h:mm:ss``
    (``clock`` True, ``"2:05"``)."""
    seconds = max(0.0, float(seconds))
    if seconds <= 120.0:
        text = f"{seconds:.1f}".rstrip("0").rstrip(".")
        return False, text
    whole = int(round(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return True, f"{hours}:{minutes:02d}:{secs:02d}"
    return True, f"{minutes}:{secs:02d}"
