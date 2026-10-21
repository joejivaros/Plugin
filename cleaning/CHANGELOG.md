# Changelog — Cleaning

All notable changes; newest first. Versions follow Semantic Versioning.

## 0.1.2 — 2026-10-21

- Fixed: the toolbar icon's theme watcher was installed on the whole
  application and redrew the icon on every widget's palette change. With
  extensions that restyle widgets on each mouse event, this slowed
  IngeTrazo down a lot (reported for Divide Points, which shares the code).
  It now watches only its own toolbar, and redraws only when the ink or
  accent colour really changed.

## 0.1.1 — 2026-10-21

- Fixed: after cleaning some models, saving failed with "list index out of
  range" and the model could not be saved. A hole listing only two points
  twice (`a, a, b, b`, left by an import) became a two-point hole once its
  repeated corners were repaired, and IngeTrazo cannot save a hole of fewer
  than three points. **Repair degenerate faces** now removes holes that
  have no area. Seen on a 175,000-face house model.
- Added: a safety check. If a clean-up would ever leave a face with fewer
  than three corners, it is rolled back whole and the dialog says it
  failed, instead of leaving a model that cannot be saved.

## 0.1.0 — 2026-10-21

First release.

- **Extensions ▸ Cleaning ▸ Clean Up…** opens a dialog where you tick what
  to clean:
  - Geometry: repair degenerate faces (erase faces with no area, repair
    faces that list a corner twice, erase zero-length edges), erase
    duplicate faces, merge coplanar faces (angle tolerance, optionally only
    faces with the same material), erase stray edges, repair split edges.
    Loose vertices are always removed.
  - Model: merge identical materials, purge unused materials, purge unused
    layers, erase empty groups.
- Apply to the whole model, only what is being edited, or only the
  selection. Locked groups are never touched.
- **Analyse** counts what would be cleaned without changing the model;
  **Clean** does it as one undo step.
- **Show in toolbar** (in the menu and in the dialog) adds a toolbar with a
  broom button. The icon is drawn in code and follows the accent colour
  chosen in Preferences.
- English, Spanish and French.
