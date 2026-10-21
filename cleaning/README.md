# Cleaning

A plugin that **cleans a model** in one undo step: it purges what is unused
and repairs the geometry left behind by imports and editing. You pick which
items to clean.

- Plugin ID: `cleaning` · Version: 0.1.1 · License: GPL-3.0-or-later
- Date: October 21 2026
- Needs IngeTrazo ≥ 0.5.9 (extension API 2); tested with 0.5.9.
- Author: G. Andreotti · Contact: https://github.com/joejivaros
- Developed with the assistance of Claude AI, Opus 5.5

## Install

Copy the whole `cleaning/` folder into your plugins folder
(**Extensions ▸ Open plugins folder**; on Windows `%APPDATA%\ingetrazo\plugins\`,
on Linux `~/.local/share/ingetrazo/plugins/`) and restart IngeTrazo.

## Use

1. **Extensions ▸ Cleaning ▸ Clean Up…**, or the toolbar button.
2. Tick what to clean (see below) and choose where.
3. **Analyse** counts what would be cleaned, item by item, without changing
   the model.
4. **Clean** does it. It is one undo step: **Edit ▸ Undo** puts everything
   back.

The dialog is modeless and remembers your choices between sessions.

### What it cleans

**Geometry**

| Item | What it does |
|---|---|
| Repair degenerate faces | Erases faces with no area (fewer than three distinct corners, or all corners on one line) and the edges only they used. Also repairs faces whose loop lists a corner twice in a row (`a, a, b, c`, a triangle some importers store as a quad), removes holes with no area (fewer than three distinct points), and erases the zero-length edges such a repeat leaves (an edge from a point to itself). |
| Erase duplicate faces | Erases a face that lies on exactly the same edges as another one. The face with more holes is kept; it takes the paint of the erased one if it had none. |
| Merge coplanar faces | Removes the edge between two faces in the same plane, so they become one face. **Angle tolerance** (default 0.05°, up to 5°): faces whose planes differ by less count as coplanar. Keep it small, because a finely divided curved surface is not flat. **Only faces with the same material** (on by default) keeps the edge between faces painted differently. Faces on different layers or with different BIM tags are never merged, and neither are faces facing opposite ways. |
| Erase stray edges | Erases edges that border no face. A mesh made only of lines (a plan, a profile waiting for Follow Me) is left alone. |
| Repair split edges | Joins the collinear pieces of a line back into one edge, with IngeTrazo's own **Join Segments** rules: the two pieces bound the same faces, have the same flags (soft, hidden, layer) and are not part of a curve. |
| Loose vertices | Always: points no edge or face uses any more. |

**Model** (always the whole document, whatever **Apply to** says)

| Item | What it does |
|---|---|
| Merge identical materials | Materials with the same colour, texture, opacity and finish become one. Faces (front and back) and painted groups are repointed to the kept one, so nothing changes on screen. The kept name is the first one in the registry without a `" (2)"`-style suffix. |
| Purge unused materials | Materials no face and no group wears (IngeTrazo's own Purge rules). Their embedded textures leave the `.igz` too. |
| Purge unused layers | Layers nothing carries. Layers a saved scene hides are kept. |
| Erase empty groups | Groups and components with nothing inside, nested ones included. Locked groups, the group being edited and component definitions kept in the file are kept. |

### Apply to

- **The whole model**: the loose geometry and every group and component.
  This option is unavailable while a group is open for editing: close it
  first, or use the next option.
- **Only what is being edited**: the open group, or the loose geometry when
  no group is open.
- **Only the selection**: the selected faces and edges, and the selected
  groups whole.

Locked groups are never touched. A component's definition is cleaned once
and every copy shows the result.

### Toolbar

**Extensions ▸ Cleaning ▸ Show in toolbar**, or the **Show in toolbar**
check box in the dialog, shows a toolbar with one button that opens the
dialog. The choice is remembered between sessions. The toolbar moves,
floats and hides like the built-in ones. Hiding it from Qt's toolbar
right-click menu also clears the check boxes.

The icon is drawn in code with QPainter (no image file): a broom in the
theme's ink colour, with sparkles in the accent colour chosen in
**Preferences ▸ General ▸ Accent colour**. It is redrawn when the theme or
the accent changes.

### Example

On a kitchen barbecue imported from SketchUp (`bbq.igz`, 30,760 faces,
339 materials), with the default options, the plugin:
- repaired 2,446 faces with a repeated corner and erased 1,720 degenerate
  faces and 3,934 zero-length edges;
- erased 19 duplicate faces and merged 11 coplanar ones;
- removed 1,211 split points;
- merged 25 identical materials and purged 297 unused ones.

That is about 4 s on a desktop PC. The surface area, the paints and the
bounding box are unchanged; the saved file went from 69 MB to 8 MB, because
the unused materials' textures were gone.

## Languages

English, Spanish and French (`i18n/en.json`, `es.json`, `fr.json`). The
plugin follows IngeTrazo's UI language; other languages fall back to
English.

## Permissions

None. The plugin only edits the open model, through IngeTrazo's undo
history. It reads and writes nothing but its own settings in IngeTrazo's
per-user settings store (`plugins/cleaning/options` as plain JSON, and
`plugins/cleaning/show_toolbar`). No network, no subprocess, no files.

## Internals used

The plugin uses the documented `setup(app)` API (`app.add_menu`) and these
IngeTrazo internals, which may change in a later 0.x release:

- `core.history.Command`, `CommandRejected`, `_dirty_group_chunks`: the
  clean-up is a `Command` run through `viewport.history.execute`.
- `core.mesh.Mesh`: `capture_state` / `restore_state` (snapshot undo),
  `add_face`, `remove_face`, `remove_edge`, `find_edge`, `_link_edge`
  (tests only), `dissolve_edge`, `dissolve_coplanar_pair`,
  `collapsible_vertex`, `prune_orphan_vertices`. Edits made in place (bulk
  edge removal, repaired loops) set the mesh's `_chunk_dirty` and
  `_mut_serial` as the primitives do. `_winding_rev` is bumped on undo and
  redo, as in IngeTrazo's Solid Inspector.
- `core.edits.join_edges` (Join Segments, new in 0.5.9).
- `core.purge`: `iter_meshes`, `unused_materials`, `unused_layers`.
- `core.group.iter_placements`; `scene.groups`, `scene.kept_components`,
  `scene.materials`, `scene.layers`, `scene.edit_group`,
  `scene._edit_stack`, `Group.locked`, `Group.material`.
- `views.theme.accent_color` (0.5.9) for the icon, with the orange as a
  fallback.
- `window._new_toolbar` for a toolbar like the built-in ones, with a plain
  `QToolBar` as a fallback.
- `history.last_error` and `history.last_rejected`.

Workarounds for IngeTrazo 0.5.9:
- The `.igz` writer fails ("list index out of range") on a face whose
  outline or a hole has fewer than three points. The plugin removes holes
  with no area, and checks every cleaned mesh before finishing: if a face
  would be left like that, the whole clean-up is rolled back.
- `Mesh.dissolve_coplanar_pair` raises `IndexError` when two faces' union
  has no outline. It does so before changing anything, so the plugin treats
  that pair as not mergeable.
- `Mesh.remove_face` can leave a face on the radial list of an edge when
  its loop repeats a corner. The plugin takes the erased face off every
  edge at its corners.

## Tests

```bash
INGETRAZO_ROOT=<IngeTrazo checkout> QT_QPA_PLATFORM=offscreen \
    python -m pytest cleaning/tests -q
```

The tests run headless and are skipped when IngeTrazo cannot be imported.
The last one (`test_zz_main_window.py`) installs the plugin in a temporary
user plugins folder and drives IngeTrazo's real main window.

## License

GPL-3.0-or-later; see `LICENSE`.
