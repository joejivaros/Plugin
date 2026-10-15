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
- The IngeTrazo repo is NOT in this folder. Clone it into a scratch folder to
  read the source (`core/`, `views/extension_api.py`, `tools/`); the version
  is in `core/version.py`. On this Windows machine git's OpenSSL lacks the CA
  store: use `git -c http.sslBackend=schannel clone --depth 1 <url>`.
- Section 5a lists API facts verified on IngeTrazo 0.5.7 and re-checked on
  0.5.8; re-check them in the source when targeting another version. A
  local 0.5.8 checkout is at
  `D:\Documents\Developement\IngeTrazo\Sources\ingetrazo-main`.
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
  English. When you add a string, add it to `en.json` and `es.json` (and
  every other catalog the plugin ships) in the same change.
  - Make the plugin's `en.json` the identity map (`"X": "X"`), so it lists
    every key; the other catalogs must have exactly the same keys.
  - The host's `core.i18n.tr` only knows IngeTrazo's own strings. Look up
    the plugin's catalog yourself, picking the language with
    `core.i18n.current_language()`. The language is set before plugins
    load, so translating class attributes at import time works.
  - A plugin catalog is only used for a language IngeTrazo itself offers.
    In 0.5.8 those are en, es, fr, de, pl, it, id, pt-BR, zh-CN.
  - Enforce all this with a test that collects the `t("...")` literals via
    `ast` (see `divide_points/tests/test_i18n.py`).
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

## 5a. API facts learned (verified on IngeTrazo 0.5.7, re-checked 0.5.8)

- **32-bit coordinates.** `QVector3D`, used by vertices and guides, stores
  32-bit floats. Before comparing or keying a computed (64-bit) point
  against stored geometry, pass it through `QVector3D` first. Otherwise
  matches fail, often far from the origin. `divide_points` 0.1.0 had this
  bug.
- **Guides.** They live in `scene.guides` as `core.guide.Guide` objects.
  `Guide(point)` with no direction is a guide point: the host draws it as a
  small cross, snaps to it and saves it. Add guides with `AddGuideCommand`
  and remove them with `DeleteGuidesCommand` (`core.history`).
- **One undo step for several changes.** Wrap the sub-commands in one
  `core.history.Command` subclass: `do` runs them in order, `undo` runs them
  in reverse. Combine with `SetPluginDataCommand(key, value)` for document
  data (`scene.plugin_data[key]`, JSON only). Run it through
  `viewport.history.execute(cmd)`, check `history.last_error`, then call
  `viewport.notify_scene_changed()`.
- **Selection.** `scene.selection` holds `Edge`, `Face`, `Group` and `Guide`
  objects. The Select tool already adds every segment of a curve (edges
  sharing `Edge.curve`). `Edge.a` and `Edge.b` are positions. An open
  group's mesh (`scene.mesh`) is edited in world coordinates.
- **Units.**
  - `core.units.model_unit()` gives the unit code.
  - `bare_number_scale()` gives metres per typed number. The feet-and-inches
    styles read bare numbers as inches.
  - `fmt_len(metres)` formats a length for display.
- **Loading.** A package loads as `ingetrazo_plugin_<plugin_id>` with
  relative imports allowed. Submodules exist only once something imports
  them.
- **Menus.** A plugin with only `setup()` (no `Tool` subclass) can use
  `app.add_menu(title)` for a submenu, but its entries are not in the F3
  command search. Say so in the README. A single entry from
  `app.add_menu_action(text, fn, tip=...)` IS found by F3.
- **Scenes and camera** (internals, no API call yet; see `scenes_play/host.py`).
  - Scenes are `scene.saved_views`, a list of `core.saved_views.SavedView`
    (`name`, `target`, `distance`, `yaw`, `pitch`, `fov_deg`, `perspective`
    plus layers/style/section/shadows). Names are unique.
  - `viewport.camera` is a `core.camera.OrbitCamera` with the same fields;
    set them and call `viewport.update()`.
  - Show a scene the way the app does with
    `window.tray.scenes._on_activate(row)` (rows in `tray.scenes.list`,
    `row.data(Qt.UserRole)` is the view), as `views/outliner.py` does.
  - The document is dirty when `scene.version != window._saved_version`;
    the Scenes panel bumps `scene.version` only when layers/style/etc.
    change, not for a camera-only scene.
- **Tools.** `window._tools` maps keys to tool objects;
  `window._activate_tool(key)` switches (e.g. `"look_around"`, `"select"`);
  `viewport.active_tool` is the current one.
- **Dialogs.** `QDialog.closeEvent` calls `reject()`. A dialog whose
  `reject()` calls `close()` (so Esc gets the unsaved-changes prompt) must
  end its `closeEvent` with `event.accept()`, not `super().closeEvent()`,
  or the close is cancelled.
