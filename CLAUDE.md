# CLAUDE.md — IngeTrazo plugin development

You are helping write or review a **plugin for IngeTrazo**, a GPL-3.0-or-later
3D modeler built on Python 3.12+ and PySide6
(https://github.com/ingelibre/ingetrazo). Follow the rules below for every
change. They come from the project's plugin guidelines, CONTRIBUTING.md and
docs/plugins.md. When a rule conflicts with a user request, say so and ask
before breaking it.

Keywords: **MUST** = never skip. **SHOULD** = default; explain any deviation.

## Before you start

- Read `docs/plugins.md` and `CONTRIBUTING.md` in the IngeTrazo repo if they
  are available. The plugin API is 0.x and may have changed since this file
  was written; the repo docs win over this file on API details.
- Use the bundled reference plugins (`plugins/model_info.py`,
  `plugins/solid_inspector.py`, `plugins/ai_assistant.py`) as models.
- Ask the user for author name, contact and target IngeTrazo version if they
  are not already in the header. Never invent them.

## 1. Mandatory header

The plugin's main file (`__init__.py` for a package) MUST start with this
block. Keep every field; update `Version`, `Release-Date` and `AI-Assistance`
on each release.

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <Author>
"""
Plugin-ID:      <plugin_id>            # lowercase a-z0-9_, never changes
Name:           <Human readable name>
Version:        <MAJOR.MINOR.PATCH>    # Semantic Versioning
Revision:       <git commit or build number>
Release-Date:   <YYYY-MM-DDTHH:MM:SSZ> # ISO 8601, UTC
Author:         <name or stable pseudonym>
Contact:        <email, GitHub handle or project URL>
IngeTrazo:      >=<min version> (tested <version>)
AI-Assistance:  none | partial | full
                - <tool / model and version>: <what it produced>
Dependencies:   none | <package==pinned.version, ...>
Permissions:    none | network(<hosts>) | filesystem(<scope>) | subprocess(<commands>)
Description:    <1-3 sentences in English>
"""
```

- The same values MUST also exist as module constants: `PLUGIN_ID`, `VERSION`,
  `NAME`. Use these constants everywhere (window titles, menus, saved data).
  One version number per release — never a second "V.1"-style label.
- **AI disclosure:** when you (Claude) write or change code, text or media in
  this plugin, make sure `AI-Assistance` is at least `partial` and lists the
  model you are running as (e.g. `Claude <model name and version>`) with what
  you produced. Do not remove existing AI entries.

## 2. Layout

A plugin with any UI text or media MUST be a package folder named after its
Plugin ID:

```
<plugin_id>/
├── __init__.py        # header, constants, Tool classes / entry point
├── <module>.py        # optional: geometry, ui, data split out
├── i18n/
│   ├── en.json        # MUST — reference language
│   └── es.json        # SHOULD — same keys as en.json
├── media/
│   ├── <files>        # icons, images, sounds as real files
│   └── LICENSE-media  # origin + license of every media file (incl. AI-generated)
├── tests/             # SHOULD — pytest, runs without a display
├── CHANGELOG.md       # MUST — one entry per version, newest first
└── README.md          # MUST — purpose, usage, permissions, internals used
```

- Build paths from `Path(__file__).parent`, never from the current directory
  or `sys.path` (IngeTrazo imports plugins by file path under a private name).
- Keep files under ~800 lines; split by concern.

## 3. General rules

- **Readable code only (MUST).** No Base64, hex or other encoded payloads; no
  minified or compressed code; no `.pyc`/`.so`/`.pyd` without source; no
  strings assembled to hide their meaning.
- **No embedded media (MUST).** Never put images, icons, fonts, sound, video or
  3D assets in source code (no Base64 strings, byte arrays or data URIs). Save
  them under `media/` and record them in `media/LICENSE-media`. Icons drawn
  with `QPainter` calls are fine. If you find an embedded blob, propose
  extracting it to a file.
- **No hardcoded UI text (MUST).** Every user-facing string goes through the
  plugin's `i18n/<lang>.json` (flat map: English source text → translation,
  same format as IngeTrazo's `i18n/es.json`). Missing keys fall back to
  English. When you add a string, add it to `en.json` and `es.json` in the same
  change.
- **English** for identifiers, comments, docstrings and commit messages.
- **PEP 8**, soft 100-character lines, docstrings on public functions,
  descriptive names.
- **No official branding.** Do not use "IngeTrazo" or its logo in the plugin's
  name, title, author or viewport overlays unless the user confirms maintainer
  approval.

## 4. Security rules

A plugin runs with the user's full rights. Anything beyond editing the model
MUST be declared in `Permissions:` and explained in the README.

- **No dynamic code:** no `eval`, `exec`, `compile`, `__import__` of computed
  names, `pickle`/`marshal` loads, or downloading and running code.
  Exception: plugins built on `core.ai.run_transactional`, which MUST show the
  code to the user before running it.
- **Network:** declare hosts; HTTPS only; local servers bind to `127.0.0.1`,
  never `0.0.0.0`; no telemetry or update checks without opt-in.
- **File system:** only files the user picks in a dialog, the plugin's own
  folder and IngeTrazo's per-user data folder. Never delete user files.
- **Subprocesses:** declared, fixed argument lists, never `shell=True` with
  user input.
- **Secrets:** never in code, logs or saved `.igz` files. Prefer the OS
  keyring; on-disk files must be user-only readable.
- **Dependencies:** stdlib + PySide6 by default. Anything else must be pinned
  in the header and README; never vendor copied code without its license.
- **Saved data:** values written into the model (e.g. `group.ext`) MUST be
  plain JSON-compatible data — never code or pickled objects.
- **Validation:** check type, range and `math.isfinite` on all dialog, file and
  network input before use.
- **Errors:** no bare `except:`. Log to the `ingetrazo.plugins` logger and
  show the user a translated message.

## 5. Integration rules

- Prefer the documented contract: `Tool` subclasses defined in the plugin file
  appear in the Extensions menu. Any other entry point or internal `core.*`
  import MUST be listed in the README under "Internals used".
- Every model change goes through `viewport.history.execute(...)` (e.g.
  `SnapshotImport`) and then `viewport.notify_scene_changed()` — one undo step
  per user action.
- Read geometry from `scene.loose_mesh` (not `scene.mesh`) and `scene.groups`.
- Store per-object data only under `obj.ext["<plugin_id>"]` with a `version`
  field; never touch other plugins' keys. New versions must read old data or
  fail with a clear message.
- Never touch the document off the main thread; relay worker results with a
  `Signal(object)` on a queued connection to a bound method (not a lambda,
  not `Signal(dict)`).
- Do not override built-in menus or shortcuts. Toolbars and other Qt objects
  get an `objectName` prefixed with the Plugin ID (`<plugin_id>_toolbar`).
- Semantic Versioning: MAJOR = breaking change to saved data or behaviour,
  MINOR = feature, PATCH = fix. Add a CHANGELOG entry for every version.

## 6. Commands

Run these from the IngeTrazo repo root (or adapt paths). Run them before
saying a change is done, and report the results.

```bash
python -m pytest -m "not slow"            # fast suite (what CI runs)
python -m pytest <plugin_id>/tests -q     # plugin tests
python -m bandit -r <plugin_id>           # security scan (pip install bandit)
grep -rEn '[A-Za-z0-9+/=]{200,}' <plugin_id>   # flags encoded blobs; must return nothing
```

Run the app with `python main.py`; plugins load from
`~/.local/share/ingetrazo/plugins/` (Linux), `%APPDATA%\ingetrazo\plugins\`
(Windows), or `<repo>/plugins/`.

## 7. Definition of done

Before finishing any task, check and report each item:

- [ ] Header complete and matching `PLUGIN_ID` / `VERSION` constants
- [ ] `AI-Assistance` updated with this session's model and contribution
- [ ] Package layout present: `i18n/en.json`, `README.md`, `CHANGELOG.md`
- [ ] No encoded payloads, embedded media or compiled-only files
- [ ] No hardcoded UI strings; `en.json` and `es.json` have identical keys
- [ ] Media files listed in `media/LICENSE-media`
- [ ] No `eval`/`exec`/pickle; `Permissions:` matches what the code does
- [ ] Bandit clean (or findings explained)
- [ ] Model edits go through the history; saved data under the Plugin ID
- [ ] Tests pass; plugin loads without a `⚠ (load error)` entry
