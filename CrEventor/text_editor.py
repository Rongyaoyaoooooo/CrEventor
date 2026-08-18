"""Text editing dialog for EventEditor DX.

Dialog for editing BOTW dialogue text, working with the built-in
BCML-format TextDatabase (not Bootup packs).

Supports: text editing, character count, Ctrl+S save, dirty tracking.
Options/choice logic is NOT handled here (deferred to later).
"""

import zlib
import typing

import PyQt5.QtCore as qc  # type: ignore
import PyQt5.QtGui as qg  # type: ignore
import PyQt5.QtWidgets as q  # type: ignore

from CrEventor.text_database import TextDatabase, TextEntry
from CrEventor.i18n import tr


class TextEditorDialog(q.QDialog):
    """Dialog for editing a single dialogue text entry.

    Fields:
      - Message ID (read-only)
      - MSBT File (read-only)
      - Character Count (auto-updating)
      - Text Area (multi-line, monospace)

    Accepts either a label (str) looked up via text_db, or a TextEntry
    directly (bypasses secondary lookup — ensures edit dialog shows the
    exact same entry that was found by lookup_by_message_id).
    """

    textSaved = qc.pyqtSignal(str, str)  # (label, new_text)

    def __init__(
        self,
        parent: typing.Optional[q.QWidget],
        text_db: TextDatabase,
        label_or_entry,  # str | TextEntry
    ) -> None:
        super().__init__(
            parent,
            qc.Qt.WindowTitleHint | qc.Qt.WindowSystemMenuHint
            | qc.Qt.WindowCloseButtonHint,
        )
        self._text_db = text_db

        if isinstance(label_or_entry, TextEntry):
            entry: typing.Optional[TextEntry] = label_or_entry
            self._label = entry.label
        else:
            self._label = str(label_or_entry)
            entry = text_db.lookup(self._label)

        self._original_text = entry.text if entry else ''
        self._msbt_file = entry.msbt_file if entry else ''
        self._hash = zlib.crc32(self._original_text.encode('utf-8'))

        self.setWindowTitle(tr('dialogue.title'))
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = q.QVBoxLayout(self)

        # --- Info section ---
        info = q.QFormLayout()

        self._label_field = q.QLineEdit(self._label)
        self._label_field.setReadOnly(True)
        info.addRow(tr('dialogue.label'), self._label_field)

        self._msbt_field = q.QLineEdit(self._msbt_file)
        self._msbt_field.setReadOnly(True)
        info.addRow(tr('dialogue.msbt_file'), self._msbt_field)

        self._char_count = q.QLabel(str(len(self._original_text)))
        info.addRow(tr('dialogue.char_count'), self._char_count)

        layout.addLayout(info)

        # --- Separator ---
        sep = q.QFrame()
        sep.setFrameShape(q.QFrame.HLine)
        sep.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(sep)

        # --- Text editor ---
        self._editor = q.QPlainTextEdit()
        self._editor.setPlainText(self._original_text)
        self._editor.setTabChangesFocus(False)
        self._editor.textChanged.connect(self._on_text_changed)
        font = qg.QFont('Consolas', 10)
        font.setStyleHint(qg.QFont.Monospace)
        self._editor.setFont(font)
        layout.addWidget(self._editor, stretch=1)

        # --- Buttons ---
        btn_box = q.QDialogButtonBox(
            q.QDialogButtonBox.Save | q.QDialogButtonBox.Cancel,
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # --- Ctrl+S shortcut ---
        save_shortcut = q.QShortcut(qg.QKeySequence.Save, self)
        save_shortcut.activated.connect(self._on_save)

    def _on_text_changed(self) -> None:
        text = self._editor.toPlainText()
        self._char_count.setText(str(len(text)))

    def _on_save(self) -> None:
        text = self._editor.toPlainText()
        new_hash = zlib.crc32(text.encode('utf-8'))
        if new_hash == self._hash:
            self.accept()
            return
        self._text_db.update(self._label, text, self._msbt_file)
        self._hash = new_hash
        self.textSaved.emit(self._label, text)
        self.accept()

    def is_dirty(self) -> bool:
        text = self._editor.toPlainText()
        return zlib.crc32(text.encode('utf-8')) != self._hash

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        if self.is_dirty():
            ret = q.QMessageBox.question(
                self,
                tr('dialogue.unsaved'),
                tr('dialogue.unsaved_prompt'),
                q.QMessageBox.Yes | q.QMessageBox.No | q.QMessageBox.Cancel,
            )
            if ret == q.QMessageBox.Yes:
                self._on_save()
            elif ret == q.QMessageBox.Cancel:
                event.ignore()
                return
        super().closeEvent(event)
