# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Everything the plugin needs from IngeTrazo, in one place.

The documented API (``views/extension_api.py``) has no call for scenes, the
camera or the active tool, so this module reaches a few internals. Each is
used defensively (``getattr`` with a fallback) and listed in the README
under "Internals used":

- ``scene.saved_views`` — the scenes (``core.saved_views.SavedView``);
- ``viewport.camera`` — the orbit camera (target, distance, yaw, pitch);
- ``window.tray.scenes`` and its ``_on_activate(row)`` — showing a scene
  exactly as a double-click in the Scenes panel does (IngeTrazo's own
  Browser goes through it the same way);
- ``window._activate_tool(key)`` and ``window._tools`` — Look Around
  during a pause, and the previous tool back afterwards;
- ``window._act_clean_screen`` (Window ▸ Clean screen) and its
  ``window._clean_exit_btn`` — only the 3D view during a full-screen play;
- ``viewport.render_image(w, h, overlays)`` — the frames of the MP4, the
  call the bundled AI bridge and the sheet composer use.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .motion import Pose
from .player import Step

log = logging.getLogger("ingetrazo.plugins")

LOOK_AROUND = "look_around"


# ---- Scenes ----------------------------------------------------------------
def scene_views(scene) -> list:
    """The model's scenes, in the Scenes panel's order."""
    return list(getattr(scene, "saved_views", None) or ())


def scene_names(scene) -> list[str]:
    return [v.name for v in scene_views(scene)]


def find_view(scene, name: str):
    return next((v for v in scene_views(scene) if v.name == name), None)


def pose_of_view(view) -> Pose:
    t = view.target
    return Pose((float(t[0]), float(t[1]), float(t[2])), float(view.distance),
                float(view.yaw), float(view.pitch), float(view.fov_deg))


def sound_ok(entry) -> bool:
    """The entry's sound file is there to be played."""
    return bool(entry.audio) and Path(entry.audio).is_file()


def build_steps(scene, entries) -> list[Step]:
    """Played entries → steps; entries whose scene is gone are left out.
    A sound whose file is missing is dropped (the scene plays silent, for
    its own Wait)."""
    steps = []
    for e in entries:
        view = find_view(scene, e.scene)
        if view is None:
            continue
        pose = pose_of_view(view)
        if pose.is_finite():
            ok = sound_ok(e)
            steps.append(Step(view, pose, e.start, e.stop, e.travel,
                              e.stay(ok), e.audio if ok else None))
    return steps


# ---- Camera ----------------------------------------------------------------
class Camera:
    """The sequencer's camera adapter over the live viewport."""

    def __init__(self, window) -> None:
        self.window = window
        self.viewport = window.viewport
        self.scene = self.viewport.scene

    def pose(self) -> Pose:
        cam = self.viewport.camera
        t = cam.target
        return Pose((t.x(), t.y(), t.z()), float(cam.distance),
                    float(cam.yaw), float(cam.pitch), float(cam.fov_deg))

    def set_pose(self, pose: Pose) -> None:
        from PySide6.QtGui import QVector3D
        cam = self.viewport.camera
        cam.target = QVector3D(*pose.target)
        cam.distance = pose.distance
        cam.yaw = pose.yaw
        cam.pitch = pose.pitch
        cam.fov_deg = pose.fov
        self.viewport.update()

    def arrive(self, step: Step) -> bool:
        """Show the step's scene as the Scenes panel does. False when the
        scene is no longer in the model (another file opened, deleted)."""
        if self.viewport.scene is not self.scene \
                or step.view not in scene_views(self.scene):
            return False
        show_scene(self.window, step.view)
        return True


def show_scene(window, view) -> None:
    """Recall ``view`` with everything a click in the Scenes panel does
    (camera, layers, style, sections, the style menu, the selection)."""
    panel = getattr(getattr(window, "tray", None), "scenes", None)
    rows = getattr(panel, "list", None)
    activate = getattr(panel, "_on_activate", None)
    if rows is not None and callable(activate):
        try:
            from PySide6.QtCore import Qt
            for i in range(rows.count()):
                row = rows.item(i)
                if row.data(Qt.UserRole) is view:
                    activate(row)
                    return
        except Exception:  # noqa: BLE001 — the internal may have changed
            log.exception("scenes_play: Scenes panel recall failed")
    # Fallback: the scene's own recall, then a repaint.
    vp = window.viewport
    view.apply(vp.scene, vp.camera)
    vp.scene.version += 1
    vp.update()


