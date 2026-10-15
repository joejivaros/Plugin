# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Export the automation as an MP4 video, through FFmpeg.

The automation is played frame by frame, not in real time: each frame is
rendered off screen at the chosen size (``viewport.render_image``), so the
video is smooth whatever the machine. Frames go to ffmpeg's standard input;
the scenes' sounds are mixed in at the times they start. A continuous
automation (Loops 0) is recorded once.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QMessageBox,
                               QProgressDialog, QPushButton, QVBoxLayout)

from . import host, media
from .player import Sequencer, timeline
from .texts import t
from .ui_lists import seconds_text

log = logging.getLogger("ingetrazo.plugins")

SIZES = (("hd", 1280, 720), ("fullhd", 1920, 1080), ("view", None, None))
RATES = (24, 30, 60)


def settings_key(app_key: str, name: str) -> str:
    return f"plugins/{app_key}/{name}"


def ffmpeg_dir(app_key: str) -> str | None:
    """The FFmpeg folder the user picked, if any (else the PATH is used)."""
    value = QSettings().value(settings_key(app_key, media.SETTINGS_DIR_KEY), "")
    return value if isinstance(value, str) and value else None


def pick_ffmpeg_dir(parent, app_key: str) -> bool:
    """Let the user show where ``ffmpeg`` is; True when it is there."""
    start = ffmpeg_dir(app_key) or ""
    folder = QFileDialog.getExistingDirectory(
        parent, t("Folder that contains ffmpeg, ffprobe and ffplay"), start)
    if not folder:
        return False
    if media.find_tool("ffmpeg", folder) is None:
        QMessageBox.warning(parent, t("Export MP4"),
                            t("There is no ffmpeg program in that folder."))
        return False
    QSettings().setValue(settings_key(app_key, media.SETTINGS_DIR_KEY),
                         folder)
    return True


def view_size(viewport) -> tuple[int, int]:
    """The 3D view in device pixels, rounded down to even numbers (H.264
    wants them even)."""
    dpr = viewport.devicePixelRatioF() if hasattr(
        viewport, "devicePixelRatioF") else 1.0
    w = max(64, int(viewport.width() * dpr)) & ~1
    h = max(64, int(round(w * viewport.height() / max(1, viewport.width()))))
    return w, h & ~1


