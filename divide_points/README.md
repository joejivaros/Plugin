# Divide Points

A plugin that places **visible measurement / guide points** along
the selected lines and curves.

- Plugin ID: `divide_points` · Version: 0.2.1 · License: GPL-3.0-or-later
- Date: October 12 2026
- Needs IngeTrazo ≥ 0.5.7 (extension API 2); tested with 0.5.7.
- Author: G. Andreotti · Contact: https://github.com/joejivaros
- Developed with the assistance of Claude AI, Opus 5.5 (Medium)

## Install

Copy the whole `divide_points/` folder into your plugins folder
(**Extensions ▸ Open plugins folder**; on Windows `%APPDATA%\ingetrazo\plugins\`,
on Linux `~/.local/share/ingetrazo/plugins/`) and restart IngeTrazo.

## Use

1. Select one or more lines, arcs, circles or curves (connected edges are
   treated as one path; a vertex where three or more selected edges meet
   splits them into separate paths).
2. **Extensions ▸ Divide Points ▸ Divide Points…**, the toolbar button, or
   right-click ▸ **Divide Points…**.
3. Pick the spacing and where to start. Orange crosses preview the points in
   the viewport; the dialog shows how many points and the resulting gaps.
4. **Place Points**. It is one undo step (Ctrl+Z removes all of them).

The dialog is modeless: change the selection while it is open and the
preview follows.

### Spacing and start

| Spacing | Start from **Both ends** | Start from **The middle** |
|---|---|---|
| **Number of points** *N* | First and last point on the ends, equal gaps of L/(N−1) | Points off the ends, centred, equal gaps of L/(N+1) |
| **Distance** *d* | A point every *d* walking in from each end; the remainder is left in the middle | A point every *d* walking out from the midpoint; the remainder is left at both ends |
| **Distance** *d* + **Limit** *N* | *N* points, alternating start / end | *N* points centred on the midpoint: odd *N* puts one on it, even *N* puts it between two |
Note: If you use *d* + **Limit** *N* plus *Both End* and that the sum of these values is greater that the segment size, some points will overlap at in the middle distance of the segments.

The distance is typed in the model's current unit. In the
feet-and-inches styles a bare number is read as inches, as everywhere in
IngeTrazo.

On a closed loop (a circle): *N* points split it into *N* equal arcs,
starting at the loop's seam (**Both ends**) or half a gap after it (**The
middle**). With a distance, the loop is opened at its seam.

A place that already has a guide point is skipped, so running the plugin
twice does not create duplicates.

### Toolbar

**Extensions ▸ Divide Points ▸ Show in toolbar** (a check box) shows a
toolbar with one button that opens the dialog. The choice is remembered
between sessions. The toolbar moves, floats and hides like the built-in ones;
hiding it from Qt's toolbar right-click menu also clears the check box.
Because IngeTrazo lays out its saved toolbars before plugins load, the
toolbar opens at the top of the window in each session.

The icon is drawn in code with QPainter (no image file): a curve divided by
three orange guide crosses over a measuring rule, in the theme's ink colour.

### The points

The points are ordinary IngeTrazo **guide points**, drawn by IngeTrazo as its
own small crosses: the drawing tools snap to them, they are saved in the
`.igz`, and the Eraser and **Edit ▸ Delete Guides** remove them.
**Delete Placed Points** in the dialog erases only the guide points this
plugin placed (one undo step).

## Languages

English, Spanish and French (`i18n/en.json`, `es.json`, `fr.json`). The
plugin follows IngeTrazo's UI language; IngeTrazo 0.5.7 offers no French
yet, so `fr.json` takes effect once it does. Other languages fall back to
English.

## Permissions

`none` — the plugin only edits the open model. No network, no files outside
its own folder (it reads its `i18n/*.json`), no subprocesses. The toolbar
on/off choice is stored in IngeTrazo's own per-user settings (`QSettings`,
key `plugins/divide_points/show_toolbar`).

## Saved data

`scene.plugin_data["divide_points"] = {"version": 1, "points": [[x, y, z], …]}`
— the positions (metres) of the guide points the plugin placed, so that
**Delete Placed Points** removes only its own points. Plain JSON. A guide
point erased by other means is simply ignored. Points are compared as
IngeTrazo stores them (32-bit floats), so data saved by 0.1.0 still works.

## Internals used

The documented `setup(app)` contract (`add_menu`, `add_overlay`,
`add_context_menu`, `world_to_pixels`, `app.window`) plus these internals.
The plugin has no `Tool` subclass: its Extensions entry is a submenu, so the
command and the **Show in toolbar** check box sit together.

- `core.guide.Guide` — guide points (`direction=None`);
- `core.history.Command`, `AddGuideCommand`, `DeleteGuidesCommand`,
  `SetPluginDataCommand` — combined into one undoable command run through
  `viewport.history.execute(...)`, followed by
  `viewport.notify_scene_changed()`;
- `core.mesh.Edge` (`v0`, `v1`, `a`, `b`) and `scene.selection` — the
  selected lines and curves (the Select tool already puts every segment of
  a curve into the selection);
- `scene.guides`, `scene.plugin_data`, `scene.version`;
- `core.units` (`model_unit`, `bare_number_scale`, `model_precision`,
  `fmt_len`) — the model unit;
- `core.i18n.current_language` — to pick the plugin's catalog;
- `viewport.flash_status`, `viewport.window()`;
- `MainWindow._new_toolbar(title, object_name)` — the host's own toolbar
  builder (icon size, overflow button); a plain `QToolBar` is used if it is
  missing.

## Development

```bash
# From this folder's parent; INGETRAZO_ROOT points at an IngeTrazo checkout
# (without it the integration tests are skipped).
INGETRAZO_ROOT=/path/to/ingetrazo QT_QPA_PLATFORM=offscreen \
    python -m pytest divide_points/tests -q
python -m bandit -r divide_points
```

Files: `__init__.py` (header, constants, setup), `geometry.py`
(pure-Python placement rules), `scene_ops.py` (selection, commands,
preview overlay), `ui.py` (dialog), `toolbar.py` (toolbar and icon),
`texts.py` (translations), `i18n/` (en, es, fr).
