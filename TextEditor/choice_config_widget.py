"""Choice Config Widgets — 移植自 CrEventor option_pool_panel.py
用于管理 choice / single_choice 的选项配置。
纯视图层：不依赖 TextDatabase，通过信号通知外部写数据。
"""

import typing

from PyQt5 import QtCore as qc
from PyQt5 import QtWidgets as q


class ChoiceConfigWidget(q.QWidget):
    """Per-dialogue choice 配置：按钮选择、光标、取消索引"""

    configChanged = qc.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool_keys: typing.List[str] = []
        self._choice_labels: typing.List[int] = []
        self._selected_index = 0
        self._cancel_index = 0
        self._unknown: typing.Any = None
        self._combo_widgets: typing.List[q.QComboBox] = []
        self._init_ui()

    def _init_ui(self):
        layout = q.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._btn_label = q.QLabel("<b>选项按钮</b>")
        layout.addWidget(self._btn_label)

        self._btn_container = q.QWidget()
        self._btn_layout = q.QVBoxLayout(self._btn_container)
        self._btn_layout.setContentsMargins(0, 0, 0, 0)
        self._btn_layout.setSpacing(3)
        layout.addWidget(self._btn_container)

        self._add_btn = q.QPushButton("+ 添加按钮")
        self._add_btn.clicked.connect(self._add_button_slot)
        layout.addWidget(self._add_btn)

        line = q.QFrame()
        line.setFrameShape(q.QFrame.HLine)
        line.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(line)

        cfg_layout = q.QFormLayout()
        cfg_layout.setSpacing(4)

        self._cursor_combo = q.QComboBox()
        self._cursor_combo.currentIndexChanged.connect(self._emit_changed)
        cfg_layout.addRow("默认光标:", self._cursor_combo)

        self._cancel_combo = q.QComboBox()
        self._cancel_combo.currentIndexChanged.connect(self._emit_changed)
        cfg_layout.addRow("取消索引:", self._cancel_combo)

        layout.addLayout(cfg_layout)

    # ---- Public API ----

    def set_pool_keys(self, keys: typing.List[str]):
        current_labels = []
        for i, combo in enumerate(self._combo_widgets):
            value = combo.currentData()
            if value is None:
                value = self._choice_labels[i] if i < len(self._choice_labels) else 0
            current_labels.append(int(value))

        self._pool_keys = list(keys)
        # Pool entries can be added while this config is visible.  Rebuild the
        # button selectors themselves so the new IDs become selectable, while
        # preserving every row's current value (including missing IDs).
        for i, combo in enumerate(self._combo_widgets):
            current = current_labels[i] if i < len(current_labels) else 0
            self._setup_combo_items(combo, current)
        self._rebuild_combos()

    def set_default_empty(self, option_count: int):
        """创建 option_count 个空按钮行"""
        self._choice_labels = [0] * option_count
        self._selected_index = 0
        self._cancel_index = max(0, option_count - 1)
        self._unknown = 2 * option_count + 2

        self._clear_button_rows()
        for i in range(option_count):
            self._add_button_row(i, 0)
        self._btn_layout.addStretch()
        self._rebuild_combos()

    def load_config(self, choice_labels: typing.List[int],
                    selected_index: int, cancel_index: int,
                    unknown: typing.Any = None):
        self._choice_labels = list(choice_labels)
        self._selected_index = selected_index
        self._cancel_index = cancel_index
        self._unknown = unknown

        self._clear_button_rows()
        for i, label_val in enumerate(choice_labels):
            self._add_button_row(i, label_val)
        self._btn_layout.addStretch()
        self._rebuild_combos()

    def get_config(self) -> dict:
        return {
            "choice_labels": list(self._choice_labels),
            "selected_index": self._selected_index,
            "cancel_index": self._cancel_index,
            "unknown": self._unknown,
        }

    # ---- Internal ----

    def _clear_button_rows(self):
        while self._btn_layout.count():
            item = self._btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._combo_widgets = []

    def _add_button_row(self, i: int, label_val: int):
        row = q.QWidget()
        row_layout = q.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        idx_label = q.QLabel(f"按钮 {i + 1}:")
        row_layout.addWidget(idx_label)

        combo = q.QComboBox()
        combo.currentIndexChanged.connect(self._on_button_combo_changed)
        self._combo_widgets.append(combo)
        self._setup_combo_items(combo, label_val)
        row_layout.addWidget(combo, stretch=1)

        remove_btn = q.QPushButton("✕")
        remove_btn.setFixedWidth(28)
        remove_btn.clicked.connect(lambda checked, idx=i: self._remove_button(idx))
        row_layout.addWidget(remove_btn)

        self._btn_layout.addWidget(row)

    def _setup_combo_items(self, combo: q.QComboBox, current_label: int):
        combo.blockSignals(True)
        combo.clear()
        has_current = False
        for idx, key in enumerate(self._pool_keys):
            combo.addItem(key, int(key))
            if int(key) == current_label:
                combo.setCurrentIndex(idx)
                has_current = True
        if not has_current:
            # Keep the ID stored in the document even when the option pool is
            # empty or that pool entry is currently missing.  An empty combo
            # returns None from currentData(), which used to crash while
            # opening the entry and could also discard an unresolved ID.
            combo.addItem(f"{current_label:04d}（池中缺失）", current_label)
            combo.setCurrentIndex(combo.count() - 1)
        combo.blockSignals(False)

    def _on_button_combo_changed(self):
        self._rebuild_choice_labels()
        self._rebuild_combos()
        self._emit_changed()

    def _rebuild_choice_labels(self):
        labels = []
        for i, combo in enumerate(self._combo_widgets):
            value = combo.currentData()
            if value is None:
                # Defensive fallback for a temporarily empty combo during a
                # UI rebuild.  Preserve the loaded value instead of crashing.
                value = self._choice_labels[i] if i < len(self._choice_labels) else 0
            labels.append(int(value))
        self._choice_labels = labels

    def _rebuild_combos(self):
        self._rebuild_choice_labels()
        count = len(self._choice_labels)

        self._cursor_combo.blockSignals(True)
        self._cursor_combo.clear()
        for i in range(count):
            self._cursor_combo.addItem(
                f"按钮 {i + 1} ({self._choice_labels[i]:04d})", i)
        if self._selected_index < count:
            self._cursor_combo.setCurrentIndex(self._selected_index)
        elif count > 0:
            self._cursor_combo.setCurrentIndex(0)
        self._cursor_combo.blockSignals(False)

        self._cancel_combo.blockSignals(True)
        self._cancel_combo.clear()
        for i in range(count):
            self._cancel_combo.addItem(
                f"按钮 {i + 1} ({self._choice_labels[i]:04d})", i)
        self._cancel_combo.addItem("无取消", count)
        if 0 <= self._cancel_index <= count:
            self._cancel_combo.setCurrentIndex(
                self._cancel_combo.findData(self._cancel_index))
        else:
            self._cancel_combo.setCurrentIndex(self._cancel_combo.findData(count))
        self._cancel_combo.blockSignals(False)

    def _add_button_slot(self):
        # The final layout item is the stretch added by load_config()/
        # set_default_empty().  Remove it *before* appending the new row.
        # Removing the last item afterwards removes the newly-added row from
        # layout management while leaving it visible as a child widget, which
        # makes every added row occupy the same position and overlap.
        if self._btn_layout.count():
            last_item = self._btn_layout.itemAt(self._btn_layout.count() - 1)
            if last_item and last_item.spacerItem():
                self._btn_layout.takeAt(self._btn_layout.count() - 1)

        old_count = len(self._combo_widgets)
        had_no_cancel = self._cancel_index == old_count
        i = old_count
        self._add_button_row(i, 0)
        if had_no_cancel:
            self._cancel_index = old_count + 1
        self._btn_layout.addStretch()
        self._rebuild_choice_labels()
        self._rebuild_combos()
        self._emit_changed()

    def _remove_button(self, idx: int):
        if len(self._combo_widgets) <= 1:
            return
        old_count = len(self._combo_widgets)
        had_no_cancel = self._cancel_index == old_count
        item = self._btn_layout.itemAt(idx)
        if item and item.widget():
            item.widget().deleteLater()
        del self._combo_widgets[idx]
        if had_no_cancel:
            self._cancel_index = old_count - 1
        self._rebuild_choice_labels()
        self._rebuild_combos()
        self._emit_changed()

    def _emit_changed(self):
        self._selected_index = self._cursor_combo.currentData()
        if self._selected_index is None:
            self._selected_index = 0
        self._cancel_index = self._cancel_combo.currentData()
        if self._cancel_index is None:
            self._cancel_index = 0
        self._rebuild_choice_labels()
        self.configChanged.emit()


