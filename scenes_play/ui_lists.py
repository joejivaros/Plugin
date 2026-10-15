# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The two scene lists of the dialog.

- **Active** (:class:`ActiveTable` over :class:`ActiveModel`): the sequence,
  one row per entry — a check box with the scene's name, then its Start,
  Stop, Travel and Wait, always editable. Rows are reordered by dragging
  them (by the name or the row number), removed with Del or by dragging
  them back to Inactive, and duplicated with Ctrl+D (or Ctrl+C / Ctrl+V).
  The last column shows the row's sound; double-click it, or right-click
  ▸ Attach sound…, to pick one (the dialog measures it).
- **Inactive** (:class:`InactiveList`): the model's scenes that are not in
  the sequence; drag them (Ctrl / Shift for several) into Active, or
  double-click / press Enter to add them at the end.

Both lists only exchange data through their own MIME types, so a drop from
anywhere else is ignored.
"""
from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

from PySide6.QtCore import (QAbstractTableModel, QEvent, QItemSelection,
                            QItemSelectionModel, QMimeData, QModelIndex, Qt,
                            Signal)
from PySide6.QtGui import QDrag, QFont, QKeySequence, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox,
                               QHeaderView, QListWidget, QMenu,
                               QStyledItemDelegate, QTableView)

from .model import EASES, TRAVEL_MAX, WAIT_MAX, Entry, split_duration
from .texts import t

MIME_ROWS = "application/x-scenes-play-rows"
MIME_NAMES = "application/x-scenes-play-names"

COL_SCENE, COL_START, COL_STOP, COL_TRAVEL, COL_WAIT, COL_SOUND = range(6)
COLUMNS = 6
PARAM_COLUMNS = (COL_START, COL_STOP, COL_TRAVEL, COL_WAIT)
FIELD_OF_COLUMN = {COL_START: "start", COL_STOP: "stop",
                   COL_TRAVEL: "travel", COL_WAIT: "wait"}
TOP_OF_COLUMN = {COL_TRAVEL: TRAVEL_MAX, COL_WAIT: WAIT_MAX}

#: Copied entries (Ctrl+C), pasted with Ctrl+V; shared by the whole plugin.
_CLIPBOARD: list[Entry] = []


def ease_names() -> dict[str, str]:
    """Slow / Medium / Fast in the UI language, by their saved key."""
    return {"slow": t("Slow"), "medium": t("Medium"), "fast": t("Fast")}


def seconds_text(seconds: float) -> str:
    """A duration as the dialog shows it: ``45 s``, or ``2:05`` past 120 s."""
    clock, text = split_duration(seconds)
    return text if clock else t("{n} s", n=text)


def _payload(mime: QMimeData, kind: str):
    """The decoded JSON of one of our MIME types, or None."""
    if mime is None or not mime.hasFormat(kind):
        return None
    try:
        return json.loads(bytes(mime.data(kind)).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _names_from(mime: QMimeData) -> list[str]:
    raw = _payload(mime, MIME_NAMES)
    if not isinstance(raw, list):
        return []
    return [n for n in raw if isinstance(n, str) and n]


# ---- Active: the model -------------------------------------------------------
class ActiveModel(QAbstractTableModel):
    """The sequence's entries as table rows."""

    #: Emitted after every change the user made to the entries.
    edited = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.entries: list[Entry] = []
        self.available: set[str] = set()
        self.token = f"{id(self)}"       # tells our own drags apart
        self._ease = ease_names()

    # ---- Filling -----------------------------------------------------------
    def set_entries(self, entries) -> None:
        self.beginResetModel()
        self.entries = [e.copy() for e in entries]
        self.endResetModel()

    def set_available(self, names) -> None:
        names = set(names)
        if names != self.available:
            self.available = names
            if self.entries:
                self.dataChanged.emit(self.index(0, COL_SCENE),
                                      self.index(len(self.entries) - 1,
                                                 COL_SCENE))

    def missing(self, entry: Entry) -> bool:
        return entry.scene not in self.available

    # ---- Qt model ----------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else COLUMNS

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Vertical:
            return str(section + 1)
        return (t("Scene"), t("Start"), t("Stop"), t("Travel"),
                t("Wait"), t("Sound"))[section]

    def _sound_data(self, e: Entry, role):
        if not e.audio:
            if role == Qt.ToolTipRole:
                return t("Double-click to attach a sound.")
            return None
        name = PureWindowsPath(e.audio).name
        there = Path(e.audio).is_file()
        if role == Qt.DisplayRole:
            if not there:
                return t("{name} (missing)", name=name)
            return f"♪ {name} · {seconds_text(e.audio_length)}"
        if role == Qt.ToolTipRole:
            if not there:
                return t("The sound file is not there; the scene plays "
                         "silent.") + "\n" + e.audio
            return e.audio + "\n" + t(
                "The scene stays {time} (at least the sound's length).",
                time=seconds_text(e.stay()))
        if role == Qt.FontRole and not there:
            font = QFont()
            font.setItalic(True)
            return font
        if role == Qt.ForegroundRole and not there:
            return QPalette().brush(QPalette.Disabled, QPalette.Text)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.entries):
            return None
        e = self.entries[index.row()]
        col = index.column()
        if col == COL_SCENE:
            missing = self.missing(e)
            if role == Qt.DisplayRole:
                return (t("{name} (missing)", name=e.scene) if missing
                        else e.scene)
            if role == Qt.CheckStateRole:
                return Qt.Checked if e.enabled else Qt.Unchecked
            if role == Qt.FontRole and missing:
                font = QFont()
                font.setItalic(True)
                return font
            if role == Qt.ForegroundRole and (missing or not e.enabled):
                return QPalette().brush(QPalette.Disabled, QPalette.Text)
            if role == Qt.ToolTipRole:
                if missing:
                    return t("This scene is not in the model; it is skipped.")
                return (t("Played") if e.enabled
                        else t("Not played (unchecked)"))
            return None
        if col == COL_SOUND:
            return self._sound_data(e, role)
        value = getattr(e, FIELD_OF_COLUMN[col])
        if role == Qt.EditRole:
            return value
        if role == Qt.DisplayRole:
            return (self._ease.get(value, value) if col in (COL_START, COL_STOP)
                    else seconds_text(value))
        return None

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or index.row() >= len(self.entries):
            return False
        e = self.entries[index.row()]
        col = index.column()
        if col == COL_SCENE:
            if role != Qt.CheckStateRole:
                return False
            on = Qt.CheckState(value) == Qt.Checked
            if on == e.enabled:
                return False
            e.enabled = on
        elif role != Qt.EditRole or col == COL_SOUND:
            return False
        elif col in (COL_START, COL_STOP):
            if value not in EASES or value == getattr(e, FIELD_OF_COLUMN[col]):
                return False
            setattr(e, FIELD_OF_COLUMN[col], value)
        else:
            try:
                seconds = min(max(float(value), 0.0), TOP_OF_COLUMN[col])
            except (TypeError, ValueError):
                return False
            if seconds == getattr(e, FIELD_OF_COLUMN[col]):
                return False
            setattr(e, FIELD_OF_COLUMN[col], seconds)
        self.dataChanged.emit(index.siblingAtColumn(0),
                              index.siblingAtColumn(COL_SOUND))
        self.edited.emit()
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        if index.column() == COL_SCENE:
            return base | Qt.ItemIsUserCheckable
        if index.column() == COL_SOUND:
            return base
        return base | Qt.ItemIsEditable

    def set_sound(self, rows, path: str | None, length: float = 0.0) -> None:
        """Attach the sound at ``path`` (``length`` s) to ``rows``, or
        remove theirs (``path`` None)."""
        changed = False
        for r in rows:
            if 0 <= r < len(self.entries):
                e = self.entries[r]
                new = (path, float(length) if path else 0.0)
                if (e.audio, e.audio_length) != new:
                    e.audio, e.audio_length = new
                    changed = True
        if changed:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self.entries) - 1,
                                             COL_SOUND))
            self.edited.emit()

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def mimeTypes(self):
        return [MIME_ROWS, MIME_NAMES]

    # ---- Editing the sequence ----------------------------------------------
    def insert_entries(self, row: int, entries) -> list[int]:
        """Insert copies of ``entries`` at ``row``; their new rows."""
        entries = [e.copy() for e in entries]
        if not entries:
            return []
        row = min(max(row, 0), len(self.entries))
        self.beginResetModel()
        self.entries[row:row] = entries
        self.endResetModel()
        self.edited.emit()
        return list(range(row, row + len(entries)))

    def remove_rows(self, rows) -> None:
        rows = sorted({r for r in rows if 0 <= r < len(self.entries)})
        if not rows:
            return
        self.beginResetModel()
        for r in reversed(rows):
            del self.entries[r]
        self.endResetModel()
        self.edited.emit()

    def move_rows(self, rows, dest: int) -> list[int]:
        """Move ``rows`` (kept in their order) to before row ``dest``;
        their new rows."""
        rows = sorted({r for r in rows if 0 <= r < len(self.entries)})
        if not rows:
            return []
        moving = [self.entries[r] for r in rows]
        dest -= sum(1 for r in rows if r < dest)
        rest = [e for i, e in enumerate(self.entries) if i not in set(rows)]
        dest = min(max(dest, 0), len(rest))
        new = rest[:dest] + moving + rest[dest:]
        if new == self.entries and all(a is b for a, b in
                                       zip(new, self.entries)):
            return rows
        self.beginResetModel()
        self.entries = new
        self.endResetModel()
        self.edited.emit()
        return list(range(dest, dest + len(moving)))

    def set_checked_field(self, field: str, value) -> int:
        """Write ``value`` into ``field`` of every checked entry; how many
        changed."""
        changed = 0
        for e in self.entries:
            if e.enabled and getattr(e, field) != value:
                setattr(e, field, value)
                changed += 1
        if changed:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self.entries) - 1, COL_SOUND))
            self.edited.emit()
        return changed

    def set_all_enabled(self, on: bool) -> None:
        if all(e.enabled == on for e in self.entries):
            return
        for e in self.entries:
            e.enabled = on
        self.dataChanged.emit(self.index(0, 0),
                              self.index(len(self.entries) - 1, COL_SOUND))
        self.edited.emit()


