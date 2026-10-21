# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The Cleaning dialog: what to clean, where, Analyse and Clean.

Modeless and reused. The choices are remembered in IngeTrazo's per-user
settings (``plugins/cleaning/options``, plain JSON).
"""
from __future__ import annotations

import json
import logging

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog,
                               QDoubleSpinBox, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton, QRadioButton,
                               QVBoxLayout, QWidget)

from core.history import CommandRejected

from . import geometry
from .command import CleanCommand, Options, preview
from .texts import t

log = logging.getLogger("ingetrazo.plugins")


def _rows() -> list[tuple[str, str, str, str]]:
    """``(option key, check box text, tooltip, result text)`` per item."""
    return [
        ("degenerate_faces", t("Repair degenerate faces"),
         t("Erase faces with no area (fewer than three distinct corners, "
           "or all of them on one line), and repair faces that list a "
           "corner twice."),
         t("Degenerate faces erased")),
        ("duplicate_faces", t("Erase duplicate faces"),
         t("Faces lying exactly on top of another face, on the same edges."),
         t("Duplicate faces erased")),
        ("coplanar_faces", t("Merge coplanar faces"),
         t("Remove the edge between two faces that lie in one plane, so "
           "they become one face."),
         t("Coplanar faces merged")),
        ("stray_edges", t("Erase stray edges"),
         t("Lines that border no face. A group made only of lines (a "
           "drawing) is left alone."),
         t("Stray edges erased")),
        ("split_edges", t("Repair split edges"),
         t("Join the collinear pieces of a line back into one edge, as "
           "Edit ▸ Join Segments does."),
         t("Split points removed")),
        ("duplicate_materials", t("Merge identical materials"),
         t("Materials with the same colour, texture, opacity and finish "
           "become one; the faces keep their look."),
         t("Identical materials merged")),
        ("unused_materials", t("Purge unused materials"),
         t("Materials no face and no group wears."),
         t("Unused materials purged")),
        ("unused_layers", t("Purge unused layers"),
         t("Layers nothing carries. Layers a scene hides are kept."),
         t("Unused layers purged")),
        ("empty_groups", t("Erase empty groups"),
         t("Groups and components with nothing inside. Locked ones are "
           "kept."),
         t("Empty groups erased")),
    ]


class CleaningDialog(QDialog):
    """Pick the items, the scope, then Analyse or Clean."""

    def __init__(self, viewport, key: str, title: str, toolbar=None,
                 parent=None) -> None:
        super().__init__(parent)
        self.viewport = viewport
        self.key = key
        self.toolbar = toolbar
        self._setting = f"plugins/{key}/options"
        self.setObjectName(f"{key}_dialog")
        self.setWindowTitle(title)
        self.setModal(False)
        self.checks: dict[str, QCheckBox] = {}
        self.counts: dict[str, QLabel] = {}
        self.results: dict[str, str] = {}
        self._build()
        self._load()

    # ---- layout -----------------------------------------------------------------
    def _build(self) -> None:
        rows = _rows()
        top = QVBoxLayout(self)
        geo = QGroupBox(t("Geometry"))
        doc = QGroupBox(t("Model (always the whole model)"))
        boxes = {"geometry": QGridLayout(geo), "document": QGridLayout(doc)}
        for key, text, tip, result in rows:
            grid = boxes["geometry" if key in Options.GEOMETRY else "document"]
            r = grid.rowCount()
            box = QCheckBox(text)
            box.setToolTip(tip)
            box.toggled.connect(self._changed)
            count = QLabel("")
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            count.setToolTip(result)
            grid.addWidget(box, r, 0)
            grid.addWidget(count, r, 1)
            self.checks[key] = box
            self.counts[key] = count
            self.results[key] = result
            if key == "degenerate_faces":
                self._add_count_row(grid, "repaired_faces",
                                    t("Faces with a repeated corner"),
                                    t("Faces with a repeated corner repaired"),
                                    indent=True)
                self._add_count_row(grid, "zero_edges",
                                    t("Zero-length edges"),
                                    t("Edges from a point to itself erased"),
                                    indent=True)
            if key == "coplanar_faces":
                grid.addWidget(self._coplanar_options(), r + 1, 0, 1, 2)
        self._add_count_row(boxes["geometry"], "loose_vertices",
                            t("Loose vertices (always)"),
                            t("Points no edge or face uses any more."))
        top.addWidget(geo)
        top.addWidget(doc)

        picks = QHBoxLayout()
        every = QPushButton(t("Select all"))
        every.clicked.connect(lambda _c=False: self._check_all(True))
        none = QPushButton(t("Select none"))
        none.clicked.connect(lambda _c=False: self._check_all(False))
        picks.addWidget(every)
        picks.addWidget(none)
        picks.addStretch(1)
        top.addLayout(picks)

        scope = QGroupBox(t("Apply to"))
        lay = QVBoxLayout(scope)
        self.scope_group = QButtonGroup(self)
        self.scopes: dict[str, QRadioButton] = {}
        for name, text, tip in (
                ("model", t("The whole model"),
                 t("The loose geometry and every group and component. Locked "
                   "groups are left alone.")),
                ("context", t("Only what is being edited"),
                 t("The open group, or the loose geometry when no group is "
                   "open.")),
                ("selection", t("Only the selection"),
                 t("The selected faces and edges, and the selected groups "
                   "whole."))):
            radio = QRadioButton(text)
            radio.setToolTip(tip)
            self.scope_group.addButton(radio)
            self.scopes[name] = radio
            lay.addWidget(radio)
        top.addWidget(scope)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        top.addWidget(self.status)

        self.show_toolbar = QCheckBox(t("Show in toolbar"))
        self.show_toolbar.setToolTip(t("Show or hide the Cleaning toolbar."))
        self.show_toolbar.setVisible(self.toolbar is not None)
        self.show_toolbar.toggled.connect(self._toolbar_toggled)
        if self.toolbar is not None:
            self.toolbar.listeners.append(self._toolbar_changed)
        top.addWidget(self.show_toolbar)

        buttons = QHBoxLayout()
        self.analyse_btn = QPushButton(t("Analyse"))
        self.analyse_btn.setToolTip(t("Count what would be cleaned, without "
                                      "changing the model."))
        self.analyse_btn.clicked.connect(lambda _c=False: self.analyse())
        self.clean_btn = QPushButton(t("Clean"))
        self.clean_btn.setToolTip(t("Clean the model. One undo step."))
        self.clean_btn.setDefault(True)
        self.clean_btn.clicked.connect(lambda _c=False: self.clean())
        close = QPushButton(t("Close"))
        close.clicked.connect(lambda _c=False: self.close())
        buttons.addWidget(self.analyse_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.clean_btn)
        buttons.addWidget(close)
        top.addLayout(buttons)

    def _add_count_row(self, grid, key: str, text: str, tip: str,
                       indent: bool = False) -> None:
        """A row with a count and no check box of its own."""
        label = QLabel(text)
        label.setToolTip(tip)
        if indent:
            label.setContentsMargins(24, 0, 0, 0)
        count = QLabel("")
        count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        count.setToolTip(tip)
        r = grid.rowCount()
        grid.addWidget(label, r, 0)
        grid.addWidget(count, r, 1)
        self.counts[key] = count
        self.results[key] = tip

    def _coplanar_options(self) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(QLabel(t("Angle tolerance")))
        self.angle = QDoubleSpinBox()
        self.angle.setRange(0.0, geometry.MAX_ANGLE_DEG)
        self.angle.setDecimals(3)
        self.angle.setSingleStep(0.01)
        self.angle.setSuffix(" °")
        self.angle.setToolTip(t("Faces whose planes differ by less than this "
                                "angle count as coplanar. Keep it small: a "
                                "finely divided curved surface is not flat."))
        self.angle.valueChanged.connect(self._changed)
        lay.addWidget(self.angle)
        self.same_material = QCheckBox(t("Only faces with the same material"))
        self.same_material.setToolTip(t("Leave the edge between two faces "
                                        "painted differently."))
        self.same_material.toggled.connect(self._changed)
        lay.addWidget(self.same_material)
        lay.addStretch(1)
        self._coplanar_box = box
        return box

    # ---- options ----------------------------------------------------------------
    def options(self) -> Options:
        opts = Options()
        for key, box in self.checks.items():
            setattr(opts, key, box.isChecked())
        opts.coplanar_angle = float(self.angle.value())
        opts.coplanar_same_material = self.same_material.isChecked()
        opts.scope = next((n for n, r in self.scopes.items() if r.isChecked()),
                          "model")
        return opts

    def set_options(self, opts: Options) -> None:
        for key, box in self.checks.items():
            box.blockSignals(True)
            box.setChecked(bool(getattr(opts, key)))
            box.blockSignals(False)
        self.angle.blockSignals(True)
        self.angle.setValue(opts.coplanar_angle)
        self.angle.blockSignals(False)
        self.same_material.blockSignals(True)
        self.same_material.setChecked(opts.coplanar_same_material)
        self.same_material.blockSignals(False)
        self.scopes.get(opts.scope, self.scopes["model"]).setChecked(True)
        self._refresh()

    def _load(self) -> None:
        raw = QSettings().value(self._setting, "")
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else {}
        except ValueError:
            log.warning("%s: ignoring unreadable saved options", self.key)
            data = {}
        self.set_options(Options.from_dict(data))

    def _save(self) -> None:
        QSettings().setValue(self._setting, json.dumps(self.options().to_dict()))

    def _check_all(self, on: bool) -> None:
        for box in self.checks.values():
            box.setChecked(on)

    def _changed(self, *_args) -> None:
        self._clear_counts()
        self._refresh()

    def _refresh(self) -> None:
        self._coplanar_box.setEnabled(self.checks["coplanar_faces"].isChecked())
        anything = any(b.isChecked() for b in self.checks.values())
        self.analyse_btn.setEnabled(anything)
        self.clean_btn.setEnabled(anything)
        editing = getattr(self.viewport.scene, "edit_group", None) is not None
        model = self.scopes["model"]
        model.setEnabled(not editing)
        if editing and model.isChecked():
            self.scopes["context"].setChecked(True)

    def _clear_counts(self) -> None:
        for label in self.counts.values():
            label.setText("")
        self.status.setText("")

    def _show_counts(self, report: dict, done: bool) -> None:
        opts = self.options()
        for key, label in self.counts.items():
            on = (key == "loose_vertices"
                  or (key in ("repaired_faces", "zero_edges")
                      and opts.degenerate_faces)
                  or getattr(opts, key, False))
            label.setText(str(report.get(key, 0)) if on else "")
        total = sum(report.values())
        if not total:
            self.status.setText(t("Nothing to clean: the model is already clean."))
        elif done:
            self.status.setText(t("Cleaned {n} items. Edit ▸ Undo puts them "
                                  "back.", n=total))
        else:
            self.status.setText(t("{n} items to clean.", n=total))

    # ---- toolbar check box ------------------------------------------------------
    def _toolbar_toggled(self, on: bool) -> None:
        if self.toolbar is not None and self.toolbar.shown() != on:
            self.toolbar.set_shown(on)

    def _toolbar_changed(self, on: bool) -> None:
        if self.show_toolbar.isChecked() != on:
            self.show_toolbar.blockSignals(True)
            self.show_toolbar.setChecked(on)
            self.show_toolbar.blockSignals(False)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        if self.toolbar is not None:
            self._toolbar_changed(self.toolbar.shown())
        self._refresh()
        super().showEvent(event)

    # ---- actions ------------------------------------------------------------------
    def _rejected_text(self, reason: str) -> str:
        if "group" in reason:
            return t("Close the group being edited to clean the whole model.")
        return t("Nothing to clean: the model is already clean.")

    def analyse(self) -> dict | None:
        """Count what Clean would do; the model is left as it was."""
        self._refresh()
        self._save()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = preview(self.viewport.scene, self.options())
        except CommandRejected as exc:
            self._clear_counts()
            self.status.setText(self._rejected_text(str(exc)))
            return None
        except Exception:  # noqa: BLE001 — report, never crash the app
            log.exception("%s: analysis failed", self.key)
            self._clear_counts()
            self.status.setText(t("The analysis failed. Details are in the log."))
            return None
        finally:
            QApplication.restoreOverrideCursor()
            self.viewport.update()
        self._show_counts(report, done=False)
        return report

    def clean(self) -> dict | None:
        """Run the clean-up as one undo step."""
        self._refresh()
        self._save()
        history = self.viewport.history
        cmd = CleanCommand(self.options())
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            history.execute(cmd)
        finally:
            QApplication.restoreOverrideCursor()
        if history.last_error:
            log.error("%s: clean-up failed: %s", self.key, history.last_error)
            self._clear_counts()
            self.status.setText(t("Cleaning failed; the model was left "
                                  "unchanged. Details are in the log."))
            self.viewport.update()
            return None
        rejected = getattr(history, "last_rejected", None)
        if rejected:
            self._show_counts({}, done=True)
            self.status.setText(self._rejected_text(rejected))
            self.viewport.update()
            return None
        self.viewport.notify_scene_changed()
        self._show_counts(cmd.report, done=True)
        flash = getattr(self.viewport, "flash_status", None)
        if flash:
            flash(t("Cleaned {n} items.", n=cmd.total), 4000)
        return dict(cmd.report)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._save()
        super().closeEvent(event)
