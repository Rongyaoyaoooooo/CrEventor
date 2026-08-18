"""
Control Dialogs — 各种 control 类型的编辑对话框
"""

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QLineEdit, QSpinBox,
    QDialogButtonBox, QVBoxLayout, QLabel, QCheckBox,
)
from PyQt5.QtCore import Qt

from models import CONTROL_FIELDS, DEFAULT_CONTROL_TEMPLATES, normalize_control


class ControlEditDialog(QDialog):
    """通用的 control 编辑对话框，根据 kind 动态生成表单"""

    def __init__(self, kind: str, current_control: dict = None, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._current_control = normalize_control(kind, current_control or {})
        self._widgets = {}
        self._result_control = None

        self.setWindowTitle(f"编辑 Control: {kind}")
        self.setMinimumWidth(350)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 类型标签
        kind_label = QLabel(f"类型: {self._kind}")
        kind_label.setStyleSheet("font-weight: bold; color: #336699;")
        layout.addWidget(kind_label)

        form = QFormLayout()
        fields = CONTROL_FIELDS.get(self._kind, [])

        for field_name, field_label, field_type, field_options in fields:
            if field_name == "_pause_mode":
                current_val = "frames" if "frames" in self._current_control else "length"
            else:
                current_val = self._get_nested_value(self._current_control, field_name)
            if field_type == "combo":
                widget = QComboBox()
                for opt in field_options:
                    if isinstance(opt, tuple):
                        widget.addItem(opt[0], opt[1])
                    else:
                        widget.addItem(str(opt))
                # 设置当前值
                if current_val is not None:
                    idx = widget.findData(current_val)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                    else:
                        idx = widget.findText(str(current_val))
                        if idx >= 0:
                            widget.setCurrentIndex(idx)
                form.addRow(field_label, widget)

            elif field_type == "int":
                widget = QSpinBox()
                widget.setRange(-99999, 99999)
                if current_val is not None:
                    widget.setValue(int(current_val))
                form.addRow(field_label, widget)

            elif field_type == "int_list":
                widget = QLineEdit()
                widget.setPlaceholderText("逗号分隔，如: 23, 24, 25")
                if self._current_control:
                    val = self._current_control.get(field_name, [])
                    if val:
                        widget.setText(",".join(str(v) for v in val))
                form.addRow(field_label, widget)

            elif field_type == "str":
                widget = QLineEdit()
                if self._current_control:
                    val = self._current_control.get(field_name, "")
                    widget.setText(str(val))
                form.addRow(field_label, widget)

            self._widgets[field_name] = (field_type, widget)

        layout.addLayout(form)

        # 按钮
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    @staticmethod
    def _get_nested_value(control: dict, field_path: str) -> any:
        """支持 'unknown[0]' 这样的嵌套路径"""
        parts = field_path.replace("[", ".").replace("]", "").split(".")
        val = control
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            elif isinstance(val, list) and part.isdigit():
                idx = int(part)
                if idx < len(val):
                    val = val[idx]
                else:
                    return None
            else:
                return None
        return val

    def _on_accept(self):
        """收集表单数据，构建 control dict"""
        template = DEFAULT_CONTROL_TEMPLATES.get(self._kind, {})
        import copy
        control = copy.deepcopy(template)

        # 覆盖已有值
        if self._current_control:
            for key, val in self._current_control.items():
                if key != "kind":
                    control[key] = copy.deepcopy(val)

        for field_name, (field_type, widget) in self._widgets.items():
            if field_type in ("combo", "str"):
                if isinstance(widget, QComboBox):
                    val = widget.currentData()
                    if val is None:
                        val = widget.currentText()
                else:
                    val = widget.text()
            elif field_type == "int":
                val = widget.value()
            elif field_type == "int_list":
                text = widget.text().strip()
                if text:
                    val = [int(x.strip()) for x in text.split(",") if x.strip()]
                else:
                    val = []
            else:
                continue

            self._set_nested_value(control, field_name, val)

        if self._kind == "pause":
            mode = control.pop("_pause_mode", "length")
            if mode == "frames":
                control.pop("length", None)
            else:
                control.pop("frames", None)

        # choice 自动计算 unknown
        if self._kind == "choice":
            n = len(control.get("choice_labels", []))
            control["unknown"] = 2 * n + 2
            # 自动设置 cancel_index（如果没有显式设置过）
            if "cancel_index" not in self._current_control or n > 0:
                control["cancel_index"] = n - 1 if n > 0 else 0

        self._result_control = control
        self.accept()

    @staticmethod
    def _set_nested_value(control: dict, field_path: str, value):
        """支持 'unknown[0]' 嵌套赋值"""
        parts = field_path.replace("[", ".").replace("]", "").split(".")
        current = control
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            if isinstance(current, list) and part.isdigit():
                idx = int(part)
                while len(current) <= idx:
                    current.append({} if not is_last else 0)
                if is_last:
                    current[idx] = value
                else:
                    current = current[idx]
            elif isinstance(current, dict):
                if is_last:
                    current[part] = value
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

    def get_result(self) -> dict:
        return self._result_control

    @classmethod
    def edit_control(cls, kind: str, current: dict = None, parent=None) -> dict:
        """静态便捷方法：打开对话框并返回 control dict（取消返回 None）"""
        dlg = cls(kind, current, parent)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.get_result()
        return None
