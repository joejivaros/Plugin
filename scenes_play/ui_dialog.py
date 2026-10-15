# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The Scene Automation window: build the sequence, save it, play it.

One modeless window, reused. Its title names the automation — the file it
was saved to or loaded from — or says it is not saved; a ``*`` marks
changes since the last Save, Load or Apply, and closing with such changes
asks first.

- **Load / Save**: an automation file (JSON) the user picks.
- **Cancel**: back to the state of the last Save, Load or Apply.
- **Apply**: keep the automation in the model (saved in the ``.igz``, one
  undo step); it comes back when the model is opened again.
- **Play**: hide this window, show the small player bar, play (in full
  screen when «Full screen» is checked), with the scenes' sounds.
- **Export MP4…**: record the sequence as a video (:mod:`export`).

Sounds are attached per row (Sound column, or right-click); FFmpeg
measures them (:mod:`media`).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from . import host, media
from .model import (AUDIO_SUFFIXES, LOOPS_MAX, TRAVEL_MAX, WAIT_MAX,
                    Automation, AutomationError, Entry, safe_audio_path)
from .texts import t
from .ui_lists import (COL_SCENE, COL_START, COL_STOP, COL_TRAVEL, COL_WAIT,
                       ActiveModel, ActiveTable, InactiveList, ease_names,
                       seconds_text)

log = logging.getLogger("ingetrazo.plugins")

DOC_VERSION = 1                 # layout of the document data
MAX_FILE_BYTES = 1_000_000


class GlobalRow(QWidget):
    """Above the Active list, lined up with its columns: «All» checks or
    unchecks every entry, and the four values are written into every
    checked entry as soon as they change (or again with «Set»)."""

    def __init__(self, table: ActiveTable, parent=None) -> None:
        super().__init__(parent)
        self.table = table
        self.model: ActiveModel = table.model()
        self.all = QCheckBox(t("All"), self)
        self.all.setTristate(True)
        self.all.setToolTip(t("Check or uncheck every scene of the sequence."))
        self.all.clicked.connect(self._on_all)
        self.set_btn = QPushButton(t("Set"), self)
        self.set_btn.setToolTip(t("Copy these four values to every checked "
                                  "scene."))
        self.set_btn.clicked.connect(self._on_set)
        self.start = self._combo()
        self.stop = self._combo()
        self.travel = self._spin(TRAVEL_MAX, 3.0)
        self.wait = self._spin(WAIT_MAX, 5.0)
        self.start.activated.connect(
            lambda _i: self.model.set_checked_field("start",
                                                    self.start.currentData()))
        self.stop.activated.connect(
            lambda _i: self.model.set_checked_field("stop",
                                                    self.stop.currentData()))
        self.travel.valueChanged.connect(
            lambda v: self.model.set_checked_field("travel", float(v)))
        self.wait.valueChanged.connect(
            lambda v: self.model.set_checked_field("wait", float(v)))
        for w, tip in ((self.start, t("How fast every checked move gets "
                                      "going.")),
                       (self.stop, t("How fast every checked move comes to "
                                     "rest at its scene.")),
                       (self.travel, t("Seconds every checked move takes "
                                       "from the previous scene.")),
                       (self.wait, t("Seconds every checked scene stays on "
                                     "screen."))):
            w.setToolTip(tip)
        self.setFixedHeight(max(self.start.sizeHint().height(),
                                self.all.sizeHint().height()) + 4)
        head = table.horizontalHeader()
        head.sectionResized.connect(lambda *_a: self._place())
        head.geometriesChanged.connect(self._place)
        self.model.modelReset.connect(self.sync_all)
        self.model.dataChanged.connect(lambda *_a: self.sync_all())
        self.sync_all()

    def _combo(self) -> QComboBox:
        box = QComboBox(self)
        for key, text in ease_names().items():
            box.addItem(text, key)
        box.setCurrentIndex(1)                   # Medium
        return box

    def _spin(self, top: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(0.0, top)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" " + t("s"))
        spin.setKeyboardTracking(False)
        spin.setAccelerated(True)
        spin.setValue(value)
        return spin

    def new_entry(self, name: str) -> Entry:
        """A scene added to the sequence takes these four values."""
        return Entry(name, True, self.start.currentData(),
                     self.stop.currentData(), float(self.travel.value()),
                     float(self.wait.value()))

    def _on_set(self) -> None:
        for field, value in (("start", self.start.currentData()),
                             ("stop", self.stop.currentData()),
                             ("travel", float(self.travel.value())),
                             ("wait", float(self.wait.value()))):
            self.model.set_checked_field(field, value)

    def _on_all(self) -> None:
        entries = self.model.entries
        self.model.set_all_enabled(not (entries and
                                        all(e.enabled for e in entries)))
        self.sync_all()

    def sync_all(self) -> None:
        entries = self.model.entries
        on = sum(1 for e in entries if e.enabled)
        state = (Qt.Checked if entries and on == len(entries)
                 else Qt.PartiallyChecked if on else Qt.Unchecked)
        self.all.blockSignals(True)
        self.all.setCheckState(state)
        self.all.blockSignals(False)

    # ---- Lining up with the table's columns --------------------------------
    def _place(self) -> None:
        head = self.table.horizontalHeader()
        left = self.table.frameWidth() + self.table.verticalHeader().width()
        h = self.height() - 4
        for col, w in ((COL_START, self.start), (COL_STOP, self.stop),
                       (COL_TRAVEL, self.travel), (COL_WAIT, self.wait)):
            w.setGeometry(left + head.sectionViewportPosition(col), 2,
                          head.sectionSize(col), h)
        scene_x = left + head.sectionViewportPosition(COL_SCENE)
        scene_w = head.sectionSize(COL_SCENE)
        self.all.setGeometry(scene_x + 4, 2, self.all.sizeHint().width(), h)
        bw = self.set_btn.sizeHint().width()
        self.set_btn.setGeometry(scene_x + scene_w - bw - 4, 2, bw, h)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._place()


