# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 <Author>
"""The plugin inside IngeTrazo: loading, undo, saving, dialog, overlay.

Runs headless (``QT_QPA_PLATFORM=offscreen``); skipped when IngeTrazo is
not importable — set ``INGETRAZO_ROOT`` to a checkout.
"""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from conftest import PLUGIN_DIR, needs_ingetrazo

pytestmark = needs_ingetrazo

KEY = "divide_points"


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
    return {"loaded": plugins[0], "pkg": sys.modules[pkg],
            "ops": importlib.import_module(f"{pkg}.scene_ops"),
            "geo": importlib.import_module(f"{pkg}.geometry"),
            "ui": importlib.import_module(f"{pkg}.ui")}


class FakeViewport:
    def __init__(self, scene, history):
        self.scene = scene
        self.history = history
        self.notified = 0
        self.flashed = []

    def notify_scene_changed(self):
        self.notified += 1

    def update(self):
        pass

    def flash_status(self, text, ms):
        self.flashed.append(text)

    def window(self):
        return None


@pytest.fixture
def doc():
    from PySide6.QtGui import QVector3D

    from core.history import History
    from core.scene import Scene
    scene = Scene()
    edge = scene.mesh.add_edge(QVector3D(0, 0, 0), QVector3D(10, 0, 0))
    scene.selection.add(edge)
    return FakeViewport(scene, History(scene))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_plugin_loads_with_a_setup(plugin):
    loaded = plugin["loaded"]
    assert loaded.tools == []
    assert loaded.setup is not None
    assert plugin["pkg"].PLUGIN_ID == KEY
    assert plugin["pkg"].VERSION == "0.2.0"


def test_header_matches_constants(plugin):
    doc_ = plugin["pkg"].__doc__
    assert f"Plugin-ID:      {plugin['pkg'].PLUGIN_ID}" in doc_
    assert f"Version:        {plugin['pkg'].VERSION}" in doc_
    assert f"Name:           {plugin['pkg'].NAME}" in doc_


def test_selected_edge_becomes_a_path(plugin, doc):
    paths = plugin["ops"].selected_paths(doc.scene)
    assert len(paths) == 1 and paths[0].length == pytest.approx(10.0)


def test_place_is_one_undo_step(plugin, doc):
    ops, geo = plugin["ops"], plugin["geo"]
    pts = geo.place(ops.selected_paths(doc.scene), geo.MODE_COUNT, count=5)
    assert ops.add_points(doc, KEY, pts) == 5
    assert len(doc.scene.guides) == 5
    assert all(g.direction is None for g in doc.scene.guides)
    assert len(ops.live_points(doc.scene, KEY)) == 5
    assert len(doc.history.undo_stack) == 1
    assert doc.notified == 1

    doc.history.undo()
    assert doc.scene.guides == []
    assert KEY not in doc.scene.plugin_data
    doc.history.redo()
    assert len(doc.scene.guides) == 5
    assert len(ops.live_points(doc.scene, KEY)) == 5


def test_placing_twice_does_not_duplicate(plugin, doc):
    ops, geo = plugin["ops"], plugin["geo"]
    pts = geo.place(ops.selected_paths(doc.scene), geo.MODE_COUNT, count=3)
    assert ops.add_points(doc, KEY, pts) == 3
    assert ops.add_points(doc, KEY, pts) == 0
    assert len(doc.scene.guides) == 3
    assert len(doc.history.undo_stack) == 1


def test_delete_removes_only_our_points(plugin, doc):
    from PySide6.QtGui import QVector3D

    from core.guide import Guide
    from core.history import AddGuideCommand
    ops, geo = plugin["ops"], plugin["geo"]
    theirs = Guide(QVector3D(50, 50, 0))
    doc.history.execute(AddGuideCommand(theirs))
    pts = geo.place(ops.selected_paths(doc.scene), geo.MODE_COUNT, count=4)
    ops.add_points(doc, KEY, pts)
    assert ops.delete_points(doc, KEY) == 4
    assert doc.scene.guides == [theirs]
    doc.history.undo()
    assert len(doc.scene.guides) == 5


