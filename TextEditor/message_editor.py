"""
Message Editor — 消息编辑主面板
左半边：文本渲染 + 右键格式菜单
右半边：Control 表格 + 添加按钮 + 选项池
"""

import copy
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTextEdit, QTableWidget, QTableWidgetItem, QPushButton,
    QLabel, QFrame, QMenu, QAction, QMessageBox, QHeaderView,
    QAbstractItemView, QSizePolicy, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import (
    QFont, QColor, QTextCharFormat, QTextCursor,
    QTextBlockFormat, QPalette, QPainter, QTextFormat,
    QKeySequence,
)

from texts_loader import TextsLoader
from models import (
    is_text_item, is_control_item, describe_control,
    PERSISTENT_KINDS, INSTANT_KINDS,
    make_text_item, make_control_item,
    DEFAULT_CONTROL_TEMPLATES,
)
from control_dialogs import ControlEditDialog
from option_pool_widget import OptionPoolWidget
from font_mapper import get_font_for_game

# ── 颜色映射 ──────────────────────────────────────────

COLOUR_MAP = {
    "blue":    QColor("#3388ff"),
    "red":     QColor("#ff3344"),
    "grey":    QColor("#888888"),
    "light_green1": QColor("#88cc88"),
    "light_green4": QColor("#66aa66"),
    "light_grey":   QColor("#aaaaaa"),
    "orange":  QColor("#ff9944"),
}

COLOUR_NAMES_CN = {
    "blue": "蓝色(重要信息)", "red": "红色(关键提示)",
    "grey": "灰色(压低声音)", "light_green1": "浅绿1",
    "light_green4": "浅绿4", "light_grey": "浅灰",
    "orange": "橙色",
}

SIZE_MAP = {80: "80%", 100: "100%", 125: "125%"}

TABLE_COL_POS = 0
TABLE_COL_KIND = 1
TABLE_COL_DESC = 2
TABLE_COL_ACTION = 3

# ── DEBUG：移动 control 调试开关 ───────────────────────
_DEBUG_MOVE = True


def _dbg(*args):
    if _DEBUG_MOVE:
        print("[MOVE-DBG]", *args)


def _is_control_block(bfmt: QTextBlockFormat) -> bool:
    """判断块格式是否属于 control 块（以 UserProperty 标签区分，不再依赖 leftMargin）"""
    return bfmt.property(QTextFormat.UserProperty) is not None


# ── 块自描述属性（新架构：数据贴在块上，不靠外部映射）──────

import json as _json

CONTROL_DATA_PROPERTY = QTextFormat.UserProperty + 1  # 存储 {"ci": N, ...control字段}
STYLE_STATE_PROPERTY = QTextFormat.UserProperty + 3   # QTextCharFormat 存储 {"colour":"red","font_kind":"normal","text_size":100}

# ── Control 块 ────────────────────────────────────────


def _tag_control_block(bfmt: QTextBlockFormat, ci: int, control: dict):
    """将 control 的完整数据 + ci 索引序列化贴在块格式上，块从此"自己知道自己是哪个"。"""
    data = {"ci": ci, **control}
    bfmt.setProperty(CONTROL_DATA_PROPERTY, _json.dumps(data, ensure_ascii=False))


def _read_control_block(block) -> tuple:
    """从文档块读取 (ci, control_dict)。非 control 块返回 (None, None)。"""
    raw = block.blockFormat().property(CONTROL_DATA_PROPERTY)
    if raw is None:
        return None, None
    data = _json.loads(raw)
    ci = data.pop("ci", -1)
    return ci, data


# ── 纯函数：_contents ↔ 文档块号映射（复现 _render_text 的块创建逻辑）────

def _compute_block_map(contents: list) -> list:
    """返回 block_ci 数组，block_ci[bn] = 该块所属的 _contents 下标。

    纯函数，直接从 _contents 推算。每个 text item（pi==0）都产生一个独立块，
    每个瞬时 control 也产生一个独立块。不复用块，保证 block↔ci 一对一。
    """
    block_ci = []

    for ci, item in enumerate(contents):
        if is_text_item(item):
            text = item.get("text", "")
            parts = text.split("\n")

            for pi, part in enumerate(parts):
                if pi > 0:
                    block_ci.append(ci)
                elif not part and len(parts) > 1:
                    # leading \n: _render_text 跳过
                    pass
                else:
                    # 不再复用块：每个 text item 的 pi==0 都强制新建块
                    block_ci.append(ci)

        elif is_control_item(item):
            kind = item["control"]["kind"]
            if kind not in PERSISTENT_KINDS:
                block_ci.append(ci)

    return block_ci


def _ci_at_block(contents: list, target_block: int) -> int:
    """给定 block 号，返回该 block 所属的 _contents 下标。越界返回 len(contents)。"""
    bmap = _compute_block_map(contents)
    if not bmap or target_block >= len(bmap):
        return len(contents)
    return bmap[target_block]


def _block_of_ci(contents: list, ci: int) -> int:
    """给定 _contents 下标，返回该项渲染出的第一个 block 号。"""
    bmap = _compute_block_map(contents)
    for bn, c in enumerate(bmap):
        if c == ci:
            return bn
    return 0


# ── 字符格式 style_state（新架构：持续型 control 不反推视觉属性）──────

def _build_style_state(colour_name: str, font_kind: str, size_pct: int) -> dict:
    """构造当前样式状态 dict，供贴标签时使用。"""
    state = {"font_kind": font_kind, "text_size": size_pct}
    if colour_name:
        state["colour"] = colour_name
    return state


def _tag_char_format_style(fmt: 'QTextCharFormat', colour_name: str, font_kind: str, size_pct: int):
    """在 QTextCharFormat 上贴上完整的 style_state 标签。"""
    state = _build_style_state(colour_name, font_kind, size_pct)
    fmt.setProperty(STYLE_STATE_PROPERTY, _json.dumps(state, ensure_ascii=False))


