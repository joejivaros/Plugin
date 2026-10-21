# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""
Plugin-ID:      divide_points
Name:           Divide Points
Version:        0.2.2
Revision:       git tag divide_points-v0.2.2
Release-Date:   2026-10-21T19:24:22Z
Author:         G. Andreotti
Contact:        https://github.com/joejivaros
IngeTrazo:      >=0.5.7 (tested 0.5.9)
AI-Assistance:  full
                - Claude Opus 5.5 (claude-opus-5-5): all code, tests,
                  translations and documentation of versions 0.1.0 to
                  0.2.2, the QPainter-drawn toolbar icon and the
                  French translation; packaging for the extensions
                  index (header, licence, release archive)
Dependencies:   none
Permissions:    none
Description:    Places visible measurement / guide points along the selected
                lines and curves, by number of points or by distance in the
                model's unit, starting from both ends or from the middle.
"""
from __future__ import annotations

import logging

from .texts import t

PLUGIN_ID = "divide_points"
NAME = "Divide Points"
VERSION = "0.2.2"

log = logging.getLogger("ingetrazo.plugins")

#: The one reused dialog and the toolbar switch.
_STATE: dict = {"dialog": None, "toolbar": None}


def show_dialog(viewport) -> None:
    """Open (or bring forward) the modeless Divide Points dialog."""
    try:
        from .ui import DividePointsDialog
        dlg = _STATE["dialog"]
        if dlg is None or dlg.viewport is not viewport:
            dlg = DividePointsDialog(viewport, PLUGIN_ID,
                                     f"{t(NAME)} {VERSION}", viewport.window())
            _STATE["dialog"] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
    except Exception:  # noqa: BLE001 — report, never crash the app
        log.exception("%s: cannot open the dialog", PLUGIN_ID)
        flash = getattr(viewport, "flash_status", None)
        if flash:
            flash(t("Divide Points could not open. Details are in the log."),
                  5000)


def setup(app) -> None:
    """Extensions ▸ Divide Points ▸ (Divide Points… / Show in toolbar), the
    right-click entry when lines or curves are selected, the optional
    toolbar and the preview overlay."""
    from PySide6.QtCore import QTimer

    from . import scene_ops
    from .toolbar import ToolbarSwitch

    app.add_overlay(scene_ops.Overlay(app))

    def open_dialog() -> None:
        show_dialog(app.viewport)

    tip = t("Place visible guide points along the selected lines and curves.")
    sub = app.add_menu(t(NAME))
    if sub is not None:
        sub.setObjectName(f"{PLUGIN_ID}_menu")
        act = sub.addAction(t("Divide Points…"))
        act.setStatusTip(tip)
        act.triggered.connect(lambda _checked=False: open_dialog())
        sub.addSeparator()
        check = sub.addAction(t("Show in toolbar"))
        check.setStatusTip(t("Show or hide the Divide Points toolbar."))
        switch = ToolbarSwitch(app.window, PLUGIN_ID, t(NAME),
                               t("Divide Points…") + "\n" + tip, open_dialog)
        switch.attach_check(check)
        _STATE["toolbar"] = switch

    def context(menu, _selection) -> None:
        if not scene_ops.selection_has_edges(app.viewport.scene):
            return
        menu.addSeparator()
        entry = menu.addAction(t("Divide Points…"))
        entry.triggered.connect(
            lambda _checked=False: QTimer.singleShot(0, open_dialog))

    app.add_context_menu(context)
