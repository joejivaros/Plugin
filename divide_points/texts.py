# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The plugin's own UI translations: ``i18n/<lang>.json`` next to this file.

Same format as IngeTrazo's ``i18n/es.json`` — a flat map from the English
source text to its translation. The language is IngeTrazo's current one;
a missing file or key falls back to the English text.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("ingetrazo.plugins")

_DIR = Path(__file__).parent / "i18n"
_catalogs: dict[str, dict[str, str]] = {}


def _language() -> str:
    try:
        from core.i18n import current_language
        return current_language() or "en"
    except ImportError:            # outside IngeTrazo (tests)
        return "en"


def catalog(lang: str) -> dict[str, str]:
    """The ``{english: translation}`` map for ``lang`` (cached)."""
    if lang not in _catalogs:
        path = _DIR / f"{lang}.json"
        data: dict[str, str] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = {str(k): str(v) for k, v in raw.items()}
            except (OSError, ValueError):
                log.warning("divide_points: cannot read %s", path)
        _catalogs[lang] = data
    return _catalogs[lang]


def t(text: str, /, **kwargs) -> str:
    """``text`` in the current language, with ``kwargs`` interpolated."""
    out = catalog(_language()).get(text) or text
    if kwargs:
        try:
            return out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text.format(**kwargs)
    return out
