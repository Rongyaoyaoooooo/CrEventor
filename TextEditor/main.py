"""
TextEditor — BotW 文本编辑器主入口
独立于 EventEditor DX，可单独使用编辑 texts.json
"""

import importlib.util
import sys
import os

# ── WebEngine 前置初始化（必须在 QApplication 创建之前）──

# Qt DLL 修复
_spec = importlib.util.find_spec('PyQt5')
if _spec and _spec.origin:
    _qt_bin = os.path.join(os.path.dirname(_spec.origin), 'Qt5', 'bin')
    if os.path.isdir(_qt_bin):
        os.add_dll_directory(_qt_bin)

# WebEngine sandbox 关闭（否则加载本地 HTML 会崩溃）
os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'

# 添加主项目 venv 的 site-packages 到 path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_site_packages = os.path.join(_project_root, "venv", "Lib", "site-packages")
if os.path.isdir(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QMenuBar, QMenu, QAction, QFileDialog, QMessageBox,
    QStatusBar, QLabel, QApplication, QStyleFactory, QScrollArea,
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWebEngineWidgets import QWebEngineView  # 触发 QtWebEngine 初始化

from texts_loader import TextsLoader
from msbt_tree import MsbtTree
from web_message_editor import WebMessageEditor


class MainWindow(QMainWindow):
    """TextEditor 主窗口"""

    def __init__(self):
        super().__init__()
        self._loader = TextsLoader()
        self._settings = QSettings("BotWTools", "TextEditor")
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._restore_state()

    def _setup_ui(self):
        self.setWindowTitle("BotW Text Editor — 文本控件编辑器")
        self.setMinimumSize(1000, 650)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧：MSBT 树
        self._tree = MsbtTree()
        self._tree.entry_selected.connect(self._on_entry_selected)
        splitter.addWidget(self._tree)

        # 右侧：消息编辑器（必须先创建，pool_wrapper 引用它）
        self._editor = WebMessageEditor()
        self._editor.data_changed.connect(self._on_data_changed)
        self._editor.pool_toggle_requested.connect(self._on_toggle_pool)
        splitter.addWidget(self._editor)

        # 最左侧：选项池面板（嵌入背景，非独立浮窗）
        self._pool_wrapper = QWidget()
        pool_layout = QVBoxLayout(self._pool_wrapper)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        pool_layout.setSpacing(0)
        self._pool_label = QLabel("<b>选项池</b>")
        pool_layout.addWidget(self._pool_label)

        pool_scroll = QScrollArea()
        pool_scroll.setWidgetResizable(True)
        pool_scroll.setWidget(self._editor._option_pool)
        pool_layout.addWidget(pool_scroll, 1)

        self._pool_wrapper.setMinimumWidth(280)
        self._pool_wrapper.setVisible(False)
        splitter.insertWidget(0, self._pool_wrapper)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([0, 280, 720])
        layout.addWidget(splitter)

    def _setup_menu(self):
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("文件(&F)")

        open_action = QAction("打开 texts.json...(&O)", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("保存(&S)", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("另存为...(&A)", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 视图菜单
        view_menu = menu_bar.addMenu("视图(&V)")

        pool_action = QAction("选项池(&M)", self)
        pool_action.setShortcut(QKeySequence("Shift+M"))
        pool_action.triggered.connect(self._on_toggle_pool)
        view_menu.addAction(pool_action)

        self._show_pool_action = QAction("始终显示选项池", self)
        self._show_pool_action.setCheckable(True)
        view_menu.addAction(self._show_pool_action)

    def _setup_statusbar(self):
        self._status_label = QLabel("就绪 — 请打开 texts.json 文件")
        self.statusBar().addWidget(self._status_label, stretch=1)

    def _restore_state(self):
        """恢复上次的窗口大小和位置"""
        geometry = self._settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self._settings.value("window_state")
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        """关闭时询问保存 + 记录窗口状态"""
        if self._loader.is_dirty():
            reply = QMessageBox.question(
                self, "未保存的更改",
                "有未保存的更改，是否先保存再退出？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                if not self._do_save():
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())
        event.accept()

    # ── 事件处理 ──────────────────────────────────────

    def _on_open(self):
        """打开 texts.json 文件"""
        last_dir = self._settings.value("last_open_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 texts.json", last_dir,
            "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return

        try:
            self._loader.load(path)
            self._settings.setValue("last_open_dir", os.path.dirname(path))
            self._tree.set_loader(self._loader)
            self._editor.clear_context()
            self._status_label.setText(f"已加载: {path}  ({len(self._loader.get_msbt_paths())} 个 MSBT)")
            self.setWindowTitle(f"BotW Text Editor — {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法加载文件:\n{str(e)}")

    def _on_save(self):
        self._do_save()

    def _on_save_as(self):
        """另存为"""
        last_dir = self._settings.value("last_save_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为 texts.json", last_dir,
            "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            self._loader.save(path)
            self._settings.setValue("last_save_dir", os.path.dirname(path))
            self._status_label.setText(f"已保存到: {path}")
            self.setWindowTitle(f"BotW Text Editor — {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存文件:\n{str(e)}")

    def _do_save(self) -> bool:
        """执行保存（到当前路径或另存为），返回是否成功"""
        try:
            if self._loader._source_path:
                self._loader.save()
                self._status_label.setText(
                    f"已保存: {self._loader._source_path}"
                )
                return True
            else:
                self._on_save_as()
                return self._loader._source_path is not None
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存文件:\n{str(e)}")
            return False

    def _on_entry_selected(self, msbt_path: str, label: str):
        """树中选中了一条 entry"""
        self._editor.set_context(self._loader, msbt_path, label)

    def _on_data_changed(self):
        """数据变更后刷新树（不重新加载编辑器，避免破坏编辑状态）"""
        self._loader.mark_dirty()
        self._tree.rebuild()

    def _on_toggle_pool(self):
        """Shift+M / 按钮: 切换选项池面板"""
        if self._pool_wrapper.isVisible():
            self._pool_wrapper.setVisible(False)
        else:
            self._editor.refresh_pool_view()
            self._pool_wrapper.setVisible(True)
            # 给 pool 分配合理宽度
            parent = self._pool_wrapper.parent()
            if isinstance(parent, QSplitter):
                parent.setSizes([300, parent.sizes()[1], parent.sizes()[2]])


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setApplicationName("BotW Text Editor")
    app.setOrganizationName("BotWTools")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
