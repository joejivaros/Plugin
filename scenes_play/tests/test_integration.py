# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The plugin inside IngeTrazo: loading, the window, Apply / Save / Load,
closing with changes, and a playback over a real scene list and camera.

Runs headless (``QT_QPA_PLATFORM=offscreen``); skipped when IngeTrazo is
not importable — set ``INGETRAZO_ROOT`` to a checkout.
"""
from __future__ import annotations

import importlib
import json
import math
import shutil
import sys

import pytest

from conftest import PLUGIN_DIR, needs_ingetrazo

pytestmark = needs_ingetrazo

KEY = "scenes_play"


@pytest.fixture(scope="module")
def plugin(tmp_path_factory):
    """The plugin loaded by IngeTrazo's own discovery, from a copy."""
    from core.extensions import discover_plugins
    root = tmp_path_factory.mktemp("plugins")
    shutil.copytree(PLUGIN_DIR, root / KEY,
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    plugins, errors = discover_plugins([root])
    assert not errors, [e.message for e in errors]
    assert [p.stem for p in plugins] == [KEY]
    pkg = f"ingetrazo_plugin_{KEY}"
    mods = {name: importlib.import_module(f"{pkg}.{name}")
            for name in ("model", "host", "ui_lists", "ui_dialog",
                         "ui_player", "player")}
    return {"loaded": plugins[0], "pkg": sys.modules[pkg], **mods}


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName("scenes_play_tests")
    QCoreApplication.setApplicationName("scenes_play_tests")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(tmp_path_factory.mktemp("settings")))
    return app


class FakeTool:
    def __init__(self, name):
        self.name = name


class FakeViewport:
    def __init__(self, scene, history):
        from core.camera import OrbitCamera
        self.scene = scene
        self.history = history
        self.camera = OrbitCamera()
        self.active_tool = None
        self.flashed = []

    def notify_scene_changed(self):
        pass

    def update(self):
        pass

    def flash_status(self, text, ms):
        self.flashed.append(text)


def _window(scene, history):
    """A QWidget standing in for the main window (tools, no tray)."""
    from PySide6.QtWidgets import QWidget

    class FakeWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.viewport = FakeViewport(scene, history)
            self._tools = {"select": FakeTool("Select"),
                           "look_around": FakeTool("Look Around")}
            self.viewport.active_tool = self._tools["select"]
            self.tray = None

        def _activate_tool(self, key):
            self.viewport.active_tool = self._tools[key]

    return FakeWindow()


class FakeApp:
    """The ExtensionApp calls the plugin uses, over a real History."""

    def __init__(self, window):
        self.key = KEY
        self.window = window
        self.viewport = window.viewport
        self.actions = []
        self.doc_hooks = []

    @property
    def scene(self):
        return self.viewport.scene

    def document_data(self, default=None):
        data = self.scene.plugin_data
        return json.loads(json.dumps(data[KEY])) if KEY in data else default

    def set_document_data(self, value):
        from core.history import SetPluginDataCommand
        self.viewport.history.execute(SetPluginDataCommand(KEY, value))

    def add_menu_action(self, text, fn, shortcut=None, tip=None):
        self.actions.append((text, fn, tip))

    def on_document_changed(self, fn):
        self.doc_hooks.append(fn)


def _view(name, x, distance=10.0, yaw=0.0, pitch=0.3):
    from core.saved_views import SavedView
    return SavedView(name, target=(x, 0.0, 0.0), distance=distance, yaw=yaw,
                     pitch=pitch)


@pytest.fixture
def app(qapp):
    from core.history import History
    from core.scene import Scene
    scene = Scene()
    scene.saved_views = [_view("Front", 0.0), _view("Side", 10.0, yaw=1.5),
                         _view("Top", 20.0, distance=40.0, pitch=1.4),
                         _view("Detail", 30.0, distance=2.0)]
    return FakeApp(_window(scene, History(scene)))


@pytest.fixture
def dialog(plugin, app):
    dlg = plugin["ui_dialog"].AutomationDialog(app, "Scene Automation")
    yield dlg
    dlg._baseline = dlg.current().to_dict()     # no prompt on teardown
    dlg.close()
    dlg.deleteLater()


