"""TextEditor 集成对话框 — 将独立 TextEditor 的 MessageEditor 嵌入 CrEventor。

对接 TextDatabase，完整支持 control 模块（颜色、字体、字号、停顿、音效等）的
可视化编辑，同时隐藏选项池（选项由 CrEventor 的 M 菜单管理）。
"""

import copy
import os
import sys

import PyQt5.QtCore as qc  # type: ignore
import PyQt5.QtGui as qg  # type: ignore
import PyQt5.QtWidgets as q  # type: ignore

# Ensure TextEditor/ is importable (MessageEditor uses bare imports like
# "from models import ..." which resolve relative to TextEditor/)
_TEXTEDITOR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'TextEditor',
)
if _TEXTEDITOR_DIR not in sys.path:
    sys.path.insert(0, _TEXTEDITOR_DIR)

from web_message_editor import WebMessageEditor  # noqa: E402

from CrEventor.text_database import TextDatabase
from CrEventor.i18n import Tr, tr


class TextDatabaseAdapter:
    """Adapter that makes TextDatabase look like TextsLoader to MessageEditor.

    MessageEditor calls:
      - get_entry(msbt_path, label)  → working copy of the entry (same dict every call)
      - mark_dirty()                 → signal that data changed (does NOT persist)
    Persistence only happens on explicit save().
    """

    def __init__(self, text_db: TextDatabase, label: str, msbt_file: str,
                 attributes=None):
        self._text_db = text_db
        self._label = label
        self._msbt_file = msbt_file
        self._dirty = False
        # 工作副本：MessageEditor._save_entry() 修改此副本，不直接写入数据库
        raw = self._text_db.get_raw_entry(self._label, self._msbt_file)
        self._entry = copy.deepcopy(raw) if raw else {'contents': [{'text': ''}], 'attributes': ''}
        # In CrEventor the Talk Event is authoritative for the speaker actor.
        # ``None`` means no Event context was supplied; an empty string is a
        # valid explicit Event-derived value and must therefore be retained.
        if attributes is not None:
            self._entry['attributes'] = str(attributes)

    def get_entry(self, _msbt_path: str, _label: str) -> dict:
        """返回工作副本（同一对象，MessageEditor 原地修改）。"""
        return self._entry

    def mark_dirty(self) -> None:
        """标记脏数据，不持久化（等待显式 save()）。"""
        self._dirty = True

    def save(self) -> None:
        """Save editable text while preserving CrEventor-owned Choice data."""
        live_raw = self._text_db.get_raw_entry(self._label, self._msbt_file) or {}
        host_choice = []
        for item in live_raw.get('contents', []):
            control = item.get('control') if isinstance(item, dict) else None
            if isinstance(control, dict) and control.get('kind') in (
                'choice', 'single_choice',
            ):
                host_choice.append(copy.deepcopy(item))

        edited_contents = []
        for item in self._entry.get('contents', []):
            control = item.get('control') if isinstance(item, dict) else None
            if isinstance(control, dict) and control.get('kind') in (
                'choice', 'single_choice',
            ):
                continue
            edited_contents.append(copy.deepcopy(item))

        # M menu is authoritative and Choice always remains at the end.
        edited_contents.extend(host_choice)
        self._entry['contents'] = edited_contents
        self._text_db.update_full_contents(
            self._label, self._msbt_file,
            edited_contents,
            self._entry.get('attributes', ''),
        )
        self._dirty = False