- **The installed build is not pip PySide6.** PyInstaller ships only what
  IngeTrazo imports. The 0.5.8 Windows build has no `PySide6.QtMultimedia`,
  `wave`, `winsound` or FFmpeg; it has `subprocess`, `tempfile`, `shutil`,
  `ctypes`, QtNetwork, QtSvg, QtPdf. Check a module before relying on it:
  `C:\Program Files\IngeTrazo\_internal\PySide6\` lists the Qt modules,
  and the stdlib ones are in the PYZ archive inside `ingetrazo.exe`
  (parse its table of contents; a plain `grep` misses them).
  `scenes_play` uses the user's FFmpeg (`media.py`) for sound and video.
- **Offscreen images.** `viewport.render_image(w, h, overlays=False)`
  renders any size; set `camera.aspect` to `w / h` around it (the sheet
  composer does). It returns `None` under `QT_QPA_PLATFORM=offscreen` (no
  OpenGL), so tests feed synthetic frames.
- **Extensions index (0.5.8).** Extensions ▸ Manage extensions… installs
  from the catalog; a release `.zip` holds ONE folder with `__init__.py`.
  The bot (`tools/catalog.py`) reports imports of `subprocess`, `socket`,
  `urllib`, `http`, `requests`, `ctypes`, `shutil`, `pickle`, `marshal`,
  bare `eval`/`exec`/`compile`/`__import__`, and `.system`/`.popen`/
  `.unlink`/`.rmtree` calls; keep these out of shipped code.
- **Toolbars.**
  - Build them with `app.window._new_toolbar(title, "<plugin_id>_toolbar")`.
    This is an internal: fall back to a plain `QToolBar`, and list it in the
    README.
  - `setup(app)` runs after the window restored its saved layout, so a
    plugin toolbar's position is not restored between sessions.
  - Keep on/off choices in `QSettings` under `plugins/<plugin_id>/…`. That
    is IngeTrazo's own per-user settings store.
- **Icons.** Draw them with QPainter like `views/icons.py`: 48 px, the
  palette's `windowText` as ink, a 3 px round pen and the orange accent
  `QColor(243, 115, 41)`. Redraw on `PaletteChange` / `ThemeChange`.

## 6. Commands

Run these from the IngeTrazo repo root (or adapt paths). Run them before
saying a change is done, and report the results.

```bash
python -m pytest -m "not slow"            # fast suite (what CI runs)
python -m pytest <plugin_id>/tests -q     # plugin tests
python -m bandit -r <plugin_id>           # security scan (pip install bandit)
grep -rEn '[A-Za-z0-9+/=]{200,}' <plugin_id>   # flags encoded blobs; must return nothing
```

Testing notes (learned on this machine, Windows):

- **Environment.** Use a venv in a scratch folder with only
  `PySide6 numpy pytest bandit`. IngeTrazo's `requirements.txt` pulls
  `openskp` from git, which fails here on SSL, and headless plugin tests do
  not need it.
- **Headless runs.** Set `QT_QPA_PLATFORM=offscreen` and
  `INGETRAZO_ROOT=<IngeTrazo checkout>`. Integration tests skip themselves
  when IngeTrazo cannot be imported.
- **`tests/pytest.ini`.** Put one in the plugin's tests folder. Without it,
  pytest imports the package's `__init__.py` (which needs IngeTrazo) and
  every test errors when IngeTrazo is absent.
- **Loading in tests.** Load the plugin as the app does: copy it to a temp
  folder and call `core.extensions.discover_plugins([folder])`; an error
  there is a `⚠ (load error)`. Import lazily loaded submodules with
  `importlib.import_module("ingetrazo_plugin_<id>.<module>")`.
- **Pure modules.** Keep `__init__.py` free of IngeTrazo/Qt imports at
  module level; tests can then load the package with
  `spec_from_file_location(name, init, submodule_search_locations=[dir])`
  and test the plain-Python modules without IngeTrazo
  (`scenes_play/tests/conftest.py`).
- **Real window.** `views.main_window.MainWindow()` builds offscreen, as in
  IngeTrazo's `tests/test_scene_recall_version.py`; use it for one smoke
  test of internals. It loads the user's installed plugins, and an
  installed copy of the plugin under test replaces its
  `ingetrazo_plugin_<id>` module: monkeypatch
  `core.extensions.user_plugins_dir` to an empty folder first. Set `QT_QPA_FONTDIR=C:/Windows/Fonts` when grabbing a
  screenshot, or text renders as boxes.
- **Bandit.** Run `python -m bandit -r <plugin_id> -x <plugin_id>/tests` for
  the plugin code. B101 (`assert`) in pytest tests is expected.
- **IngeTrazo's own suite.** The fast suite only matters when IngeTrazo
  itself changes. If its dependencies are missing, say so; don't skip it
  silently.

Run the app with `python main.py`; plugins load from
`~/.local/share/ingetrazo/plugins/` (Linux), `%APPDATA%\ingetrazo\plugins\`
(Windows), or `<repo>/plugins/`.

## 7. Definition of done

Before finishing any task, check and report each item:

- [ ] Header complete and matching `PLUGIN_ID` / `VERSION` constants
- [ ] `AI-Assistance` updated with this session's model and contribution
- [ ] Package layout present: `i18n/en.json`, `README.md`, `CHANGELOG.md`
- [ ] No encoded payloads, embedded media or compiled-only files
- [ ] No hardcoded UI strings; all `i18n/*.json` catalogs have identical keys
- [ ] Positions compared with stored geometry go through `QVector3D` first
- [ ] Media files listed in `media/LICENSE-media`
- [ ] No `eval`/`exec`/pickle; `Permissions:` matches what the code does
- [ ] Bandit clean (or findings explained)
- [ ] Model edits go through the history; saved data under the Plugin ID
- [ ] Tests pass; plugin loads without a `⚠ (load error)` entry
## 8. 
@.cursor\rules\karpathy-guidelines.mdc
