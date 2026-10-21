# Changelog — Divide Points

All notable changes; newest first. Versions follow Semantic Versioning.

## 0.2.2 — 2026-10-21

- Fixed: with many extensions loaded, IngeTrazo became very slow (a click
  went from about 2 s to 15 s in a reviewer's test on 0.5.9). The toolbar
  icon's theme watcher was installed on the whole application and redrew
  the icon on every widget's palette change, which some extensions trigger
  on each mouse event. It now watches only its own toolbar, and redraws
  only when the theme's ink colour really changed. Thanks to the
  IngeTrazo reviewers for the report.
- Tested with IngeTrazo 0.5.9.

## 0.2.1 — 2026-10-12

- Added: French translation (`i18n/fr.json`). It is used once IngeTrazo
  offers French as a UI language (0.5.7 does not yet).

## 0.2.0 — 2026-10-11

* New: **Extensions ▸ Divide Points ▸ Show in toolbar** check box shows a
toolbar with a button that opens the dialog (icon drawn in code). The
choice is remembered. The Extensions entry is now a submenu.
* Changed: the placed points show as IngeTrazo's own guide crosses (more
precise, matches the app). The blue discs are gone, and the preview is now
orange crosses.
* Fixed: guide points store 32-bit coordinates, so away from the origin
most points were not recognised. They lost their marker (shown as plain
crosses), and **Delete Placed Points** and the duplicate check missed
them. Data saved by 0.1.0 is read correctly.
* French UI

## 0.1.0 — 2026-10-11

First version.

* Place guide points along the selected lines and curves (connected edges
form one path; closed loops supported).
* Spacing by number of points or by distance in the model's unit, with an
optional limit on the number of points.
* Start from both ends or from the middle.
* Live preview (orange rings) and visible markers (blue discs) for the
placed points; existing guide points are not duplicated.
* One undo step per placement; **Delete Placed Points** removes only this
plugin's points.
* English and Spanish UI.