class AutomationDialog(QDialog):
    """The plugin's window."""

    def __init__(self, app, plugin_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenes_play_dialog")
        self.app = app
        self.plugin_name = plugin_name
        self.setModal(False)
        self.resize(940, 500)
        self._name: str | None = None
        self._baseline = Automation().to_dict()
        self._doc_seen = None
        self._player = None
        self._settings = QSettings()
        self._key = f"plugins/{app.key}"

        self.model = ActiveModel(self)
        self.table = ActiveTable(self.model, lambda n: self.globals.new_entry(n))
        self.globals = GlobalRow(self.table)
        self.inactive = InactiveList(self.table)
        self.loops = QSpinBox()
        self.loops.setRange(0, LOOPS_MAX)
        self.loops.setValue(1)
        self.loops.setSpecialValueText(t("Continuous"))
        self.loops.setToolTip(t("How many times the sequence is played; 0 "
                                "plays it continuously until Stop."))
        self.full_screen = QCheckBox(t("Full screen"))
        self.full_screen.setToolTip(t("Play with only the 3D view, on the "
                                      "whole screen. Esc stops."))
        self.full_screen.setChecked(
            str(self._settings.value(f"{self._key}/full_screen", "false"))
            .lower() == "true")
        self.full_screen.toggled.connect(
            lambda on: self._settings.setValue(f"{self._key}/full_screen",
                                               bool(on)))
        self.single = QLabel()
        self.total = QLabel()
        self.status = QLabel()
        self.status.setStyleSheet("color: gray;")
        self.status.setWordWrap(True)
        self.buttons = {}
        self._build()

        self.table.sound_requested.connect(self.attach_sound)
        self.model.edited.connect(self._on_edited)
        self.loops.valueChanged.connect(lambda _v: self._on_edited())
        self.inactive.add_requested.connect(self.table.add_names)
        self.inactive.rows_returned.connect(self.model.remove_rows)

        self._load_document_data(force=True)
        self.on_document_changed()
        geometry = self._settings.value(f"{self._key}/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _build(self) -> None:
        bold = "font-weight: bold;"
        left = QVBoxLayout()
        title = QLabel(t("Active"))
        title.setStyleSheet(bold)
        hint = QLabel(t("Drag scenes here from Inactive, and rows to reorder "
                        "them. Ctrl+D duplicates, Del removes, Space checks."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        left.addWidget(title)
        left.addWidget(hint)
        left.addWidget(self.globals)
        left.addWidget(self.table, 1)
        loops_row = QHBoxLayout()
        loops_row.addWidget(QLabel(t("Loops:")))
        loops_row.addWidget(self.loops)
        loops_row.addSpacing(12)
        loops_row.addWidget(self.full_screen)
        loops_row.addSpacing(16)
        times = QVBoxLayout()
        times.addWidget(self.single)
        times.addWidget(self.total)
        loops_row.addLayout(times, 1)
        left.addLayout(loops_row)
        left.addWidget(self.status)

        middle = QVBoxLayout()
        title = QLabel(t("Inactive"))
        title.setStyleSheet(bold)
        middle.addWidget(title)
        hint = QLabel(t("Scenes of the model not in the sequence."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        middle.addWidget(hint)
        middle.addWidget(self.inactive, 1)

        right = QVBoxLayout()
        right.addStretch(1)
        for key, text, tip, fn in (
                ("load", t("Load"), t("Open a saved automation file."),
                 self.load),
                ("save", t("Save"), t("Save the automation to a file."),
                 self.save),
                ("cancel", t("Cancel"), t("Undo the changes made since the "
                                          "last Save, Load or Apply."),
                 self.revert),
                ("apply", t("Apply"), t("Keep the automation in this model "
                                        "(saved with it); does not play."),
                 self.apply),
                ("play", t("Play"), t("Play the checked scenes."),
                 self.play),
                ("export", t("Export MP4…"), t("Record the sequence as an "
                                               "MP4 video (needs FFmpeg)."),
                 self.export)):
            btn = QPushButton(text)
            btn.setObjectName(f"scenes_play_{key}")
            btn.setToolTip(tip)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda _c=False, f=fn: f())
            right.addWidget(btn)
            self.buttons[key] = btn

        lay = QHBoxLayout(self)
        lay.addLayout(left, 3)
        lay.addLayout(middle, 1)
        lay.addLayout(right)

    # ---- The automation being edited ------------------------------------------
    def current(self) -> Automation:
        return Automation([e.copy() for e in self.model.entries],
                          self.loops.value())

    def set_current(self, auto: Automation) -> None:
        self.model.set_entries(auto.entries)
        self.loops.blockSignals(True)
        self.loops.setValue(auto.loops)
        self.loops.blockSignals(False)
        self._on_edited()

    def is_dirty(self) -> bool:
        return self.current().to_dict() != self._baseline

    def _mark_clean(self) -> None:
        self._baseline = self.current().to_dict()
        self._refresh()

    def _on_edited(self) -> None:
        self._refresh_inactive()
        self._refresh()

    def _refresh(self) -> None:
        name = self._name or t("Not saved")
        self.setWindowTitle(t("{plugin}: {name}", plugin=self.plugin_name,
                              name=name) + "[*]")
        dirty = self.is_dirty()
        self.setWindowModified(dirty)
        self.buttons["cancel"].setEnabled(dirty)
        auto = self.current()
        names = host.scene_names(self.app.scene)
        played = len(auto.played(names))
        single = auto.single_runtime(names, host.sound_ok)
        self.single.setText(t("Scenes played: {n}   Single run: {time}",
                              n=played, time=seconds_text(single)))
        total = auto.total_runtime(names, host.sound_ok)
        self.total.setText(t("Total: plays continuously") if total is None
                           else t("Total for all loops: {time}",
                                  time=seconds_text(total)))
        self.buttons["play"].setEnabled(played > 0)
        self.buttons["export"].setEnabled(played > 0)

    def _refresh_inactive(self) -> None:
        used = {e.scene for e in self.model.entries}
        self.inactive.set_names([n for n in host.scene_names(self.app.scene)
                                 if n not in used])

    def say(self, text: str) -> None:
        self.status.setText(text)

    # ---- The model's side ----------------------------------------------------------
    def on_document_changed(self) -> None:
        """An edit, undo, New or Open: scenes may have come or gone, and the
        model may carry another automation."""
        self.model.set_available(host.scene_names(self.app.scene))
        self._load_document_data()
        self._refresh_inactive()
        self._refresh()

    def _load_document_data(self, force: bool = False) -> None:
        """Show the automation kept in the model when it changed (another
        model opened, Apply undone) — unless there are unsaved edits."""
        data = self.app.document_data()
        if not force and data == self._doc_seen:
            return
        self._doc_seen = data
        if data is None or (self.is_dirty() and not force):
            return
        try:
            auto, name = _read_document_data(data)
        except AutomationError as exc:
            log.warning("scenes_play: automation in the model ignored: %s",
                        exc)
            self.say(t("The automation kept in the model cannot be read: "
                       "{error}", error=t(exc.message, **exc.fields)))
            return
        self._name = name
        self.set_current(auto)
        self._mark_clean()

    # ---- Buttons ---------------------------------------------------------------------
    def _start_dir(self) -> str:
        value = self._settings.value(f"{self._key}/last_dir", "")
        return value if isinstance(value, str) else ""

    def save(self) -> bool:
        """Save to a file the user picks; False when nothing was saved."""
        start = str(Path(self._start_dir()) / f"{self._name or 'automation'}"
                                              ".json")
        path, _f = QFileDialog.getSaveFileName(
            self, t("Save scene automation"), start,
            t("Scene automation (*.json)"))
        if not path:
            return False
        path = Path(path)
        if path.suffix.lower() != ".json":
            path = path.with_name(path.name + ".json")
        text = json.dumps(self.current().to_dict(), indent=2,
                          ensure_ascii=False)
        try:
            path.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            log.exception("scenes_play: cannot save %s", path)
            QMessageBox.warning(self, self.plugin_name,
                                t("The automation could not be saved: "
                                  "{error}", error=exc.strerror or str(exc)))
            return False
        self._settings.setValue(f"{self._key}/last_dir", str(path.parent))
        self._name = path.stem
        self._mark_clean()
        self.say(t("Saved to {file}.", file=path.name))
        return True

    def load(self) -> None:
        if not self._may_discard():
            return
        path, _f = QFileDialog.getOpenFileName(
            self, t("Load scene automation"), self._start_dir(),
            t("Scene automation (*.json)"))
        if not path:
            return
        path = Path(path)
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise AutomationError("The file is too large.")
            raw = json.loads(path.read_text(encoding="utf-8"))
            auto = Automation.from_dict(raw)
        except OSError as exc:
            log.warning("scenes_play: cannot read %s: %s", path, exc)
            self._error(t("The file could not be read: {error}",
                          error=exc.strerror or str(exc)))
            return
        except (UnicodeDecodeError, ValueError) as exc:
            log.warning("scenes_play: %s rejected: %s", path, exc)
            msg = (t(exc.message, **exc.fields)
                   if isinstance(exc, AutomationError)
                   else t("This is not a scene automation."))
            self._error(msg)
            return
        self._settings.setValue(f"{self._key}/last_dir", str(path.parent))
        self._name = path.stem
        self.set_current(auto)
        self._mark_clean()
        missing = sum(1 for e in auto.entries if self.model.missing(e))
        silent = sum(1 for e in auto.entries
                     if e.audio and not host.sound_ok(e))
        self.say(t("Loaded {file}.", file=path.name) + (
            " " + t("{n} scene(s) of it are not in this model.", n=missing)
            if missing else "") + (
            " " + t("{n} sound file(s) are missing.", n=silent)
            if silent else ""))

    def _ffmpeg_dir(self) -> str | None:
        value = self._settings.value(f"{self._key}/{media.SETTINGS_DIR_KEY}",
                                     "")
        return value if isinstance(value, str) and value else None

    def attach_sound(self, rows) -> None:
        """Pick a sound file for ``rows``, measure it with ffprobe and
        attach it; their Wait then lasts at least as long as the sound."""
        if not rows:
            return
        from .export import pick_ffmpeg_dir
        if media.find_tool("ffprobe", self._ffmpeg_dir()) is None:
            answer = QMessageBox.question(
                self, self.plugin_name,
                t("Sounds need FFmpeg (free, ffmpeg.org), which was not "
                  "found. Show the folder where it is installed?"),
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes)
            if answer != QMessageBox.Yes \
                    or not pick_ffmpeg_dir(self, self.app.key):
                return
        start = self._settings.value(f"{self._key}/sound_dir", "")
        pattern = " ".join(f"*{s}" for s in AUDIO_SUFFIXES)
        path, _f = QFileDialog.getOpenFileName(
            self, t("Attach sound"), start if isinstance(start, str) else "",
            t("Sound ({patterns})", patterns=pattern))
        if not path:
            return
        path = str(Path(path))
        if safe_audio_path(path) is None:
            self._error(t("This sound cannot be used: pick a sound file on "
                          "this computer (not on a network share)."))
            return
        try:
            length = media.probe_length(path, self._ffmpeg_dir())
        except media.MediaError as exc:
            self._error(t(exc.message, **exc.fields))
            return
        if length > WAIT_MAX:
            self._error(t("The sound is longer than {time}.",
                          time=seconds_text(WAIT_MAX)))
            return
        self._settings.setValue(f"{self._key}/sound_dir",
                                str(Path(path).parent))
        self.model.set_sound(rows, path, length)
        self.say(t("Sound attached: {file} ({time}).", file=Path(path).name,
                   time=seconds_text(length)))

    def revert(self) -> None:
        if not self.is_dirty():
            return
        try:
            self.set_current(Automation.from_dict(self._baseline))
        except AutomationError:            # our own data: cannot happen
            log.exception("scenes_play: cannot revert")
            return
        self._refresh()
        self.say(t("Changes undone."))

    def apply(self) -> bool:
        """Keep the automation in the model: one undo step."""
        data = {"version": DOC_VERSION, "name": self._name,
                "automation": self.current().to_dict()}
        try:
            self.app.set_document_data(data)
        except Exception:  # noqa: BLE001 — report, never crash the app
            log.exception("scenes_play: Apply failed")
            self._error(t("The automation could not be kept in the model. "
                          "Details are in the log."))
            return False
        error = getattr(self.app.viewport.history, "last_error", None)
        if error:
            log.error("scenes_play: Apply failed: %s", error)
            self._error(t("The automation could not be kept in the model. "
                          "Details are in the log."))
            return False
        self._doc_seen = self.app.document_data()
        self._mark_clean()
        self.say(t("Kept in the model. Save the model to keep it there."))
        return True

    def play(self) -> None:
        names = host.scene_names(self.app.scene)
        auto = self.current()
        steps = host.build_steps(self.app.scene, auto.played(names))
        if not steps:
            self._error(t("No checked scene of the sequence is in the model."))
            return
        sound = None
        if any(s.audio for s in steps):
            sound = media.SoundPlayer(self._ffmpeg_dir())
            if not sound.available:
                sound = None
                QMessageBox.information(
                    self, self.plugin_name,
                    t("FFmpeg (ffplay) was not found: playing without "
                      "sound."))
        from .ui_player import PlaybackController
        if self._player is None:
            self._player = PlaybackController(self.app.window, self.plugin_name,
                                              self)
            self._player.finished.connect(self._on_played)
        self.hide()
        self._player.play(steps, auto.loops, self.full_screen.isChecked(),
                          sound)

    def export(self) -> None:
        names = host.scene_names(self.app.scene)
        auto = self.current()
        steps = host.build_steps(self.app.scene, auto.played(names))
        if not steps:
            self._error(t("No checked scene of the sequence is in the model."))
            return
        from .export import export_video
        try:
            export_video(self, self.app.key, self.app.window, steps,
                         auto.loops)
        except Exception:  # noqa: BLE001 — report, never crash the app
            log.exception("scenes_play: export failed")
            self._error(t("The video could not be made. Details are in the "
                          "log."))

    def _on_played(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    @property
    def playing(self) -> bool:
        return self._player is not None and self._player.active

    def stop_playing(self) -> None:
        if self._player is not None:
            self._player.stop()

    # ---- Closing -----------------------------------------------------------------------
    def _may_discard(self) -> bool:
        """True when unsaved changes may go: saved, discarded or none."""
        if not self.is_dirty():
            return True
        answer = QMessageBox.question(
            self, self.plugin_name,
            t("The automation has changes that are not saved. Save them "
              "first?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save()
        return answer == QMessageBox.Discard

    def closeEvent(self, event) -> None:
        if not self._may_discard():
            event.ignore()
            return
        if self.is_dirty():                 # discarded: start from the last
            self.revert()                   # saved state next time
            self.say("")
        self._settings.setValue(f"{self._key}/geometry", self.saveGeometry())
        # Not QDialog.closeEvent: it calls reject(), which closes again.
        event.accept()

    def reject(self) -> None:
        """Esc closes through closeEvent, so it asks too."""
        self.close()

    def _error(self, text: str) -> None:
        self.say(text)
        QMessageBox.warning(self, self.plugin_name, text)


def _read_document_data(data) -> tuple[Automation, str | None]:
    """The automation and its name kept in the model; AutomationError when
    the data is not ours or is damaged."""
    if not isinstance(data, dict):
        raise AutomationError("This is not a scene automation.")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) \
            or version < 1:
        raise AutomationError("This is not a scene automation.")
    if version > DOC_VERSION:
        raise AutomationError(
            "This automation was made by a newer version of the plugin.")
    name = data.get("name")
    if name is not None and (not isinstance(name, str) or len(name) > 200):
        name = None
    return Automation.from_dict(data.get("automation")), name
