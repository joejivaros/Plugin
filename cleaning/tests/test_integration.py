# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The plugin inside IngeTrazo: loading, header, menu, toolbar, dialog.

Runs headless (``QT_QPA_PLATFORM=offscreen``); skipped when IngeTrazo is
not importable — set ``INGETRAZO_ROOT`` to a checkout.
"""
from __future__ import annotations

import importlib
import re

import pytest

from conftest import KEY, PLUGIN_DIR, FakeViewport, needs_ingetrazo, two_squares, v

pytestmark = needs_ingetrazo


@pytest.fixture
def doc(qapp):
    from core.history import History
    from core.scene import Scene
    scene = Scene()
    return FakeViewport(scene, History(scene))


class FakeApp:
    def __init__(self, viewport, window):
        from PySide6.QtWidgets import QMenu
        self.viewport = viewport
        self.window = window
        self.ext_menu = QMenu()

    def add_menu(self, title):
        return self.ext_menu.addMenu(title)


def _submenu(app):
    sub = app.ext_menu.actions()[0].menu()
    return sub, {a.text(): a for a in sub.actions() if a.text()}


@pytest.fixture(autouse=True)
def _fresh_state(plugin):
    yield
    state = plugin["pkg"]._STATE
    if state["dialog"] is not None:
        state["dialog"].close()
    state["dialog"] = state["toolbar"] = None


def test_plugin_loads_with_a_setup_and_no_tools(plugin):
    assert plugin["loaded"].tools == []
    assert callable(plugin["loaded"].setup)


def test_header_matches_constants(plugin):
    pkg = plugin["pkg"]
    head = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
    assert re.search(rf"^Plugin-ID:\s+{pkg.PLUGIN_ID}$", head, re.M)
    assert re.search(rf"^Version:\s+{re.escape(pkg.VERSION)}$", head, re.M)
    assert re.search(rf"^Name:\s+{pkg.NAME}$", head, re.M)
    assert pkg.PLUGIN_ID == KEY
    changelog = (PLUGIN_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {pkg.VERSION} " in changelog


def test_setup_registers_the_submenu(plugin, doc, qapp, settings):
    from PySide6.QtWidgets import QMainWindow, QToolBar
    win = QMainWindow()
    app = FakeApp(doc, win)
    plugin["loaded"].setup(app)
    _sub, acts = _submenu(app)
    assert app.ext_menu.actions()[0].text() == "Cleaning"
    assert set(acts) == {"Clean Up…", "Show in toolbar"}
    assert acts["Show in toolbar"].isCheckable()
    assert not acts["Show in toolbar"].isChecked()
    assert win.findChild(QToolBar, f"{KEY}_toolbar") is None


def test_show_in_toolbar_from_menu_and_dialog(plugin, doc, qapp, settings):
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
    assert len(tb.actions()) == 1 and not tb.actions()[0].icon().isNull()
    assert QSettings().value(f"plugins/{KEY}/show_toolbar") == "1"

    tb.actions()[0].trigger()                      # opens the dialog
    dlg = plugin["pkg"]._STATE["dialog"]
    assert dlg is not None and dlg.isVisible()
    assert dlg.show_toolbar.isChecked()

    dlg.show_toolbar.setChecked(False)             # the dialog's check box
    assert not tb.isVisible() and not check.isChecked()
    assert QSettings().value(f"plugins/{KEY}/show_toolbar") == "0"

    tb.show()                                      # Qt's toolbar menu
    tb.hide()
    check.setChecked(True)
    assert tb.isVisible() and dlg.show_toolbar.isChecked()
    tb.hide()
    assert not check.isChecked() and not dlg.show_toolbar.isChecked()
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


def test_icon_follows_the_accent(plugin, qapp):
    from PySide6.QtGui import QColor
    toolbar = importlib.import_module(f"ingetrazo_plugin_{KEY}.toolbar")
    red = toolbar.make_icon(QColor(255, 0, 0)).pixmap(48, 48).toImage()
    blue = toolbar.make_icon(QColor(0, 0, 255)).pixmap(48, 48).toImage()
    assert red != blue
    centre = red.pixelColor(37, 36)                # the big sparkle
    assert centre.red() > 200 and centre.blue() < 60


def test_dialog_analyses_then_cleans(plugin, doc, qapp, settings):
    ui = plugin["ui"]
    scene = doc.scene
    two_squares(scene.mesh)
    scene.mesh.add_edge(v(5, 5), v(6, 6))
    dlg = ui.CleaningDialog(doc, KEY, "Cleaning")
    report = dlg.analyse()
    assert report["coplanar_faces"] == 1 and report["stray_edges"] == 1
    assert len(scene.mesh.faces) == 2              # nothing changed yet
    assert dlg.counts["coplanar_faces"].text() == "1"

    dlg.checks["stray_edges"].setChecked(False)
    assert dlg.counts["coplanar_faces"].text() == ""   # stale counts cleared
    done = dlg.clean()
    assert done["stray_edges"] == 0 and done["coplanar_faces"] == 1
    assert len(scene.mesh.faces) == 1 and doc.notified == 1
    assert len(doc.history.undo_stack) == 1

    assert dlg.clean() is None                     # already clean
    assert len(doc.history.undo_stack) == 1
    dlg.close()


def test_dialog_remembers_the_choices(plugin, doc, qapp, settings):
    ui = plugin["ui"]
    dlg = ui.CleaningDialog(doc, KEY, "Cleaning")
    dlg.checks["unused_layers"].setChecked(False)
    dlg.angle.setValue(0.5)
    dlg.scopes["selection"].setChecked(True)
    dlg.close()
    again = ui.CleaningDialog(doc, KEY, "Cleaning")
    opts = again.options()
    assert not opts.unused_layers and opts.coplanar_angle == 0.5
    assert opts.scope == "selection"
    again.close()


def test_dialog_select_none_disables_the_buttons(plugin, doc, qapp, settings):
    ui = plugin["ui"]
    dlg = ui.CleaningDialog(doc, KEY, "Cleaning")
    dlg._check_all(False)
    assert not dlg.clean_btn.isEnabled() and not dlg.analyse_btn.isEnabled()
    dlg._check_all(True)
    assert dlg.clean_btn.isEnabled()
    dlg.close()


def test_whole_model_scope_is_off_inside_a_group(plugin, doc, qapp, settings):
    from core.group import Group
    ui = plugin["ui"]
    g = Group()
    two_squares(g.mesh)
    doc.scene.groups.append(g)
    doc.scene.begin_group_edit(g)
    try:
        dlg = ui.CleaningDialog(doc, KEY, "Cleaning")
        dlg.show()
        assert not dlg.scopes["model"].isEnabled()
        assert dlg.scopes["context"].isChecked()
        assert dlg.clean()["coplanar_faces"] == 1
        dlg.close()
    finally:
        doc.scene.end_group_edit()


def test_icon_ignores_other_widgets_but_follows_the_theme(plugin, qapp, settings):
    """Review of 0.5.9: an application-wide filter rebuilt the icon each
    time another extension restyled one of its widgets."""
    import importlib

    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QLabel, QMainWindow
    toolbar = importlib.import_module("ingetrazo_plugin_cleaning.toolbar")
    win = QMainWindow()
    others = [QLabel(str(i), win) for i in range(50)]
    win.show()
    switch = toolbar.ToolbarSwitch(win, "cleaning", "T", "tip", lambda: None)
    switch.set_shown(True)
    action = switch.toolbar.actions()[0]
    built = action.icon().cacheKey()
    for label in others:                       # another extension restyles
        label.setStyleSheet("color: red")
        label.setPalette(QPalette(QColor(10, 200, 10)))
    qapp.processEvents()
    assert action.icon().cacheKey() == built

    old = qapp.palette()
    new = QPalette(old)
    new.setColor(QPalette.WindowText, QColor(250, 10, 10))
    try:
        qapp.setPalette(new)                   # the theme changed
        qapp.processEvents()
        assert action.icon().cacheKey() != built
    finally:
        qapp.setPalette(old)
        win.close()
