# Changelog — Cleaning

All notable changes; newest first. Versions follow Semantic Versioning.

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
