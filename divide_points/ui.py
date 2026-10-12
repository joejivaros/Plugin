# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The Divide Points dialog: modeless, follows the selection, previews the
points in the viewport and places them as one undo step."""
from __future__ import annotations

import logging
import math

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QGridLayout,
                               QGroupBox, QLabel, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout)

from . import geometry, scene_ops
from .texts import t

log = logging.getLogger("ingetrazo.plugins")

#: Bare-number unit labels (a value typed without a unit in IngeTrazo is in
#: this unit — the imperial "feet and inches" styles read bare numbers as
#: inches, see core.units.bare_number_scale).
_BARE_LABEL = {"ft-in": "in", "in-frac": "in", "ft-in-frac": "in"}


def model_unit() -> tuple[float, str, int]:
    """``(metres per unit, unit label, decimals)`` of the document."""
    try:
        from core import units
        code = units.model_unit()
        return (float(units.bare_number_scale()), _BARE_LABEL.get(code, code),
                max(2, int(units.model_precision())))
    except Exception:  # noqa: BLE001 — units are a display nicety
        log.exception("divide_points: cannot read the model units")
        return 1.0, "m", 3


def fmt_len(metres: float) -> str:
    """A length in the document's units and precision."""
    try:
        from core.units import fmt_len as _fmt
        return _fmt(metres)
    except Exception:  # noqa: BLE001
        return f"{metres:.3f} m"


