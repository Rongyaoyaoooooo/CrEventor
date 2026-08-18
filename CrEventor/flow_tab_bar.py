"""Vertical tab bar for switching between open flows, like browser tabs rotated 90°."""
from PyQt5 import QtCore as qc
from PyQt5 import QtGui as qg
from PyQt5 import QtWidgets as q


class FlowTab(q.QWidget):
    """A single vertical tab: rotated name + close button."""
    clicked = qc.pyqtSignal()
    closeClicked = qc.pyqtSignal()

    TAB_WIDTH = 30          # fixed horizontal width
    TAB_MIN_HEIGHT = 60     # minimum vertical height
    TAB_MAX_HEIGHT = 220    # maximum vertical height
    CHAR_HEIGHT = 10        # pixels per character (approx for rotated text)

    def __init__(self, name: str, index: int, parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._index = index
        self._current = False
        self._hover = False
        self._close_hover = False
        self.setCursor(qc.Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip(name)
        self._calc_size()

    def _calc_size(self) -> None:
        """Calculate tab height based on name length so text fits."""
        fm = qg.QFontMetrics(qg.QFont('Segoe UI', 9))
        text_w = fm.width(self._name[:20])
        h = max(self.TAB_MIN_HEIGHT,
                min(self.TAB_MAX_HEIGHT, text_w + 50))
        self.setFixedSize(self.TAB_WIDTH, h)

    @property
    def index(self) -> int:
        return self._index

    @index.setter
    def index(self, value: int) -> None:
        self._index = value

    @property
    def name(self) -> str:
        return self._name

    def set_name(self, name: str) -> None:
        self._name = name
        self._calc_size()
        self.setToolTip(name)
        self.update()

    def set_current(self, current: bool) -> None:
        self._current = current
        self.update()

    def _close_rect(self) -> qc.QRect:
        return qc.QRect(0, 0, 16, 16)

    def _is_over_close(self, pos) -> bool:
        return self._close_rect().contains(pos)

    def paintEvent(self, event) -> None:
        painter = qg.QPainter(self)
        painter.setRenderHint(qg.QPainter.Antialiasing)

        r = self.rect()

        # Background
        if self._current:
            painter.fillRect(r, qg.QColor(255, 255, 255))
        elif self._hover:
            painter.fillRect(r, qg.QColor(230, 245, 255))
        else:
            painter.fillRect(r, qg.QColor(200, 225, 240))

        # Border for current
        if self._current:
            painter.setPen(qg.QColor(180, 200, 210))
            painter.drawRect(r.adjusted(0, 0, -1, -1))

        # Close button
        cr = self._close_rect()
        if self._close_hover:
            painter.fillRect(cr, qg.QColor(200, 60, 60))
            painter.setPen(qg.QColor(255, 255, 255))
        else:
            painter.setPen(qg.QColor(180, 80, 80))
        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(cr, qc.Qt.AlignCenter, "\u00d7")

        # Rotated name — black text, top→bottom (rotate -90°)
        painter.save()
        painter.setPen(qg.QColor(30, 30, 30))
        font = qg.QFont('Segoe UI', 9)
        font.setBold(self._current)
        painter.setFont(font)

        # Origin at top of text area (below X button)
        cx = r.center().x()
        painter.translate(cx, 22)
        painter.rotate(-90)
        # After rotation: X+ goes UP, Y+ goes RIGHT
        # We draw text going DOWN (negative X) across available height
        avail_h = float(r.height() - 28)
        text = self._name[:20]
        # Rect: spans from near-bottom to near-top of available space,
        # centered horizontally across tab width
        text_rect = qc.QRectF(-avail_h + 4, -14, avail_h - 8, 28)
        painter.drawText(text_rect, qc.Qt.AlignCenter, text)
        painter.restore()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._close_hover = False
        self.update()

    def mouseMoveEvent(self, event) -> None:
        over = self._is_over_close(event.pos())
        if over != self._close_hover:
            self._close_hover = over
            self.update()

    def mousePressEvent(self, event) -> None:
        if self._is_over_close(event.pos()):
            self.closeClicked.emit()
        else:
            self.clicked.emit()


class FlowTabBar(q.QScrollArea):
    """Vertical scrollable tab bar, max 10 tabs, with click-to-switch and drag reorder."""

    tabClicked = qc.pyqtSignal(int)   # switch to tab at index
    tabClosed = qc.pyqtSignal(int)    # close tab at index
    tabsReordered = qc.pyqtSignal()   # order changed

    MAX_TABS = 10

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(qc.Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(True)
        self.setFixedWidth(46)

        self._container = q.QWidget()
        self._layout = q.QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(3)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._tabs: list[FlowTab] = []
        self._current = -1
        self._drag_idx = -1

        self.setAcceptDrops(True)

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def count(self) -> int:
        return len(self._tabs)

    @property
    def names(self) -> list:
        return [t.name for t in self._tabs]

    def add_tab(self, name: str) -> int:
        if len(self._tabs) >= self.MAX_TABS:
            return -1
        idx = len(self._tabs)
        tab = FlowTab(name, idx)
        tab.clicked.connect(self._make_click_handler(idx))
        tab.closeClicked.connect(self._make_close_handler(idx))
        self._install_drag(tab, idx)
        self._layout.insertWidget(idx, tab)
        self._tabs.append(tab)
        if self._current == -1:
            self.set_current(idx)
        return idx

    def remove_tab(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._tabs):
            return
        tab = self._tabs.pop(idx)
        self._layout.removeWidget(tab)
        tab.deleteLater()
        # Re-index remaining tabs
        for i, t in enumerate(self._tabs):
            self._reindex_tab(t, i)
        # Adjust current
        if self._current >= len(self._tabs):
            self._current = len(self._tabs) - 1
        if self._current >= 0:
            self.set_current(self._current)

    def set_current(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._tabs):
            self._current = max(0, len(self._tabs) - 1) if self._tabs else -1
            idx = self._current
        self._current = idx
        for i, t in enumerate(self._tabs):
            t.set_current(i == idx)

    def update_name(self, idx: int, name: str) -> None:
        if 0 <= idx < len(self._tabs):
            self._tabs[idx].set_name(name)

    def _make_click_handler(self, idx: int):
        """Closure to capture idx; reconnected on reindex."""
        def handler():
            self.set_current(idx)
            self.tabClicked.emit(idx)
        return handler

    def _make_close_handler(self, idx: int):
        def handler():
            self.tabClosed.emit(idx)
        return handler

    def _reindex_tab(self, tab: FlowTab, new_idx: int) -> None:
        tab.index = new_idx
        try:
            tab.clicked.disconnect()
        except TypeError:
            pass
        try:
            tab.closeClicked.disconnect()
        except TypeError:
            pass
        tab.clicked.connect(self._make_click_handler(new_idx))
        tab.closeClicked.connect(self._make_close_handler(new_idx))
        self._install_drag(tab, new_idx)

    # ---- drag reorder -------------------------------------------------------

    def _install_drag(self, tab: FlowTab, idx: int) -> None:
        tab.mouseMoveEvent = lambda e, t=tab, i=idx: self._start_drag(e, t, i)

    def _start_drag(self, event, tab: FlowTab, idx: int) -> None:
        if event.buttons() != qc.Qt.LeftButton:
            return
        if tab._is_over_close(event.pos()):
            return
        self._drag_idx = idx
        drag = qg.QDrag(self)
        mime = qc.QMimeData()
        mime.setText(str(idx))
        drag.setMimeData(mime)
        drag.exec_(qc.Qt.MoveAction)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        src = int(event.mimeData().text())
        if src < 0 or src >= len(self._tabs):
            return
        # Find target position based on drop Y
        pos = event.pos()
        target = 0
        for i, t in enumerate(self._tabs):
            widget_y = t.mapToParent(qc.QPoint(0, 0)).y()
            if pos.y() > widget_y + t.height() / 2:
                target = i + 1
        # Adjust if inserting after source
        if target > src:
            target -= 1
        if target != src:
            tab = self._tabs.pop(src)
            self._tabs.insert(target, tab)
            # Re-layout
            for i in reversed(range(self._layout.count())):
                item = self._layout.itemAt(i)
                if item and item.widget():
                    self._layout.removeWidget(item.widget())
            for i, t in enumerate(self._tabs):
                self._reindex_tab(t, i)
                self._layout.insertWidget(i, t)
            self._current = target
            self.set_current(target)
            self.tabsReordered.emit()
        event.acceptProposedAction()