class ExportDialog(QDialog):
    """Size, frame rate and where FFmpeg is."""

    def __init__(self, app_key: str, viewport, duration: float, sounds: int,
                 continuous: bool, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenes_play_export")
        self.setWindowTitle(t("Export MP4"))
        self.app_key = app_key
        settings = QSettings()
        w, h = view_size(viewport)
        self.size_box = QComboBox()
        for key, text in (("hd", t("1280 × 720 (HD)")),
                          ("fullhd", t("1920 × 1080 (Full HD)")),
                          ("view", t("The 3D view as it is ({w} × {h})",
                                     w=w, h=h))):
            self.size_box.addItem(text, key)
        self._select(self.size_box,
                     settings.value(settings_key(app_key, "export_size"),
                                    "fullhd"))
        self.rate_box = QComboBox()
        for fps in RATES:
            self.rate_box.addItem(t("{n} frames per second", n=fps), fps)
        try:
            fps = int(settings.value(settings_key(app_key, "export_fps"), 30))
        except (TypeError, ValueError):
            fps = 30
        self._select(self.rate_box, fps)
        self.ffmpeg_label = QLabel()
        self.ffmpeg_label.setWordWrap(True)
        locate = QPushButton(t("FFmpeg folder…"))
        locate.clicked.connect(self._locate)
        about = QLabel(t("Length: {time}", time=seconds_text(duration))
                       + ("  ·  " + t("{n} sound(s)", n=sounds)
                          if sounds else ""))
        form = QFormLayout()
        form.addRow(t("Size:"), self.size_box)
        form.addRow(t("Frame rate:"), self.rate_box)
        row = QHBoxLayout()
        row.addWidget(self.ffmpeg_label, 1)
        row.addWidget(locate)
        form.addRow(t("FFmpeg:"), row)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(about)
        if continuous:
            note = QLabel(t("Loops is 0 (continuous): the video holds one "
                            "pass."))
            note.setWordWrap(True)
            lay.addWidget(note)
        hint = QLabel(t("Dimensions and texts are only drawn at the 3D "
                        "view's own size."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(t("Export…"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._refresh()

    @staticmethod
    def _select(box: QComboBox, value) -> None:
        i = box.findData(value)
        if i >= 0:
            box.setCurrentIndex(i)

    def _locate(self) -> None:
        pick_ffmpeg_dir(self, self.app_key)
        self._refresh()

    def _refresh(self) -> None:
        exe = media.find_tool("ffmpeg", ffmpeg_dir(self.app_key))
        self.ffmpeg_label.setText(str(exe) if exe else t(
            "Not found. Install FFmpeg (ffmpeg.org) and show its folder."))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(exe is not None)

    def choice(self) -> tuple[str, int]:
        key, fps = self.size_box.currentData(), int(self.rate_box.currentData())
        settings = QSettings()
        settings.setValue(settings_key(self.app_key, "export_size"), key)
        settings.setValue(settings_key(self.app_key, "export_fps"), fps)
        return key, fps


def export_video(parent, app_key: str, window, steps, loops: int) -> None:
    """Ask the options and the file, then record. Errors are shown."""
    vp = window.viewport
    start = host.Camera(window).pose()
    duration, sounds = timeline(steps, loops, start)
    if duration <= 0:
        QMessageBox.warning(parent, t("Export MP4"),
                            t("The sequence lasts 0 seconds: nothing to "
                              "record."))
        return
    if len(sounds) > media.MAX_SOUNDS:
        QMessageBox.warning(parent, t("Export MP4"),
                            t("Too many sounds for one video (more than "
                              "{n}).", n=media.MAX_SOUNDS))
        return
    dlg = ExportDialog(app_key, vp, duration, len(sounds), loops == 0, parent)
    if dlg.exec() != QDialog.Accepted:
        return
    size_key, fps = dlg.choice()
    folder = ffmpeg_dir(app_key)
    last = QSettings().value(settings_key(app_key, "export_dir"), "")
    out, _f = QFileDialog.getSaveFileName(
        parent, t("Export MP4"), str(Path(last if isinstance(last, str)
                                          else "") / "automation.mp4"),
        t("MP4 video (*.mp4)"))
    if not out:
        return
    out_path = Path(out)
    if out_path.suffix.lower() != ".mp4":
        out_path = out_path.with_name(out_path.name + ".mp4")
    QSettings().setValue(settings_key(app_key, "export_dir"),
                         str(out_path.parent))
    if size_key == "view":
        (width, height), exact = view_size(vp), False
    else:
        _k, width, height = next(s for s in SIZES if s[0] == size_key)
        exact = True
    try:
        _record(parent, window, steps, loops, start, duration, sounds,
                out_path, width, height, exact, fps, folder)
    except media.MediaError as exc:
        log.warning("scenes_play: export failed: %s", exc)
        QMessageBox.warning(parent, t("Export MP4"),
                            t("The video could not be made: {error}",
                              error=t(exc.message, **exc.fields)))


def _record(parent, window, steps, loops, start, duration, sounds, out_path,
            width, height, exact, fps, folder) -> None:
    ffmpeg = media.find_tool("ffmpeg", folder)
    if ffmpeg is None:
        raise media.MediaError("FFmpeg (ffmpeg) was not found.")
    vp = window.viewport
    host.Camera(window).set_pose(start)
    frames = max(1, int(math.ceil(duration * fps)))
    encoder = media.Encoder(media.export_args(
        str(ffmpeg), str(out_path), width, height, fps, duration, sounds))
    progress = QProgressDialog(t("Recording the video…"), t("Cancel"), 0,
                               frames, parent)
    progress.setWindowTitle(t("Export MP4"))
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    seq = Sequencer(steps, loops or 1, host.Camera(window))
    seq.start()
    try:
        for k in range(frames):
            if k:
                seq.advance(1.0 / fps)
            image = host.render_frame(vp, width, height if exact else None)
            if image is None:
                raise media.MediaError("The 3D view could not be rendered.")
            if image.width() != width or image.height() != height:
                image = image.copy(0, 0, width, height)
            encoder.write(image.constBits().tobytes())
            progress.setValue(k + 1)
            QApplication.processEvents()
            if progress.wasCanceled():
                encoder.abort()
                QMessageBox.information(
                    parent, t("Export MP4"),
                    t("Export cancelled; {file} is incomplete.",
                      file=out_path.name))
                return
        encoder.finish()
    except media.MediaError:
        encoder.abort()
        raise
    finally:
        progress.close()
    QMessageBox.information(parent, t("Export MP4"),
                            t("Video saved: {file}", file=str(out_path)))