def _names(dlg):
    return [e.scene for e in dlg.model.entries]


def _inactive(dlg):
    return [dlg.inactive.item(i).text() for i in range(dlg.inactive.count())]


# ---- Loading -----------------------------------------------------------------
def test_plugin_loads_with_a_setup(plugin):
    loaded = plugin["loaded"]
    assert loaded.tools == []
    assert loaded.setup is not None
    assert plugin["pkg"].PLUGIN_ID == KEY
    assert plugin["pkg"].VERSION == "0.2.1"


def test_header_matches_constants(plugin):
    doc_ = plugin["pkg"].__doc__
    assert f"Plugin-ID:      {plugin['pkg'].PLUGIN_ID}" in doc_
    assert f"Version:        {plugin['pkg'].VERSION}" in doc_
    assert f"Name:           {plugin['pkg'].NAME}" in doc_


def test_setup_registers_the_menu_entry(plugin, app):
    plugin["loaded"].setup(app)
    assert len(app.actions) == 1 and app.actions[0][2]
    assert len(app.doc_hooks) == 1
    app.doc_hooks[0]()                      # no window yet: nothing to do


# ---- The window --------------------------------------------------------------
def test_new_window_lists_every_scene_as_inactive(dialog):
    assert _names(dialog) == []
    assert _inactive(dialog) == ["Front", "Side", "Top", "Detail"]
    assert "Not saved" in dialog.windowTitle()
    assert not dialog.buttons["play"].isEnabled()


def test_adding_moves_scenes_out_of_inactive(dialog):
    dialog.table.add_names(["Top", "Front"])
    assert _names(dialog) == ["Top", "Front"]
    assert _inactive(dialog) == ["Side", "Detail"]
    assert dialog.isWindowModified()
    assert dialog.buttons["play"].isEnabled()


def test_runtime_labels(dialog):
    dialog.table.add_names(["Front", "Side"])
    dialog.model.entries[0].wait = 100.0     # 3 + 100 + 3 + 5 = 111 s
    dialog.loops.setValue(3)                 # 333 s
    assert "2" in dialog.single.text() and "111 s" in dialog.single.text()
    assert "5:33" in dialog.total.text()
    dialog.loops.setValue(0)
    assert dialog.total.text() == "Total: plays continuously"


def test_global_row_writes_only_checked_entries(dialog, plugin):
    dialog.table.add_names(["Front", "Side", "Top"])
    m = dialog.model
    from PySide6.QtCore import Qt
    m.setData(m.index(1, 0), Qt.Unchecked, Qt.CheckStateRole)
    dialog.globals.travel.setValue(9.0)
    dialog.globals.stop.setCurrentIndex(0)
    dialog.globals.stop.activated.emit(0)    # "slow", as a user pick
    assert [e.travel for e in m.entries] == [9.0, 3.0, 9.0]
    assert [e.stop for e in m.entries] == ["slow", "medium", "slow"]
    assert dialog.globals.all.checkState() == Qt.PartiallyChecked
    dialog.globals.all.click()
    assert all(e.enabled for e in m.entries)


def test_new_entries_take_the_global_values(dialog):
    dialog.globals.wait.setValue(42.0)
    dialog.table.add_names(["Detail"])
    assert dialog.model.entries[0].wait == 42.0


def test_reorder_duplicate_copy_paste_remove(dialog):
    t = dialog.table
    t.add_names(["Front", "Side", "Top", "Detail"])
    t.select_rows([0, 2])
    assert dialog.model.move_rows([0, 2], 4) == [2, 3]
    assert _names(dialog) == ["Side", "Detail", "Front", "Top"]
    t.select_rows([1])
    t.duplicate_selected()
    assert _names(dialog) == ["Side", "Detail", "Detail", "Front", "Top"]
    assert t.selected_rows() == [2]
    t.select_rows([0])
    t.copy_selected()
    t.select_rows([4])
    t.paste()
    assert _names(dialog)[-1] == "Side"
    t.select_rows([0, 1])
    t.remove_selected()
    assert _names(dialog) == ["Detail", "Front", "Top", "Side"]
    assert _inactive(dialog) == []