# ---- Active: the always-open editors -----------------------------------------
class ParamDelegate(QStyledItemDelegate):
    """A combo box for Start / Stop, a seconds box for Travel / Wait. They
    are opened once per cell and stay open, as in a form."""

    def createEditor(self, parent, _option, index):
        col = index.column()
        if col in (COL_START, COL_STOP):
            box = QComboBox(parent)
            for key, text in ease_names().items():
                box.addItem(text, key)
            box.activated.connect(lambda _i, b=box: self.commitData.emit(b))
            return box
        spin = QDoubleSpinBox(parent)
        spin.setRange(0.0, TOP_OF_COLUMN[col])
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" " + t("s"))
        spin.setKeyboardTracking(False)
        spin.setAccelerated(True)
        spin.valueChanged.connect(lambda _v, s=spin: self.commitData.emit(s))
        return spin

    def setEditorData(self, editor, index):
        value = index.data(Qt.EditRole)
        editor.blockSignals(True)
        if isinstance(editor, QComboBox):
            i = editor.findData(value)
            editor.setCurrentIndex(max(i, 0))
        else:
            editor.setValue(float(value or 0.0))
        editor.blockSignals(False)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentData(), Qt.EditRole)
        else:
            model.setData(index, editor.value(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, _index):
        editor.setGeometry(option.rect)


# ---- Active: the view -----------------------------------------------------------
_ACTIVE_KEYS = {
    (Qt.Key_Delete, Qt.NoModifier), (Qt.Key_Backspace, Qt.NoModifier),
    (Qt.Key_D, Qt.ControlModifier), (Qt.Key_C, Qt.ControlModifier),
    (Qt.Key_V, Qt.ControlModifier), (Qt.Key_Space, Qt.NoModifier),
}


def _key_of(event) -> tuple:
    mods = event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier
                                | Qt.AltModifier)
    return (event.key(), mods)