# ---- Tools -----------------------------------------------------------------
class ToolSwitch:
    """Look Around while paused, and the tool the user had back after."""

    def __init__(self, window) -> None:
        self.window = window
        self._previous: str | None = None

    def _key_of_active(self) -> str | None:
        tools = getattr(self.window, "_tools", None) or {}
        active = getattr(self.window.viewport, "active_tool", None)
        return next((k for k, tool in tools.items() if tool is active), None)

    def look_around(self) -> None:
        activate = getattr(self.window, "_activate_tool", None)
        tools = getattr(self.window, "_tools", None) or {}
        if not callable(activate) or LOOK_AROUND not in tools:
            return
        current = self._key_of_active()
        if current != LOOK_AROUND:
            self._previous = current
        try:
            activate(LOOK_AROUND)
        except Exception:  # noqa: BLE001 — never break the playback
            log.exception("scenes_play: cannot switch to Look Around")

    def restore(self) -> None:
        key, self._previous = self._previous, None
        activate = getattr(self.window, "_activate_tool", None)
        if key is None or not callable(activate) \
                or self._key_of_active() != LOOK_AROUND:
            return                    # the user picked another tool: keep it
        try:
            activate(key)
        except Exception:  # noqa: BLE001
            log.exception("scenes_play: cannot restore the tool %r", key)


# ---- Full screen -----------------------------------------------------------
class FullScreen:
    """Only the 3D view, filling the screen, while playing: the window
    full screen with Window ▸ Clean screen on. Everything goes back as it
    was on :meth:`leave`."""

    def __init__(self, window) -> None:
        self.window = window
        self._state = None
        self._was_clean = True

    def enter(self) -> None:
        win = self.window
        self._state = win.windowState()
        act = getattr(win, "_act_clean_screen", None)
        self._was_clean = act is None or act.isChecked()
        try:
            if not self._was_clean:
                act.setChecked(True)         # its toggled() hides the bars
            btn = getattr(win, "_clean_exit_btn", None)
            if btn is not None:
                btn.hide()                   # Stop is on the player bar
            win.showFullScreen()
        except Exception:  # noqa: BLE001 — play anyway, just not full screen
            log.exception("scenes_play: cannot go full screen")

    def leave(self) -> None:
        if self._state is None:
            return
        win, state, self._state = self.window, self._state, None
        try:
            win.setWindowState(state)
            act = getattr(win, "_act_clean_screen", None)
            if act is not None and not self._was_clean:
                act.setChecked(False)
        except Exception:  # noqa: BLE001
            log.exception("scenes_play: cannot leave full screen")


# ---- Frames for the video ------------------------------------------------------
def render_frame(viewport, width: int, height: int | None):
    """The current view as an opaque ``QImage`` (Format_RGB32, so each
    row is BGRA bytes). ``height`` None: the view's own shape, with its
    dimensions and texts; else exactly ``width`` × ``height`` without them
    (they are placed for the view's own shape, like the sheet composer)."""
    from PySide6.QtGui import QImage
    cam = viewport.camera
    if height is None:
        image = viewport.render_image(width)
    else:
        aspect = cam.aspect
        cam.set_aspect(width, height)
        try:
            image = viewport.render_image(width, height, overlays=False)
        finally:
            cam.aspect = aspect
    if image is None:
        return None
    image = image.copy()
    # The read-back may be labelled premultiplied while translucent faces
    # left alpha < 1: treat the composed colours as opaque (the composer's
    # own fix), then drop alpha.
    straight = {QImage.Format_ARGB32_Premultiplied: QImage.Format_ARGB32,
                QImage.Format_RGBA8888_Premultiplied: QImage.Format_RGBA8888,
                }.get(image.format())
    if straight is not None:
        image.reinterpretAsFormat(straight)
    return image.convertToFormat(QImage.Format_RGB32)
