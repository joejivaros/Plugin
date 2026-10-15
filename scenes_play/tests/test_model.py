# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The automation: runtimes, durations and reading saved data safely."""
from __future__ import annotations

import json
import math

import pytest


def _auto(model, loops=1):
    E = model.Entry
    return model.Automation([E("A", travel=3, wait=60),
                             E("B", travel=5, wait=10),
                             E("C", enabled=False, travel=2, wait=2),
                             E("Gone", travel=4, wait=4)], loops)


def test_only_checked_existing_scenes_are_played(model):
    auto = _auto(model)
    assert [e.scene for e in auto.played(["A", "B", "C"])] == ["A", "B"]


def test_single_and_total_runtime(model):
    auto = _auto(model, loops=3)
    names = ["A", "B", "C"]
    assert auto.single_runtime(names) == pytest.approx(78.0)
    assert auto.total_runtime(names) == pytest.approx(234.0)


def test_zero_loops_is_continuous(model):
    assert _auto(model, loops=0).total_runtime(["A"]) is None


@pytest.mark.parametrize("seconds, clock, text", [
    (0, False, "0"), (45, False, "45"), (7.5, False, "7.5"),
    (120, False, "120"), (121, True, "2:01"), (605.4, True, "10:05"),
    (3725, True, "1:02:05"),
])
def test_split_duration(model, seconds, clock, text):
    assert model.split_duration(seconds) == (clock, text)


def test_round_trip_through_json(model):
    auto = _auto(model, loops=4)
    back = model.Automation.from_dict(json.loads(json.dumps(auto.to_dict())))
    assert back == auto


def test_defaults_fill_missing_fields(model):
    raw = {"format": model.FORMAT, "version": 1,
           "entries": [{"scene": "A"}]}
    auto = model.Automation.from_dict(raw)
    assert auto.loops == 1
    e = auto.entries[0]
    assert (e.enabled, e.start, e.stop) == (True, "medium", "medium")
    assert (e.travel, e.wait) == (model.DEFAULT_TRAVEL, model.DEFAULT_WAIT)


def _bad(model, **change):
    raw = {"format": model.FORMAT, "version": 1, "loops": 1,
           "entries": [{"scene": "A", "start": "slow", "stop": "fast",
                        "travel": 1.0, "wait": 1.0, "enabled": True}]}
    entry = change.pop("entry", {})
    raw["entries"][0].update(entry)
    raw.update(change)
    return raw


@pytest.mark.parametrize("change", [
    {"format": "something.else"},
    {"version": 3},
    {"version": True},
    {"version": "1"},
    {"loops": -1},
    {"loops": 1000},
    {"loops": 2.5},
    {"loops": True},
    {"entries": "A"},
    {"entries": [None]},
    {"entry": {"scene": ""}},
    {"entry": {"scene": 3}},
    {"entry": {"scene": "x" * 201}},
    {"entry": {"start": "warp"}},
    {"entry": {"enabled": "yes"}},
    {"entry": {"travel": -1}},
    {"entry": {"travel": 601}},
    {"entry": {"travel": math.nan}},
    {"entry": {"wait": math.inf}},
    {"entry": {"wait": "5"}},
    {"entry": {"wait": True}},
])
def test_bad_data_is_refused(model, change):
    with pytest.raises(model.AutomationError):
        model.Automation.from_dict(_bad(model, **change))


def test_too_many_entries_are_refused(model):
    raw = _bad(model)
    raw["entries"] = raw["entries"] * (model.MAX_ENTRIES + 1)
    with pytest.raises(model.AutomationError):
        model.Automation.from_dict(raw)


def test_not_a_dict_is_refused(model):
    for raw in (None, [], "x", 3):
        with pytest.raises(model.AutomationError):
            model.Automation.from_dict(raw)


def test_error_keeps_its_source_text(model):
    with pytest.raises(model.AutomationError) as info:
        model.Automation.from_dict(_bad(model, entry={"travel": -1}))
    assert info.value.message == "Entry {n} has a time out of range."
    assert info.value.fields == {"n": 1}


# ---- Sounds ------------------------------------------------------------------
@pytest.mark.parametrize("path, ok", [
    ("C:\\Music\\intro.mp3", True),
    ("C:/Music/intro.WAV", True),
    ("/home/me/sound.ogg", True),
    ("\\\\server\\share\\intro.mp3", False),     # network share
    ("//server/share/intro.mp3", False),
    ("http://example.com/a.mp3", False),
    ("file:///C:/a.mp3", False),
    ("music/intro.mp3", False),                  # relative
    ("C:intro.mp3", False),                      # drive-relative
    ("C:\\Music\\intro.exe", False),
    ("C:\\Music\\intro", False),
    ("C:\\Music\\in\0tro.mp3", False),
    ("", False), (None, False), (3, False),
])
def test_safe_audio_path(model, path, ok):
    assert (model.safe_audio_path(path) is not None) == ok


def test_a_sound_stretches_the_stay(model):
    e = model.Entry("A", wait=5.0, audio="C:\\a.mp3", audio_length=12.5)
    assert e.stay() == 12.5
    assert e.stay(sound=False) == 5.0
    e.audio_length = 2.0
    assert e.stay() == 5.0


def test_runtime_counts_only_playable_sounds(model):
    E = model.Entry
    auto = model.Automation([E("A", travel=1, wait=2, audio="C:\\a.mp3",
                               audio_length=10),
                             E("B", travel=1, wait=2, audio="C:\\b.mp3",
                               audio_length=10)], 2)
    names = ["A", "B"]
    assert auto.single_runtime(names) == pytest.approx(22.0)

    def only_a(e):                               # B's file is missing
        return e.scene == "A"
    assert auto.single_runtime(names, only_a) == pytest.approx(14.0)
    assert auto.total_runtime(names, only_a) == pytest.approx(28.0)


def test_sound_round_trip_and_version_1_still_loads(model):
    auto = model.Automation([model.Entry("A", audio="C:\\a.wav",
                                         audio_length=3.25)])
    raw = json.loads(json.dumps(auto.to_dict()))
    assert raw["version"] == 2
    assert model.Automation.from_dict(raw) == auto
    old = {"format": model.FORMAT, "version": 1,
           "entries": [{"scene": "A", "wait": 4}]}
    assert model.Automation.from_dict(old).entries[0].audio is None


@pytest.mark.parametrize("entry", [
    {"audio": "\\\\evil\\share\\x.mp3", "audio_length": 1},
    {"audio": "relative.mp3", "audio_length": 1},
    {"audio": "C:\\x.mp3", "audio_length": math.nan},
    {"audio": "C:\\x.mp3", "audio_length": -1},
    {"audio": "C:\\x.mp3", "audio_length": 4000},
    {"audio": 7},
])
def test_bad_sound_is_refused(model, entry):
    with pytest.raises(model.AutomationError):
        model.Automation.from_dict(_bad(model, entry=entry))