def test_points_far_from_the_origin_are_tracked(plugin, qapp):
    """Guides keep 32-bit floats: every placed point must still be found
    (regression: away from the origin most points were lost)."""
    import math

    from PySide6.QtGui import QVector3D

    from core.history import History
    from core.scene import Scene
    ops, geo = plugin["ops"], plugin["geo"]
    scene = Scene()
    n = 48
    ring = [QVector3D(13.37 * math.cos(2 * math.pi * i / n) + 101.3,
                      8.91 * math.sin(2 * math.pi * i / n) + 57.7, 3.3)
            for i in range(n)]
    for i in range(n):
        scene.selection.add(scene.mesh.add_edge(ring[i], ring[(i + 1) % n]))
    vp = FakeViewport(scene, History(scene))
    pts = geo.place(ops.selected_paths(scene), geo.MODE_COUNT, count=20)
    assert ops.add_points(vp, KEY, pts) == 20
    assert len(ops.live_points(scene, KEY)) == 20
    assert ops.add_points(vp, KEY, pts) == 0
    assert ops.delete_points(vp, KEY) == 20
    assert scene.guides == []


def test_registry_of_version_0_1_0_still_matches(plugin, doc):
    """0.1.0 saved 64-bit coordinates; they must still find their guides."""
    from PySide6.QtGui import QVector3D

    from core.guide import Guide
    from core.history import AddGuideCommand
    ops = plugin["ops"]
    p = (101.123456789, 57.987654321, 0.333333333)
    doc.history.execute(AddGuideCommand(Guide(QVector3D(*p))))
    doc.scene.plugin_data[KEY] = {"version": 1, "points": [list(p)]}
    assert len(ops.live_points(doc.scene, KEY)) == 1
    assert ops.delete_points(doc, KEY) == 1


def test_erased_guide_is_dropped(plugin, doc):
    from core.history import DeleteGuidesCommand
    ops, geo = plugin["ops"], plugin["geo"]
    pts = geo.place(ops.selected_paths(doc.scene), geo.MODE_COUNT, count=3)
    ops.add_points(doc, KEY, pts)
    doc.history.execute(DeleteGuidesCommand(doc.scene.guides[:1]))
    assert len(ops.live_points(doc.scene, KEY)) == 2


def test_points_survive_save_and_reopen(plugin, doc, tmp_path):
    from core.scene import Scene
    from formats import igz
    ops, geo = plugin["ops"], plugin["geo"]
    pts = geo.place(ops.selected_paths(doc.scene), geo.MODE_DISTANCE,
                    spacing=2.5, origin=geo.ORIGIN_ENDS)
    ops.add_points(doc, KEY, pts)
    path = tmp_path / "m.igz"
    igz.save_scene(doc.scene, path)
    back = Scene()
    igz.load_into(back, path)
    assert len(ops.live_points(back, KEY)) == 5
    assert back.plugin_data[KEY]["version"] == ops.DATA_VERSION


def test_bad_document_data_is_ignored(plugin, doc):
    ops = plugin["ops"]
    doc.scene.plugin_data[KEY] = {"version": 1, "points": [[1, 2], "x",
                                                          [1, 2, True]]}
    assert ops.read_registry(doc.scene, KEY) == []
    doc.scene.plugin_data[KEY] = "garbage"
    assert ops.read_registry(doc.scene, KEY) == []


def test_dialog_previews_and_places(plugin, doc, qapp):
    ui, ops = plugin["ui"], plugin["ops"]
    dlg = ui.DividePointsDialog(doc, KEY, "test")
    dlg.show()
    dlg.r_dist.setChecked(True)
    dlg.dist.setValue(3.0 / dlg._scale)
    dlg.r_ends.setChecked(True)
    assert len(dlg._points) == 4                  # 0, 3, 7, 10
    assert len(ops.PREVIEW) == 4
    dlg.r_mid.setChecked(True)
    assert len(dlg._points) == 3                  # 2, 5, 8
    dlg.limit_on.setChecked(True)
    dlg.limit.setValue(2)
    assert len(dlg._points) == 2                  # 3.5, 6.5
    dlg._place()
    assert len(doc.scene.guides) == 2
    assert doc.flashed
    dlg.close()
    assert ops.PREVIEW == []


def test_dialog_without_selection_disables_place(plugin, doc, qapp):
    doc.scene.selection.clear()
    dlg = plugin["ui"].DividePointsDialog(doc, KEY, "test")
    dlg.show()
    assert not dlg.b_place.isEnabled()
    dlg.close()


