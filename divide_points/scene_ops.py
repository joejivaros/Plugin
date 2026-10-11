# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 <Author>
"""Divide Points ↔ the IngeTrazo document.

* the selected lines and curves → :class:`geometry.Path` objects;
* the points → IngeTrazo **guide points** (``core.guide.Guide`` with no
  direction): they snap, are saved in the ``.igz`` and are erased like any
  guide (Eraser, Edit ▸ Delete Guides);
* a registry of the points this plugin made, in the document data
  (``scene.plugin_data[PLUGIN_ID]``), so **Delete Placed Points** removes
  only those;
* the overlay draws the dialog's preview as orange crosses;
* the guides and the registry change together in ONE command, so every
  user action is one undo step.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPen, QVector3D

from core.guide import Guide
from core.history import (AddGuideCommand, Command, DeleteGuidesCommand,
                          SetPluginDataCommand)

from . import geometry

log = logging.getLogger("ingetrazo.plugins")

#: Version of the data saved under ``scene.plugin_data[PLUGIN_ID]``.
DATA_VERSION = 1

#: Preview crosses: half-size in pixels, colour.
PREVIEW_HALF = 6.0
PREVIEW_COLOR = QColor(255, 120, 0)

#: Points the open dialog would place — drawn as orange crosses.
PREVIEW: list = []


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _p3(v) -> tuple[float, float, float]:
    return (float(v.x()), float(v.y()), float(v.z()))


def as_stored(p) -> tuple[float, float, float]:
    """``p`` as a guide stores it: ``QVector3D`` keeps 32-bit floats, so a
    point must go through it before it is compared with a guide's."""
    return _p3(QVector3D(float(p[0]), float(p[1]), float(p[2])))


def _key(p) -> tuple:
    return geometry.point_key(as_stored(p))


def selected_paths(scene) -> list[geometry.Path]:
    """The selected edges (lines and curve segments) joined into paths.

    The edges of the active mesh (the loose geometry, or the open group,
    whose mesh is edited in world coordinates) are in world coordinates.
    Everything else in the selection (faces, groups, guides) is ignored.
    """
    from core.mesh import Edge
    segs = []
    for ent in list(scene.selection):
        if isinstance(ent, Edge):
            segs.append((id(ent.v0), id(ent.v1), _p3(ent.a), _p3(ent.b)))
    return geometry.build_paths(segs)


def selection_has_edges(scene) -> bool:
    from core.mesh import Edge
    return any(isinstance(e, Edge) for e in scene.selection)


# ---------------------------------------------------------------------------
# Registry (document data)
# ---------------------------------------------------------------------------

def read_registry(scene, key: str) -> list[tuple]:
    """The points this plugin placed, as ``(x, y, z)`` tuples. Data of an
    unknown (newer) version is read if its shape is understood, else
    ignored with a log entry."""
    raw = (getattr(scene, "plugin_data", None) or {}).get(key)
    if not isinstance(raw, dict):
        return []
    if raw.get("version") != DATA_VERSION:
        log.warning("%s: document data version %r, expected %r", key,
                    raw.get("version"), DATA_VERSION)
    out = []
    for p in raw.get("points", []) if isinstance(raw.get("points"), list) else []:
        if isinstance(p, (list, tuple)) and len(p) == 3 and all(
                isinstance(c, (int, float)) and not isinstance(c, bool)
                for c in p):
            out.append((float(p[0]), float(p[1]), float(p[2])))
    return out


def _registry_value(points) -> dict:
    return {"version": DATA_VERSION,
            "points": [[round(c, 9) for c in p] for p in points]}


def guide_points(scene) -> dict:
    """``{point_key: guide}`` for every guide POINT in the document."""
    out = {}
    for g in getattr(scene, "guides", None) or ():
        if getattr(g, "direction", None) is None:
            out[_key(_p3(g.point))] = g
    return out


def live_points(scene, key: str) -> list[tuple]:
    """Registered points that still have their guide point (one erased
    by other means is dropped)."""
    have = guide_points(scene)
    return [as_stored(p) for p in read_registry(scene, key)
            if _key(p) in have]


# ---------------------------------------------------------------------------
# Commands — one undo step per action
# ---------------------------------------------------------------------------

class BatchCommand(Command):
    """Several commands as one undo step; a failure undoes what ran."""

    def __init__(self, parts) -> None:
        self.parts = list(parts)

    def do(self, scene) -> None:
        done = []
        try:
            for part in self.parts:
                part.do(scene)
                done.append(part)
        except Exception:
            for part in reversed(done):
                part.undo(scene)
            raise

    def undo(self, scene) -> None:
        for part in reversed(self.parts):
            part.undo(scene)


def _execute(viewport, cmd) -> None:
    hist = viewport.history
    hist.execute(cmd)
    err = getattr(hist, "last_error", None)
    if err:
        raise RuntimeError(err)
    notify = getattr(viewport, "notify_scene_changed", None)
    if notify:
        notify()
    viewport.update()


def add_points(viewport, key: str, points) -> int:
    """Add ``points`` as guide points (skipping places that already have
    one) and register them. Returns how many were added."""
    scene = viewport.scene
    have = guide_points(scene)
    new = []
    for p in points:
        p = as_stored(p)
        k = geometry.point_key(p)
        if k in have:
            continue
        have[k] = None
        new.append(p)
    if not new:
        return 0
    registry = live_points(scene, key) + new
    parts = [AddGuideCommand(Guide(QVector3D(*p))) for p in new]
    parts.append(SetPluginDataCommand(key, _registry_value(registry)))
    _execute(viewport, BatchCommand(parts))
    return len(new)


def delete_points(viewport, key: str) -> int:
    """Erase every guide point this plugin placed. Returns how many."""
    scene = viewport.scene
    have = guide_points(scene)
    gone = [have[_key(p)] for p in read_registry(scene, key)
            if _key(p) in have]
    if not gone and key not in (getattr(scene, "plugin_data", None) or {}):
        return 0
    parts = []
    if gone:
        parts.append(DeleteGuidesCommand(gone))
    parts.append(SetPluginDataCommand(key, None))
    _execute(viewport, BatchCommand(parts))
    return len(gone)


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

class Overlay:
    """Draws the open dialog's preview as orange crosses. The placed points
    need nothing more: they are guide points, drawn by IngeTrazo as its own
    small crosses."""

    def __init__(self, app) -> None:
        self.app = app

    def __call__(self, viewport, painter) -> None:
        if not PREVIEW:
            return
        px, py, front = self.app.world_to_pixels(PREVIEW)
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(PREVIEW_COLOR, 2.0))
        h = PREVIEW_HALF
        for x, y, ok in zip(px, py, front):
            if ok:
                x, y = float(x), float(y)
                painter.drawLine(QPointF(x - h, y), QPointF(x + h, y))
                painter.drawLine(QPointF(x, y - h), QPointF(x, y + h))
