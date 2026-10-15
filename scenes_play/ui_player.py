# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Playing: a frame timer driving the sequencer, and the small player bar
(Pause / Resume and Stop) shown instead of the main window.

While paused the Look Around tool is active, so the user can turn the
camera; Resume (or Stop) gives back the tool they had. In full screen only
the 3D view shows; Esc stops, and the window comes back as it was.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import (QElapsedTimer, QEvent, QObject, Qt, QTimer,
                            Signal)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                               QStyle, QWidget)

from . import host
from .player import DONE, Sequencer
from .texts import t

log = logging.getLogger("ingetrazo.plugins")

FRAME_MS = 15
#: A frame later than this (the app was busy) counts as this long, so the
#: camera does not leap across half a move.
MAX_FRAME_S = 0.5


class PlayerBar(QWidget):
    """Pause / Resume, Stop and where the playback is."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent, Qt.Tool | Qt.CustomizeWindowHint
                         | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setObjectName("scenes_play_player")
        self.setWindowTitle(title)
        self.on_close = None
        style = self.style()
        self._icons = {"pause": style.standardIcon(QStyle.SP_MediaPause),
                       "play": style.standardIcon(QStyle.SP_MediaPlay)}
        self.pause_btn = QPushButton()
        self.pause_btn.setObjectName("scenes_play_pause")
        self.stop_btn = QPushButton(style.standardIcon(QStyle.SP_MediaStop),
                                    t("Stop"))
        self.stop_btn.setObjectName("scenes_play_stop")
        self.stop_btn.setToolTip(t("Stop the playback."))
        self.label = QLabel()
        self.label.setMinimumWidth(220)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.addWidget(self.pause_btn)
        lay.addWidget(self.stop_btn)
        lay.addWidget(self.label, 1)
        self.set_paused(False)

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.pause_btn.setIcon(self._icons["play"])
            self.pause_btn.setText(t("Resume"))
            self.pause_btn.setToolTip(t("Go on from where the camera is."))
        else:
            self.pause_btn.setIcon(self._icons["pause"])
            self.pause_btn.setText(t("Pause"))
            self.pause_btn.setToolTip(t("Pause; drag in the view to look "
                                        "around."))

    def closeEvent(self, event) -> None:
        if self.on_close is not None:
            self.on_close()
        super().closeEvent(event)


class PlaybackController(QObject):
    """One playback at a time over the main window's viewport."""

    finished = Signal()

    def __init__(self, window, title: str, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.bar = PlayerBar(title, window)
        self.bar.pause_btn.clicked.connect(self.toggle_pause)
        self.bar.stop_btn.clicked.connect(self.stop)
        self.bar.on_close = self.stop
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(FRAME_MS)
        self.timer.timeout.connect(self._tick)
        self.clock = QElapsedTimer()
        self.tools = host.ToolSwitch(window)
        self.full = host.FullScreen(window)
        self.seq: Sequencer | None = None
        self._camera: host.Camera | None = None
        self._watching_keys = False

    @property
    def active(self) -> bool:
        return self.seq is not None and self.seq.phase != DONE

    def play(self, steps, loops: int, full_screen: bool = False,
             sound=None) -> None:
        """Play ``steps``; ``sound`` is the audio adapter (a
        :class:`media.SoundPlayer`) or None for silence."""
        if self.active:
            self.stop()
        self._camera = host.Camera(self.window)
        self.seq = Sequencer(steps, loops, self._camera, self._on_change,
                             audio=sound)
        if full_screen:
            self.full.enter()
        # Esc stops, while (and only while) playing.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._watching_keys = True
        self.bar.set_paused(False)
        self._place_bar()
        self.bar.show()
        self.bar.raise_()
        if full_screen:                     # the window settles first
            QTimer.singleShot(200, self._place_bar)
        self.seq.start()
        if self.active:
            self.clock.start()
            self.timer.start()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt override
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape \
                and self.active:
            self.stop()
            return True
        return super().eventFilter(obj, event)

    def toggle_pause(self) -> None:
        if not self.active:
            return
        if self.seq.paused:
            self.tools.restore()
            self.seq.resume()
            self.clock.restart()
            self.timer.start()
        else:
            self.timer.stop()
            self.seq.pause()
            self.tools.look_around()
        self.bar.set_paused(self.seq.paused)

    def stop(self) -> None:
        if self.seq is not None:
            self.seq.stop()                 # → _on_change → _finish

    def _tick(self) -> None:
        if not self.active:
            return
        if self.window.viewport.scene is not self._camera.scene:
            self.stop()                     # another model was opened
            return
        dt = min(self.clock.restart() / 1000.0, MAX_FRAME_S)
        try:
            self.seq.advance(dt)
        except Exception:  # noqa: BLE001 — stop, never break the app
            log.exception("scenes_play: playback failed")
            self.stop()

    def _on_change(self) -> None:
        seq = self.seq
        if seq is None:
            return
        if seq.phase == DONE:
            self._finish()
            return
        step = seq.step
        name = getattr(step.view, "name", "") if step is not None else ""
        where = t("Scene {i}/{n}: {name}", i=seq.index + 1,
                  n=len(seq.steps), name=name)
        loop = (t("Loop {i}", i=seq.loop) if seq.loops == 0
                else t("Loop {i}/{n}", i=seq.loop, n=seq.loops))
        self.bar.label.setText(f"{where} · {loop}")

    def _finish(self) -> None:
        self.timer.stop()
        self.tools.restore()
        if self._watching_keys:
            QApplication.instance().removeEventFilter(self)
            self._watching_keys = False
        self.full.leave()
        self.bar.hide()                     # hide() is not a close: no Stop
        self.finished.emit()

    def _place_bar(self) -> None:
        """Top-left corner of the 3D view."""
        vp = self.window.viewport
        try:
            corner = vp.mapToGlobal(vp.rect().topLeft())
            self.bar.adjustSize()
            self.bar.move(corner.x() + 16, corner.y() + 16)
        except (AttributeError, RuntimeError):
            pass                            # a test double: leave it