class SingleChoiceConfigWidget(q.QWidget):
    """Per-dialogue single_choice 配置：开关 + 标签选择"""

    configChanged = qc.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool_keys: typing.List[str] = []
        self._label: int = 0
        self._enabled: bool = False
        self._init_ui()

    def _init_ui(self):
        layout = q.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._enable_check = q.QCheckBox("启用单选项")
        self._enable_check.toggled.connect(self._on_toggled)
        layout.addWidget(self._enable_check)

        self._label_container = q.QWidget()
        clayout = q.QVBoxLayout(self._label_container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(4)

        clayout.addWidget(q.QLabel("<b>选项编号</b>"))
        self._label_combo = q.QComboBox()
        self._label_combo.currentIndexChanged.connect(self._on_label_changed)
        clayout.addWidget(self._label_combo)

        hint = q.QLabel("<i>选择此对话关联的选项池按钮</i>")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        clayout.addWidget(hint)

        self._label_container.hide()
        layout.addWidget(self._label_container)
        layout.addStretch()

    def set_pool_keys(self, keys: typing.List[str]):
        self._pool_keys = list(keys)
        self._setup_combo()

    def load_config(self, label: int, enabled: bool):
        self._label = label
        self._enabled = enabled
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(enabled)
        self._enable_check.blockSignals(False)
        self._label_container.setVisible(enabled)
        if enabled:
            self._setup_combo()

    def is_enabled(self) -> bool:
        return self._enabled

    def get_label(self) -> int:
        return self._label

    def _setup_combo(self):
        combo = self._label_combo
        combo.blockSignals(True)
        combo.clear()
        has_current = False
        for idx, key in enumerate(self._pool_keys):
            combo.addItem(key, int(key))
            if int(key) == self._label:
                combo.setCurrentIndex(idx)
                has_current = True
        if not has_current and self._pool_keys:
            combo.setCurrentIndex(0)
            self._label = int(self._pool_keys[0])
        combo.blockSignals(False)

    def _on_toggled(self, checked: bool):
        self._enabled = checked
        self._label_container.setVisible(checked)
        self.configChanged.emit()

    def _on_label_changed(self):
        self._label = self._label_combo.currentData()
        self.configChanged.emit()
