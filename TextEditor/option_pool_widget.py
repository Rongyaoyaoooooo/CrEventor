"""
Option Pool + Choice Config Panel
移植自 eventeditor 的 option_pool_panel.py，适配 TextEditor 的 TextsLoader 后端
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QScrollArea, QLabel, QFrame,
    QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from typing import Optional

from texts_loader import TextsLoader
from choice_config_widget import ChoiceConfigWidget, SingleChoiceConfigWidget


class OptionEntryRow(QFrame):
    """单行选项池条目：key 标签 + text 输入 + 删除按钮"""

    delete_clicked = pyqtSignal(str)
    text_changed = pyqtSignal(str, str)

    def __init__(self, label: str, text: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._text = text
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        key_lbl = QLabel(self._label)
        key_lbl.setFixedWidth(45)
        key_lbl.setStyleSheet("font-weight: bold; color: #336699;")
        key_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(key_lbl)

        self._text_edit = QLineEdit(self._text)
        self._text_edit.setPlaceholderText("按钮文案...")
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit, stretch=1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            "QPushButton { border: none; color: #cc0000; font-weight: bold; }"
            "QPushButton:hover { background: #ffeeee; border-radius: 4px; }"
        )
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._label))
        layout.addWidget(del_btn)

    def _on_text_changed(self):
        self.text_changed.emit(self._label, self._text_edit.text())

    def label(self) -> str:
        return self._label

    def text(self) -> str:
        return self._text_edit.text()


class OptionPoolWidget(QWidget):
    """选项池编辑面板 — 包含池条目 + choice/single_choice 配置"""

    pool_changed = pyqtSignal()
    choice_config_changed = pyqtSignal(object)  # 传 config dict 给外部写 _contents

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: Optional[TextsLoader] = None
        self._current_msbt: Optional[str] = None
        self._rows: dict[str, OptionEntryRow] = {}
        self._contents: Optional[list] = None  # 当前消息的 _contents
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # ── 标题行 ──
        header_layout = QHBoxLayout()
        title = QLabel("<b>选项按钮池</b>")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._add_btn = QPushButton("+ 添加")
        self._add_btn.setFixedHeight(26)
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add_pool_entry)
        header_layout.addWidget(self._add_btn)
        layout.addLayout(header_layout)

        # ── 池条目（普通 QWidget，不嵌套 scroll，无 maxHeight）──
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(2)
        layout.addWidget(self._container)

        # ── 分隔线 ──
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line1)

        # ── Choice 配置区 ──
        config_header = QHBoxLayout()
        self._config_title = QLabel("<b>选择项配置</b>")
        config_header.addWidget(self._config_title)
        config_header.addStretch()
        self._add_choice_btn = QPushButton("+ 选项")
        self._add_choice_btn.setFixedHeight(24)
        self._add_choice_btn.clicked.connect(self._on_add_choice)
        config_header.addWidget(self._add_choice_btn)
        self._add_single_btn = QPushButton("+ 单选项")
        self._add_single_btn.setFixedHeight(24)
        self._add_single_btn.clicked.connect(self._on_add_single_choice)
        config_header.addWidget(self._add_single_btn)
        self._del_choice_btn = QPushButton("删除")
        self._del_choice_btn.setFixedHeight(24)
        self._del_choice_btn.setStyleSheet("QPushButton { color: #cc0000; }")
        self._del_choice_btn.clicked.connect(self._on_delete_choice)
        self._del_choice_btn.hide()
        config_header.addWidget(self._del_choice_btn)
        layout.addLayout(config_header)

        self._config_hint = QLabel("<i>此消息没有 choice/single_choice</i>")
        self._config_hint.setWordWrap(True)
        self._config_hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._config_hint)

        self._choice_config = ChoiceConfigWidget()
        self._choice_config.configChanged.connect(self._on_choice_changed)
        self._choice_config.hide()
        layout.addWidget(self._choice_config)

        self._single_choice_config = SingleChoiceConfigWidget()
        self._single_choice_config.configChanged.connect(self._on_single_choice_changed)
        self._single_choice_config.hide()
        layout.addWidget(self._single_choice_config)

        layout.addStretch()

    # ── 池条目操作 ──

    def set_context(self, loader: TextsLoader, msbt_path: str):
        self._loader = loader
        self._current_msbt = msbt_path
        self._add_btn.setEnabled(True)
        self._refresh()

    def clear_context(self):
        self._loader = None
        self._current_msbt = None
        self._add_btn.setEnabled(False)
        self._clear_rows()

    def _refresh(self):
        self._clear_rows()
        if not self._loader or not self._current_msbt:
            return

        pool_keys = self._loader.get_pool_keys(self._current_msbt)
        for key in pool_keys:
            entry = self._loader.get_entry(self._current_msbt, key)
            text = ""
            if entry and entry.get("contents"):
                for item in entry["contents"]:
                    if "text" in item:
                        text = item["text"]
                        break

            row = OptionEntryRow(key, text)
            row.delete_clicked.connect(self._on_delete_entry)
            row.text_changed.connect(self._on_text_changed)
            self._container_layout.addWidget(row)
            self._rows[key] = row

        # 更新 choice 配置的 combo 选项
        self._sync_pool_to_choice_config()

    def _clear_rows(self):
        for row in self._rows.values():
            self._container_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

    def _on_add_pool_entry(self):
        if not self._loader or not self._current_msbt:
            return
        new_key = self._loader.allocate_pool_key(self._current_msbt)
        self._loader.set_entry(self._current_msbt, new_key, {
            "attributes": "",
            "contents": [{"text": ""}],
        })
        self._refresh()
        self.pool_changed.emit()

    def _on_delete_entry(self, label: str):
        if not self._loader or not self._current_msbt:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除按钮 {label} 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._loader.delete_entry(self._current_msbt, label)
        self._refresh()
        self.pool_changed.emit()

    def _on_text_changed(self, label: str, new_text: str):
        if not self._loader or not self._current_msbt:
            return
        entry = self._loader.get_entry(self._current_msbt, label)
        if entry:
            entry["contents"] = [{"text": new_text}]
            self._loader.mark_dirty()

    # ── Choice / Single Choice 配置 ──

    def set_contents(self, contents: list):
        """设置当前消息的 _contents，自动解析 choice/single_choice 并更新 UI"""
        import copy
        self._contents = contents

        # 查找 choice / single_choice
        choice_ctrl = None
        single_choice_ctrl = None
        for item in contents:
            if "control" in item:
                kind = item["control"].get("kind", "")
                if kind == "choice":
                    choice_ctrl = copy.deepcopy(item["control"])
                elif kind == "single_choice":
                    single_choice_ctrl = copy.deepcopy(item["control"])

        self._choice_config.hide()
        self._single_choice_config.hide()

        if choice_ctrl:
            self._add_choice_btn.setVisible(False)
            self._add_single_btn.setVisible(False)
            self._del_choice_btn.setVisible(True)
            self._config_hint.hide()
            self._choice_config.show()
            self._choice_config.load_config(
                choice_labels=choice_ctrl.get("choice_labels", []),
                selected_index=choice_ctrl.get("selected_index", 0),
                cancel_index=choice_ctrl.get("cancel_index", 0),
                unknown=choice_ctrl.get("unknown"),
            )
        elif single_choice_ctrl:
            self._add_choice_btn.setVisible(False)
            self._add_single_btn.setVisible(False)
            self._del_choice_btn.setVisible(True)
            self._config_hint.hide()
            self._single_choice_config.show()
            self._single_choice_config.load_config(
                label=single_choice_ctrl.get("label", 0),
                enabled=True,
            )
        else:
            self._add_choice_btn.setVisible(True)
            self._add_single_btn.setVisible(True)
            self._del_choice_btn.setVisible(False)
            self._config_hint.setText("<i>此消息没有 choice/single_choice</i>")
            self._config_hint.show()

        self._sync_pool_to_choice_config()

    def _sync_pool_to_choice_config(self):
        """同步池条目到 choice 配置的 combo 选项"""
        keys = []
        if self._loader and self._current_msbt:
            pool_keys = self._loader.get_pool_keys(self._current_msbt)
            keys = list(pool_keys) if pool_keys else ["0000"]
        self._choice_config.set_pool_keys(keys)
        self._single_choice_config.set_pool_keys(keys)

    def _on_choice_changed(self):
        """choice 配置变更 → 写回 _contents"""
        import copy
        if self._contents is None:
            return
        config = self._choice_config.get_config()
        n = len(config["choice_labels"])
        config["unknown"] = 2 * n + 2

        # 找到并替换/追加 choice control
        replaced = False
        for item in self._contents:
            if "control" in item and item["control"].get("kind") == "choice":
                item["control"] = {"kind": "choice", **config}
                replaced = True
                break
        if not replaced:
            self._contents.append({"control": {"kind": "choice", **config}})

        self.choice_config_changed.emit(config)
        self.pool_changed.emit()

    def _on_single_choice_changed(self):
        """single_choice 配置变更 → 写回 _contents"""
        import copy
        if self._contents is None:
            return
        enabled = self._single_choice_config.is_enabled()
        label = self._single_choice_config.get_label()

        # 找到并更新或删除 single_choice
        for i, item in enumerate(self._contents):
            if "control" in item and item["control"].get("kind") == "single_choice":
                if enabled:
                    item["control"] = {"kind": "single_choice", "label": label}
                else:
                    del self._contents[i]
                self.choice_config_changed.emit({"kind": "single_choice", "label": label, "enabled": enabled})
                self.pool_changed.emit()
                return

        # 不存在则新增
        if enabled:
            self._contents.append({"control": {"kind": "single_choice", "label": label}})
            self.choice_config_changed.emit({"kind": "single_choice", "label": label, "enabled": True})
            self.pool_changed.emit()

    def _on_add_choice(self):
        """创建新的 choice control"""
        if self._contents is None:
            return
        # 追加到 _contents 末尾
        self._contents.append({"control": {
            "kind": "choice",
            "choice_labels": [],
            "selected_index": 0,
            "cancel_index": 0,
            "unknown": 2,
        }})
        self.set_contents(self._contents)
        self.choice_config_changed.emit({"kind": "choice"})
        self.pool_changed.emit()

    def _on_add_single_choice(self):
        """创建新的 single_choice control"""
        if self._contents is None:
            return
        self._contents.append({"control": {
            "kind": "single_choice",
            "label": 0,
        }})
        self.set_contents(self._contents)
        self.choice_config_changed.emit({"kind": "single_choice"})
        self.pool_changed.emit()

    def _on_delete_choice(self):
        """删除当前消息的 choice/single_choice control"""
        if self._contents is None:
            return
        for i, item in enumerate(self._contents):
            if "control" in item and item["control"].get("kind") in ("choice", "single_choice"):
                del self._contents[i]
                self.set_contents(self._contents)
                self.choice_config_changed.emit({"kind": "none"})
                self.pool_changed.emit()
                return
