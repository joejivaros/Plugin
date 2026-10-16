# Scene Automation

IngeTrazo has a built-in function for playing back scenes, I discovered this only after I had already begun developing a similar plugin. It seems to me that mine offers a bit more flexibility:
1- My plugin uses existing scenes; there is no need to recreate scenes specifically for a cinematic sequence.
2- When the plugin is opened, the scenes appear in an "Inactive" window.
3- You can drag and drop scenes from the "Inactive" window to the "Active" window. Use "Ctrl+click" for individual selections and "Shift+click" for a continuous range of selections. Within the "Active" window, use "Ctrl+D" to duplicate a scene.
4- The order of scenes in the "Active" window can be changed via click-and-drag.
5- Transitions can be applied globally or on a per-scene basis.
6- A scene in the "Active" window can be deselected, in which case it will not be played.
7- The sequence (scenario) can be saved and loaded. Multiple sequences can be created for the same 3D drawing.
8- An audio file can be associated with each scene and will play automatically.
9- While a sequence is running, the plugin minimizes, leaving only three buttons visible: Pause, Start, and Stop. During a pause, IngeTrazo’s navigation tools remain functional.

A plugin that **plays the model's scenes in a sequence** with smooth,
cinematic camera moves. For each scene you set how fast the move starts and stops, how long it travels and how long the scene stays on screen, and you can attach a sound. You can loop the sequence, play it full screen, pause it and look around, export it as an MP4 video, save it to a file or keep it in the model.
There is already a similar function in IngeTrazo, I discovered this only after I had already begun developing a similar plugin. It seems to me that mine offers a bit more flexibility:
1- My plugin uses existing scenes; there is no need to recreate scenes specifically for a cinematic sequence.
2- When the plugin is opened, the scenes appear in an "Inactive" window.
3- You can drag and drop scenes from the "Inactive" window to the "Active" window. Use "Ctrl+click" for individual selections and "Shift+click" for a continuous range of selections. Within the "Active" window, use "Ctrl+D" to duplicate a scene.
4- The order of scenes in the "Active" window can be changed via click-and-drag.
5- Transitions can be applied globally or on a per-scene basis.
6- A scene in the "Active" window can be deselected, in which case it will not be played.
7- The sequence (scenario) can be saved and loaded. Multiple sequences can be created for the same 3D drawing.
8- An audio file can be associated with each scene and will play automatically.
9- While a sequence is running, the plugin minimizes, leaving only three buttons visible: Pause, Start, and Stop. During a pause, IngeTrazo’s navigation tools remain functional.
Tested on Windows 11 and Ubuntu, not tested on MacOs

- Plugin ID: `scenes_play` · Version: 0.2.1 · License: GPL-3.0-or-later
- Needs IngeTrazo ≥ 0.5.8 (extension API 2); tested with 0.5.8.
- Author: G. Andreotti · Contact: https://github.com/joejivaros
- Developed with the assistance of Claude AI, Opus 5.5

## Install

