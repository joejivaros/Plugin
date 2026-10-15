# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Sound and video through FFmpeg, which the user installs.

IngeTrazo's installed builds carry no audio or video support of their own
(no QtMultimedia, no ``wave``/``winsound``), so the plugin runs the three
FFmpeg programs:

- ``ffprobe`` — the length of a sound, when it is attached;
- ``ffplay`` — the sound of a scene while playing (no window);
- ``ffmpeg`` — the MP4: video frames come in on its standard input, the
  sounds are mixed in at their times.

Every call is a fixed argument list (never a shell). Every input file is
given as ``file:<path>``, so FFmpeg reads it as a plain local file and
never as one of its URLs or protocols, and only paths that passed
:func:`model.safe_audio_path` (or the user's own output choice) get here.
The programs are found in the folder the user picked (remembered in
IngeTrazo's settings) or on the ``PATH``.
"""
from __future__ import annotations

import logging
import math
import os
# Only the FFmpeg programs, with fixed argument lists and no shell.
import subprocess  # nosec B404
import sys
from pathlib import Path

log = logging.getLogger("ingetrazo.plugins")

SETTINGS_DIR_KEY = "ffmpeg_dir"
PROBE_TIMEOUT_S = 20.0

#: No console window flashing up on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class MediaError(RuntimeError):
    """FFmpeg missing or failing. ``message`` is the English source of the
    text to show (translated by the caller), ``fields`` its values."""

    def __init__(self, message: str, **fields) -> None:
        super().__init__(message.format(**fields) if fields else message)
        self.message = message
        self.fields = fields


# ---- Finding the programs ----------------------------------------------------
def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _on_path(name: str) -> Path | None:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder:
            continue
        candidate = Path(folder) / _exe(name)
        if candidate.is_file():
            return candidate
    return None


def find_tool(name: str, folder: str | None = None) -> Path | None:
    """``ffmpeg`` / ``ffprobe`` / ``ffplay``: in ``folder`` if given and
    there, else on the PATH."""
    if folder:
        candidate = Path(folder) / _exe(name)
        if candidate.is_file():
            return candidate
    return _on_path(name)


def _run_flags() -> dict:
    return {"stdin": subprocess.DEVNULL, "creationflags": _NO_WINDOW}


# ---- Sound length ----------------------------------------------------------------
def probe_length(path: str, folder: str | None = None) -> float:
    """The length in seconds of the sound at ``path``; raises MediaError."""
    probe = find_tool("ffprobe", folder)
    if probe is None:
        raise MediaError("FFmpeg (ffprobe) was not found.")
    args = [str(probe), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", f"file:{path}"]
    try:
        done = subprocess.run(  # nosec B603
            args, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
            check=False, **_run_flags())
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("scenes_play: ffprobe failed on %s: %s", path, exc)
        raise MediaError("The sound could not be read.") from exc
    try:
        seconds = float((done.stdout or "").strip().splitlines()[0])
    except (IndexError, ValueError):
        seconds = math.nan
    if done.returncode != 0 or not math.isfinite(seconds) or seconds <= 0:
        log.warning("scenes_play: ffprobe on %s: %s", path,
                    (done.stderr or "").strip()[:500])
        raise MediaError("The sound could not be read.")
    return seconds


# ---- Playing a sound -----------------------------------------------------------------
class SoundPlayer:
    """The live playback's audio adapter: one ``ffplay`` at a time."""

    def __init__(self, folder: str | None = None) -> None:
        self.ffplay = find_tool("ffplay", folder)
        self._proc: subprocess.Popen | None = None

    @property
    def available(self) -> bool:
        return self.ffplay is not None

    def start(self, step, offset: float) -> None:
        self.stop()
        if self.ffplay is None or not step.audio \
                or not Path(step.audio).is_file():
            return
        args = [str(self.ffplay), "-nodisp", "-autoexit", "-loglevel",
                "quiet", "-ss", f"{max(0.0, offset):.3f}",
                f"file:{step.audio}"]
        try:
            self._proc = subprocess.Popen(  # nosec B603
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **_run_flags())
        except OSError:
            log.exception("scenes_play: cannot start ffplay")
            self._proc = None

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---- Making the MP4 --------------------------------------------------------------------
#: More sounds than this in one video: refused (each is one FFmpeg input).
MAX_SOUNDS = 200


def export_args(ffmpeg: str, out: str, width: int, height: int, fps: int,
                duration: float, sounds) -> list[str]:
    """The ffmpeg command for an MP4 of ``duration`` seconds whose frames
    (``width`` × ``height``, BGRA bytes) come on standard input, with each
    ``(time, file, offset)`` of ``sounds`` mixed in at its time."""
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgra",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0"]
    for _time, path, offset in sounds:
        if offset > 0:
            args += ["-ss", f"{offset:.3f}"]
        args += ["-i", f"file:{path}"]
    if sounds:
        parts, labels = [], []
        for i, (time, _path, _offset) in enumerate(sounds, start=1):
            ms = max(0, int(round(time * 1000)))
            parts.append(f"[{i}:a]adelay=delays={ms}:all=1[a{i}]")
            labels.append(f"[a{i}]")
        parts.append("".join(labels) + f"amix=inputs={len(sounds)}"
                     ":duration=longest:normalize=0[aout]")
        args += ["-filter_complex", ";".join(parts),
                 "-map", "0:v", "-map", "[aout]",
                 "-c:a", "aac", "-b:a", "192k"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-t", f"{duration:.3f}", "-f", "mp4", f"file:{out}"]
    return args


class Encoder:
    """One running ffmpeg taking frames on its standard input; its
    messages go to a temporary file (a full pipe would stall it)."""

    def __init__(self, args: list[str]) -> None:
        import tempfile
        self._log = tempfile.TemporaryFile()
        try:
            self.proc = subprocess.Popen(  # nosec B603
                args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=self._log, creationflags=_NO_WINDOW)
        except OSError as exc:
            self._log.close()
            raise MediaError("FFmpeg could not be started.") from exc

    def write(self, frame: bytes) -> None:
        try:
            self.proc.stdin.write(frame)
        except (BrokenPipeError, OSError) as exc:
            raise MediaError("FFmpeg stopped: {error}",
                             error=self.messages() or str(exc)) from exc

    def finish(self) -> None:
        """Close the input and wait for the file to be written."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        code = self.proc.wait()
        text = self.messages()
        self._log.close()
        if code != 0:
            raise MediaError("FFmpeg stopped: {error}",
                             error=text or f"exit code {code}")

    def abort(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        self._log.close()

    def messages(self) -> str:
        try:
            self._log.seek(0)
            return self._log.read().decode("utf-8", "replace").strip()[-600:]
        except (OSError, ValueError):
            return ""
