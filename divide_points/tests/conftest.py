# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 <Author>
"""Test helpers: load the plugin's modules by file path (as IngeTrazo
does), and find IngeTrazo itself for the integration tests.

Set ``INGETRAZO_ROOT`` to an IngeTrazo checkout to run the integration
tests from anywhere; they are skipped when IngeTrazo cannot be imported.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent

_root = os.environ.get("INGETRAZO_ROOT")
if _root and _root not in sys.path:
    sys.path.insert(0, _root)


def load_module(name: str):
    """Import ``<plugin>/<name>.py`` alone, under a private module name.
    Only for modules without relative imports (geometry, texts)."""
    mod_name = f"_divide_points_test_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name,
                                                  PLUGIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


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


@pytest.fixture
def geometry():
    return load_module("geometry")