def test_overlay_draws_only_the_preview(plugin, doc, qapp):
    import numpy as np
    from PySide6.QtGui import QImage, QPainter
    ops, geo = plugin["ops"], plugin["geo"]
    calls = []

    class App:
        def world_to_pixels(self, pts):
            a = np.asarray(pts, dtype=float).reshape(-1, 3)
            calls.append(len(a))
            return a[:, 0] * 10, a[:, 1] * 10, np.ones(len(a), bool)

    pts = geo.place(ops.selected_paths(doc.scene), geo.MODE_COUNT, count=3)
    ops.add_points(doc, KEY, pts)
    img = QImage(200, 200, QImage.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    try:
        ops.Overlay(App())(doc, painter)          # placed points: host draws
        ops.PREVIEW[:] = [(5.0, 5.0, 0.0)]
        ops.Overlay(App())(doc, painter)
    finally:
        painter.end()
        ops.PREVIEW.clear()
    assert calls == [1]
    assert img.pixelColor(50, 50).alpha() > 0     # the cross centre


class FakeApp:
    def __init__(self, viewport, window):
        from PySide6.QtWidgets import QMenu
        self.viewport = viewport
        self.window = window
        self.ext_menu = QMenu()
        self.got = {}

    def add_overlay(self, fn):
        self.got["overlay"] = fn

    def add_context_menu(self, fn):
        self.got["menu"] = fn

    def add_menu(self, title):
        return self.ext_menu.addMenu(title)


@pytest.fixture
def settings(tmp_path):
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.setOrganizationName("divide_points_tests")
    QCoreApplication.setApplicationName("divide_points_tests")
    QSettings().remove(f"plugins/{KEY}")
    yield
    QSettings().remove(f"plugins/{KEY}")


def _submenu(app):
    sub = app.ext_menu.actions()[0].menu()
    return sub, {a.text(): a for a in sub.actions() if a.text()}


def test_setup_registers_menu_overlay_and_context_menu(plugin, doc, qapp,
                                                       settings):
    from PySide6.QtWidgets import QMainWindow, QMenu, QToolBar
    win = QMainWindow()
    app = FakeApp(doc, win)
    plugin["loaded"].setup(app)
    sub, acts = _submenu(app)
    assert app.ext_menu.actions()[0].text() == "Divide Points"
    assert set(acts) == {"Divide Points…", "Show in toolbar"}
    assert acts["Show in toolbar"].isCheckable()
    assert not acts["Show in toolbar"].isChecked()
    assert win.findChild(QToolBar, f"{KEY}_toolbar") is None

    menu = QMenu()
    app.got["menu"](menu, list(doc.scene.selection))
    assert any(a.text() == "Divide Points…" for a in menu.actions())
    doc.scene.selection.clear()
    empty = QMenu()
    app.got["menu"](empty, [])
    assert empty.actions() == []


def test_show_in_toolbar_check_box(plugin, doc, qapp, settings):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMainWindow, QToolBar
    win = QMainWindow()
    win.show()
    app = FakeApp(doc, win)
    plugin["loaded"].setup(app)
    _sub, acts = _submenu(app)
    check = acts["Show in toolbar"]

    check.setChecked(True)
    tb = win.findChild(QToolBar, f"{KEY}_toolbar")
    assert tb is not None and tb.isVisible()
    assert len(tb.actions()) == 1
    assert not tb.actions()[0].icon().isNull()
    assert QSettings().value(f"plugins/{KEY}/show_toolbar") == "1"

    tb.actions()[0].trigger()                      # opens the dialog
    dlg = plugin["pkg"]._STATE["dialog"]
    assert dlg is not None and dlg.isVisible()
    dlg.close()

    tb.hide()                                      # Qt's toolbar menu
    assert not check.isChecked()
    assert QSettings().value(f"plugins/{KEY}/show_toolbar") == "0"

    check.setChecked(True)
    assert tb.isVisible()
    assert win.findChildren(QToolBar) == [tb]      # built once only
    win.close()


def test_toolbar_comes_back_next_session(plugin, doc, qapp, settings):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMainWindow, QToolBar
    QSettings().setValue(f"plugins/{KEY}/show_toolbar", "1")
    win = QMainWindow()
    app = FakeApp(doc, win)
    plugin["loaded"].setup(app)
    _sub, acts = _submenu(app)
    assert acts["Show in toolbar"].isChecked()
    assert win.findChild(QToolBar, f"{KEY}_toolbar") is not None