class DividePointsDialog(QDialog):
    """Settings + live preview + Place / Delete buttons."""

    def __init__(self, viewport, key: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.viewport = viewport
        self.key = key
        self.setObjectName(f"{key}_dialog")
        self.setWindowTitle(title)
        self._paths: list = []
        self._points: list = []
        self._sig = None

        lay = QVBoxLayout(self)
        self.sel_label = QLabel(self)
        self.sel_label.setWordWrap(True)
        lay.addWidget(self.sel_label)

        # Spacing ------------------------------------------------------------
        box = QGroupBox(t("Spacing"), self)
        grid = QGridLayout(box)
        self.r_count = QRadioButton(t("Number of points"), box)
        self.r_dist = QRadioButton(t("Distance between points"), box)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.r_count)
        self.mode_group.addButton(self.r_dist)
        self.count = QSpinBox(box)
        self.count.setRange(1, geometry.MAX_POINTS)
        self.count.setValue(5)
        self.dist = QDoubleSpinBox(box)
        grid.addWidget(self.r_count, 0, 0)
        grid.addWidget(self.count, 0, 1)
        grid.addWidget(self.r_dist, 1, 0)
        grid.addWidget(self.dist, 1, 1)
        self.limit_on = QCheckBox(t("Limit the number of points"), box)
        self.limit = QSpinBox(box)
        self.limit.setRange(1, geometry.MAX_POINTS)
        self.limit.setValue(3)
        grid.addWidget(self.limit_on, 2, 0)
        grid.addWidget(self.limit, 2, 1)
        lay.addWidget(box)

        # Origin -------------------------------------------------------------
        box2 = QGroupBox(t("Start from"), self)
        v2 = QVBoxLayout(box2)
        self.r_ends = QRadioButton(t("Both ends"), box2)
        self.r_mid = QRadioButton(t("The middle"), box2)
        self.origin_group = QButtonGroup(self)
        self.origin_group.addButton(self.r_ends)
        self.origin_group.addButton(self.r_mid)
        v2.addWidget(self.r_ends)
        v2.addWidget(self.r_mid)
        self.origin_help = QLabel(box2)
        self.origin_help.setWordWrap(True)
        v2.addWidget(self.origin_help)
        lay.addWidget(box2)

        self.info = QLabel(self)
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        buttons = QDialogButtonBox(self)
        self.b_place = QPushButton(t("Place Points"), self)
        self.b_place.setDefault(True)
        self.b_delete = QPushButton(t("Delete Placed Points"), self)
        self.b_delete.setToolTip(t("Erase every guide point this plugin "
                                   "placed in the model (one undo step)."))
        b_close = QPushButton(t("Close"), self)
        buttons.addButton(self.b_place, QDialogButtonBox.AcceptRole)
        buttons.addButton(self.b_delete, QDialogButtonBox.ActionRole)
        buttons.addButton(b_close, QDialogButtonBox.RejectRole)
        lay.addWidget(buttons)

        self.r_count.setChecked(True)
        self.r_ends.setChecked(True)
        self.limit_on.setChecked(False)
        self._apply_units()

        for w in (self.r_count, self.r_dist, self.r_ends, self.r_mid,
                  self.limit_on):
            w.toggled.connect(self._changed)
        self.count.valueChanged.connect(self._changed)
        self.limit.valueChanged.connect(self._changed)
        self.dist.valueChanged.connect(self._changed)
        self.b_place.clicked.connect(self._place)
        self.b_delete.clicked.connect(self._delete)
        b_close.clicked.connect(self.close)

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._poll)

    # ---- units ---------------------------------------------------------------
    def _apply_units(self) -> None:
        """Show the distance in the document's current unit."""
        old_m = getattr(self, "_dist_m", None)
        self._scale, unit, dec = model_unit()
        self.dist.blockSignals(True)
        self.dist.setDecimals(dec)
        self.dist.setRange(geometry.MIN_SPACING / self._scale, 1.0e6)
        self.dist.setSuffix(f" {unit}")
        self.dist.setValue(old_m / self._scale if old_m else 1.0)
        self.dist.blockSignals(False)
        self._dist_m = self.dist.value() * self._scale

    # ---- life cycle ------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self._apply_units()
        self._sig = None
        self._poll()
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._timer.stop()
        self._set_preview([])
        super().hideEvent(event)

    def _selection_sig(self):
        scene = self.viewport.scene
        return (id(scene), getattr(scene, "version", None),
                frozenset(id(e) for e in scene.selection))

    def _poll(self) -> None:
        try:
            sig = self._selection_sig()
            if sig == self._sig:
                return
            self._sig = sig
            self._paths = scene_ops.selected_paths(self.viewport.scene)
        except Exception:  # noqa: BLE001 — never break the timer
            log.exception("divide_points: cannot read the selection")
            self._paths = []
        self._changed()

    # ---- settings → points -----------------------------------------------------
    def settings(self) -> dict:
        """The current settings as :func:`geometry.place` keyword arguments
        (lengths in metres)."""
        self._dist_m = self.dist.value() * self._scale
        mode = (geometry.MODE_COUNT if self.r_count.isChecked()
                else geometry.MODE_DISTANCE)
        origin = (geometry.ORIGIN_MIDDLE if self.r_mid.isChecked()
                  else geometry.ORIGIN_ENDS)
        kw = {"mode": mode, "origin": origin}
        if mode == geometry.MODE_COUNT:
            kw["count"] = int(self.count.value())
        else:
            kw["spacing"] = float(self._dist_m)
            if self.limit_on.isChecked():
                kw["limit"] = int(self.limit.value())
        return kw

    def _origin_text(self, kw) -> str:
        if kw["mode"] == geometry.MODE_COUNT:
            if kw["origin"] == geometry.ORIGIN_ENDS:
                return t("The first and last point are on the ends; equal gaps.")
            return t("The points stay off the ends, centred; equal gaps.")
        if kw["origin"] == geometry.ORIGIN_ENDS:
            return t("Points walk in from both ends; the remainder is left in "
                     "the middle.")
        if "limit" in kw:
            return t("Points are centred on the midpoint: an odd number puts "
                     "one on it, an even number puts it between two.")
        return t("Points walk out from the midpoint; the remainder is left at "
                 "both ends.")

    def _changed(self, *_args) -> None:
        self.count.setEnabled(self.r_count.isChecked())
        self.dist.setEnabled(self.r_dist.isChecked())
        self.limit_on.setEnabled(self.r_dist.isChecked())
        self.limit.setEnabled(self.r_dist.isChecked() and
                              self.limit_on.isChecked())
        kw = self.settings()
        self.origin_help.setText(self._origin_text(kw))

        if not self._paths:
            self.sel_label.setText(t("Select one or more lines or curves in "
                                     "the model."))
            self._fail("")
            return
        total = sum(p.length for p in self._paths)
        self.sel_label.setText(t("Selected: {paths} path(s), total length "
                                 "{length}.", paths=len(self._paths),
                                 length=fmt_len(total)))
        try:
            pts = geometry.place(self._paths, **kw)
        except geometry.PlacementError as exc:
            self._fail(t(exc.message, **exc.kwargs))
            return
        self._points = pts
        lines = [t("Points to place: {n}", n=len(pts))]
        if len(self._paths) == 1:
            p = self._paths[0]
            params = geometry.positions(p.length, closed=p.closed, **kw)
            g = geometry.gaps(params)
            if g:
                lo, hi = min(g), max(g)
                if math.isclose(lo, hi, rel_tol=1e-6, abs_tol=1e-7):
                    lines.append(t("Gap: {gap}", gap=fmt_len(lo)))
                else:
                    lines.append(t("Gaps: {small} to {large}",
                                   small=fmt_len(lo), large=fmt_len(hi)))
        if "limit" in kw and len(pts) < kw["limit"] * len(self._paths):
            lines.append(t("Not all points fit on the path."))
        self.info.setStyleSheet("")
        self.info.setText("\n".join(lines))
        self.b_place.setEnabled(bool(pts))
        self._set_preview(pts)

    def _fail(self, message: str) -> None:
        self._points = []
        self.info.setStyleSheet("color: #c0392b;" if message else "")
        self.info.setText(message)
        self.b_place.setEnabled(False)
        self._set_preview([])

    def _set_preview(self, pts) -> None:
        scene_ops.PREVIEW[:] = list(pts)
        self.viewport.update()

    # ---- actions ---------------------------------------------------------------
    def _status(self, text: str) -> None:
        flash = getattr(self.viewport, "flash_status", None)
        if flash:
            flash(text, 4000)

    def _place(self) -> None:
        if not self._points:
            return
        try:
            n = scene_ops.add_points(self.viewport, self.key, self._points)
        except Exception:  # noqa: BLE001 — report, never crash the app
            log.exception("divide_points: placing the points failed")
            self._fail(t("The points could not be placed. Details are in the "
                         "log."))
            return
        if n:
            self._status(t("{n} guide points placed.", n=n))
        else:
            self._status(t("Every point already has a guide point."))
        self._sig = None
        self._poll()

    def _delete(self) -> None:
        try:
            n = scene_ops.delete_points(self.viewport, self.key)
        except Exception:  # noqa: BLE001
            log.exception("divide_points: deleting the points failed")
            self._fail(t("The points could not be deleted. Details are in the "
                         "log."))
            return
        self._status(t("{n} guide points deleted.", n=n))
        self._sig = None
        self._poll()
