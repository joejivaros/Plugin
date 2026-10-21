# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""One smoke test in IngeTrazo's real main window: the plugin installed in
a user plugins folder, its menu, the host-built toolbar, a clean-up and
the window's own Undo.

Named to run last: the window loads the plugin again, which replaces the
``ingetrazo_plugin_cleaning`` module the other tests hold.
"""
from __future__ import annotations

import shutil

from PySide6.QtWidgets import QMenu, QToolBar

from conftest import KEY, PLUGIN_DIR, needs_ingetrazo, two_squares, v

pytestmark = needs_ingetrazo


def test_in_the_real_window(qapp, settings, tmp_path, monkeypatch):
    import sys

    import core.extensions
    from views.main_window import MainWindow
    user_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_DIR, user_dir / KEY,
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    monkeypatch.setattr(core.extensions, "user_plugins_dir", lambda: user_dir)
    win = MainWindow()
    try:
        menu = win.findChild(QMenu, f"{KEY}_menu")
        assert menu is not None, "Extensions ▸ Cleaning is missing"
        acts = {a.text(): a for a in menu.actions() if a.text()}
        assert set(acts) == {"Clean Up…", "Show in toolbar"}

        acts["Show in toolbar"].setChecked(True)
        tb = win.findChild(QToolBar, f"{KEY}_toolbar")
        assert tb is not None
        assert tb.iconSize().width() > 0 and len(tb.actions()) == 1

        scene = win.viewport.scene
        two_squares(scene.mesh)
        scene.mesh.add_edge(v(5, 5), v(6, 6))
        pkg = sys.modules[f"ingetrazo_plugin_{KEY}"]
        tb.actions()[0].trigger()
        dlg = pkg._STATE["dialog"]
        assert dlg is not None and dlg.viewport is win.viewport
        assert dlg.analyse()["coplanar_faces"] == 1
        assert not win._is_dirty()                 # Analyse changed nothing
        report = dlg.clean()
        assert report["coplanar_faces"] == 1 and report["stray_edges"] == 1
        assert len(scene.mesh.faces) == 1 and win._is_dirty()
        win._on_undo()
        assert len(scene.mesh.faces) == 2 and len(scene.mesh.edges) == 8
        dlg.close()
    finally:
        win._saved_version = win.viewport.scene.version
        win.close()
