# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The optional Cleaning toolbar and its icon.

The icon is drawn with QPainter (no image file), the way IngeTrazo draws
its own (views/icons.py): 48 px, the palette's text colour as ink, a 3 px
pen, and the accent colour chosen in Preferences (orange by default). It
is redrawn when the theme or the accent changes.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QToolBar

log = logging.getLogger("ingetrazo.plugins")

ORANGE = QColor(243, 115, 41)       # IngeTrazo's default accent
ICON_PX = 48


def _ink() -> QColor:
    app = QApplication.instance()
    if app is None:
        return QColor(40, 44, 52)
    return QColor(app.palette().windowText().color())


def accent() -> QColor:
    """The accent in force (IngeTrazo ≥ 0.5.9), else the orange."""
    try:
        from views.theme import accent_color
        return QColor(accent_color())
    except Exception:  # noqa: BLE001 — older host or no theme module
        return QColor(ORANGE)


def _sparkle(p: QPainter, cx: float, cy: float, r: float) -> None:
    """A four-pointed star, filled."""
    k = r * 0.3
    path = QPainterPath(QPointF(cx, cy - r))
    for x, y in ((cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
                 (cx, cy + r), (cx - k, cy + k), (cx - r, cy),
                 (cx - k, cy - k)):
        path.lineTo(QPointF(x, y))
    path.closeSubpath()
    p.fillPath(path, p.brush())


def draw_icon(p: QPainter, ink: QColor, accent_color: QColor) -> None:
    """A broom (ink) sweeping, with sparkles (accent) where it cleaned."""
    pen = QPen(ink, 3.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(42, 5), QPointF(25, 23))            # the handle
    head = QPainterPath(QPointF(20, 20))                   # the bristles
    head.lineTo(QPointF(28, 28))
    head.lineTo(QPointF(21, 44))
    head.lineTo(QPointF(4, 27))
    head.closeSubpath()
    p.drawPath(head)
    thin = QPen(ink, 2.0)
    thin.setCapStyle(Qt.RoundCap)
    p.setPen(thin)
    p.drawLine(QPointF(22, 26), QPointF(14, 38))
    p.drawLine(QPointF(17, 22), QPointF(9, 33))
    p.setPen(Qt.NoPen)
    p.setBrush(accent_color)
    _sparkle(p, 37.0, 36.0, 7.0)
    _sparkle(p, 44.0, 24.0, 4.0)
    p.drawEllipse(QPointF(31.0, 45.0), 1.8, 1.8)


def make_icon(accent_color: QColor | None = None) -> QIcon:
    pm = QPixmap(ICON_PX, ICON_PX)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        p.setClipRect(QRectF(0, 0, ICON_PX, ICON_PX))
        draw_icon(p, _ink(), accent_color or accent())
    finally:
        p.end()
    return QIcon(pm)


class _ThemeWatcher(QObject):
    """Redraws the icon when the theme changes its ink colour, or the
    accent changed (Preferences repaints the window; it sends no event).

    Installed on the toolbar alone, never on the whole application: Qt
    sends ``PaletteChange`` to every widget whose palette or stylesheet
    changes, so an application-wide filter rebuilt the icon each time
    another extension restyled its own widgets (many times per second with
    some of them). A theme switch re-palettes the toolbar too, so it still
    arrives here, and the icon is redrawn only if a colour really changed."""

    _EVENTS = (QEvent.ApplicationPaletteChange, QEvent.PaletteChange,
               QEvent.ThemeChange, QEvent.Paint)

    def __init__(self, action: QAction, parent) -> None:
        super().__init__(parent)
        self.action = action
        self.colours = self._colours()

    @staticmethod
    def _colours() -> tuple:
        return _ink().rgba(), accent().rgba()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt override
        if obj is self.parent() and event.type() in self._EVENTS:
            colours = self._colours()
            if colours != self.colours:
                self.colours = colours
                self.action.setIcon(make_icon())
        return False


class ToolbarSwitch:
    """Creates the toolbar on first need and keeps the menu check box, the
    dialog's check box, the toolbar's visibility and the saved setting in
    step. Hiding the toolbar from Qt's toolbar right-click menu clears the
    check boxes."""

    def __init__(self, window, key: str, title: str, tip: str, run) -> None:
        self.window = window
        self.key = key
        self.title = title
        self.tip = tip
        self.run = run
        self.toolbar: QToolBar | None = None
        self.check: QAction | None = None
        #: Called with the new state (the dialog's check box listens).
        self.listeners: list = []
        self._setting = f"plugins/{key}/show_toolbar"

    # ---- setting -------------------------------------------------------------
    def saved(self) -> bool:
        return str(QSettings().value(self._setting, "0")) in ("1", "true")

    def _save(self, on: bool) -> None:
        QSettings().setValue(self._setting, "1" if on else "0")

    def shown(self) -> bool:
        return self.toolbar is not None and self.toolbar.isVisible()

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
        tb.installEventFilter(self._watcher)
        tb.visibilityChanged.connect(self._visibility_changed)
        return tb

    def _run(self, _checked: bool = False) -> None:
        self.run()

    def _sync(self, on: bool) -> None:
        if self.check is not None and self.check.isChecked() != on:
            self.check.blockSignals(True)
            self.check.setChecked(on)
            self.check.blockSignals(False)
        for listener in list(self.listeners):
            listener(on)

    def set_shown(self, on: bool) -> None:
        """Show or hide the toolbar (building it the first time)."""
        on = bool(on)
        if on and self.toolbar is None:
            self.toolbar = self._build()
        if self.toolbar is not None:
            self.toolbar.setVisible(on)
        self._save(on)
        self._sync(on)

    def _visibility_changed(self, visible: bool) -> None:
        # Hidden while the window is minimised or closing is not a choice.
        if self.window.isMinimized() or not self.window.isVisible():
            return
        if self.check is not None and self.check.isChecked() != visible:
            self._save(visible)
            self._sync(visible)

    def attach_check(self, action: QAction) -> None:
        """Make ``action`` the menu's check box and apply the saved state."""
        self.check = action
        action.setCheckable(True)
        action.setChecked(self.saved())
        action.toggled.connect(self.set_shown)
        if self.saved():
            self.set_shown(True)