def _read_style_state(fmt: 'QTextCharFormat') -> dict:
    """从 QTextCharFormat 读取 style_state 标签，未贴返回 None。"""
    raw = fmt.property(STYLE_STATE_PROPERTY)
    if raw is None:
        return None
    return _json.loads(raw)


class MessageTextEdit(QTextEdit):
    """文本显示区域：Shift+滚轮缩放，control 块禁止编辑/选中/复制"""

    zoom_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_factor = 1.0
        self._nb_fmt = QTextBlockFormat()
        self._nb_fmt.setTopMargin(1)
        self._nb_fmt.setBottomMargin(1)
        self._nb_fmt.setLeftMargin(24)

    def insertFromMimeData(self, source):
        """粘贴时剔除外部格式，仅保留纯文本，并确保 leftMargin=24。"""
        if source.hasText():
            plain = source.text()
            cursor = self.textCursor()
            # 用默认格式插入纯文本，避免带入外部字体/颜色/字号
            default_fmt = QTextCharFormat()
            default_fmt.setFont(get_font_for_game("默认", 12))
            zoom = getattr(self, 'zoom_factor', 1.0)
            default_fmt.setFontPointSize(12 * zoom)
            default_fmt.setForeground(QColor(0, 0, 0))
            cursor.insertText(plain, default_fmt)
            # 修正粘贴产生的文本块格式
            doc = self.document()
            block = doc.firstBlock()
            while block.isValid():
                if not _is_control_block(block.blockFormat()):
                    bfmt = block.blockFormat()
                    bfmt.setLeftMargin(24)
                    bfmt.setTopMargin(1)
                    bfmt.setBottomMargin(1)
                    save_cursor = QTextCursor(doc)
                    save_cursor.setPosition(block.position())
                    save_cursor.setBlockFormat(bfmt)
                block = block.next()
        else:
            super().insertFromMimeData(source)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_factor = min(3.0, self.zoom_factor + 0.1)
            elif delta < 0:
                self.zoom_factor = max(0.5, self.zoom_factor - 0.1)
            event.accept()
            self.zoom_changed.emit()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        try:
            # Ctrl+C / Ctrl+X / Ctrl+Insert / Shift+Delete：只复制文本块，排除 control 块
            if event.matches(QKeySequence.Copy) or event.matches(QKeySequence.Cut):
                self._copy_text_blocks_only()
                return

            cursor = self.textCursor()
            block = cursor.block()
            if block.isValid() and _is_control_block(block.blockFormat()):
                nav_keys = {
                    Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                    Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown,
                    Qt.Key_Tab, Qt.Key_Backtab,
                }
                if event.key() in nav_keys:
                    super().keyPressEvent(event)
                else:
                    event.ignore()
            else:
                super().keyPressEvent(event)
        except Exception:
            import traceback
            traceback.print_exc()

    def _copy_text_blocks_only(self):
        """复制：只取选区内的文本块内容，完全排除 control 块。"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        # 边界保护：确保 start/end 在文档范围内
        doc = self.document()
        if start >= doc.characterCount() or end <= 0 or start >= end:
            return

        parts = []
        block = doc.findBlock(start)
        if not block.isValid():
            return
        end_block = doc.findBlock(max(start, end - 1))
        if not end_block.isValid():
            return

        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            if not _is_control_block(block.blockFormat()):  # 文本块
                txt = block.text()
                bp = block.position()
                tl = len(txt)
                s = max(start, bp) - bp
                e = min(end, bp + tl) - bp
                if s < e:
                    parts.append(txt[s:e])
            block = block.next()

        if parts:
            QApplication.clipboard().setText("\n".join(parts))

    def paintEvent(self, event):
        """绘制位置编号 + control 标签（均不在文档内，不可选中/编辑/复制）。"""
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        layout = self.document().documentLayout()
        h_scroll = self.horizontalScrollBar().value()
        v_scroll = self.verticalScrollBar().value()

        # 位置编号字体
        pos_font = painter.font()
        pos_font.setPointSizeF(8.5 * self.zoom_factor)

        # Control 标签字体
        label_font = painter.font()
        label_font.setPointSizeF(9 * self.zoom_factor)
        label_font.setItalic(True)

        block = self.document().firstBlock()
        pos = 0
        while block.isValid():
            rect = layout.blockBoundingRect(block)
            rect.translate(-h_scroll, -v_scroll)

            bfmt = block.blockFormat()
            label = bfmt.property(QTextFormat.UserProperty)

            # 位置编号（纯顺序计数，每块 +1）
            painter.setPen(QColor("#999999"))
            painter.setFont(pos_font)
            painter.drawText(int(rect.x() + 2), int(rect.y()), 22, int(rect.height()),
                             Qt.AlignRight | Qt.AlignVCenter, str(pos))

            if label is not None:
                painter.setPen(QColor("#555555"))
                painter.setFont(label_font)
                painter.drawText(rect.adjusted(24, 0, 0, 0),
                                 Qt.AlignLeft | Qt.AlignVCenter, str(label))

            pos += 1
            block = block.next()

        painter.end()


class ControlTable(QTableWidget):
    """右侧 Control 列表表格 — 行号由纯函数 _block_of_ci 现算，不存储映射"""

    control_edit_requested = pyqtSignal(int)        # table_row
    control_delete_requested = pyqtSignal(int)      # table_row
    control_move_requested = pyqtSignal(int, int)   # (old_ci, target_block_number)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_to_ci = []  # table row → _contents 下标
        self._populating = False
        self.hide_choice_controls: bool = False
        self._setup_ui()

    def _setup_ui(self):
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["位置", "类型", "描述", ""])
        self.horizontalHeader().setSectionResizeMode(TABLE_COL_POS, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(TABLE_COL_KIND, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(TABLE_COL_DESC, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(TABLE_COL_ACTION, QHeaderView.ResizeToContents)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.verticalHeader().setVisible(False)
        self.setMinimumWidth(260)
        self.cellChanged.connect(self._on_cell_changed)

    def _on_cell_changed(self, row: int, col: int):
        if self._populating:
            return
        if col != TABLE_COL_POS:
            return
        if row < 0 or row >= len(self._row_to_ci):
            return
        old_ci = self._row_to_ci[row]
        item = self.item(row, col)
        if item is None:
            return
        text = item.text().strip()
        try:
            target_block = int(text)
        except ValueError:
            QMessageBox.warning(self, "输入错误",
                                f"位置必须是数字，当前输入「{item.text()}」无效。",
                                QMessageBox.Ok)
            return
        if target_block < 0:
            QMessageBox.warning(self, "输入错误",
                                f"位置不能为负数（当前值：{target_block}）。",
                                QMessageBox.Ok)
            return
        self.control_move_requested.emit(old_ci, target_block)
        _dbg(f"用户操作: 移动 ci={old_ci} 的 control 到块 {target_block}")

    def populate(self, contents: list):
        """遍历 _contents，用纯函数 _block_of_ci 计算每个瞬时型 control 的显示块号。"""
        self._populating = True
        self.setRowCount(0)
        self._row_to_ci = []

        row = 0
        for ci, item in enumerate(contents):
            if is_control_item(item):
                kind = item["control"]["kind"]
                if kind not in INSTANT_KINDS:
                    continue
                if self.hide_choice_controls and kind in ("choice", "single_choice"):
                    continue
                self.insertRow(row)
                self._row_to_ci.append(ci)

                block_bn = _block_of_ci(contents, ci)
                pos_item = QTableWidgetItem(str(block_bn))
                pos_item.setFlags(pos_item.flags() | Qt.ItemIsEditable)
                self.setItem(row, TABLE_COL_POS, pos_item)
                self.setItem(row, TABLE_COL_KIND, QTableWidgetItem(kind))
                self.setItem(row, TABLE_COL_DESC, QTableWidgetItem(describe_control(item["control"])))

                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(2, 1, 2, 1)
                btn_layout.setSpacing(2)
                edit_btn = QPushButton("编辑")
                edit_btn.setFixedSize(40, 22)
                edit_btn.clicked.connect(lambda checked, r=row: self.control_edit_requested.emit(r))
                btn_layout.addWidget(edit_btn)
                del_btn = QPushButton("删")
                del_btn.setFixedSize(28, 22)
                del_btn.setStyleSheet("QPushButton { color: #cc0000; }")
                del_btn.clicked.connect(lambda checked, r=row: self.control_delete_requested.emit(r))
                btn_layout.addWidget(del_btn)
                self.setCellWidget(row, TABLE_COL_ACTION, btn_widget)
                row += 1
        self._populating = False


class MessageEditor(QWidget):
    """消息编辑器主体"""

    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: TextsLoader = None
        self._current_msbt: str = ""
        self._current_label: str = ""
        self._contents: list = []
        self._attributes: str = ""
        # 嵌入模式：隐藏 choice/single_choice 控件（由宿主 M 菜单管理）
        self.hide_choice_controls: bool = False
        # source_map: plain_pos → (content_idx, source_char_offset)
        # source_offset 是原始 text 字符串"你好\n世界"中的索引, 其中\n占1字符
        self._source_map: list = []
        self._adjusting_selection = False
        self._syncing = False  # 防止 textChanged 递归
        self._rendering = False  # 渲染期间忽略 textChanged
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        info_layout = QHBoxLayout()
        self._info_label = QLabel("未选择消息")
        self._info_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #336699;")
        info_layout.addWidget(self._info_label)
        info_layout.addStretch()
        self._attr_edit = QLabel("")
        self._attr_edit.setStyleSheet("color: #888;")
        info_layout.addWidget(self._attr_edit)
        main_layout.addLayout(info_layout)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(sep)

        splitter = QSplitter(Qt.Horizontal)

        self._text_display = MessageTextEdit()
        # 将文档默认字体设为游戏对话字体，避免空文本块回退到系统默认字体
        self._text_display.document().setDefaultFont(get_font_for_game("默认", 12))
        self._text_display.setContextMenuPolicy(Qt.CustomContextMenu)
        self._text_display.customContextMenuRequested.connect(self._on_context_menu)
        self._text_display.selectionChanged.connect(self._on_selection_changed)
        self._text_display.zoom_changed.connect(self._on_zoom_changed)
        self._text_display.textChanged.connect(self._on_text_changed)
        self._text_display.setMinimumWidth(350)

        # 让失焦时的选区颜色与聚焦时一致（右键菜单期间不丢高亮）
        p = self._text_display.palette()
        p.setColor(QPalette.Inactive, QPalette.Highlight, p.color(QPalette.Active, QPalette.Highlight))
        p.setColor(QPalette.Inactive, QPalette.HighlightedText, p.color(QPalette.Active, QPalette.HighlightedText))
        self._text_display.setPalette(p)
        splitter.addWidget(self._text_display)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        ctrl_header = QLabel("Control 列表")
        ctrl_header.setStyleSheet("font-weight: bold; font-size: 12px;")
        right_layout.addWidget(ctrl_header)

        self._control_table = ControlTable()
        self._control_table.control_edit_requested.connect(self._on_edit_control)
        self._control_table.control_delete_requested.connect(self._on_delete_control)
        self._control_table.control_move_requested.connect(self._on_move_control)
        right_layout.addWidget(self._control_table, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        self._add_control_btn = QPushButton("+ 添加 Control")
        self._add_control_btn.clicked.connect(self._on_add_control)
        self._add_control_btn.setEnabled(False)
        btn_layout.addWidget(self._add_control_btn)
        right_layout.addLayout(btn_layout)

        self._option_pool = OptionPoolWidget()
        self._option_pool.pool_changed.connect(self._on_pool_changed)
        right_layout.addWidget(self._option_pool)

        self._opt_toggle_btn = QPushButton("展开选项池")
        self._opt_toggle_btn.setCheckable(True)
        self._opt_toggle_btn.clicked.connect(self._toggle_option_pool)
        self._opt_toggle_btn.setEnabled(False)
        right_layout.addWidget(self._opt_toggle_btn)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, stretch=1)

        from font_mapper import get_legend_text
        legend = QLabel(get_legend_text())
        legend.setStyleSheet(
            "font-size: 10px; color: #666; padding: 2px;"
            "background: #f0f0f0; border-radius: 3px;"
        )
        legend.setWordWrap(True)
        main_layout.addWidget(legend)

        self.setEnabled(False)

    # ── 公共接口 ──────────────────────────────────────

    def set_context(self, loader: TextsLoader, msbt_path: str, label: str):
        self._loader = loader
        self._current_msbt = msbt_path
        self._current_label = label
        self.setEnabled(True)
        self._add_control_btn.setEnabled(True)
        self._opt_toggle_btn.setEnabled(True)
        self._load_entry()
        self._option_pool.set_context(loader, msbt_path)

    def clear_context(self):
        self._loader = None
        self._current_msbt = ""
        self._current_label = ""
        self._contents = []
        self._attributes = ""
        self._source_map = []
        self.setEnabled(False)
        self._add_control_btn.setEnabled(False)
        self._opt_toggle_btn.setEnabled(False)
        self._text_display.clear()
        self._control_table.setRowCount(0)
        self._info_label.setText("未选择消息")
        self._attr_edit.setText("")
        self._option_pool.clear_context()
        self._opt_toggle_btn.setChecked(False)
        self._option_pool.setVisible(False)
        self._opt_toggle_btn.setText("展开选项池")

    def _load_entry(self):
        entry = self._loader.get_entry(self._current_msbt, self._current_label)
        if entry is None:
            self._contents = [{"text": ""}]
            self._attributes = ""
        else:
            self._contents = entry.get("contents", [])
            self._attributes = entry.get("attributes", "")
        # 确保始终存在至少一个文本项（否则光标无处可去）
        if not any(is_text_item(it) for it in self._contents):
            self._contents.insert(0, {"text": ""})
        self._render_text()
        self._control_table.populate(self._contents)
        self._info_label.setText(f"{self._current_msbt}  →  {self._current_label}")
        self._attr_edit.setText(
            f"attributes: {self._attributes}" if self._attributes else ""
        )

    def _save_entry(self, extract_formatting=True):
        if not self._loader or not self._current_label:
            return
        entry = self._loader.get_entry(self._current_msbt, self._current_label)
        if entry is not None:
            if extract_formatting:
                # 从文档 fragment 读取 style_state 标签，重建带持续型 control 的 _contents
                try:
                    self._contents = self._build_contents_from_document()
                except Exception:
                    import traceback
                    traceback.print_exc()
                    # 提取失败时保留当前 _contents（至少不会丢数据）
            entry["contents"] = copy.deepcopy(self._contents)
            entry["attributes"] = self._attributes
            self._loader.mark_dirty()

    def _build_contents_from_document(self):
        """从文档重建 _contents（纯文档驱动，零 ci，零旧 _contents 依赖）。

        控制块：直接从块标签读完整 control dict，按文档顺序排列。
        持续型 control：按 fragment 的 style_state 标签检测格式变化。
        文本：相邻文本块合并为单个 text item，跨块加 \\n 分隔。
        choice / single_choice 始终保持在末尾。
        """
        doc = self._text_display.document()
        zoom = getattr(self._text_display, 'zoom_factor', 1.0)
        leading_nl_blocks = getattr(self._text_display, '_leading_nl_blocks', set())

        new = []
        choice_controls = []  # 末尾单独收集
        prev_state = None
        prev_was_text = False

        block = doc.firstBlock()
        while block.isValid():
            if _is_control_block(block.blockFormat()):
                prev_was_text = False
                _, control_data = _read_control_block(block)
                if control_data is not None:
                    kind = control_data.get("kind", "?")
                    if kind in ("choice", "single_choice"):
                        choice_controls.append({"control": copy.deepcopy(control_data)})
                    elif kind in INSTANT_KINDS:
                        new.append({"control": copy.deepcopy(control_data)})
                    # 持续型 control 不产生块，忽略
                block = block.next()
                continue

            # 文本块之间加 \n 分隔（仿 BCML 原文格式）
            if prev_was_text and new and is_text_item(new[-1]):
                new[-1]["text"] += "\n"
            elif block.blockNumber() in leading_nl_blocks:
                if new and is_text_item(new[-1]):
                    new[-1]["text"] += "\n"
                else:
                    new.append({"text": "\n"})

            # 按 QTextFragment 扫描格式变化
            it = block.begin()
            while it != block.end():
                fragment = it.fragment()
                if fragment.isValid() and fragment.length() > 0:
                    text = fragment.text().replace("\u200B", "")
                    if text:
                        fmt = fragment.charFormat()
                        state = _read_style_state(fmt)
                        if state is None:
                            state = self._calc_style_from_format(fmt, zoom)

                        if state != prev_state:
                            self._emit_style_diff(new, prev_state, state)
                            prev_state = state

                        if new and is_text_item(new[-1]):
                            new[-1]["text"] += text
                        else:
                            new.append({"text": text})
                it += 1

            prev_was_text = True
            block = block.next()

        # choice/single_choice 始终在末尾
        new.extend(choice_controls)

        if not any(is_text_item(it) for it in new):
            new.insert(0, {"text": ""})

        return new

    def _calc_style_from_format(self, fmt: QTextCharFormat, zoom: float) -> dict:
        """从 QTextCharFormat 视觉属性反算 style_state dict（回退路径）。"""
        state = {"font_kind": "normal", "text_size": 100}

        fg = fmt.foreground().color()
        for name, c in COLOUR_MAP.items():
            if c == fg:
                state["colour"] = name
                break

        font = fmt.font()
        if "Hylian" in font.family():
            state["font_kind"] = "hylian"

        raw_pt = fmt.fontPointSize()
        if raw_pt > 0:
            pct = round(raw_pt / (12 * zoom) * 100)
            if 50 <= pct <= 200:
                state["text_size"] = pct

        return state

    def _emit_style_diff(self, target: list, prev: dict, curr: dict):
        """向 target 列表插入持续型 control，完成从 prev 到 curr 的样式过渡。"""
        if prev is None:
            prev = {"font_kind": "normal", "text_size": 100}

        prev_colour = prev.get("colour")
        curr_colour = curr.get("colour")
        if curr_colour != prev_colour:
            if curr_colour is not None:
                target.append({"control": {"kind": "set_colour", "colour": curr_colour}})
            elif prev_colour is not None:
                target.append({"control": {"kind": "reset_colour"}})

        prev_font = prev.get("font_kind", "normal")
        curr_font = curr.get("font_kind", "normal")
        if curr_font != prev_font:
            target.append({"control": {"kind": "font", "font_kind": curr_font}})

        prev_size = prev.get("text_size", 100)
        curr_size = curr.get("text_size", 100)
        if curr_size != prev_size:
            target.append({"control": {"kind": "text_size", "percent": curr_size}})

    # ═══════════════════════════════════════════════════
    #  文本渲染 + 精确字符位置映射
    # ═══════════════════════════════════════════════════

    def _render_text(self):
        """渲染内容到 QTextEdit，同时建立精确的 source_map。

        source_map[plain_pos] = (content_idx, source_char_offset)
          - plain_pos: QTextEdit 中的纯文本字符位置
          - source_char_offset: 原始 text 字符串中的字符索引
            （\n 在原文占1字符，在渲染中占1字符）

        持续型 control 不产生字符，只更新渲染状态。
        瞬时型 control 渲染为独立灰色标签行。
        """
        self._rendering = True
        self._source_map = []  # 必须在 clear() 之前，否则 selectionChanged 会访问旧数据导致崩溃
        self._text_display.clear()
        cursor = self._text_display.textCursor()
        _actual_block_ci = []

        # DEBUG: 录制实际的 block→ci，与 _compute_block_map 对比
        def _rec_new_block(ci_val):
            bn = cursor.block().blockNumber()
            while len(_actual_block_ci) <= bn:
                _actual_block_ci.append(-1)
            _actual_block_ci[bn] = ci_val

        # _leading_nl_blocks: 记录哪些块来自开头 \n（渲染时不显示空块，保存时需补回）
        self._text_display._leading_nl_blocks = set()
        self._next_leading_nl = False  # 标记下一个文本块是否来自开头 \n

        zoom = getattr(self._text_display, 'zoom_factor', 1.0)
        col = None
        colour_name = None  # 字符串名称，供 style_state 标签使用
        font_kind = "normal"
        size_pct = 100

        nb_fmt = QTextBlockFormat()
        nb_fmt.setTopMargin(1)
        nb_fmt.setBottomMargin(1)
        nb_fmt.setLeftMargin(24)  # 给位置编号留空

        plain_pos = 0

        for ci, item in enumerate(self._contents):
            if is_text_item(item):
                text = item["text"]  # 原始字符串，\n 是一个字符
                fmt = QTextCharFormat()
                if col:
                    fmt.setForeground(col)
                if font_kind == "hylian":
                    fmt.setFont(get_font_for_game("Hylian", 12))
                else:
                    fmt.setFont(get_font_for_game("默认", 12))
                fmt.setFontPointSize(12 * zoom * size_pct / 100)
                _tag_char_format_style(fmt, colour_name, font_kind, size_pct)

                source_off = 0  # 在 text 字符串中的当前偏移

                # 按 \n 拆分为多个段落
                parts = text.split("\n")
                for pi, part in enumerate(parts):
                    if pi > 0:
                        # 换行：插入新块，格式化状态不变（同一 text item 内延续）
                        cursor.insertBlock(nb_fmt)
                        _rec_new_block(ci)
                        if self._next_leading_nl:
                            self._text_display._leading_nl_blocks.add(cursor.block().blockNumber())
                            self._next_leading_nl = False
                        # plain_pos 对应 source_off（\n 的位置）
                        self._source_map.append((ci, source_off))
                        plain_pos += 1
                        source_off += 1  # 跳过 \n（1 字符）

                    if pi == 0 and not part and len(parts) > 1:
                        # 开头 \n：表示续写到下一行，不创建空白块（否则 control 后多一个空行）
                        self._source_map.append((ci, source_off))
                        plain_pos += 1
                        source_off += 1  # 跳过 \n
                        self._next_leading_nl = True
                        continue

                    if pi == 0:
                        # 每个 text item pi==0 都强制 insertBlock，不复用块
                        # 避免多个 ci 共享同一个 QTextDocument block 导致 block↔ci 一对多
                        cursor.insertBlock(nb_fmt)
                        _rec_new_block(ci)
                        self._source_map.append((-1, -1))
                        plain_pos += 1

                    # 空文本块插入零宽空格保持块高度，否则无法点击输入
                    if part:
                        cursor.insertText(part, fmt)
                        for ch_i in range(len(part)):
                            self._source_map.append((ci, source_off + ch_i))
                        plain_pos += len(part)
                    else:
                        cursor.insertText("\u200B", fmt)
                        self._source_map.append((ci, source_off))
                        plain_pos += 1
                    source_off += len(part)

            elif is_control_item(item):
                kind = item["control"]["kind"]
                if kind in PERSISTENT_KINDS:
                    if kind == "set_colour":
                        colour_name = item["control"].get("colour", "")
                        col = COLOUR_MAP.get(colour_name, None)
                    elif kind == "reset_colour":
                        colour_name = None
                        col = None
                    elif kind == "font":
                        font_kind = item["control"].get("font_kind", "normal")
                    elif kind == "text_size":
                        size_pct = item["control"].get("percent", 100)
                else:
                    # 瞬时型：空块 + 透明占位字符（维持文档块结构，标签由 paintEvent 绘制）
                    desc = describe_control(item["control"])
                    label_text = f"◆ {desc}"
                    cb_fmt = QTextBlockFormat()
                    cb_fmt.setTopMargin(2)
                    cb_fmt.setBottomMargin(2)
                    cb_fmt.setLeftMargin(24)
                    cb_fmt.setProperty(QTextFormat.UserProperty, label_text)
                    _tag_control_block(cb_fmt, ci, item["control"])  # 块自描述：贴上完整 control 数据

                    if not cursor.atBlockStart():
                        cursor.insertBlock(cb_fmt)
                        _rec_new_block(ci)
                        self._source_map.append((-1, -1))
                        plain_pos += 1
                    else:
                        cursor.setBlockFormat(cb_fmt)
                        _rec_new_block(ci)

                    # 透明占位字符：给块一个"身体"，防止下游 setBlockFormat 覆盖
                    dummy_fmt = QTextCharFormat()
                    dummy_fmt.setForeground(QColor(0, 0, 0, 0))
                    cursor.insertText(" ", dummy_fmt)
                    self._source_map.append((-1, -1))
                    plain_pos += 1

        self._text_display.moveCursor(QTextCursor.Start)
        self._text_display.viewport().update()

        # DEBUG: 对比 _render_text 实际录制的 block_ci 和 _compute_block_map
        _computed = _compute_block_map(self._contents)
        if _actual_block_ci != _computed:
            _dbg(f"[BLOCK-MISMATCH] 渲染录制: {_actual_block_ci}")
            _dbg(f"[BLOCK-MISMATCH] 纯函数算: {_computed}")

        self._rendering = False
        # 确保空文本块不会被遗留的 \u200B 格式污染后续输入
        self._reset_empty_block_formats()

    def _on_zoom_changed(self):
        """Shift+滚轮缩放后重渲染，同步更新文档默认字体大小。"""
        zoom = self._text_display.zoom_factor
        default_font = get_font_for_game("默认", 12)
        default_font.setPointSizeF(12 * zoom)
        self._text_display.document().setDefaultFont(default_font)
        self._render_text()

    def _on_text_changed(self):
        """用户编辑文本时，将文档内容同步到 _contents 并自动保存。"""
        if self._syncing or self._rendering:
            return
        self._syncing = True
        try:
            self._sync_contents_from_document()
            self._save_entry()
            self._reset_empty_block_formats()
            self._control_table.populate(self._contents)
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            self._syncing = False

    def _sync_contents_from_document(self):
        """从 QTextDocument 块结构重建 _contents（仅文本 + 瞬时型 control）。

        持续型 control（set_colour / font / text_size 等）不在此方法处理；
        它们由 _save_entry 从文档 QTextCharFormat 中提取。
        choice / single_choice 始终保持在末尾（由宿主 M 菜单管理，不参与块匹配）。
        """
        doc = self._text_display.document()
        old = self._contents

        # 收集旧数据中的瞬时型 control（忽略持续型）
        # choice/single_choice 单独分离，始终放在末尾
        old_instants = []
        choice_controls = []
        for item in old:
            if is_control_item(item):
                kind = item["control"]["kind"]
                if kind in INSTANT_KINDS:
                    if kind in ("choice", "single_choice"):
                        choice_controls.append(copy.deepcopy(item))
                    else:
                        old_instants.append(copy.deepcopy(item))

        new = []
        ci = 0

        block = doc.firstBlock()
        while block.isValid():
            bfmt = block.blockFormat()
            if _is_control_block(bfmt):
                # Control 块 → 匹配瞬时型 control
                if ci < len(old_instants):
                    new.append(old_instants[ci])
                    ci += 1
                block = block.next()
            else:
                # 文本块 → 收集连续文本块，保留开头 \n 标记
                leading_nl_blocks = getattr(self._text_display, '_leading_nl_blocks', set())
                texts = []
                needs_leading_nl = False
                while block.isValid() and not _is_control_block(block.blockFormat()):
                    bn = block.blockNumber()
                    if bn in leading_nl_blocks and not texts:
                        needs_leading_nl = True
                    texts.append(block.text())
                    block = block.next()
                merged = "\n".join(texts).replace("\u200B", "")
                if needs_leading_nl and merged:
                    merged = "\n" + merged
                if merged:
                    new.append({"text": merged})

        # 追加剩余的瞬时型 control（非 choice 类）
        while ci < len(old_instants):
            new.append(old_instants[ci])
            ci += 1

        # choice/single_choice 始终在最末尾
        new.extend(choice_controls)

        # 确保始终存在至少一个文本项（否则光标无处可落）
        if not any(is_text_item(it) for it in new):
            new.insert(0, {"text": ""})

        self._contents = new

    def _reset_empty_block_formats(self):
        """确保所有清空的文本块使用默认字符格式，防止重新输入时格式延续。"""
        doc = self._text_display.document()
        block = doc.firstBlock()
        tc = self._text_display.textCursor()  # 必须用文本编辑器的光标，否则 setCharFormat 无效
        zoom = getattr(self._text_display, 'zoom_factor', 1.0)
        default_fmt = QTextCharFormat()
        default_fmt.setFont(get_font_for_game("默认", 12))
        default_fmt.setFontPointSize(12 * zoom)
        default_fmt.setForeground(QColor(0, 0, 0))
        saved_pos = tc.position()
        saved_anchor = tc.anchor()
        while block.isValid():
            if not _is_control_block(block.blockFormat()):
                text = block.text().replace("\u200B", "")
                if not text:
                    tc.setPosition(block.position())
                    tc.setCharFormat(default_fmt)
            block = block.next()
        # 恢复光标位置
        tc.setPosition(saved_anchor)
        tc.setPosition(saved_pos, QTextCursor.KeepAnchor)
        self._text_display.setTextCursor(tc)

    # ═══════════════════════════════════════════════════
    #  精确位置映射
    # ═══════════════════════════════════════════════════

    def _plain_to_source(self, plain_pos: int) -> tuple:
        """渲染位置 → (content_idx, source_char_offset)"""
        if 0 <= plain_pos < len(self._source_map):
            return self._source_map[plain_pos]
        return (-1, -1)

    # ── 选区调整：排除 control 标记 ──────────────────

    def _on_selection_changed(self):
        """选区变化时：排除 control 块区域。用块格式判断，不依赖 source_map。"""
        # 渲染/同步期间文档状态不稳定，跳过选区调整
        if self._adjusting_selection or self._rendering or self._syncing:
            return
        try:
            cursor = self._text_display.textCursor()
            doc = self._text_display.document()

            if cursor.hasSelection():
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                changed = False

                # 将 start 向前推进：跳过 control 块
                while start < end:
                    b = doc.findBlock(start)
                    if not b.isValid():
                        break
                    if not _is_control_block(b.blockFormat()):
                        break  # 已在文本块
                    start = b.position() + b.length()  # 跳到下一块开头
                    changed = True

                # 将 end 向后收缩：跳过 control 块
                while end > start:
                    b = doc.findBlock(max(0, end - 1))
                    if not b.isValid():
                        break
                    if not _is_control_block(b.blockFormat()):
                        break
                    end = b.position()  # 缩到 control 块开头之前
                    changed = True

                if start >= end:
                    self._adjusting_selection = True
                    cursor.clearSelection()
                    self._snap_cursor_to_text(cursor)
                    self._text_display.setTextCursor(cursor)
                    self._adjusting_selection = False
                    return

                if changed:
                    self._adjusting_selection = True
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.KeepAnchor)
                    self._text_display.setTextCursor(cursor)
                    self._adjusting_selection = False
            else:
                # 无选区：光标不能落在 control 块
                b = cursor.block()
                if b.isValid() and _is_control_block(b.blockFormat()):
                    self._adjusting_selection = True
                    self._snap_cursor_to_text(cursor)
                    self._text_display.setTextCursor(cursor)
                    self._adjusting_selection = False
        except Exception:
            import traceback
            traceback.print_exc()
            self._adjusting_selection = False

    def _snap_cursor_to_text(self, cursor):
        """将光标移到最近的文本块开头。"""
        doc = self._text_display.document()
        # 尝试当前块 → 下一块 → 上一块
        for delta in (0, 1, -1, 2, -2, 3, -3):
            bn = cursor.block().blockNumber() + delta
            b = doc.findBlockByNumber(bn)
            if b.isValid() and not _is_control_block(b.blockFormat()):
                cursor.setPosition(b.position())
                return
        cursor.setPosition(0)

    # ═══════════════════════════════════════════════════
    #  右键菜单
    # ═══════════════════════════════════════════════════

    def _on_context_menu(self, pos: QPoint):
        if not self._contents:
            return

        menu = QMenu(self)

        colour_menu = menu.addMenu("设置颜色")
        for colour_name, cn_name in COLOUR_NAMES_CN.items():
            action = colour_menu.addAction(cn_name)
            action.triggered.connect(
                lambda checked, c=colour_name: self._apply_persistent_control(
                    "set_colour", {"kind": "set_colour", "colour": c},
                    {"kind": "reset_colour"},
                )
            )
        black_action = colour_menu.addAction("黑色(默认)")
        black_action.triggered.connect(
            lambda: self._apply_black_colour()
        )
        reset_colour_action = colour_menu.addAction("重置颜色")
        reset_colour_action.triggered.connect(
            lambda: self._remove_persistent_controls(("set_colour", "reset_colour"))
        )

        size_menu = menu.addMenu("设置字号")
        for pct, label in SIZE_MAP.items():
            action = size_menu.addAction(label)
            action.triggered.connect(
                lambda checked, s=pct: self._apply_persistent_control(
                    "text_size", {"kind": "text_size", "percent": s},
                    {"kind": "text_size", "percent": 100},
                )
            )

        font_menu = menu.addMenu("设置字体")
        for font_name in ("normal", "hylian"):
            label = "默认字体" if font_name == "normal" else "Hylian 字体"
            action = font_menu.addAction(label)
            action.triggered.connect(
                lambda checked, f=font_name: self._apply_persistent_control(
                    "font", {"kind": "font", "font_kind": f},
                    {"kind": "font", "font_kind": "normal"},
                )
            )

        menu.addSeparator()
        nl_action = menu.addAction("此处插入换行")
        nl_action.triggered.connect(self._insert_newline)
        menu.exec_(self._text_display.mapToGlobal(pos))

    # ═══════════════════════════════════════════════════
    #  格式应用：直接操作文档 QTextCharFormat
    # ═══════════════════════════════════════════════════

    def _apply_persistent_control(self, kind: str, open_ctrl: dict, close_ctrl: dict):
        """直接对文档选中区域应用 QTextCharFormat，不修改 _contents。

        持续型 control 在 _save_entry → _build_contents_from_document 时
        从文档 fragment 的 style_state 标签中自动提取，无需手动拆分 text item。
        """
        cursor = self._text_display.textCursor()
        if not cursor.hasSelection():
            return

        fmt = QTextCharFormat()
        if kind == "set_colour":
            col = COLOUR_MAP.get(open_ctrl.get("colour", ""))
            if col:
                fmt.setForeground(col)
        elif kind == "font":
            font_kind = open_ctrl.get("font_kind", "normal")
            fmt.setFont(get_font_for_game("Hylian" if font_kind == "hylian" else "默认", 12))
        elif kind == "text_size":
            pct = open_ctrl.get("percent", 100)
            zoom = getattr(self._text_display, 'zoom_factor', 1.0)
            fmt.setFontPointSize(12 * zoom * pct / 100)

        cursor.mergeCharFormat(fmt)
        self._save_entry()

    def _remove_persistent_controls(self, kinds: tuple):
        """移除指定类型的持续型 control：对全文应用默认格式后保存。"""
        cursor = self._text_display.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()

        if "set_colour" in kinds or "reset_colour" in kinds:
            fmt.setForeground(QColor(0, 0, 0))  # 默认黑色
        if "font" in kinds:
            fmt.setFont(get_font_for_game("默认", 12))
        if "text_size" in kinds:
            zoom = getattr(self._text_display, 'zoom_factor', 1.0)
            fmt.setFontPointSize(12 * zoom)

        cursor.mergeCharFormat(fmt)
        self._save_entry()
        self._render_text()
        self._control_table.populate(self._contents)

    def _apply_black_colour(self):
        """对选中区域应用黑色（默认颜色），用于单次换回原色。"""
        cursor = self._text_display.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(0, 0, 0))
        cursor.mergeCharFormat(fmt)
        self._save_entry()

    def _insert_newline(self):
        """在当前光标处插入换行"""
        cursor = self._text_display.textCursor()
        plain_p = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        ci, soff = self._plain_to_source(plain_p)
        if ci >= 0:
            t = self._contents[ci]["text"]
            self._contents[ci]["text"] = t[:soff] + "\n" + t[soff:]
        else:
            for item in reversed(self._contents):
                if is_text_item(item):
                    item["text"] += "\n"
                    break
            else:
                self._contents.append({"text": "\n"})
        self._refresh()

    # ── Control 表格操作 ───────────────────────────────

    def _on_add_control(self):
        menu = QMenu(self)
        kinds = ["pause", "sound", "sound2", "icon",
                 "variable", "animation", "auto_advance",
                 "choice", "single_choice", "raw"]
        labels = {
            "pause": "停顿 (pause)", "sound": "音效 (sound)",
            "sound2": "音效2 (sound2)", "icon": "图标 (icon)",
            "variable": "变量 (variable)", "animation": "动画 (animation)",
            "auto_advance": "自动推进 (auto_advance)",
            "choice": "选项 (choice)", "single_choice": "单选项 (single_choice)",
            "raw": "消息延续 (raw)",
        }
        if self.hide_choice_controls:
            kinds = [k for k in kinds if k not in ("choice", "single_choice")]
        for kind in kinds:
            action = menu.addAction(labels.get(kind, kind))
            action.triggered.connect(
                lambda checked, k=kind: self._insert_control(k)
            )
        menu.exec_(self._add_control_btn.mapToGlobal(
            QPoint(0, self._add_control_btn.height())))

    def _insert_control(self, kind: str):
        """在 _contents 末尾追加新 control，然后整体重新渲染。"""
        control = make_control_item(kind)
        result = ControlEditDialog.edit_control(kind, control, self)
        if result is not None:
            self._contents.append({"control": result})
            self._refresh()

    def _on_move_control(self, old_ci: int, target_block: int):
        """移动 control：在 _contents 中 pop + insert，然后整体 _render_text 重建文档。
        
        old_ci: 源 control 的 _contents 下标
        target_block: 用户期望的目标块号（纯函数 _ci_at_block 反算 ci）
        """
        if old_ci < 0 or old_ci >= len(self._contents):
            return

        _dbg(f"_contents 级移动: old_ci={old_ci} → target_block={target_block}")
        _dbg(f"移动前 _contents 结构: {[(i, 'text' if is_text_item(it) else it.get('control',{}).get('kind','?')) for i, it in enumerate(self._contents)]}")

        item = self._contents.pop(old_ci)

        # pop 之后 _contents 已变化，用新的 _contents 反算 target_block 对应的 ci
        target_ci = _ci_at_block(self._contents, target_block)
        if target_ci > len(self._contents):
            target_ci = len(self._contents)

        _dbg(f"  pop 后 target_ci={target_ci}, 插入到位置 {target_ci}")
        self._contents.insert(target_ci, item)
        _dbg(f"移动后 _contents 结构: {[(i, 'text' if is_text_item(it) else it.get('control',{}).get('kind','?')) for i, it in enumerate(self._contents)]}")
        self._refresh()

    def _dump_doc_blocks(self):
        """调试：打印当前文档的块结构。"""
        doc = self._text_display.document()
        block = doc.firstBlock()
        while block.isValid():
            _, ctrl = _read_control_block(block)
            if ctrl:
                _dbg(f"  块 {block.blockNumber()}: CONTROL kind={ctrl.get('kind','?')}")
            else:
                _dbg(f"  块 {block.blockNumber()}: TEXT [{block.text()[:40]}]")
            block = block.next()

    def _on_edit_control(self, row: int):
        """编辑 control：从 _contents 读取，修改后重新渲染。"""
        if row < 0 or row >= len(self._control_table._row_to_ci):
            return
        ci = self._control_table._row_to_ci[row]
        control = self._contents[ci]["control"]
        kind = control.get("kind", "")
        result = ControlEditDialog.edit_control(kind, control, self)
        if result is not None:
            self._contents[ci]["control"] = result
            self._refresh()

    def _on_delete_control(self, row: int):
        """删除 control：从 _contents 删除，重新渲染。"""
        if row < 0 or row >= len(self._control_table._row_to_ci):
            return
        ci = self._control_table._row_to_ci[row]
        del self._contents[ci]
        self._refresh()

    def _toggle_option_pool(self, checked: bool):
        self._option_pool.setVisible(checked)
        self._opt_toggle_btn.setText("收起选项池" if checked else "展开选项池")

    def _on_pool_changed(self):
        self.data_changed.emit()

    def _refresh(self):
        self._render_text()
        self._save_entry(extract_formatting=False)
        self._control_table.populate(self._contents)
