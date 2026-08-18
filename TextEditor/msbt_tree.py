"""
MSBT Tree — 左侧面板：按文件夹/文件层级展示所有 MSBT 条目
"""

from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from typing import Optional

from texts_loader import TextsLoader


# 自定义角色枚举（用于 QTreeWidgetItem 识别节点类型）
ROLE_TYPE = Qt.UserRole + 1
ROLE_PATH = Qt.UserRole + 2
ROLE_LABEL = Qt.UserRole + 3

TYPE_FOLDER = "folder"
TYPE_FILE = "file"
TYPE_ENTRY = "entry"
TYPE_POOL = "pool"      # 数字池 section header
TYPE_NAMED = "named"    # 具名消息 section header


class MsbtTree(QTreeWidget):
    """MSBT 文件树"""

    # 用户选中了某条具体的 entry（双击或单击后加载）
    entry_selected = pyqtSignal(str, str)  # (msbt_path, label)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: Optional[TextsLoader] = None
        self._setup_ui()
        self.itemClicked.connect(self._on_item_clicked)

    def _setup_ui(self):
        self.setHeaderLabel("MSBT 文件")
        self.setRootIsDecorated(True)
        self.setAnimated(True)
        self.setIndentation(16)
        self.setMinimumWidth(240)

    def set_loader(self, loader: TextsLoader):
        """绑定数据源并刷新树"""
        self._loader = loader
        self.rebuild()

    def rebuild(self):
        """完全重建树结构"""
        self.clear()
        if not self._loader:
            return

        paths = self._loader.get_msbt_paths()
        # 按文件夹分组
        folders: dict[str, list[str]] = {}
        for p in paths:
            if "/" in p:
                folder, filename = p.split("/", 1)
            else:
                folder, filename = "(无目录)", p
            folders.setdefault(folder, []).append(filename)

        for folder_name in sorted(folders):
            folder_item = QTreeWidgetItem(self)
            folder_item.setText(0, folder_name)
            folder_item.setData(0, ROLE_TYPE, TYPE_FOLDER)

            for filename in sorted(folders[folder_name]):
                msbt_path = f"{folder_name}/{filename}"
                file_item = QTreeWidgetItem(folder_item)
                file_item.setText(0, filename)
                file_item.setData(0, ROLE_TYPE, TYPE_FILE)
                file_item.setData(0, ROLE_PATH, msbt_path)

                # 数字池分组
                pool_keys = self._loader.get_pool_keys(msbt_path)
                named_keys = self._loader.get_named_keys(msbt_path)

                if pool_keys:
                    pool_header = QTreeWidgetItem(file_item)
                    pool_header.setText(0, f"▼ 选项按钮池 ({len(pool_keys)})")
                    pool_header.setData(0, ROLE_TYPE, TYPE_POOL)
                    pool_header.setData(0, ROLE_PATH, msbt_path)
                    pool_header.setForeground(0, Qt.gray)

                    for key in pool_keys:
                        entry_item = QTreeWidgetItem(pool_header)
                        entry_item.setText(0, key)
                        entry_item.setData(0, ROLE_TYPE, TYPE_ENTRY)
                        entry_item.setData(0, ROLE_PATH, msbt_path)
                        entry_item.setData(0, ROLE_LABEL, key)

                if named_keys:
                    named_header = QTreeWidgetItem(file_item)
                    named_header.setText(0, f"▼ 对话消息 ({len(named_keys)})")
                    named_header.setData(0, ROLE_TYPE, TYPE_NAMED)
                    named_header.setData(0, ROLE_PATH, msbt_path)
                    named_header.setForeground(0, Qt.gray)

                    for key in named_keys:
                        entry_item = QTreeWidgetItem(named_header)
                        entry_item.setText(0, key)
                        entry_item.setData(0, ROLE_TYPE, TYPE_ENTRY)
                        entry_item.setData(0, ROLE_PATH, msbt_path)
                        entry_item.setData(0, ROLE_LABEL, key)

        # 默认折叠所有文件夹
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setExpanded(False)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """点击条目时加载对应的 entry"""
        item_type = item.data(0, ROLE_TYPE)
        if item_type == TYPE_ENTRY:
            msbt_path = item.data(0, ROLE_PATH)
            label = item.data(0, ROLE_LABEL)
            if msbt_path and label:
                self.entry_selected.emit(msbt_path, label)

    def get_selected_info(self) -> Optional[tuple]:
        """获取当前选中的 (msbt_path, label)，未选中 entry 返回 None"""
        items = self.selectedItems()
        if not items:
            return None
        item = items[0]
        if item.data(0, ROLE_TYPE) != TYPE_ENTRY:
            return None
        return (item.data(0, ROLE_PATH), item.data(0, ROLE_LABEL))