Copy the whole `scenes_play/` folder into your plugins folder
(**Extensions ▸ Open plugins folder**; on Windows `%APPDATA%\ingetrazo\plugins\`,
on Linux `~/.local/share/ingetrazo/plugins/`) and restart IngeTrazo.

### FFmpeg (for sounds and MP4 only)

IngeTrazo itself has no audio or video support, so sounds and the MP4
export use **FFmpeg**, a free program you install once. Everything else
works without it.

- Windows: download a build from https://ffmpeg.org/download.html (for
  example the "release essentials" zip from gyan.dev), unzip it anywhere.
  The `bin` folder holds `ffmpeg.exe`, `ffprobe.exe` and `ffplay.exe`.
- Linux: your package manager (`sudo apt install ffmpeg`).
- macOS: `brew install ffmpeg`.

If FFmpeg is on the `PATH` it is found by itself; otherwise the plugin asks for its folder the first time (or **Export MP4… ▸ FFmpeg folder…**) and remembers it.

## Use

1. Make a few scenes first (Scenes panel in the side tray: **+ Scene**).
2. **Extensions ▸ Scene Automation…** (or search "Scene Automation" with F3).
3. Build the sequence:
   - **Inactive** (right) lists the model's scenes that are not in the
     sequence. Select several with Ctrl+click or Shift+click and drag them
     into **Active**. Double-click or Enter adds them at the end.
   - **Active** (left) is the sequence, played top to bottom. Drag rows (by
     the name or the row number) to reorder them; drag them back to
     Inactive, or press Del, to take them out.
   - **Ctrl+D** duplicates the selected rows; **Ctrl+C / Ctrl+V** copy and
     paste them. A scene can appear several times. Right-click shows the
     same commands.
   - The **check box** of a row says whether it is played. Space toggles the
     selected rows. An unchecked row stays in the list but is skipped.
4. Set the four values of each row:

   | Column | Values | Meaning |
   |---|---|---|
   | **Start** | Slow / Medium / Fast | How long the move takes to reach full speed |
   | **Stop** | Slow / Medium / Fast | How long it takes to come to rest at the scene |
   | **Travel** | seconds (0–600) | Time of the whole move from the previous scene; 0 = cut |
   | **Wait** | seconds (0–3600) | Time the scene stays on screen |
   | **Sound** | a sound file (optional) | Plays when the camera arrives; the scene stays at least as long as the sound |

   The row above the list (**All**, then the four values) sets every
   **checked** row at once: changing a value there writes it into all
   checked rows; **Set** writes all four again. **All** checks or unchecks
   every row. New rows take these values.
5. **Loops**: how many times the sequence plays; 0 = continuously until
   Stop. Under the list: the number of scenes played, the time of one pass
   and the total time (seconds up to 120 s, then minutes:seconds), sounds
   included.
6. **Play**. The window is replaced by a small bar with **Pause / Resume**
   and **Stop**. During a pause the **Look Around** tool is active: drag in
   the view to turn the camera. **Resume** goes on from where the camera is
   (a pause during a stay first moves back to the scene); the tool you had
   comes back. When the playback ends or is stopped, the window comes back.
   With **Full screen** checked, only the 3D view shows, on the whole
   screen (IngeTrazo's Window ▸ Clean screen, plus full screen); **Esc**
   stops, and the window comes back as it was.

### Sounds

Double-click a row's **Sound** cell, or right-click ▸ **Attach sound…**
(several selected rows get the same sound). Formats: WAV, MP3, OGG, FLAC,
M4A, AAC, Opus, WMA. FFmpeg measures the sound when you attach it; the
column shows its name and length. Right-click ▸ **Remove sound** takes it
off.

- The sound starts when the camera **arrives** at the scene. The scene stays
  **Wait** seconds or the sound's length, whichever is longer.
- Pause stops the sound; Resume plays it on from where it was.
- The automation stores the sound's **path**, not the sound itself. A file
  that has moved shows as "(missing)" and its scene plays silent, for its
  own Wait. Sounds on a network share are refused: copy them to this
  computer first.

### Export MP4

**Export MP4…** records the sequence as a video:

- **Size**: 1280 × 720, 1920 × 1080, or the 3D view as it is. Only the
  last one draws dimensions and texts (IngeTrazo places them for the
  view's own shape, as in its sheets).
- **Frame rate**: 24, 30 or 60 frames per second.
- The frames are rendered one by one, not in real time, so the video is
  smooth even when the model is heavy; a progress window shows how far it
  is and can cancel (the file is then incomplete).
- The sounds are mixed in at the times they start. With Loops 0
  (continuous), the video holds one pass.
- H.264 video and AAC sound, which every player and video site reads.

### How a move works

Every move goes from wherever the camera is to the row's scene in **Travel**
seconds. The first move of a playback starts from the current view; each
new loop starts from the last scene. The move speeds up, keeps a steady
speed, then slows down, with smooth corners:

| Start / Stop | Share of the travel time spent speeding up / slowing down |
|---|---|
| Slow | 45 % |
| Medium | 30 % |
| Fast | 12 % |

The camera's target, distance (zoom), direction and field of view are
blended; the direction always turns the short way round. On arrival the
scene is shown exactly as a double-click in the Scenes panel shows it, so
its layers, style, section and shadows switch at that moment. A scene saved
in parallel projection switches to it on arrival.

### Buttons

| Button | What it does |
|---|---|
| **Load** | Opens an automation file (`.json`) |
| **Save** | Saves the automation to a file you choose; the window's title then shows the file name |
| **Cancel** | Undoes the changes made since the last Save, Load or Apply |
| **Apply** | Keeps the automation in the model, without playing it. It is saved in the `.igz` with the model and comes back when the model is opened. One undo step (Ctrl+Z) |
| **Play** | Plays the checked scenes |
| **Export MP4…** | Records them as a video (needs FFmpeg) |

The title shows **Scene Automation: <name>** — the file name — or **Not
saved**. A `*` marks changes since the last Save, Load or Apply. Closing the
window (or Esc) with such changes asks whether to save them first.

An automation names its scenes, so a file can be loaded onto another model
with scenes of the same names. Rows whose scene is not in the model are shown
in italics as "(missing)" and skipped. If a scene is deleted or another
model is opened while playing, the playback stops.

### Notes

- Showing a scene that changes layers, style or hidden objects marks the
  model as modified, as a click in the Scenes panel does. Scenes that only
  move the camera do not.
- The window is not shown while playing; open the menu entry again after
  Stop.

## Languages

English, Spanish and French (`i18n/en.json`, `es.json`, `fr.json`). The
plugin follows IngeTrazo's UI language; other languages fall back to
English.

## Permissions

`filesystem(automation .json, sound and .mp4 files the user picks in file
dialogs; a temporary log file)` and `subprocess(ffprobe, ffplay, ffmpeg from
the user's FFmpeg folder or PATH; fixed argument lists, no shell)`.

**Files**

- It reads and writes only the files you pick in its file dialogs
  (automation, sound, video). It never deletes files. An automation file
  over 1 MB is refused, and every value read is checked (type, range,
  finite numbers) before use.
- While exporting, FFmpeg's messages go to a temporary file that the system
  removes when it is closed.
- It remembers folders, the FFmpeg folder, the export choices, Full screen
  and the window position in IngeTrazo's own settings, under
  `plugins/scenes_play/`.
- The automation kept in the model (Apply) is plain JSON in the model's
  plugin data, under the key `scenes_play`. It holds sound **paths**, never
  sound data.

**Programs (only for sounds and MP4)**

- Only `ffprobe` (length of a sound you attach), `ffplay` (the sound while
  playing, no window) and `ffmpeg` (the MP4) are run. They come from the
  folder you chose or from the `PATH`, with fixed argument lists and never
  through a shell. Nothing runs if you use no sound and do not export.
- Every input is given to FFmpeg as `file:<path>`, so it is always read as a
  plain local file, never as a URL or one of FFmpeg's protocols.
- Sound paths read from an automation file or a model must be absolute,
  local paths ending in a sound extension. Network paths (`\\server\…`,
  `//host/…`) and URLs are refused, so a file from someone else cannot make
  your computer contact a server (for example, to leak Windows credentials
  over SMB) or open an unexpected file.
- No network, no `eval`/`exec`, no pickle.
- The extensions index's automatic check will report the `subprocess` use;
  this section is what a reviewer needs to know about it.

## Internals used

The documented extension API (`setup(app)`: `add_menu_action`,
`document_data`, `set_document_data`, `on_document_changed`) has no call for
scenes, the camera or tools, so the plugin also uses these IngeTrazo
internals. They may change in a later 0.x version; each is used with a
fallback, all in `host.py`:

- `scene.saved_views` — the scenes (`core.saved_views.SavedView`: name,
  target, distance, yaw, pitch, fov).
- `viewport.camera` — the orbit camera (`target`, `distance`, `yaw`,
  `pitch`, `fov_deg`), set directly during a move.
- `window.tray.scenes.list` and `window.tray.scenes._on_activate(row)` —
  shows a scene exactly as the Scenes panel does (IngeTrazo's own Browser
  goes through it the same way). Fallback: `SavedView.apply`.
- `window._tools` and `window._activate_tool("look_around")` — Look Around
  during a pause, and the previous tool back afterwards.
- `window._act_clean_screen` (Window ▸ Clean screen) and
  `window._clean_exit_btn` — Full screen shows only the 3D view; the
  "Exit clean screen" button is hidden while playing (Stop is on the bar).
- `viewport.render_image(width, height, overlays)` — the video frames, as
  IngeTrazo's sheet composer and bundled AI bridge use it; the camera's
  `aspect` is set to the video's shape around each call.

## Files

| File | Contents |
|---|---|
| `__init__.py` | Header, constants, `setup(app)` |
| `model.py` | The automation, its JSON form and its checks (no Qt) |
| `motion.py` | Speed curve and camera blending (no Qt) |
| `player.py` | The playback state machine (no Qt) |
| `host.py` | Everything taken from IngeTrazo |
| `media.py` | FFmpeg: finding it, sound length, playing a sound, the MP4 command |
| `export.py` | The Export MP4 dialog and the frame-by-frame recording |
| `ui_dialog.py` | The window, its buttons and the row of global values |
| `ui_lists.py` | The Active table and the Inactive list (drag and drop, keys) |
| `ui_player.py` | The player bar, the frame timer and full screen |
| `texts.py`, `i18n/` | Translations |
| `tests/` | pytest suite (not shipped in the release archive) |

## Tests

From the plugin folder, with PySide6 and pytest installed:

```bash
QT_QPA_PLATFORM=offscreen INGETRAZO_ROOT=/path/to/ingetrazo python -m pytest tests -q
```

The tests of `model`, `motion`, `player` and `media` need no IngeTrazo
and run no FFmpeg; the integration tests are skipped when IngeTrazo cannot
be imported.

## Ideas for later versions

- A timeline editor with a scene track and an audio track.
