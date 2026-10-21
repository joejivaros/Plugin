# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""
Plugin-ID:      cleaning
Name:           Cleaning
Version:        0.1.2
Revision:       git tag cleaning-v0.1.2
Release-Date:   2026-10-21T19:24:22Z
Author:         G. Andreotti
Contact:        https://github.com/joejivaros
IngeTrazo:      >=0.5.9 (tested 0.5.9)
AI-Assistance:  full
                - Claude Opus 5.5 (claude-opus-5-5): all code, tests,
                  translations and documentation of versions 0.1.0 to
                  0.1.2, and the QPainter-drawn toolbar icon
Dependencies:   none
Permissions:    none
Description:    Cleans the model in one undo step: erases stray edges,
                degenerate and duplicate faces, merges coplanar faces,
                repairs split edges, merges identical materials and purges
                unused materials, layers and empty groups. The user picks
                which items to clean.
"""
from __future__ import annotations

import logging

from .texts import t

PLUGIN_ID = "cleaning"
NAME = "Cleaning"
VERSION = "0.1.2"

log = logging.getLogger("ingetrazo.plugins")

#: The one reused dialog and the toolbar switch.
_STATE: dict = {"dialog": None, "toolbar": None}


def show_dialog(viewport) -> None:
    """Open (or bring forward) the modeless Cleaning dialog."""
    try:
        from .ui import CleaningDialog
        dlg = _STATE["dialog"]
        if dlg is None or dlg.viewport is not viewport:
            dlg = CleaningDialog(viewport, PLUGIN_ID, f"{t(NAME)} {VERSION}",
                                 _STATE["toolbar"], viewport.window())
            _STATE["dialog"] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
    except Exception:  # noqa: BLE001 — report, never crash the app
        log.exception("%s: cannot open the dialog", PLUGIN_ID)
        flash = getattr(viewport, "flash_status", None)
        if flash:
            flash(t("Cleaning could not open. Details are in the log."), 5000)


def setup(app) -> None:
    """Extensions ▸ Cleaning ▸ (Clean Up… / Show in toolbar) and the
    optional toolbar."""
    from .toolbar import ToolbarSwitch

    def open_dialog() -> None:
        show_dialog(app.viewport)

    tip = t("Purge unused items and repair the geometry of the model.")
    sub = app.add_menu(t(NAME))
    if sub is None:
        return
    sub.setObjectName(f"{PLUGIN_ID}_menu")
    act = sub.addAction(t("Clean Up…"))
    act.setStatusTip(tip)
    act.triggered.connect(lambda _checked=False: open_dialog())
    sub.addSeparator()
    check = sub.addAction(t("Show in toolbar"))
    check.setStatusTip(t("Show or hide the Cleaning toolbar."))
    switch = ToolbarSwitch(app.window, PLUGIN_ID, t(NAME),
                           t("Clean Up…") + "\n" + tip, open_dialog)
    switch.attach_check(check)
    _STATE["toolbar"] = switch
