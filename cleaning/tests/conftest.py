# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Test helpers: load the plugin as IngeTrazo does (by file path, through
its own discovery), and find IngeTrazo itself.

Set ``INGETRAZO_ROOT`` to an IngeTrazo checkout to run the tests that need
it from anywhere; they are skipped when IngeTrazo cannot be imported.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
KEY = "cleaning"

_root = os.environ.get("INGETRAZO_ROOT")
if _root and _root not in sys.path:
    sys.path.insert(0, _root)


def ingetrazo_available() -> bool:
    try:
        import core.scene  # noqa: F401
        import tools.base  # noqa: F401
    except ImportError:
        return False
    return True


needs_ingetrazo = pytest.mark.skipif(
    not ingetrazo_available(),
    reason="IngeTrazo not importable (set INGETRAZO_ROOT)")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="session")
def plugin(tmp_path_factory, qapp):
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
            "geo": importlib.import_module(f"{pkg}.geometry"),
            "doc": importlib.import_module(f"{pkg}.document"),
            "cmd": importlib.import_module(f"{pkg}.command"),
            "ui": importlib.import_module(f"{pkg}.ui")}


class FakeViewport:
    """What the dialog uses of IngeTrazo's viewport."""

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
def settings(tmp_path):
    """A throw-away QSettings store."""
    from PySide6.QtCore import QCoreApplication, QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("cleaning_tests")
    QCoreApplication.setApplicationName("cleaning_tests")
    QSettings().remove(f"plugins/{KEY}")
    yield
    QSettings().remove(f"plugins/{KEY}")


# ---- geometry builders ----------------------------------------------------------

def v(x, y, z=0.0):
    from PySide6.QtGui import QVector3D
    return QVector3D(float(x), float(y), float(z))


def two_squares(mesh, paint_b=None, tilt=0.0):
    """Two unit squares sharing the edge x=1; the second one tilted by
    ``tilt`` radians around that edge, painted ``paint_b``."""
    import math
    a = mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    dz = math.sin(tilt)
    dx = math.cos(tilt)
    b = mesh.add_face([v(1, 0), v(1 + dx, 0, dz), v(1 + dx, 1, dz), v(1, 1)])
    if paint_b:
        b.attrs.update(paint_b)
    return a, b