def test_keys_on_the_active_list(dialog):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    t = dialog.table
    t.add_names(["Front", "Side"])
    t.select_rows([0])
    QTest.keyClick(t, Qt.Key_D, Qt.ControlModifier)
    assert _names(dialog) == ["Front", "Front", "Side"]
    QTest.keyClick(t, Qt.Key_Space)
    assert not dialog.model.entries[1].enabled
    QTest.keyClick(t, Qt.Key_Delete)
    assert _names(dialog) == ["Front", "Side"]


def _drop(table, mime, row):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QDropEvent
    m = table.model()
    if row < m.rowCount():
        rect = table.visualRect(m.index(row, 0))
        pos = QPointF(rect.center().x(), rect.top() + 2)
    else:
        pos = QPointF(5, table.viewport().height() - 2)
    event = QDropEvent(pos, Qt.CopyAction | Qt.MoveAction, mime,
                       Qt.LeftButton, Qt.NoModifier)
    table.dropEvent(event)
    return event


def test_drop_names_and_own_rows(dialog, plugin):
    from PySide6.QtCore import QMimeData
    lists = plugin["ui_lists"]
    dialog.resize(900, 500)
    dialog.show()
    t = dialog.table
    mime = QMimeData()
    mime.setData(lists.MIME_NAMES, json.dumps(["Top", "Side"]).encode())
    _drop(t, mime, 0)
    assert _names(dialog) == ["Top", "Side"]
    mime = QMimeData()
    mime.setData(lists.MIME_ROWS, json.dumps(
        {"source": dialog.model.token, "rows": [1]}).encode())
    _drop(t, mime, 0)
    assert _names(dialog) == ["Side", "Top"]
    foreign = QMimeData()
    foreign.setData(lists.MIME_ROWS, json.dumps(
        {"source": "someone else", "rows": [0]}).encode())
    _drop(t, foreign, 0)
    assert _names(dialog) == ["Side", "Top"]


def test_missing_scene_is_shown_and_skipped(dialog, app):
    dialog.table.add_names(["Front", "Side"])
    app.scene.saved_views = [v for v in app.scene.saved_views
                             if v.name != "Side"]
    dialog.on_document_changed()
    index = dialog.model.index(1, 0)
    assert "(missing)" in index.data()
    assert "Scenes played: 1" in dialog.single.text()


# ---- Apply / Cancel / Save / Load ----------------------------------------------
def test_apply_keeps_it_in_the_model_as_one_undo_step(dialog, app, plugin):
    dialog.table.add_names(["Front", "Top"])
    assert dialog.apply()
    data = app.scene.plugin_data[KEY]
    assert data["version"] == 1
    assert [e["scene"] for e in data["automation"]["entries"]] == \
        ["Front", "Top"]
    assert len(app.viewport.history.undo_stack) == 1
    assert not dialog.isWindowModified()
    # A new window on the same model shows it.
    again = plugin["ui_dialog"].AutomationDialog(app, "Scene Automation")
    assert _names(again) == ["Front", "Top"]
    again.deleteLater()
    app.viewport.history.undo()
    assert KEY not in app.scene.plugin_data


def test_applied_automation_survives_save_and_reopen(dialog, app, tmp_path):
    from core.scene import Scene
    from formats import igz
    dialog.table.add_names(["Side"])
    dialog.apply()
    path = tmp_path / "m.igz"
    igz.save_scene(app.scene, path)
    back = Scene()
    igz.load_into(back, path)
    assert back.plugin_data[KEY]["automation"]["entries"][0]["scene"] == \
        "Side"


def test_cancel_reverts_to_the_last_apply(dialog):
    dialog.table.add_names(["Front"])
    dialog.apply()
    dialog.table.add_names(["Top"])
    assert dialog.buttons["cancel"].isEnabled()
    dialog.revert()
    assert _names(dialog) == ["Front"]
    assert not dialog.isWindowModified()


