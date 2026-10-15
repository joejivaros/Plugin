# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Finding FFmpeg and the commands given to it (nothing is run here)."""
from __future__ import annotations

import pytest

from conftest import submodule


@pytest.fixture
def media():
    return submodule("media")


def test_find_tool_in_the_chosen_folder(media, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert media.find_tool("ffmpeg", str(tmp_path)) is None
    exe = tmp_path / media._exe("ffmpeg")
    exe.write_bytes(b"")
    assert media.find_tool("ffmpeg", str(tmp_path)) == exe


def test_find_tool_on_the_path(media, tmp_path, monkeypatch):
    exe = tmp_path / media._exe("ffprobe")
    exe.write_bytes(b"")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert media.find_tool("ffprobe") == exe
    assert media.find_tool("ffprobe", str(tmp_path / "nowhere")) == exe


def test_probe_without_ffprobe_says_so(media, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(media.MediaError) as info:
        media.probe_length("C:\\a.mp3", None)
    assert "ffprobe" in info.value.message


def test_sound_player_without_ffplay_is_silent(media, monkeypatch):
    monkeypatch.setenv("PATH", "")
    player = media.SoundPlayer(None)
    assert not player.available
    player.start(None, 0.0)                  # nothing happens
    player.stop()


def test_export_args_without_sound(media):
    args = media.export_args("ffmpeg", "C:\\out\\v.mp4", 1280, 720, 30,
                             12.5, [])
    assert args[0] == "ffmpeg"
    assert args[args.index("-s") + 1] == "1280x720"
    assert args[args.index("-r") + 1] == "30"
    assert args[args.index("-i") + 1] == "pipe:0"
    assert "-filter_complex" not in args
    assert args[args.index("-t") + 1] == "12.500"
    assert args[-3:] == ["-f", "mp4", "file:C:\\out\\v.mp4"]


def test_export_args_mix_each_sound_at_its_time(media):
    sounds = [(2.0, "C:\\a.mp3", 0.0), (9.25, "D:\\b c.wav", 1.5)]
    args = media.export_args("ffmpeg", "C:\\v.mp4", 640, 360, 24, 20.0,
                             sounds)
    inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
    assert inputs == ["pipe:0", "file:C:\\a.mp3", "file:D:\\b c.wav"]
    assert args[args.index("-ss") + 1] == "1.500"   # only the second
    graph = args[args.index("-filter_complex") + 1]
    assert "[1:a]adelay=delays=2000:all=1[a1]" in graph
    assert "[2:a]adelay=delays=9250:all=1[a2]" in graph
    assert "[a1][a2]amix=inputs=2" in graph
    assert args[args.index("-map") + 1] == "0:v"
