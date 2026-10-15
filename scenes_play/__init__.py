# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""
Plugin-ID:      scenes_play
Name:           Scene Automation
Version:        0.2.0
Revision:       unreleased (not tagged yet)
Release-Date:   2026-10-15T16:00:00Z
Author:         G. Andreotti
Contact:        https://github.com/joejivaros
IngeTrazo:      >=0.5.8 (tested 0.5.8)
AI-Assistance:  full
                - Claude Opus 5.5 (claude-opus-5-5): all code, tests,
                  translations (es, fr) and documentation of versions
                  0.1.0 and 0.2.0 (sounds, MP4 export, full screen), from
                  the author's specification and mockup
Dependencies:   none in Python; optional external program FFmpeg
                (ffmpeg, ffprobe, ffplay; any recent version) for sounds
                and MP4 export
Permissions:    filesystem(automation .json, sound and .mp4 files the user
                picks in file dialogs; a temporary log file) |
                subprocess(ffprobe, ffplay, ffmpeg from the user's FFmpeg
                folder or PATH; fixed argument lists, no shell)
Description:    Plays the model's scenes in a sequence with smooth,
                cinematic camera moves: per scene, how fast the move starts
                and stops, how long it travels and stays, and an optional
                sound; loops, full screen, pause with Look Around, MP4
                export, and automations saved to a file or kept in the model.
"""
from __future__ import annotations

import logging

from .texts import t

PLUGIN_ID = "scenes_play"
NAME = "Scene Automation"
VERSION = "0.2.0"

log = logging.getLogger("ingetrazo.plugins")

#: The one reused window.
_STATE: dict = {"dialog": None}


def show_dialog(app) -> None:
    """Open (or bring forward) the Scene Automation window."""
    try:
        dlg = _STATE["dialog"]
        if dlg is not None and dlg.playing:
            return                        # the player bar is the UI now
        if dlg is None:
            from .ui_dialog import AutomationDialog
            dlg = AutomationDialog(app, t(NAME), app.window)
            _STATE["dialog"] = dlg
        dlg.on_document_changed()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
    except Exception:  # noqa: BLE001 — report, never crash the app
        log.exception("%s: cannot open the window", PLUGIN_ID)
        flash = getattr(app.viewport, "flash_status", None)
        if flash:
            flash(t("Scene Automation could not open. Details are in the "
                    "log."), 5000)


def _on_document_changed() -> None:
    dlg = _STATE["dialog"]
    if dlg is None:
        return
    try:
        dlg.on_document_changed()
    except Exception:  # noqa: BLE001 — a refresh must not break editing
        log.exception("%s: refresh after a document change failed",
                      PLUGIN_ID)


def setup(app) -> None:
    """Extensions ▸ Scene Automation… (also found with F3)."""
    app.add_menu_action(
        t(NAME) + "…", lambda: show_dialog(app),
        tip=t("Play the model's scenes in sequence with smooth camera "
              "moves."))
    app.on_document_changed(_on_document_changed)