def test_save_and_load_a_file(dialog, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    target = tmp_path / "Scenario demo"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    dialog.table.add_names(["Top", "Front"])
    dialog.loops.setValue(2)
    assert dialog.save()
    saved = tmp_path / "Scenario demo.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["loops"] == 2
    assert dialog.windowTitle().startswith("Scene Automation: Scenario demo")
    assert not dialog.isWindowModified()

    dialog.model.remove_rows([0, 1])
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(saved), "")))
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Discard))
    dialog.load()
    assert _names(dialog) == ["Top", "Front"]
    assert dialog.loops.value() == 2


@pytest.mark.parametrize("content", [
    "not json", json.dumps({"format": "other"}),
    json.dumps({"format": "scenes_play.automation", "version": 1,
                "entries": [{"scene": "A", "travel": 1e9}]}),
])
def test_bad_file_is_refused(dialog, monkeypatch, tmp_path, content):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(bad), "")))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    dialog.table.add_names(["Front"])
    dialog._mark_clean()
    dialog.load()
    assert warned and _names(dialog) == ["Front"]


def test_bad_document_data_is_ignored(plugin, app):
    app.scene.plugin_data[KEY] = {"version": 1, "automation": "junk"}
    dlg = plugin["ui_dialog"].AutomationDialog(app, "Scene Automation")
    assert _names(dlg) == [] and dlg.status.text()
    dlg.deleteLater()


def test_closing_with_changes_asks(dialog, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    dialog.show()
    dialog.table.add_names(["Front"])
    answers = [QMessageBox.Cancel]
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: answers.pop(0)))
    assert not dialog.close()
    assert dialog.isVisible()
    answers.append(QMessageBox.Discard)
    assert dialog.close()
    assert _names(dialog) == []               # discarded


# ---- Playing ---------------------------------------------------------------------
def test_playback_moves_the_camera_and_brings_the_window_back(dialog, app):
    cam = app.viewport.camera
    dialog.table.add_names(["Front", "Detail"])
    for e in dialog.model.entries:
        e.travel, e.wait = 2.0, 1.0
    dialog.show()
    dialog.play()
    player = dialog._player
    assert dialog.playing and not dialog.isVisible()
    assert player.bar.isVisible()
    seq = player.seq
    seq.advance(1.0)                         # half way to Front
    assert 0.0 < cam.distance < 20.0 or cam.target.x() != 0.0
    seq.advance(1.5)                         # at Front, waiting
    assert cam.target.x() == pytest.approx(0.0)
    assert cam.distance == pytest.approx(10.0)
    seq.advance(1.0)                         # half way to Detail
    assert 0.0 < cam.target.x() < 30.0
    assert 2.0 < cam.distance < 10.0
    seq.advance(5.0)                         # done
    assert not dialog.playing
    assert dialog.isVisible() and not player.bar.isVisible()
    assert cam.target.x() == pytest.approx(30.0)
    assert cam.distance == pytest.approx(2.0)


def test_pause_looks_around_and_resume_gives_the_tool_back(dialog, app):
    win = app.window
    dialog.table.add_names(["Front"])
    dialog.loops.setValue(0)
    dialog.play()
    player = dialog._player
    player.toggle_pause()
    assert player.seq.paused
    assert win.viewport.active_tool is win._tools["look_around"]
    player.toggle_pause()
    assert not player.seq.paused
    assert win.viewport.active_tool is win._tools["select"]
    player.toggle_pause()
    player.stop()
    assert win.viewport.active_tool is win._tools["select"]
    assert not dialog.playing and dialog.isVisible()


def test_a_scene_deleted_while_playing_stops(dialog, app):
    dialog.table.add_names(["Front", "Side"])
    dialog.play()
    app.scene.saved_views = [v for v in app.scene.saved_views
                             if v.name != "Front"]
    dialog._player.seq.advance(10.0)
    assert not dialog.playing and dialog.isVisible()


def test_camera_pose_round_trip(plugin, app):
    host = plugin["host"]
    cam = host.Camera(app.window)
    view = app.scene.saved_views[2]
    pose = host.pose_of_view(view)
    cam.set_pose(pose)
    back = cam.pose()
    assert back.close_to(pose)
    assert math.isfinite(back.distance)


