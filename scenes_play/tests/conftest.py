# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Test helpers: load the plugin package by file path (as IngeTrazo does),
and find IngeTrazo itself for the integration tests.

The plain-Python modules (model, motion, player) are tested without
IngeTrazo. Set ``INGETRAZO_ROOT`` to an IngeTrazo checkout to run the
integration tests from anywhere; they are skipped when IngeTrazo cannot be
imported.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TEST_PKG = "_scenes_play_test"

_root = os.environ.get("INGETRAZO_ROOT")
if _root and _root not in sys.path:
    sys.path.insert(0, _root)


def load_package():
    """The plugin package under a private name; its ``__init__`` imports
    nothing from IngeTrazo, so this works without it."""
    if TEST_PKG in sys.modules:
        return sys.modules[TEST_PKG]
    spec = importlib.util.spec_from_file_location(
        TEST_PKG, PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[TEST_PKG] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def submodule(name: str):
    load_package()
    return importlib.import_module(f"{TEST_PKG}.{name}")


def ingetrazo_available() -> bool:
    try:
        import core.saved_views  # noqa: F401
        import core.scene  # noqa: F401
    except ImportError:
        return False
    return True


needs_ingetrazo = pytest.mark.skipif(
    not ingetrazo_available(),
    reason="IngeTrazo not importable (set INGETRAZO_ROOT)")


@pytest.fixture
def model():
    return submodule("model")


@pytest.fixture
def motion():
    return submodule("motion")


@pytest.fixture
def player():
    return submodule("player")