class ActiveTable(QTableView):
    """The sequence: reorder by dragging, Del, Ctrl+D / C / V, Space."""

    #: Rows to attach a sound to (the dialog picks and measures it).
    sound_requested = Signal(list)

    def __init__(self, model: ActiveModel, entry_factory, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenes_play_active")
        self._entry_factory = entry_factory      # name → new Entry
        self.setModel(model)
        self.setItemDelegate(ParamDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        head = self.horizontalHeader()
        head.setSectionResizeMode(COL_SCENE, QHeaderView.Stretch)
        for col in PARAM_COLUMNS:
            head.setSectionResizeMode(col, QHeaderView.Fixed)
        head.resizeSection(COL_START, 96)
        head.resizeSection(COL_STOP, 96)
        head.resizeSection(COL_TRAVEL, 84)
        head.resizeSection(COL_WAIT, 92)
        head.setSectionResizeMode(COL_SOUND, QHeaderView.Interactive)
        head.resizeSection(COL_SOUND, 170)
        self.doubleClicked.connect(self._on_double_click)
        self.verticalHeader().setDefaultSectionSize(
            QComboBox().sizeHint().height() + 2)
        model.modelReset.connect(self.open_editors)
        self.open_editors()

    def model(self) -> ActiveModel:            # typed shortcut
        return super().model()

    def open_editors(self) -> None:
        m = self.model()
        for row in range(m.rowCount()):
            for col in PARAM_COLUMNS:
                self.openPersistentEditor(m.index(row, col))

    # ---- Selection ---------------------------------------------------------
    def selected_rows(self) -> list[int]:
        sm = self.selectionModel()
        return sorted({i.row() for i in sm.selectedRows()}) if sm else []

    def select_rows(self, rows) -> None:
        m, sm = self.model(), self.selectionModel()
        sel = QItemSelection()
        for r in rows:
            if 0 <= r < m.rowCount():
                sel.select(m.index(r, 0), m.index(r, COL_SOUND))
        sm.select(sel, QItemSelectionModel.ClearAndSelect)
        if rows:
            sm.setCurrentIndex(m.index(rows[-1], 0),
                               QItemSelectionModel.NoUpdate)

    # ---- Commands ----------------------------------------------------------
    def remove_selected(self) -> None:
        rows = self.selected_rows()
        self.model().remove_rows(rows)
        if rows:
            self.select_rows([min(rows[0], self.model().rowCount() - 1)])

    def duplicate_selected(self) -> None:
        """Copies of the selected rows, right after the last of them."""
        rows = self.selected_rows()
        if not rows:
            return
        entries = [self.model().entries[r] for r in rows]
        self.select_rows(self.model().insert_entries(rows[-1] + 1, entries))

    def copy_selected(self) -> None:
        rows = self.selected_rows()
        if rows:
            _CLIPBOARD[:] = [self.model().entries[r].copy() for r in rows]

    def paste(self) -> None:
        if not _CLIPBOARD:
            return
        rows = self.selected_rows()
        at = rows[-1] + 1 if rows else self.model().rowCount()
        self.select_rows(self.model().insert_entries(at, _CLIPBOARD))

    def toggle_selected(self) -> None:
        m = self.model()
        rows = self.selected_rows()
        if not rows:
            return
        on = not all(m.entries[r].enabled for r in rows)
        for r in rows:
            m.setData(m.index(r, COL_SCENE),
                      Qt.Checked if on else Qt.Unchecked, Qt.CheckStateRole)

    def add_names(self, names, row: int | None = None) -> None:
        m = self.model()
        at = m.rowCount() if row is None else row
        self.select_rows(m.insert_entries(
            at, [self._entry_factory(n) for n in names]))

    # ---- Keys and menu -----------------------------------------------------
    def event(self, event) -> bool:
        # Our keys win over any application shortcut while the list has
        # the focus (they are only ours inside this list).
        if event.type() == QEvent.ShortcutOverride \
                and _key_of(event) in _ACTIVE_KEYS:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        key = _key_of(event)
        actions = {
            (Qt.Key_Delete, Qt.NoModifier): self.remove_selected,
            (Qt.Key_Backspace, Qt.NoModifier): self.remove_selected,
            (Qt.Key_D, Qt.ControlModifier): self.duplicate_selected,
            (Qt.Key_C, Qt.ControlModifier): self.copy_selected,
            (Qt.Key_V, Qt.ControlModifier): self.paste,
            (Qt.Key_Space, Qt.NoModifier): self.toggle_selected,
        }
        if key in actions:
            actions[key]()
            event.accept()
            return
        super().keyPressEvent(event)

    def _menu(self, pos) -> None:
        index = self.indexAt(pos)
        if index.isValid() and index.row() not in self.selected_rows():
            self.select_rows([index.row()])
        rows = self.selected_rows()
        has_rows = bool(rows)
        has_sound = any(self.model().entries[r].audio for r in rows)
        menu = QMenu(self)
        for text, keys, fn, enabled in (
                (t("Duplicate"), "Ctrl+D", self.duplicate_selected, has_rows),
                (t("Copy"), "Ctrl+C", self.copy_selected, has_rows),
                (t("Paste"), "Ctrl+V", self.paste, bool(_CLIPBOARD)),
                (t("Remove from the sequence"), "Del", self.remove_selected,
                 has_rows),
                (None, None, None, None),
                (t("Attach sound…"), None,
                 lambda: self.sound_requested.emit(self.selected_rows()),
                 has_rows),
                (t("Remove sound"), None, self.remove_sound, has_sound)):
            if text is None:
                menu.addSeparator()
                continue
            act = menu.addAction(text)
            if keys:
                act.setShortcut(QKeySequence(keys))   # shown, handled above
            act.setEnabled(enabled)
            act.triggered.connect(lambda _c=False, f=fn: f())
        menu.exec(self.viewport().mapToGlobal(pos))

    def remove_sound(self) -> None:
        self.model().set_sound(self.selected_rows(), None)

    def _on_double_click(self, index) -> None:
        if index.isValid() and index.column() == COL_SOUND:
            self.sound_requested.emit([index.row()])

    # ---- Drag and drop -----------------------------------------------------
    def startDrag(self, _actions) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        mime = QMimeData()
        mime.setData(MIME_ROWS, json.dumps(
            {"source": self.model().token, "rows": rows}).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def _accepts(self, mime) -> bool:
        return mime.hasFormat(MIME_NAMES) or self._own_rows(mime) is not None

    def _own_rows(self, mime):
        raw = _payload(mime, MIME_ROWS)
        if not isinstance(raw, dict) or raw.get("source") != self.model().token:
            return None
        rows = raw.get("rows")
        if not isinstance(rows, list):
            return None
        return [r for r in rows if isinstance(r, int)
                and not isinstance(r, bool)]

    def dragEnterEvent(self, event) -> None:
        if self._accepts(event.mimeData()):
            super().dragEnterEvent(event)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._accepts(event.mimeData()):
            super().dragMoveEvent(event)        # draws the drop indicator
            event.setDropAction(Qt.MoveAction if event.source() is self
                                else Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def drop_row(self, pos) -> int:
        """The row a drop at viewport ``pos`` inserts before."""
        index = self.indexAt(pos)
        if not index.isValid():
            return self.model().rowCount()
        rect = self.visualRect(index)
        return index.row() + (1 if pos.y() > rect.center().y() else 0)

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        row = self.drop_row(event.position().toPoint())
        own = self._own_rows(mime)
        if own is not None:
            self.select_rows(self.model().move_rows(own, row))
        elif mime.hasFormat(MIME_NAMES):
            self.add_names(_names_from(mime), row)
        else:
            event.ignore()
            return
        # Never MoveAction back to the source: it removes nothing itself.
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.stopAutoScroll()
        self.setState(QAbstractItemView.NoState)
        self.viewport().update()


# ---- Inactive ------------------------------------------------------------------
class InactiveList(QListWidget):
    """The model's scenes that are not in the sequence."""

    #: Names to add at the end of Active (double-click, Enter).
    add_requested = Signal(list)
    #: Active rows dropped here, to take out of the sequence.
    rows_returned = Signal(list)

    def __init__(self, active: ActiveTable, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenes_play_inactive")
        self._active = active
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.itemDoubleClicked.connect(
            lambda item: self.add_requested.emit([item.text()]))

    def set_names(self, names) -> None:
        """Show ``names``, keeping the selection of those still there."""
        names = list(names)
        if names == [self.item(i).text() for i in range(self.count())]:
            return
        keep = {i.text() for i in self.selectedItems()}
        self.clear()
        self.addItems(names)
        for i in range(self.count()):
            if self.item(i).text() in keep:
                self.item(i).setSelected(True)

    def selected_names(self) -> list[str]:
        rows = sorted(self.row(i) for i in self.selectedItems())
        return [self.item(r).text() for r in rows]

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) \
                and self.selected_names():
            self.add_requested.emit(self.selected_names())
            event.accept()
            return
        super().keyPressEvent(event)

    def startDrag(self, _actions) -> None:
        names = self.selected_names()
        if not names:
            return
        mime = QMimeData()
        mime.setData(MIME_NAMES, json.dumps(names).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)

    def _rows(self, event):
        if event.source() is not self._active:
            return None
        return self._active._own_rows(event.mimeData())

    def dragEnterEvent(self, event) -> None:
        if self._rows(event) is not None:
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        rows = self._rows(event)
        if rows is None:
            event.ignore()
            return
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.rows_returned.emit(rows)
