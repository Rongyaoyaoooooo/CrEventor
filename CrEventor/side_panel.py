"""Left side panel — collapsible via N key. All content arranged vertically.

Sections (top to bottom):
  1. sbeventpack dependencies list
  2. gamedata flag card editor
"""

import typing

from PyQt5 import QtCore as qc
from PyQt5 import QtWidgets as q

from CrEventor.gamedata_editor import GamedataSection
from CrEventor.i18n import tr, Tr
from CrEventor.sbeventpack_analyzer import analyze_sbeventpack


class SidePanel(q.QDockWidget):
    """Left-docked panel with sbeventpack + gamedata sections."""

    PANEL_WIDTH = 840

    def __init__(self, parent=None) -> None:
        super().__init__(tr('side_panel.title'), parent)
        self.setAllowedAreas(qc.Qt.LeftDockWidgetArea | qc.Qt.RightDockWidgetArea)
        self.setFeatures(q.QDockWidget.DockWidgetClosable |
                         q.QDockWidget.DockWidgetMovable)
        self.setMinimumWidth(500)

        # Connect language change — update title and content labels
        Tr.instance.languageChanged.connect(self._update_texts)

        # Scrollable content
        scroll = q.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea { border: none; }')

        content = q.QWidget()
        layout = q.QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # ---- Section 1: sbeventpack ----
        self._sbep_title = q.QLabel(f'<b>{tr("side_panel.sbep_title")}</b>')
        layout.addWidget(self._sbep_title)

        self._sbep_intro = q.QLabel(tr('side_panel.sbep_intro'))
        self._sbep_intro.setWordWrap(True)
        layout.addWidget(self._sbep_intro)

        self._sbep_list = q.QListWidget()
        self._sbep_list.setAlternatingRowColors(True)
        self._sbep_list.setWordWrap(True)
        layout.addWidget(self._sbep_list)

        # ---- Separator ----
        line = q.QFrame()
        line.setFrameShape(q.QFrame.HLine)
        line.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(line)

        # ---- Section 2: gamedata ----
        self._gd_title = q.QLabel(f'<b>{tr("side_panel.gamedata_title")}</b>')
        layout.addWidget(self._gd_title)

        self._gamedata_section = GamedataSection()
        layout.addWidget(self._gamedata_section, 1)

        scroll.setWidget(content)
        self.setWidget(scroll)

        # State
        self._current_flow = None
        self._current_flow_name = ''
        self._gamedata_cache: typing.Dict[str, typing.Dict[str, dict]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        """Toggle panel visibility."""
        self.setVisible(not self.isVisible())

    def _update_texts(self, _lang: str = '') -> None:
        """Update all labels when language changes."""
        self.setWindowTitle(tr('side_panel.title'))
        self._sbep_title.setText(f'<b>{tr("side_panel.sbep_title")}</b>')
        self._sbep_intro.setText(tr('side_panel.sbep_intro'))
        self._gd_title.setText(f'<b>{tr("side_panel.gamedata_title")}</b>')
        # Rebuild sbep list to refresh "none" text
        if self._current_flow is not None:
            self.set_flow(self._current_flow_name, self._current_flow)

    def set_flow(self, flow_name: str, flow) -> None:
        """Update panel content for the given flow."""
        self._current_flow = flow
        self._current_flow_name = flow_name

        # sbeventpack
        self._sbep_list.clear()
        if flow:
            deps = analyze_sbeventpack(flow)
            if deps:
                for dep in deps:
                    self._sbep_list.addItem(dep)
            else:
                self._sbep_list.addItem(tr('side_panel.sbep_none'))

        # gamedata
        cached = self._gamedata_cache.get(flow_name, {})
        self._gamedata_section.flags = cached
        self._gamedata_section.set_flow(flow)

    def save_gamedata_cache(self, flow_name: str) -> None:
        """Save current gamedata state to cache."""
        self._gamedata_cache[flow_name] = dict(self._gamedata_section.flags)

    def load_gamedata_cache(self, flow_name: str) -> typing.Dict[str, dict]:
        """Return cached gamedata for a flow."""
        return self._gamedata_cache.get(flow_name, {})

    def load_all_gamedata_cache(self, data: dict) -> None:
        """Bulk-load gamedata cache from persistent storage."""
        self._gamedata_cache = data

    @property
    def gamedata_table(self):
        """Backward-compat alias for __main__.py."""
        return self._gamedata_section