# ---- Against IngeTrazo's real main window ----------------------------------------
@pytest.fixture
def real_window(qapp, monkeypatch, tmp_path):
    import core.extensions
    from core.saved_views import SavedView
    from views.main_window import MainWindow
    # The user's own plugins (maybe an installed copy of this one) stay out.
    empty = tmp_path / "no_user_plugins"
    empty.mkdir()
    monkeypatch.setattr(core.extensions, "user_plugins_dir", lambda: empty)
    win = MainWindow()
    scene, cam = win.viewport.scene, win.viewport.camera
    cam.yaw, cam.pitch, cam.distance = 0.3, 0.4, 30.0
    scene.saved_views.append(SavedView.capture("A", scene, cam))
    cam.yaw, cam.pitch, cam.distance = 1.2, 0.9, 12.0
    scene.saved_views.append(SavedView.capture("B", scene, cam))
    win.tray.scenes.refresh()
    win._saved_version = scene.version
    yield win
    win._saved_version = scene.version
    win.close()


def test_real_window_menu_playback_and_look_around(plugin, real_window):
    from views.extension_api import ExtensionApp
    win = real_window
    pkg = plugin["pkg"]
    before = {a.text() for a in win._ext_menu.actions()}
    pkg.setup(ExtensionApp(win, KEY))
    added = {a.text() for a in win._ext_menu.actions()} - before
    assert added == {"Scene Automation…"}

    pkg.show_dialog(ExtensionApp(win, KEY))
    dlg = pkg._STATE["dialog"]
    try:
        assert _inactive(dlg) == ["A", "B"]
        dlg.table.add_names(["A", "B"])
        dlg.play()
        seq = dlg._player.seq
        cam = win.viewport.camera
        seq.advance(4.0)                      # at A (travel 3), waiting
        assert cam.distance == pytest.approx(30.0)
        assert cam.yaw == pytest.approx(0.3)
        dlg._player.toggle_pause()
        assert win.viewport.active_tool is win._tools["look_around"]
        dlg._player.toggle_pause()
        assert win.viewport.active_tool is not win._tools["look_around"]
        seq.advance(12.5)                     # rest of A (wait 5), B, done
        assert cam.distance == pytest.approx(12.0)
        assert not dlg.playing and dlg.isVisible()
        assert not win._is_dirty()            # camera-only scenes
    finally:
        dlg._baseline = dlg.current().to_dict()
        dlg.close()
        pkg._STATE["dialog"] = None


def test_real_window_full_screen_and_back(plugin, real_window):
    from views.extension_api import ExtensionApp
    win = real_window
    pkg = plugin["pkg"]
    pkg.show_dialog(ExtensionApp(win, KEY))
    dlg = pkg._STATE["dialog"]
    try:
        assert not win._act_clean_screen.isChecked()
        dlg.table.add_names(["A"])
        dlg.full_screen.setChecked(True)
        dlg.play()
        assert win._act_clean_screen.isChecked()
        assert win.isFullScreen()
        assert win.menuBar().isHidden()
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        esc = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        assert dlg._player.eventFilter(win.viewport, esc)   # Esc stops
        assert not dlg.playing
        assert not win._act_clean_screen.isChecked()
        assert not win.isFullScreen()
    finally:
        dlg.full_screen.setChecked(False)
        dlg._baseline = dlg.current().to_dict()
        dlg.close()
        pkg._STATE["dialog"] = None


# ---- Sounds and video ------------------------------------------------------------
@pytest.fixture
def sound_file(tmp_path):
    path = tmp_path / "voice.mp3"
    path.write_bytes(b"not really audio")      # ffprobe is faked
    return path


def _fake_probe(monkeypatch, plugin, length=12.0):
    from pathlib import Path
    media = importlib.import_module(f"ingetrazo_plugin_{KEY}.media")
    monkeypatch.setattr(media, "find_tool",
                        lambda name, folder=None: Path(f"/fake/{name}"))
    monkeypatch.setattr(media, "probe_length",
                        lambda path, folder=None: length)
    return media


