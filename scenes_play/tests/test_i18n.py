# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Every UI string is in the catalogs, and the catalogs agree."""
from __future__ import annotations

import ast
import json
import string

from conftest import PLUGIN_DIR

LANGS = ("en", "es", "fr")


def _catalog(lang):
    return json.loads((PLUGIN_DIR / "i18n" / f"{lang}.json")
                      .read_text(encoding="utf-8"))


def ui_strings() -> set[str]:
    """Literal first arguments of ``t(...)``, ``AutomationError(...)`` and
    ``media.MediaError(...)`` in the plugin's source, plus the plugin
    name."""
    out = {"Scene Automation"}
    for path in PLUGIN_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            func = getattr(node, "func", None)
            name = (func.id if isinstance(func, ast.Name) else
                    func.attr if isinstance(func, ast.Attribute)
                    and func.attr.endswith("Error") else None)
            if (isinstance(node, ast.Call)
                    and name in ("t", "AutomationError", "MediaError")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                out.add(node.args[0].value)
    return out


def _fields(text):
    return {f for _l, f, _s, _c in string.Formatter().parse(text) if f}


def test_every_ui_string_is_in_en_json():
    missing = ui_strings() - set(_catalog("en"))
    assert not missing, sorted(missing)


def test_no_unused_keys():
    unused = set(_catalog("en")) - ui_strings()
    assert not unused, sorted(unused)


def test_catalogs_have_identical_keys():
    keys = [set(_catalog(lang)) for lang in LANGS]
    assert all(k == keys[0] for k in keys)


def test_en_is_the_identity_map():
    assert all(k == v for k, v in _catalog("en").items())


def test_translations_keep_their_placeholders():
    for lang in LANGS:
        for k, v in _catalog(lang).items():
            assert v.strip(), (lang, k)
            assert _fields(k) == _fields(v), (lang, k, v)
