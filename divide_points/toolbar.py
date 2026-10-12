# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The optional Divide Points toolbar and its icon.

The icon is drawn with QPainter (no image file), the way IngeTrazo draws
its own (views/icons.py): 48 px, the palette's text colour as ink, a 3 px
pen and the orange accent. It is redrawn when the theme changes.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QToolBar

log = logging.getLogger("ingetrazo.plugins")

ACCENT = QColor(243, 115, 41)       # IngeTrazo's orange accent
ICON_PX = 48


def _ink() -> QColor:
    app = QApplication.instance()
    if app is None:
        return QColor(40, 44, 52)
    return QColor(app.palette().windowText().color())


def draw_icon(p: QPainter, ink: QColor, accent: QColor) -> None:
    """A curve (ink) divided by three guide-point crosses (orange)."""
    pen = QPen(ink, 3.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    curve = QPainterPath(QPointF(7, 33))
    curve.cubicTo(QPointF(15, 1), QPointF(33, 1), QPointF(41, 33))
    p.drawPath(curve)
    cross = QPen(accent, 3.0)
    cross.setCapStyle(Qt.RoundCap)
    p.setPen(cross)
    h = 5.0
    for t in (0.0, 0.5, 1.0):
        c = curve.pointAtPercent(t)
        p.drawLine(QPointF(c.x() - h, c.y()), QPointF(c.x() + h, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - h), QPointF(c.x(), c.y() + h))
    # A short measuring tick under the curve: equal spacing.
    p.setPen(QPen(ink, 2.0))
    p.drawLine(QPointF(7, 44), QPointF(41, 44))
    for x in (7.0, 24.0, 41.0):
        p.drawLine(QPointF(x, 41), QPointF(x, 47))


def make_icon() -> QIcon:
    pm = QPixmap(ICON_PX, ICON_PX)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        p.setClipRect(QRectF(0, 0, ICON_PX, ICON_PX))
        draw_icon(p, _ink(), ACCENT)
    finally:
        p.end()
    return QIcon(pm)


class _ThemeWatcher(QObject):
    """Redraws the icon when the palette or theme changes."""

    def __init__(self, action: QAction, parent) -> None:
        super().__init__(parent)
        self.action = action

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt override
        if event.type() in (QEvent.ApplicationPaletteChange,
                            QEvent.PaletteChange, QEvent.ThemeChange):
            self.action.setIcon(make_icon())
        return False


class ToolbarSwitch:
    """Creates the toolbar on first need and keeps the menu check box, the
    toolbar's visibility and the saved setting in step. The toolbar can
    also be hidden from Qt's toolbar right-click menu; the check box
    follows."""

    def __init__(self, window, key: str, title: str, tip: str, run) -> None:
        self.window = window
        self.key = key
        self.title = title
        self.tip = tip
        self.run = run
        self.toolbar: QToolBar | None = None
        self.check: QAction | None = None
        self._setting = f"plugins/{key}/show_toolbar"

    # ---- setting -------------------------------------------------------------
    def saved(self) -> bool:
        return str(QSettings().value(self._setting, "0")) in ("1", "true")

    def _save(self, on: bool) -> None:
        QSettings().setValue(self._setting, "1" if on else "0")

    # ---- toolbar -------------------------------------------------------------
    def _build(self) -> QToolBar:
        name = f"{self.key}_toolbar"
        tb = None
        make = getattr(self.window, "_new_toolbar", None)   # the host's builder
        if callable(make):
            try:
                tb = make(self.title, name)
            except Exception:  # noqa: BLE001 — fall back to a plain one
                log.exception("%s: host toolbar builder failed", self.key)
                tb = None
        if tb is None:
            tb = QToolBar(self.title, self.window)
            tb.setObjectName(name)
            tb.setMovable(True)
            tb.setFloatable(True)
            tb.setIconSize(QSize(24, 24))
            tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.window.addToolBar(Qt.TopToolBarArea, tb)
        act = QAction(make_icon(), self.title, tb)
        act.setObjectName(f"{self.key}_action")
        act.setToolTip(self.tip)
        act.setStatusTip(self.tip)
        act.triggered.connect(self._run)
        tb.addAction(act)
        self._watcher = _ThemeWatcher(act, tb)
        QApplication.instance().installEventFilter(self._watcher)
        tb.visibilityChanged.connect(self._visibility_changed)
        return tb

    def _run(self, _checked: bool = False) -> None:
        self.run()

    def set_shown(self, on: bool) -> None:
        """Show or hide the toolbar (building it the first time)."""
        if on and self.toolbar is None:
            self.toolbar = self._build()
        if self.toolbar is not None:
            self.toolbar.setVisible(on)
        self._save(on)
        if self.check is not None and self.check.isChecked() != on:
            self.check.blockSignals(True)
            self.check.setChecked(on)
            self.check.blockSignals(False)

    def _visibility_changed(self, visible: bool) -> None:
        # Hidden while the window is minimised or closing is not a choice.
        if self.window.isMinimized() or not self.window.isVisible():
            return
        if self.check is not None and self.check.isChecked() != visible:
            self.check.blockSignals(True)
            self.check.setChecked(visible)
            self.check.blockSignals(False)
            self._save(visible)

    def attach_check(self, action: QAction) -> None:
        """Make ``action`` the menu's check box and apply the saved state."""
        self.check = action
        action.setCheckable(True)
        action.setChecked(self.saved())
        action.toggled.connect(self.set_shown)
        if self.saved():
            self.set_shown(True)