def test_attach_a_sound(dialog, plugin, monkeypatch, sound_file):
    from PySide6.QtWidgets import QFileDialog
    _fake_probe(monkeypatch, plugin)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(sound_file), "")))
    dialog.table.add_names(["Front", "Side"])          # 3 + 5 each
    dialog.attach_sound([1])
    e = dialog.model.entries[1]
    assert e.audio == str(sound_file) and e.audio_length == 12.0
    assert "Single run: 23 s" in dialog.single.text()  # 8 + 3 + 12
    text = dialog.model.index(1, plugin["ui_lists"].COL_SOUND).data()
    assert "voice.mp3" in text and "12 s" in text
    dialog.table.select_rows([1])
    dialog.table.remove_sound()
    assert dialog.model.entries[1].audio is None


def test_attach_refuses_a_network_file(dialog, plugin, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    _fake_probe(monkeypatch, plugin)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(
        lambda *a, **k: ("\\\\server\\share\\voice.mp3", "")))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    dialog.table.add_names(["Front"])
    dialog.attach_sound([0])
    assert warned and dialog.model.entries[0].audio is None


def test_a_missing_sound_file_plays_silent(dialog, plugin):
    dialog.table.add_names(["Front"])
    dialog.model.set_sound([0], "C:\\gone\\voice.mp3", 30.0)
    assert "Single run: 8 s" in dialog.single.text()   # not stretched
    assert "(missing)" in dialog.model.index(
        0, plugin["ui_lists"].COL_SOUND).data()


def test_playback_starts_the_sound_on_arrival(dialog, plugin, monkeypatch,
                                              sound_file):
    media = _fake_probe(monkeypatch, plugin)
    played = []

    class FakePlayer:
        available = True

        def __init__(self, folder=None):
            pass

        def start(self, step, offset):
            played.append((step.view.name, offset))

        def stop(self):
            played.append("stop")

    monkeypatch.setattr(media, "SoundPlayer", FakePlayer)
    dialog.table.add_names(["Front"])
    dialog.model.set_sound([0], str(sound_file), 10.0)
    dialog.play()
    seq = dialog._player.seq
    seq.advance(3.5)
    assert ("Front", 0.0) in played
    seq.advance(9.4)                          # still in the 10 s stay
    assert dialog.playing
    seq.advance(0.2)                          # 3 + 10 s: done
    assert not dialog.playing and played[-1] == "stop"


def test_export_pipes_every_frame_to_ffmpeg(dialog, plugin, monkeypatch,
                                            app, sound_file, tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QMessageBox
    media = _fake_probe(monkeypatch, plugin)
    export = importlib.import_module(f"ingetrazo_plugin_{KEY}.export")
    host = plugin["host"]
    got = {"frames": 0, "args": None, "finished": False}

    class FakeEncoder:
        def __init__(self, args):
            got["args"] = args

        def write(self, frame):
            assert len(frame) == 64 * 36 * 4
            got["frames"] += 1

        def finish(self):
            got["finished"] = True

        def abort(self):
            pass

    def fake_render(viewport, width, height):
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(0xFF336699)
        return image

    monkeypatch.setattr(media, "Encoder", FakeEncoder)
    monkeypatch.setattr(host, "render_frame", fake_render)
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    dialog.table.add_names(["Front", "Side"])
    for e in dialog.model.entries:
        e.travel, e.wait = 1.0, 1.0
    dialog.model.set_sound([1], str(sound_file), 1.5)
    steps = host.build_steps(app.scene, dialog.current().played(
        host.scene_names(app.scene)))
    start = host.Camera(app.window).pose()
    duration, sounds = plugin["player"].timeline(steps, 1, start)
    assert duration == pytest.approx(4.5)
    export._record(None, app.window, steps, 1, start, duration, sounds,
                   tmp_path / "v.mp4", 64, 36, True, 10, None)
    assert got["frames"] == 45 and got["finished"]
    args = got["args"]
    assert f"file:{sound_file}" in args
    graph = args[args.index("-filter_complex") + 1]
    assert "adelay=delays=3000" in graph       # Side arrives at 1 + 1 + 1
    assert app.viewport.camera.target.x() == pytest.approx(10.0)
