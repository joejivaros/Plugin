# Changelog — Scene Automation

All notable changes; newest first. Versions follow Semantic Versioning.

## 0.2.1 — 2026-10-15

* First release for the extensions index (release archive, header). No
  change in behaviour from 0.2.0.

## 0.2.0 — 2026-10-15

* New: **sounds**. Attach a sound file to a scene (Sound column or
  right-click); it plays when the camera arrives, and the scene stays at
  least as long as the sound. Pause / Resume follow it. Needs FFmpeg.
* New: **Export MP4…**: records the sequence as an H.264 / AAC video at
  1280 × 720, 1920 × 1080 or the view's size, 24 / 30 / 60 fps, frame by
  frame, with the sounds mixed in. Needs FFmpeg.
* New: **Full screen** check box: play with only the 3D view on the whole
  screen; Esc stops.
* Security: sound paths from automation files and models must be local and
  absolute (no network shares or URLs). FFmpeg runs with fixed argument
  lists and `file:` inputs. New permission: `subprocess(ffprobe, ffplay,
  ffmpeg)`.
* Saved format version 2 (adds the sound); version 1 files still load.
  0.1.0 cannot read files saved by 0.2.0.

## 0.1.0 — 2026-10-15

First version.

* Play the model's scenes in sequence with smooth camera moves. Each scene
  has its own Start and Stop speed (Slow / Medium / Fast), Travel time and
  Wait time.
* Active and Inactive lists with drag and drop, multiple selection
  (Ctrl / Shift), reordering, duplicate (Ctrl+D), copy / paste and a check
  box per scene. A row above the list sets the four values of every checked
  scene.
* Loops (0 = continuously), with the number of scenes, the time of one pass
  and the total time shown.
* Player bar with Pause / Resume and Stop; Look Around while paused.
* Save / Load automation files (JSON), Apply to keep the automation in the
  model (one undo step), Cancel to undo unsaved changes, and a warning when
  closing with unsaved changes.
* English, Spanish and French.