class TextEditorIntegrationDialog(q.QDialog):
    """QDialog wrapper around TextEditor's MessageEditor, for use in CrEventor.

    Usage:
        dialog = TextEditorIntegrationDialog(parent, text_db, label, msbt_file)
        if dialog.exec_() == q.QDialog.Accepted:
            # TextDatabase already updated via adapter
            pass
    """

    textSaved = qc.pyqtSignal(str, list)  # (label, contents)

    def __init__(
        self,
        parent: q.QWidget,
        text_db: TextDatabase,
        label: str,
        msbt_file: str,
        attributes=None,
    ) -> None:
        super().__init__(
            parent,
            qc.Qt.WindowTitleHint | qc.Qt.WindowSystemMenuHint
            | qc.Qt.WindowCloseButtonHint,
        )
        self._text_db = text_db
        self._label = label
        self._msbt_file = msbt_file
        self._adapter = TextDatabaseAdapter(
            text_db, label, msbt_file, attributes=attributes,
        )
        self._original_contents = copy.deepcopy(
            self._adapter.get_entry(msbt_file, label).get('contents', [])
        )
        self._closing = False  # 防 closeEvent 重复弹窗

        self.setWindowTitle(tr('dialogue.title'))
        self.resize(1000, 650)

        self._init_ui()
        self._load_data()

    def _init_ui(self) -> None:
        layout = q.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── 信息栏 ──
        info_layout = q.QHBoxLayout()
        info_layout.addWidget(q.QLabel(f"<b>{tr('dialogue.label')}:</b> {self._label}"))
        info_layout.addStretch()
        info_layout.addWidget(q.QLabel(f"<b>MSBT:</b> {self._msbt_file}"))
        layout.addLayout(info_layout)

        sep = q.QFrame()
        sep.setFrameShape(q.QFrame.HLine)
        sep.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(sep)

        # ── WebMessageEditor (核心) ──
        self._editor = WebMessageEditor(self)
        self._editor.set_host_language(
            Tr.instance.language if Tr.instance else 'zh_CN'
        )

        # CrEventor's original M panel exclusively owns pool/Choice editing.
        self._editor.set_choice_managed_by_host(True)

        layout.addWidget(self._editor, stretch=1)

        # ── 按钮 ──
        btn_box = q.QDialogButtonBox()
        self._save_btn = btn_box.addButton(tr('dialogue.save'), q.QDialogButtonBox.AcceptRole)
        self._cancel_btn = btn_box.addButton(tr('dialogue.cancel'), q.QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self._on_cancel)
        layout.addWidget(btn_box)

        # Ctrl+S 快捷键
        save_shortcut = q.QShortcut(qg.QKeySequence.Save, self)
        save_shortcut.activated.connect(self._on_save)

    def _load_data(self) -> None:
        """Load the current MessageId through WebMessageEditor's public API."""
        self._editor.set_context(self._adapter, self._msbt_file, self._label)

    def _on_save(self) -> None:
        """触发 MessageEditor 保存，将工作副本持久化到 TextDatabase。"""
        # ProseMirror changes already synchronize through _save_raw().
        self._editor._save_raw()
        self._adapter.save()
        # 更新基线，确保 is_dirty() 在保存后返回 False
        self._original_contents = copy.deepcopy(
            self._adapter.get_entry(self._msbt_file, self._label).get('contents', [])
        )
        entry = self._adapter.get_entry(self._msbt_file, self._label)
        contents = entry.get('contents', [])
        self.textSaved.emit(self._label, contents)
        self._closing = True
        self.accept()

    def _on_cancel(self) -> None:
        """取消按钮：有未保存修改时弹窗确认。"""
        if self.is_dirty():
            ret = q.QMessageBox.question(
                self,
                tr('dialogue.unsaved'),
                tr('dialogue.unsaved_prompt'),
                q.QMessageBox.Yes | q.QMessageBox.No | q.QMessageBox.Cancel,
                q.QMessageBox.Yes,
            )
            if ret == q.QMessageBox.Yes:
                self._on_save()
                return  # _on_save 会设 _closing 并 accept
            elif ret == q.QMessageBox.Cancel:
                return  # 不关闭
        self._closing = True
        self.reject()

    def is_dirty(self) -> bool:
        current = self._adapter.get_entry(self._msbt_file, self._label)
        current_contents = current.get('contents', [])
        return current_contents != self._original_contents

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        if self._closing:
            super().closeEvent(event)
            return
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
