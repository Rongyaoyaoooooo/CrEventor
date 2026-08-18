"""EventEditor DX entry point — based on event-editor-master, with i18n support."""
import argparse
import gzip
import importlib.util
import json
import os
import re
import shutil
import signal
import sys
import traceback
import typing

# ---- Path setup: ensure the eventeditor package from event-editor-master is importable ----
_SRC_DIR = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ICON_PATH = os.path.join(_SRC_DIR, '新知识', 'Icon.png')
_LOGO_PATH = os.path.join(_SRC_DIR, '新知识', 'Logo.png')
_MASTER_DIR = os.path.join(_SRC_DIR, 'event-editor-master')
if os.path.isdir(_MASTER_DIR) and _MASTER_DIR not in sys.path:
    sys.path.insert(0, _MASTER_DIR)

# ---- Qt DLL directory fix for Chinese Windows usernames ----
_spec = importlib.util.find_spec('PyQt5')
if _spec and _spec.origin:
    _pyqt5_root = os.path.dirname(_spec.origin)
    _qt_bin_dir = os.path.join(_pyqt5_root, 'Qt5', 'bin')
    if os.path.isdir(_qt_bin_dir):
        os.add_dll_directory(_qt_bin_dir)

import PyQt5
_pyqt5_dir = os.path.dirname(PyQt5.__file__)
_qt_plugins_path = os.path.join(_pyqt5_dir, 'Qt5', 'plugins')
if os.path.isdir(_qt_plugins_path):
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(_qt_plugins_path, 'platforms')

import evfl
from evfl import EventFlow, Flowchart, Actor, Event, ActionEvent, SwitchEvent, ForkEvent, JoinEvent, SubFlowEvent
from evfl.common import RequiredIndex, StringHolder
from evfl.container import Container
from evfl.entry_point import EntryPoint
import eventeditor.ai as ai
import eventeditor.actor_json as aj
from eventeditor.actor_view import ActorView
from eventeditor.event_view import EventView
from eventeditor.flow_data import FlowData, FlowDataChangeReason
from eventeditor.flowchart_view import _get_message_id, _is_talk_event, _msg_id_to_msyt_path
from eventeditor.flow_serialize import validate_flow_dict, dict_to_flow, flow_to_dict
import eventeditor.util as util
import PyQt5.QtCore as qc  # type: ignore
import PyQt5.QtGui as qg  # type: ignore
import PyQt5.QtWidgets as q  # type: ignore

from CrEventor.i18n import Tr, tr, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE
from CrEventor.project_manager import ProjectManager, FLOW_SUBDIR
from CrEventor.flow_tab_bar import FlowTabBar
from CrEventor.side_panel import SidePanel
from CrEventor.option_pool_panel import OptionPoolPanel
from CrEventor import export_utils as export_util
from CrEventor import texts as game_texts
from CrEventor.text_database import TextDatabase
from CrEventor.flowchart_view import FlowchartView

# ---------------------------------------------------------------------------
# Application identity — separate from original EventEditor to avoid conflicts
# ---------------------------------------------------------------------------
ORG_NAME = 'EventEditorDX'
APP_NAME = 'EventEditorDX'


class FlowEntry:
    """Holds the state of a single open flow."""
    __slots__ = ('name', 'flow_path', 'unsaved', 'flow_data')

    def __init__(self) -> None:
        self.name: str = ''
        self.flow_path: str = ''
        self.unsaved: bool = False
        self.flow_data: FlowData = FlowData()

    @property
    def flow(self) -> typing.Optional[EventFlow]:
        return self.flow_data.flow


# ------------------------------------------------------------------
# Module-level helpers for option pool / GeneralChoice
# ------------------------------------------------------------------

_GC_PATTERN = re.compile(r'GeneralChoice(\d+)', re.IGNORECASE)


def _extract_choice_count(event: 'Event') -> typing.Optional[int]:
    """Extract option count from a GeneralChoice event.

    GeneralChoice nodes are primarily SwitchEvents whose query matches
    ``GeneralChoice{N}``.  Fallbacks: ActionEvents with a matching
    action name, and ForkEvents (branch count).
    """
    data = event.data
    if isinstance(data, SwitchEvent):
        try:
            query_name = str(data.actor_query.v)
            m = _GC_PATTERN.search(query_name)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    if isinstance(data, ActionEvent):
        try:
            action_name = str(data.actor_action.v)
            m = _GC_PATTERN.search(action_name)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    if isinstance(data, ForkEvent):
        try:
            return len(data.forks)
        except Exception:
            pass
    return None


def _find_all_parent_talk_msg_ids(flow: 'EventFlow', target: 'Event') -> typing.List[str]:
    """Find the nearest upstream MessageId on every path into *target*.

    Non-message events such as FlagOn are traversed backwards.  Each path
    stops at its nearest MessageId so older unrelated dialogues are ignored.
    """
    if not hasattr(flow, 'flowchart') or not flow.flowchart:
        return []

    events = list(flow.flowchart.events)

    def outgoing(event: 'Event') -> typing.List['Event']:
        data = event.data
        refs = []
        if isinstance(data, (ActionEvent, JoinEvent, SubFlowEvent)):
            refs.append(getattr(data, 'nxt', None))
        elif isinstance(data, SwitchEvent):
            refs.extend(data.cases.values())
        elif isinstance(data, ForkEvent):
            refs.extend(data.forks)
        result = []
        for ref in refs:
            value = getattr(ref, 'v', None)
            values = value if isinstance(value, list) else [value]
            result.extend(item for item in values if item is not None)
        return result

    predecessors: typing.Dict[int, typing.List['Event']] = {
        id(event): [] for event in events
    }
    for candidate in events:
        for successor in outgoing(candidate):
            if id(successor) in predecessors:
                predecessors[id(successor)].append(candidate)

    result: typing.List[str] = []
    seen_messages: typing.Set[str] = set()
    visited: typing.Set[int] = {id(target)}
    queue = list(predecessors.get(id(target), []))
    while queue:
        candidate = queue.pop(0)
        candidate_id = id(candidate)
        if candidate_id in visited:
            continue
        visited.add(candidate_id)

        data = candidate.data
        message_id = _msg_id_from_action(data) if isinstance(data, ActionEvent) else None
        if message_id and ':' in message_id:
            if message_id not in seen_messages:
                seen_messages.add(message_id)
                result.append(message_id)
            continue
        queue.extend(predecessors.get(candidate_id, []))
    return result


def _msg_id_from_action(data: 'ActionEvent') -> typing.Optional[str]:
    """Extract MessageId string from an ActionEvent's params."""
    try:
        params = data.params
        if params and params.data:
            msg_id = params.data.get('MessageId')
            return msg_id if msg_id else None
    except Exception:
        pass
    return None


class MainWindow(q.QMainWindow):
    def __init__(self, args) -> None:
        super().__init__()
        self.args = args
        self.project = ProjectManager()

        # Text database — loaded from built-in CNzh.json, shared across all flows
        self.text_database = TextDatabase()

        # Multi-flow workspace
        self._flows: typing.List[FlowEntry] = []
        self._current_idx: int = -1
        # Sentinel FlowData used when no flow is open (for init before first tab)
        self._sentinel_fd = FlowData()
        self._sentinel_fd.text_database = self.text_database

        # JSON auto-save timer (5 minutes)
        self.json_auto_save_timer = qc.QTimer(self)
        self.json_auto_save_timer.timeout.connect(self._onAutoSaveJson)

        # Left side panel (N key to toggle) — sbeventpack + gamedata editor
        self.side_panel = SidePanel(self)
        self.addDockWidget(qc.Qt.LeftDockWidgetArea, self.side_panel)
        self.side_panel.hide()

        # Option pool panel (M key to toggle) — option pool + generalchoice config
        self.option_pool_panel = OptionPoolPanel(self)
        self.option_pool_panel.set_text_database(self.text_database)
        self.addDockWidget(qc.Qt.LeftDockWidgetArea, self.option_pool_panel)
        self.option_pool_panel.hide()

        self.initMenu()
        self.initWidgets()
        self.initLayout()

        self.connectWidgets()
        self._connectI18n()  # 必须在 readSettings 之前，否则语言恢复信号无人接收
        self.centralWidget().setHidden(True)
        self.updateTitleAndActions()

        self.readSettings()

        if os.path.isfile(_ICON_PATH):
            self.setWindowIcon(qg.QIcon(_ICON_PATH))

    def show(self) -> None:
        self.showMaximized()
        if self.args.event_flow_file:
            self.readFlow(self.args.event_flow_file)

    # ------------------------------------------------------------------
    # Current-flow delegation (multi-flow workspace)
    # ------------------------------------------------------------------

    @property
    def _current_entry(self) -> typing.Optional[FlowEntry]:
        if 0 <= self._current_idx < len(self._flows):
            return self._flows[self._current_idx]
        return None

    @property
    def flow(self) -> typing.Optional[EventFlow]:
        e = self._current_entry
        return e.flow if e else None

    @property
    def flow_data(self) -> FlowData:
        e = self._current_entry
        return e.flow_data if e else self._sentinel_fd

    @property
    def flow_path(self) -> str:
        e = self._current_entry
        return e.flow_path if e else ''

    @flow_path.setter
    def flow_path(self, value: str) -> None:
        e = self._current_entry
        if e:
            e.flow_path = value

    @property
    def unsaved(self) -> bool:
        e = self._current_entry
        return e.unsaved if e else False

    @unsaved.setter
    def unsaved(self, value: bool) -> None:
        e = self._current_entry
        if e:
            e.unsaved = value

    # ------------------------------------------------------------------
    # I18n
    # ------------------------------------------------------------------

    def _connectI18n(self) -> None:
        Tr.instance.languageChanged.connect(self._onLanguageChanged)

    def _onLanguageChanged(self, lang: str) -> None:
        # Preserve checked states before menu rebuild
        visible_names = self.event_name_visible_action.isChecked()
        visible_params = self.event_param_visible_action.isChecked()
        visible_notes = self.notes_display_action.isChecked()
        auto_open = self.auto_open_project_action.isChecked()
        self.menuBar().clear()
        self.initMenu()
        self._connectActions()
        self.initLayout()
        self.updateTitleAndActions()
        # Restore checked states
        self.event_name_visible_action.setChecked(visible_names)
        self.event_param_visible_action.setChecked(visible_params)
        self.notes_display_action.setChecked(visible_notes)
        self.auto_open_project_action.setChecked(auto_open)

    def _makeLangAction(self, lang_code: str, lang_name: str) -> q.QAction:
        action = q.QAction(lang_name, self)
        action.setCheckable(True)
        action.setChecked(Tr.instance.language == lang_code)
        action.triggered.connect(lambda checked, code=lang_code: self._onLangAction(code))
        return action

    def _onLangAction(self, lang_code: str) -> None:
        Tr.instance.set_language(lang_code)
        settings = qc.QSettings()
        settings.setValue('app/language', lang_code)

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def initMenu(self) -> None:
        menu = self.menuBar()

        # ---- Project ----
        project_menu = menu.addMenu(tr('menu.project'))
        self.new_project_action = q.QAction(tr('menu.project.new'), self)
        self.new_project_action.setShortcut('Ctrl+Shift+N')
        self.new_project_action.triggered.connect(self.onNewProject)
        project_menu.addAction(self.new_project_action)
        self.open_project_action = q.QAction(tr('menu.project.open'), self)
        self.open_project_action.setShortcut('Ctrl+Shift+O')
        self.open_project_action.triggered.connect(self.onOpenProject)
        project_menu.addAction(self.open_project_action)
        project_menu.addSeparator()
        self.save_project_action = q.QAction(tr('menu.project.save_project'), self)
        self.save_project_action.setShortcut('Ctrl+S')
        self.save_project_action.setEnabled(False)
        self.save_project_action.triggered.connect(self._saveProject)
        project_menu.addAction(self.save_project_action)
        self.save_json_action = q.QAction(tr('menu.project.save_json'), self)
        self.save_json_action.setEnabled(False)
        self.save_json_action.triggered.connect(self.onSaveJson)
        project_menu.addAction(self.save_json_action)
        project_menu.addSeparator()
        self.restore_backup_action = q.QAction(tr('menu.project.restore_backup'), self)
        self.restore_backup_action.setEnabled(False)
        self.restore_backup_action.triggered.connect(self._onRestoreBackup)
        project_menu.addAction(self.restore_backup_action)

        # ---- File ----
        file_menu = menu.addMenu(tr('menu.file'))
        self.new_action = q.QAction(tr('menu.file.new'), self)
        self.new_action.setShortcut(qg.QKeySequence.New)
        self.new_action.setEnabled(False)
        self.new_action.triggered.connect(self.onNewFile)
        file_menu.addAction(self.new_action)
        self.open_action = q.QAction(tr('menu.file.open'), self)
        self.open_action.setShortcut(qg.QKeySequence.Open)
        self.open_action.setEnabled(False)
        self.open_action.triggered.connect(self.onOpenFile)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        self.open_autosave_action = q.QAction(tr('menu.file.open_autosave'), self)
        self.open_autosave_action.setEnabled(False)
        self.open_autosave_action.triggered.connect(lambda: self.onOpenFile(
            str(self.flow_data.auto_save.get_directory()),
            name_filter=f'Flowchart autosave (autosave_{self.flow_data.flow.name}_*.bfevfl.gz)',
        ))
        self.open_autosave_action.setVisible(False)
        file_menu.addAction(self.open_autosave_action)
        self.save_action = q.QAction(tr('menu.file.save'), self)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.onSaveFile)
        file_menu.addAction(self.save_action)
        self.save_as_action = q.QAction(tr('menu.file.save_as'), self)
        self.save_as_action.setShortcut('Ctrl+Shift+S')
        self.save_as_action.setEnabled(False)
        self.save_as_action.triggered.connect(self.onSaveAsFile)
        file_menu.addAction(self.save_as_action)
        self.rename_flow_action = q.QAction(tr('menu.file.rename_flow'), self)
        self.rename_flow_action.setEnabled(False)
        self.rename_flow_action.triggered.connect(self.renameFlow)
        file_menu.addAction(self.rename_flow_action)
        file_menu.addSeparator()
        self.exit_action = q.QAction(tr('menu.file.exit'), self)
        self.exit_action.setShortcut(qg.QKeySequence.Quit)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        # ---- Flowchart ----
        view_menu = menu.addMenu(tr('menu.flowchart'))
        self.event_name_visible_action = q.QAction(tr('menu.flowchart.show_event_names'), self)
        self.event_name_visible_action.setCheckable(True)
        self.event_name_visible_action.setChecked(False)
        self.event_name_visible_action.triggered.connect(self.onEventNameVisibilityChanged)
        view_menu.addAction(self.event_name_visible_action)
        self.event_param_visible_action = q.QAction(tr('menu.flowchart.show_event_params'), self)
        self.event_param_visible_action.setCheckable(True)
        self.event_param_visible_action.setChecked(False)
        self.event_param_visible_action.triggered.connect(self.onEventParamVisibilityChanged)
        view_menu.addAction(self.event_param_visible_action)
        self.notes_display_action = q.QAction(tr('menu.flowchart.show_notes'), self)
        self.notes_display_action.setCheckable(True)
        self.notes_display_action.setChecked(False)
        self.notes_display_action.triggered.connect(self.onNotesDisplayChanged)
        view_menu.addAction(self.notes_display_action)
        view_menu.addSeparator()
        self.reload_graph_action = q.QAction(tr('menu.flowchart.reload_graph'), self)
        self.reload_graph_action.setShortcut('Ctrl+Shift+R')
        self.reload_graph_action.setEnabled(False)
        view_menu.addAction(self.reload_graph_action)
        self.export_graph_action = q.QAction(tr('menu.flowchart.export_graph'), self)
        self.export_graph_action.setEnabled(False)
        view_menu.addAction(self.export_graph_action)
        self.import_graph_action = q.QAction(tr('menu.flowchart.import_graph'), self)
        self.import_graph_action.setEnabled(False)
        view_menu.addAction(self.import_graph_action)
        self.export_definitions_action = q.QAction(tr('menu.flowchart.export_definitions'), self)
        self.export_definitions_action.setEnabled(False)
        view_menu.addAction(self.export_definitions_action)
        self.reorder_event_parameters_action = q.QAction(tr('menu.flowchart.reorder_params'), self)
        self.reorder_event_parameters_action.setEnabled(False)
        view_menu.addAction(self.reorder_event_parameters_action)
        view_menu.addSeparator()
        self.add_event_action = q.QAction(tr('menu.flowchart.add_event'), self)
        self.add_event_action.setEnabled(False)
        view_menu.addAction(self.add_event_action)
        self.add_fork_action = q.QAction(tr('menu.flowchart.add_fork'), self)
        self.add_fork_action.setEnabled(False)
        view_menu.addAction(self.add_fork_action)

        # ---- Settings ----
        settings_menu = menu.addMenu(tr('menu.settings'))
        # Auto-open last project
        self.auto_open_project_action = q.QAction(tr('menu.settings.auto_open_project'), self)
        self.auto_open_project_action.setCheckable(True)
        self.auto_open_project_action.setChecked(False)
        settings_menu.addAction(self.auto_open_project_action)

        # Auto-load dialogue texts
        self.auto_load_text_action = q.QAction(tr('menu.settings.extract_texts'), self)
        self.auto_load_text_action.triggered.connect(self._extractTexts)
        settings_menu.addAction(self.auto_load_text_action)
        settings_menu.addSeparator()
        # Platform submenu
        platform_menu = settings_menu.addMenu(tr('menu.settings.platform'))
        self.platform_group = q.QActionGroup(self)
        self.platform_switch_action = q.QAction(tr('menu.settings.platform_switch'), self)
        self.platform_switch_action.setCheckable(True)
        self.platform_switch_action.setChecked(True)
        self.platform_switch_action.triggered.connect(
            lambda: self.onPlatformChanged('switch'))
        self.platform_group.addAction(self.platform_switch_action)
        platform_menu.addAction(self.platform_switch_action)
        self.platform_wiiu_action = q.QAction(tr('menu.settings.platform_wiiu'), self)
        self.platform_wiiu_action.setCheckable(True)
        self.platform_wiiu_action.triggered.connect(
            lambda: self.onPlatformChanged('wiiu'))
        self.platform_group.addAction(self.platform_wiiu_action)
        platform_menu.addAction(self.platform_wiiu_action)
        # Language submenu
        lang_menu = settings_menu.addMenu(tr('menu.settings.language'))
        self.language_group = q.QActionGroup(self)
        self._lang_actions: typing.Dict[str, q.QAction] = {}
        for code, name in SUPPORTED_LANGUAGES.items():
            action = self._makeLangAction(code, name)
            self.language_group.addAction(action)
            lang_menu.addAction(action)
            self._lang_actions[code] = action

        # Game text language submenu (14 BOTW languages)
        text_lang_menu = settings_menu.addMenu(tr('menu.settings.text_language'))
        self.text_lang_group = q.QActionGroup(self)
        self._text_lang_actions: typing.Dict[str, q.QAction] = {}
        for lang_code in game_texts.GAME_LANGUAGES:
            label = game_texts.GAME_LANGUAGE_NAMES.get(lang_code, lang_code)
            action = q.QAction(label, self)
            action.setCheckable(True)
            action.setChecked(lang_code == game_texts.DEFAULT_TEXT_LANGUAGE)
            action.triggered.connect(
                lambda checked, code=lang_code: self.onTextLanguageChanged(code))
            self.text_lang_group.addAction(action)
            text_lang_menu.addAction(action)
            self._text_lang_actions[lang_code] = action

        # ---- Help ----
        help_menu = menu.addMenu(tr('menu.help'))
        wiki_action = q.QAction(tr('menu.help.wiki'), self)
        wiki_action.triggered.connect(
            lambda: qg.QDesktopServices.openUrl(qc.QUrl('https://zeldamods.org')))
        help_menu.addAction(wiki_action)
        github_repo_action = q.QAction(tr('menu.help.github'), self)
        github_repo_action.triggered.connect(
            lambda: qg.QDesktopServices.openUrl(qc.QUrl('https://github.com/Rongyaoyaoooooo/CrEventor')))
        help_menu.addAction(github_repo_action)
        help_menu.addSeparator()
        about_action = q.QAction(tr('menu.help.about'), self)
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

    def about(self) -> None:
        msg = q.QMessageBox(self)
        msg.setWindowTitle(tr('app.about_title'))
        msg.setText(tr('app.about_text'))
        if os.path.isfile(_LOGO_PATH):
            msg.setIconPixmap(qg.QPixmap(_LOGO_PATH).scaledToWidth(256, qc.Qt.SmoothTransformation))
        msg.exec_()

    # ------------------------------------------------------------------
    # Widgets & Layout
    # ------------------------------------------------------------------

    def initWidgets(self) -> None:
        self.flow_tab_bar = FlowTabBar(self)

        self.tab_widget = q.QTabWidget(self)
        self.tab_widget.setTabPosition(q.QTabWidget.South)

        # FlowchartView needs a flow_data to init; use sentinel until first tab opens
        self.flowchart_view = FlowchartView(self, self._sentinel_fd)
        self.actor_view = ActorView(self, self._sentinel_fd)
        self.event_view = EventView(self, self._sentinel_fd)

    def initLayout(self) -> None:
        self.tab_widget.clear()
        self.tab_widget.addTab(self.flowchart_view, tr('tab.flowchart'))
        self.tab_widget.addTab(self.actor_view, tr('tab.actors'))
        self.tab_widget.addTab(self.event_view, tr('tab.events'))

        # Left: FlowTabBar | Right: tab_widget
        splitter = q.QSplitter()
        splitter.addWidget(self.flow_tab_bar)
        splitter.addWidget(self.tab_widget)
        splitter.setSizes([46, 800])
        self.setCentralWidget(splitter)

    def connectWidgets(self) -> None:
        self._fd_set_unsaved = lambda reason: setattr(self._current_entry, 'unsaved', True) if self._current_entry else None
        self._fd_update_actions = lambda reason: self.updateTitleAndActions()
        # Connect to sentinel initially; _switchToFlow will reconnect
        self._sentinel_fd.flowDataChanged.connect(self._fd_set_unsaved)
        self._sentinel_fd.flowDataChanged.connect(self._fd_update_actions)

        self.flowchart_view.readySignal.connect(self.onViewReady)
        self.flowchart_view.eventSelected.connect(self.onEventSelected)
        self.flowchart_view.graphEmptySpaceContextMenu.connect(self._onGraphEmptyContextMenu)

        self._connectActions()

        self.actor_view.detail_pane.jumpToEventsRequested.connect(self.onJumpToEventsRequested)
        self.actor_view.jumpToActorEventsRequested.connect(self.onJumpToEventsRequested)
        self.event_view.jumpToFlowchartRequested.connect(self.onJumpToFlowchartRequested)

        self.tab_widget.currentChanged.connect(self.onTabChanged)

        # FlowTabBar connections
        self.flow_tab_bar.tabClicked.connect(self._onTabSwitch)
        self.flow_tab_bar.tabClosed.connect(self._onTabClose)
        self.flow_tab_bar.tabsReordered.connect(self._onTabReorder)

        # N key toggles the left side panel
        self._side_panel_shortcut = q.QShortcut(qg.QKeySequence('N'), self)
        self._side_panel_shortcut.activated.connect(self._toggleSidePanel)

        # M key toggles the option pool panel
        self._option_pool_shortcut = q.QShortcut(qg.QKeySequence('M'), self)
        self._option_pool_shortcut.activated.connect(self._toggleOptionPoolPanel)

    def _onTabSwitch(self, idx: int) -> None:
        """User clicked a different flow tab."""
        if idx == self._current_idx:
            return
        self._switchToFlow(idx)

    def _onTabClose(self, idx: int) -> None:
        """User clicked X on a flow tab."""
        if idx < 0 or idx >= len(self._flows):
            return
        entry = self._flows[idx]
        name = entry.name or tr('app.untitled')
        reply = q.QMessageBox.question(
            self, tr('flow_tab.close_title'),
            tr('flow_tab.close_text', name=name),
            q.QMessageBox.Yes | q.QMessageBox.No,
        )
        if reply != q.QMessageBox.Yes:
            return
        # Auto-backup BEFORE removal (so the flow being deleted is included)
        self._autoBackup()
        # Disconnect signals BEFORE removing
        if idx == self._current_idx:
            try:
                entry.flow_data.flowDataChanged.disconnect(self._fd_set_unsaved)
            except TypeError:
                pass
            try:
                entry.flow_data.flowDataChanged.disconnect(self._fd_update_actions)
            except TypeError:
                pass
        # Remove
        self._flows.pop(idx)
        self.flow_tab_bar.remove_tab(idx)
        # Adjust current
        if self._current_idx >= len(self._flows):
            self._current_idx = len(self._flows) - 1
        if self._current_idx >= 0:
            self._switchToFlow(self._current_idx, skip_disconnect=True)
        else:
            self._current_idx = -1
            self._stopAutoSaveTimer()
            self.flowchart_view.setFlowData(self._sentinel_fd)
            self.actor_view.setFlowData(self._sentinel_fd)
            self.event_view.setFlowData(self._sentinel_fd)
            self.updateTitleAndActions()

    def _closeAllTabs(self) -> None:
        """Close all open flow tabs without prompting."""
        while self._flows:
            entry = self._flows[-1]
            if len(self._flows) - 1 == self._current_idx:
                try:
                    entry.flow_data.flowDataChanged.disconnect(self._fd_set_unsaved)
                except TypeError:
                    pass
                try:
                    entry.flow_data.flowDataChanged.disconnect(self._fd_update_actions)
                except TypeError:
                    pass
            self._flows.pop()
            self.flow_tab_bar.remove_tab(len(self._flows))
        self._current_idx = -1
        self._stopAutoSaveTimer()
        self.flowchart_view.setFlowData(self._sentinel_fd)
        self.actor_view.setFlowData(self._sentinel_fd)
        self.event_view.setFlowData(self._sentinel_fd)
        self.updateTitleAndActions()

    def _onTabReorder(self) -> None:
        """Tabs were reordered via drag-drop."""
        # Rebuild _flows order to match tab bar order
        tab_names = self.flow_tab_bar.names
        name_to_entry = {e.name: e for e in self._flows}
        new_order = []
        for name in tab_names:
            if name in name_to_entry:
                new_order.append(name_to_entry[name])
        self._flows = new_order
        self._current_idx = self.flow_tab_bar.current_index

    def _switchToFlow(self, idx: int, skip_disconnect: bool = False) -> None:
        """Switch the UI to display the flow at the given index."""
        if idx < 0 or idx >= len(self._flows):
            return
        old_entry = self._current_entry
        self._current_idx = idx
        new_entry = self._flows[idx]
        # Reconnect flow_data signals in MainWindow
        if old_entry and not skip_disconnect:
            try:
                old_entry.flow_data.flowDataChanged.disconnect(self._fd_set_unsaved)
            except TypeError:
                pass
            try:
                old_entry.flow_data.flowDataChanged.disconnect(self._fd_update_actions)
            except TypeError:
                pass
        new_entry.flow_data.flowDataChanged.connect(self._fd_set_unsaved)
        new_entry.flow_data.flowDataChanged.connect(self._fd_update_actions)
        # Switch FlowchartView
        self.flowchart_view.setFlowData(new_entry.flow_data)
        # Switch Actor / Event views
        self.actor_view.setFlowData(new_entry.flow_data)
        self.event_view.setFlowData(new_entry.flow_data)
        # Sync notes display state
        new_entry.flow_data.set_notes_display(self.notes_display_action.isChecked())
        self.flow_tab_bar.set_current(idx)
        self.updateTitleAndActions()
        # Refresh side panel for the new flow
        self._updateSidePanel()

        # Update option pool panel for the new flow
        self._updateOptionPoolOnFlowSwitch()

    def _updateOptionPoolOnFlowSwitch(self) -> None:
        """Keep the option pool panel in sync with the current flow."""
        panel = self.option_pool_panel
        if not panel.isVisible():
            return
        flow = self.flow
        if not flow:
            return
        msyt_path = self._find_flow_msyt_path(flow)
        if msyt_path:
            panel.set_context(msyt_path, '', [])
        else:
            panel.set_context('', '', [])

    def _updateSidePanel(self) -> None:
        """Update the side panel for the current flow. Safe wrap."""
        try:
            for entry in self._flows:
                if entry.name:
                    self.side_panel.save_gamedata_cache(entry.name)
            entry = self._current_entry
            if entry and entry.flow:
                self.side_panel.set_flow(entry.name, entry.flow)
        except Exception:
            traceback.print_exc()

    def _connectActions(self) -> None:
        """Connect flowchart menu actions. Re-called on language change (actions are recreated)."""
        self.reload_graph_action.triggered.connect(self.flowchart_view.reload)
        self.export_graph_action.triggered.connect(self.flowchart_view.export)
        self.import_graph_action.triggered.connect(self.onImportGraph)
        self.export_definitions_action.triggered.connect(self.flowchart_view.export_definitions)
        self.reorder_event_parameters_action.triggered.connect(self.flowchart_view.reorder_event_parameters)
        self.add_event_action.triggered.connect(self.flowchart_view.addNewEvent)
        self.add_fork_action.triggered.connect(self.flowchart_view.addFork)

    # ------------------------------------------------------------------
    # Close / Settings persistence
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        # Only show save prompt when there are flows with actual content
        # and a project is open. We no longer rely solely on the 'unsaved'
        # flag because signal disconnection / reconnection across multi-flow
        # switching can cause it to miss updates.
        flows_with_content = [
            e for e in self._flows
            if e.flow and e.flow.flowchart and e.flow.flowchart.events
        ]
        if not flows_with_content or not self.project.is_open:
            self._stopAutoSaveTimer()
            event.accept()
            self.writeSettings()
            return

        msg_box = q.QMessageBox(self)
        msg_box.setWindowTitle(tr('project.save.title'))
        msg_box.setText(tr('project.save.close_text', count=len(flows_with_content)))
        btn_save = msg_box.addButton(tr('project.save.save'), q.QMessageBox.YesRole)
        btn_no = msg_box.addButton(tr('project.save.no_save'), q.QMessageBox.NoRole)
        btn_cancel = msg_box.addButton(tr('project.save.cancel'), q.QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_save)
        msg_box.exec_()

        if msg_box.clickedButton() == btn_save:
            self._saveProject()
            self._stopAutoSaveTimer()
            self.writeSettings()
            event.accept()
        elif msg_box.clickedButton() == btn_cancel:
            event.ignore()
        else:
            self._stopAutoSaveTimer()
            self.writeSettings()
            event.accept()

    def readSettings(self) -> None:
        settings = qc.QSettings()
        ai.set_rom_path(settings.value('paths/rom_root'))
        aj.set_actor_definitions_path(settings.value('paths/actor_definitions_root'))

        # Restore language
        lang = settings.value('app/language', DEFAULT_LANGUAGE)
        if lang in SUPPORTED_LANGUAGES:
            Tr.instance.set_language(lang)

        # Restore platform
        platform = settings.value('project/platform', 'switch')
        self.project.set_platform(platform)
        self.platform_switch_action.setChecked(platform == 'switch')
        self.platform_wiiu_action.setChecked(platform == 'wiiu')

        # Restore game text language
        text_lang = settings.value('settings/text_language', game_texts.DEFAULT_TEXT_LANGUAGE)
        if text_lang in game_texts.GAME_LANGUAGES:
            if text_lang in self._text_lang_actions:
                self._text_lang_actions[text_lang].setChecked(True)

        settings.beginGroup('MainWindow')
        self.resize(settings.value('size', qc.QSize(800, 600)))
        self.move(settings.value('pos', qc.QPoint(200, 200)))
        settings.endGroup()

        settings.beginGroup('flowchart')
        self.event_name_visible_action.setChecked(settings.value('visible_names', False, type=bool))
        self.event_param_visible_action.setChecked(settings.value('visible_params', False, type=bool))
        visible_notes = settings.value('visible_notes', False, type=bool)
        self.notes_display_action.setChecked(visible_notes)
        self.flow_data.set_notes_display(visible_notes)
        settings.endGroup()

        # Restore auto-open preference
        auto_open = settings.value('project/auto_open', False, type=bool)
        self.auto_open_project_action.setChecked(auto_open)

        # Restore auto-load texts preference
        # Restore last project (auto-open)
        if auto_open:
            last_path = settings.value('project/last_path', '')
            if last_path and os.path.isdir(last_path) and os.path.isfile(os.path.join(last_path, 'project.json')):
                self._doOpenProject(last_path)

        # Load extracted texts at startup (if available)
        self._loadTextDatabase()

    def writeSettings(self) -> None:
        settings = qc.QSettings()
        settings.beginGroup('MainWindow')
        settings.setValue('size', self.size())
        settings.setValue('pos', self.pos())
        settings.endGroup()

        settings.beginGroup('flowchart')
        settings.setValue('visible_names', self.event_name_visible_action.isChecked())
        settings.setValue('visible_params', self.event_param_visible_action.isChecked())
        settings.setValue('visible_notes', self.notes_display_action.isChecked())
        settings.endGroup()

        settings.setValue('app/language', Tr.instance.language)
        settings.setValue('project/auto_open', self.auto_open_project_action.isChecked())

        if aj._actor_definitions_path:
            settings.beginGroup('paths')
            settings.setValue('actor_definitions_root', str(aj._actor_definitions_path))
            settings.endGroup()

    # ------------------------------------------------------------------
    # Title & actions
    # ------------------------------------------------------------------

    def updateTitleAndActions(self) -> None:
        project_open = self.project.is_open
        if project_open:
            proj_name = self.project.project_name
            if self.flow:
                title = f'{proj_name} \u2014 {self.flow.name} - CrEventor'
            else:
                title = f'{proj_name} - CrEventor'
        else:
            title = tr('app.title')
        self.setWindowTitle(title)

        has_flow = bool(self.flow)
        has_path = bool(self.flow_path)

        # Project actions
        self.save_project_action.setEnabled(project_open and has_flow)
        self.save_json_action.setEnabled(project_open and has_flow)
        self.restore_backup_action.setEnabled(project_open)

        # File actions — require project
        self.new_action.setEnabled(project_open)
        self.open_action.setEnabled(project_open)
        self.open_autosave_action.setEnabled(project_open and has_flow and has_path)
        self.save_action.setEnabled(project_open and has_flow and has_path)
        self.save_as_action.setEnabled(project_open and has_flow)
        self.rename_flow_action.setEnabled(project_open and has_flow and has_path)

        # Flowchart actions — require project
        self.reload_graph_action.setEnabled(project_open and has_flow and has_path)
        self.export_graph_action.setEnabled(project_open and has_flow)
        self.import_graph_action.setEnabled(project_open)
        self.export_definitions_action.setEnabled(project_open and has_flow)
        self.reorder_event_parameters_action.setEnabled(project_open and has_flow)
        self.add_event_action.setEnabled(project_open and has_flow and has_path)
        self.add_fork_action.setEnabled(project_open and has_flow and has_path)

        # Platform actions — always available
        self.platform_switch_action.setChecked(self.project.platform == 'switch')
        self.platform_wiiu_action.setChecked(self.project.platform == 'wiiu')

    # ------------------------------------------------------------------
    # Project operations
    # ------------------------------------------------------------------

    def onNewProject(self) -> None:
        if self._flows and self.project.is_open:
            msg_box = q.QMessageBox(self)
            msg_box.setWindowTitle(tr('project.save.title'))
            msg_box.setText(tr('project.save.close_text', count=len(self._flows)))
            btn_save = msg_box.addButton(tr('project.save.save'), q.QMessageBox.YesRole)
            btn_no = msg_box.addButton(tr('project.save.no_save'), q.QMessageBox.NoRole)
            btn_cancel = msg_box.addButton(tr('project.save.cancel'), q.QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_save)
            msg_box.exec_()
            if msg_box.clickedButton() == btn_cancel:
                return
            if msg_box.clickedButton() == btn_save:
                self._saveProject()

        self._stopAutoSaveTimer()
        path = q.QFileDialog.getExistingDirectory(
            self, tr('project.new.dialog_title'))
        if not path:
            return

        # project.json already exists → ask to open
        if os.path.isfile(os.path.join(path, 'project.json')):
            reply = q.QMessageBox.question(
                self, tr('project.new.exists_title'),
                tr('project.new.exists_text', path=path),
                q.QMessageBox.Yes | q.QMessageBox.No,
            )
            if reply == q.QMessageBox.Yes:
                self._doOpenProject(path)
            return

        if not self.project.create(path, self.project.platform):
            q.QMessageBox.critical(self, tr('project.new.create_failed'),
                                   tr('project.new.create_failed_text', path=path))
            return
        self._onProjectOpened()

    def onOpenProject(self) -> None:
        if self._flows and self.project.is_open:
            msg_box = q.QMessageBox(self)
            msg_box.setWindowTitle(tr('project.save.title'))
            msg_box.setText(tr('project.save.close_text', count=len(self._flows)))
            btn_save = msg_box.addButton(tr('project.save.save'), q.QMessageBox.YesRole)
            btn_no = msg_box.addButton(tr('project.save.no_save'), q.QMessageBox.NoRole)
            btn_cancel = msg_box.addButton(tr('project.save.cancel'), q.QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_save)
            msg_box.exec_()
            if msg_box.clickedButton() == btn_cancel:
                return
            if msg_box.clickedButton() == btn_save:
                self._saveProject()

        self._stopAutoSaveTimer()
        path = q.QFileDialog.getExistingDirectory(
            self, tr('project.open.dialog_title'))
        if not path:
            return
        if not self.project.open(path):
            q.QMessageBox.critical(self, tr('project.open.invalid'),
                                   tr('project.open.invalid_text', path=path))
            return
        self._onProjectOpened()

    def _doOpenProject(self, path: str) -> None:
        if not self.project.open(path):
            q.QMessageBox.critical(self, tr('project.open.invalid'),
                                   tr('project.open.invalid_text', path=path))
            return
        self._onProjectOpened()

    def _onProjectOpened(self) -> None:
        # ---- Clear existing workspace ----
        self._closeAllTabs()

        self.updateTitleAndActions()
        # Save project path for next session
        settings = qc.QSettings()
        settings.setValue('project/last_path', self.project.project_dir)

        # ── Load ONLY from Original Json backups ────────────────────
        # Mod/Event/ is an output directory — never used for restoration.
        # Find latest manual backup folder (non-Auto*), load all flows.
        oj = self.project.original_json_path
        if not os.path.isdir(oj):
            return

        backup_folders = [
            d for d in os.listdir(oj)
            if os.path.isdir(os.path.join(oj, d)) and not d.startswith('Auto')
        ]
        if not backup_folders:
            return
        backup_folders.sort(reverse=True)  # datetime-named, newest first
        latest_folder = backup_folders[0]

        flow_files = self.project.get_flow_files_in_folder(latest_folder)
        if not flow_files:
            return

        for fpath in flow_files:
            try:
                self.readFlow(fpath)
            except Exception:
                traceback.print_exc()

        # Load built-in texts after project flow files are loaded
        self._loadTextDatabase()

    def _json_to_eventflow(self, data: dict) -> typing.Optional[EventFlow]:
        """Convert a validated JSON dict to an EventFlow via the canonical
        flow_serialize.dict_to_flow() — supports both raw Format A and
        flow_meta-wrapped Format A."""
        flow = None
        if isinstance(data, dict):
            flow_meta = data.get('flow_meta')
            if flow_meta:
                flow = dict_to_flow(flow_meta)
            elif 'actors' in data or 'events' in data or 'entry_points' in data:
                flow = dict_to_flow(data)
        # If dict_to_flow returned None (unexpected), fall back to graph
        # reconstruction as a last resort.
        if flow is None:
            flow = self._rebuild_flow_from_json(data)
        return flow

    def onPlatformChanged(self, platform: str) -> None:
        self.project.set_platform(platform)
        settings = qc.QSettings()
        settings.setValue('project/platform', platform)
        self.updateTitleAndActions()
        self._loadTextDatabase()

    def onTextLanguageChanged(self, lang_code: str) -> None:
        """Handle game text language selection change."""
        settings = qc.QSettings()
        settings.setValue('settings/text_language', lang_code)
        # Update checked state for all text language actions
        for code, action in self._text_lang_actions.items():
            action.setChecked(code == lang_code)
        self._loadTextDatabase()

    def _text_language_code(self) -> str:
        """Return the current game text language code (e.g. 'CNzh', 'JPja')."""
        settings = qc.QSettings()
        return settings.value('settings/text_language', game_texts.DEFAULT_TEXT_LANGUAGE)

    def _flow_msyt_paths(self, flow: 'eventeditor.event.flow.EventFlow') -> typing.Set[str]:
        """Collect all unique .msyt paths referenced by events in *flow*."""
        msyts: typing.Set[str] = set()
        if not flow.flowchart:
            return msyts
        for event in flow.flowchart.events:
            if not _is_talk_event(event):
                continue
            msg_id = _get_message_id(event)
            if not msg_id:
                continue
            msyt = _msg_id_to_msyt_path(msg_id)
            if msyt:
                msyts.add(msyt)
        return msyts

    def _syncTextAttributesFromEvents(self) -> None:
        """Make every referenced text entry carry its Talk Event actor name."""
        for flow_entry in self._flows:
            flow = flow_entry.flow
            if not flow or not flow.flowchart:
                continue
            for event in flow.flowchart.events:
                if not _is_talk_event(event):
                    continue
                message_id = _get_message_id(event)
                if not message_id:
                    continue
                try:
                    actor_name = str(event.data.actor.v.identifier.name or '')
                except (AttributeError, TypeError):
                    actor_name = ''
                self.text_database.update_attributes_by_message_id(
                    message_id, actor_name,
                )

    def _saveCurrentTexts(self) -> None:
        """Persist current text database state back to Texts/ per-flow files."""
        if not self.project.is_open:
            return
        self._syncTextAttributesFromEvents()
        language = self._text_language_code()
        texts_dir = os.path.join(self.project.project_dir, 'Texts')
        os.makedirs(texts_dir, exist_ok=True)
        for flow_entry in self._flows:
            if not flow_entry.flow:
                continue
            flow_name = flow_entry.name or 'Untitled'
            msyts = self._flow_msyt_paths(flow_entry.flow)
            if not msyts:
                continue
            data = self.text_database.save_for_flow(msyts, language)
            if not data.get(language):
                continue
            path = os.path.join(texts_dir, f'{flow_name}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_latest_backup_dir(self) -> str:
        """Return the path to the latest non-Auto backup folder."""
        oj = self.project.original_json_path
        if not os.path.isdir(oj):
            return ''
        backup_folders = [
            d for d in os.listdir(oj)
            if os.path.isdir(os.path.join(oj, d)) and not d.startswith('Auto')
        ]
        if not backup_folders:
            return ''
        backup_folders.sort(reverse=True)
        return os.path.join(oj, backup_folders[0])

    def _loadTextDatabase(self) -> None:
        """Load text database with the correct overlay order.

        Loading order:
          1. Texts/ — extracted original texts (read-only baseline).
             Only overwritten by the explicit "extract texts" operation.
          2. Original Json/{latest}/ — backup with user modifications
             (pool entries, choice controls, edited texts) merged on top.
        """
        if not self.project.is_open:
            return

        language = self._text_language_code()

        # Step 1 — load extracted originals from Texts/ as baseline
        texts_dir = os.path.join(self.project.project_dir, 'Texts')
        base_count = self.text_database.load_extracted(texts_dir, language,
                                                        clear_first=True)
        if base_count:
            print(f'[Texts] Loaded {base_count} baseline entries from Texts/')

        # Step 2 — merge user modifications from latest backup on top
        backup_dir = self._get_latest_backup_dir()
        if backup_dir:
            merged = self.text_database.merge_backup_dir(backup_dir, language)
            if merged:
                print(f'[Texts] Merged {merged} modified entries from {backup_dir}')

        # Notify all open flows
        for entry in self._flows:
            if entry.flow_data.text_database is self.text_database:
                entry.flow_data.dialogueDataChanged.emit()

    def _extractTexts(self) -> None:
        """Manually extract texts: scan all flows → load full MSBT from built-in
        → save per-flow extracted files to Texts/."""
        if not self.project.is_open:
            q.QMessageBox.warning(self, tr('dialogue.title'),
                                  'Please open a project first.')
            return
        platform = self.project.platform
        language = self._text_language_code()

        # Scan all flows for MessageIds → collect unique MSYT paths per flow
        flow_msyts: typing.Dict[str, typing.Set[str]] = {}
        all_msyts: typing.Set[str] = set()
        for flow_entry in self._flows:
            if not flow_entry.flow:
                continue
            flow_name = flow_entry.name or 'Untitled'
            msyts = self._flow_msyt_paths(flow_entry.flow)
            if msyts:
                flow_msyts[flow_name] = msyts
                all_msyts.update(msyts)

        if not all_msyts:
            q.QMessageBox.information(self, tr('dialogue.title'),
                                      'No MessageId references found in open flows.')
            return

        # Extract all referenced MSYTs from built-in
        count = self.text_database.extract_from_builtin(all_msyts, platform, language)
        if not count:
            q.QMessageBox.warning(self, tr('dialogue.title'),
                                  f'Failed to extract any text entries.')
            return

        self._syncTextAttributesFromEvents()

        # Save per-flow extracted files to Texts/
        texts_dir = os.path.join(self.project.project_dir, 'Texts')
        os.makedirs(texts_dir, exist_ok=True)
        for flow_name, msyts in flow_msyts.items():
            data = self.text_database.save_for_flow(msyts, language)
            data_clean = data.get(language, {})
            if not data_clean:
                continue
            path = os.path.join(texts_dir, f'{flow_name}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        # Notify all flows
        for entry in self._flows:
            if entry.flow_data.text_database is self.text_database:
                entry.flow_data.dialogueDataChanged.emit()

        q.QMessageBox.information(
            self, tr('dialogue.title'),
            f'Extracted {count} entries across {len(flow_msyts)} flow(s).\n'
            f'Saved to Texts/ folder.'
        )

    # ------------------------------------------------------------------
    # JSON backup / auto-save
    # ------------------------------------------------------------------

    def _startAutoSaveTimer(self) -> None:
        self.json_auto_save_timer.start(5 * 60 * 1000)  # 5 minutes

    def _stopAutoSaveTimer(self) -> None:
        self.json_auto_save_timer.stop()

    def _onAutoSaveJson(self) -> None:
        if not self.project.is_open:
            return
        for entry in self._flows:
            if not entry.flow:
                continue
            data_dict = flow_to_dict(entry.flow)
            name = entry.name or 'Untitled'
            path = self.project.save_json_auto(data_dict, name)
            if path:
                print(f'[AutoSave JSON] {path}')

        # Auto-export modified texts to logs/ so backup stays current
        self._exportTextsToLogs()

    def onSaveJson(self) -> None:
        """Manual JSON save with folder-name dialog (current flow only)."""
        if not self.project.is_open or not self.flow:
            return
        data = flow_to_dict(self.flow)
        flow_name = self.flow.name if self.flow else 'Untitled'
        default_name = self.project._now_str()
        folder_name, ok = q.QInputDialog.getText(
            self, tr('project.save_json.title'),
            tr('project.save_json.prompt'),
            q.QLineEdit.Normal, default_name)
        if not ok or not folder_name:
            return
        path = self.project.save_original_json_as(data, flow_name, folder_name)
        if path:
            q.QMessageBox.information(
                self, tr('project.save_json.saved'),
                tr('project.save_json.saved_text', path=path))

    def _saveProject(self) -> None:
        """Save ALL flows to Mod + force JSON save for each."""
        if not self.project.is_open:
            return
        # Clean old .bfevfl files from Mod/Event/ that aren't in current workspace
        keep_names = [e.name for e in self._flows if e.name]
        self.project.clean_mod_event(keep_names)

        # Ask user for backup folder name
        default_name = self.project._now_str()
        folder_name, ok = q.QInputDialog.getText(
            self, tr('project.save_json.title'),
            tr('project.save_json.prompt'),
            q.QLineEdit.Normal, default_name)
        if not ok or not folder_name:
            folder_name = default_name

        saved = 0
        for entry in self._flows:
            if not entry.flow:
                continue
            flow_name = entry.name or 'Untitled'
            if entry.flow_path:
                self.project.save_event_flow_to_mod(entry.flow_path)
            else:
                self.project.save_flow_to_mod(entry.flow, flow_name)
            # Save full EventFlow JSON (Format A) to backup folder
            data_dict = flow_to_dict(entry.flow)
            path = self.project.save_original_json_as(data_dict, flow_name, folder_name)
            # Also save .bfevfl in the same backup folder (flows/ subfolder)
            bfevfl_backup_folder = os.path.join(
                self.project.original_json_path, folder_name, FLOW_SUBDIR)
            os.makedirs(bfevfl_backup_folder, exist_ok=True)
            try:
                util.write_flow(os.path.join(bfevfl_backup_folder, f'{flow_name}.bfevfl'), entry.flow)
            except Exception:
                pass
            if path:
                saved += 1

        # Export eventinfo / gamedata / savedata to logs/
        if saved and self.project.is_open:
            self._exportToLogs(folder_name)

        # Save gamedata cache alongside backup for future restore
        if saved:
            self._saveGamedataToBackup(folder_name)
            self._saveTextsBackup(folder_name)

        if saved:
            q.QMessageBox.information(
                self, tr('project.save.title'),
                tr('project.save.saved_text', count=saved))

    def _exportTextsToLogs(self) -> None:
        """Export complete MSBT files (with modifications) to logs/texts.json."""
        if not self.project.is_open:
            return
        self._syncTextAttributesFromEvents()
        lang = self._text_language_code()
        merged = self.text_database.export_merged(lang)
        if not merged:
            return
        logs_dir = self.project.logs_path
        os.makedirs(logs_dir, exist_ok=True)
        path = os.path.join(logs_dir, 'texts.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    def _exportToLogs(self, folder_name: str = '') -> None:
        """Generate gamedata.yml, savedata.yml, eventinfo.yml, texts_*.json in logs/.
        Merges all open flows into single output files."""
        logs_dir = os.path.join(self.project.project_dir, 'logs')
        os.makedirs(logs_dir, exist_ok=True)

        # Collect all gamedata from side panel cache (merged across all flows)
        all_gamedata: dict = {}
        all_flows: list = []
        for entry in self._flows:
            if not entry.flow:
                continue
            flow_name = entry.name or 'Untitled'
            gd = self.side_panel.load_gamedata_cache(flow_name)
            all_gamedata.update(gd)
            all_flows.append((flow_name, entry.flow))

        # Write logs/gamedata.yml
        with open(os.path.join(logs_dir, 'gamedata.yml'), 'w', encoding='utf-8') as f:
            f.write(export_util.generate_gamedata_yml(all_gamedata))

        # Write logs/savedata.yml (IsSave:true subset)
        with open(os.path.join(logs_dir, 'savedata.yml'), 'w', encoding='utf-8') as f:
            f.write(export_util.generate_savedata_yml(all_gamedata))

        # Write logs/eventinfo.yml (merged across all flows)
        with open(os.path.join(logs_dir, 'eventinfo.yml'), 'w', encoding='utf-8') as f:
            f.write(export_util.generate_eventinfo_yml(all_flows))

        # Text backup (modified entries → logs/texts_{lang}.json)
        self._exportTextsToLogs()

    def _saveGamedataToBackup(self, folder_name: str) -> None:
        """Save gamedata per-flow flag settings as JSON in the backup folder."""
        backup_dir = os.path.join(self.project.original_json_path, folder_name)
        os.makedirs(backup_dir, exist_ok=True)

        all_cache: dict = {}
        for entry in self._flows:
            if not entry.flow:
                continue
            flow_name = entry.name or 'Untitled'
            # Get current table data from side panel
            self.side_panel.save_gamedata_cache(flow_name)
            # Also collect all cache for a merged dump
            gd = self.side_panel.load_gamedata_cache(flow_name)
            all_cache[flow_name] = gd

        # Save per-flow gamedata JSON
        if all_cache:
            all_path = os.path.join(backup_dir, '_gamedata_cache.json')
            export_util.save_gamedata_to_json(all_cache, all_path)

    def _saveTextsBackup(self, folder_name: str) -> None:
        """Save per-flow text files to backup folder."""
        self._syncTextAttributesFromEvents()
        language = self._text_language_code()
        backup_dir = os.path.join(self.project.original_json_path, folder_name)
        os.makedirs(backup_dir, exist_ok=True)
        for flow_entry in self._flows:
            if not flow_entry.flow:
                continue
            flow_name = flow_entry.name or 'Untitled'
            msyts = self._flow_msyt_paths(flow_entry.flow)
            if not msyts:
                continue
            data = self.text_database.save_for_flow(msyts, language)
            if not data.get(language):
                continue
            path = os.path.join(backup_dir, f'{flow_name}.texts.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Auto-backup
    # ------------------------------------------------------------------

    def _autoBackup(self) -> None:
        """Auto-save ALL current flows as a timestamped backup in Original Json.
        Called after import, new, open, delete operations."""
        if not self.project.is_open:
            return
        folder_name = f'AutoBackup{self.project._now_str()}'
        for entry in self._flows:
            if not entry.flow:
                continue
            flow_name = entry.name or 'Untitled'
            data_dict = flow_to_dict(entry.flow)
            self.project.save_original_json_as(data_dict, flow_name, folder_name)
            # Also save .bfevfl
            bfevfl_folder = os.path.join(
                self.project.original_json_path, folder_name, FLOW_SUBDIR)
            os.makedirs(bfevfl_folder, exist_ok=True)
            try:
                util.write_flow(os.path.join(bfevfl_folder, f'{flow_name}.bfevfl'), entry.flow)
            except Exception:
                pass

        # Also save text backup alongside auto-backup
        self._saveTextsBackup(folder_name)

    # ------------------------------------------------------------------
    # Restore backup
    # ------------------------------------------------------------------

    def _clearWorkspace(self) -> None:
        """Close all open flows without prompting."""
        self._stopAutoSaveTimer()
        while self._flows:
            entry = self._flows[-1]
            # Disconnect signals
            try:
                entry.flow_data.flowDataChanged.disconnect(self._fd_set_unsaved)
            except TypeError:
                pass
            try:
                entry.flow_data.flowDataChanged.disconnect(self._fd_update_actions)
            except TypeError:
                pass
            self._flows.pop()
        self._current_idx = -1
        # Clear tab bar
        while self.flow_tab_bar.count > 0:
            self.flow_tab_bar.remove_tab(0)
        self.flowchart_view.setFlowData(self._sentinel_fd)
        self.updateTitleAndActions()

    def _onRestoreBackup(self) -> None:
        """Show a two-tab dialog listing manual and auto backup folders.
        Left tab: manual backups. Right tab: auto backups (for crash recovery).
        User picks one, then workspace is cleared and all flows from that
        folder are imported."""
        if not self.project.is_open:
            return

        manual_folders = self.project.get_backup_folders()
        auto_folders = self.project.get_auto_backup_folders()
        if not manual_folders and not auto_folders:
            q.QMessageBox.information(
                self, tr('project.restore.title'),
                tr('project.restore.no_backups'))
            return

        # Build dialog
        dialog = q.QDialog(self)
        dialog.setWindowTitle(tr('project.restore.title'))
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(350)
        layout = q.QVBoxLayout(dialog)

        label = q.QLabel(tr('project.restore.prompt'))
        layout.addWidget(label)

        tabs = q.QTabWidget()

        def _build_folder_list(folders: list, tab_label: str) -> q.QWidget:
            """Create a list widget for a set of backup folders."""
            page = q.QWidget()
            pl = q.QVBoxLayout(page)
            pl.setContentsMargins(0, 4, 0, 0)
            lw = q.QListWidget()
            lw.setAlternatingRowColors(True)
            from datetime import datetime
            for folder_name, mtime in folders:
                dt = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                item_text = f'{folder_name}  [{dt}]'
                item = q.QListWidgetItem(item_text)
                lw.addItem(item)
            if folders:
                lw.setCurrentRow(0)
            pl.addWidget(lw)
            tabs.addTab(page, tab_label)
            return lw

        manual_list = (_build_folder_list(manual_folders, tr('project.restore.tab_manual'))
                       if manual_folders else None)
        auto_list = (_build_folder_list(auto_folders, tr('project.restore.tab_auto'))
                     if auto_folders else None)

        # Set initial tab — prefer manual, fall back to auto
        if manual_folders:
            tabs.setCurrentIndex(0)
        else:
            tabs.setCurrentIndex(0)  # only auto tab, index 0
        layout.addWidget(tabs)

        btn_layout = q.QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = q.QPushButton(tr('project.restore.cancel'))
        btn_restore = q.QPushButton(tr('project.restore.restore'))
        btn_restore.setDefault(True)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_restore)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(dialog.reject)
        btn_restore.clicked.connect(dialog.accept)

        if dialog.exec_() != q.QDialog.Accepted:
            return

        # Determine which tab and which folder was selected
        current_tab = tabs.currentIndex()
        current_list = [manual_list, auto_list][current_tab] if manual_list and auto_list else (
            manual_list or auto_list)
        if current_list is None:
            return
        sel_idx = current_list.currentRow()
        source_folders = [manual_folders, auto_folders][current_tab] if manual_folders and auto_folders else (
            manual_folders or auto_folders)
        if sel_idx < 0 or sel_idx >= len(source_folders):
            return
        selected_folder = source_folders[sel_idx][0]

        # Confirm
        reply = q.QMessageBox.question(
            self, tr('project.restore.confirm_title'),
            tr('project.restore.confirm_text', folder=selected_folder),
            q.QMessageBox.Yes | q.QMessageBox.No)
        if reply != q.QMessageBox.Yes:
            return

        # Clear workspace
        self._clearWorkspace()

        # Import all flows from the selected backup folder
        flow_files = self.project.get_flow_files_in_folder(selected_folder)
        loaded_count = 0
        failed_files = []
        for fpath in flow_files:
            fname = os.path.basename(fpath)
            if fname.endswith('.bfevfl'):
                if self.readFlow(fpath):
                    loaded_count += 1
                else:
                    failed_files.append(fname)
            elif fname.endswith('.json'):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception as e:
                    failed_files.append(f'{fname} (read error: {e})')
                    continue
                errors = validate_flow_dict(data)
                if errors:
                    failed_files.append(f'{fname} (validation failed)')
                    continue
                flow = self._json_to_eventflow(data)
                if flow:
                    flow_name = os.path.splitext(fname)[0]
                    self.project.save_flow_to_mod(flow, flow_name)
                    idx = self._addFlow(flow_name, flow=flow)
                    if idx >= 0:
                        loaded_count += 1
                    else:
                        failed_files.append(f'{fname} (max tabs)')
                else:
                    failed_files.append(f'{fname} (conversion failed)')

        # Load gamedata cache from backup if present
        cache_path = os.path.join(
            self.project.original_json_path, selected_folder, '_gamedata_cache.json')
        if os.path.isfile(cache_path):
            cache_data = export_util.load_gamedata_from_json(cache_path)
            if cache_data:
                self.side_panel.load_all_gamedata_cache(cache_data)
                # Refresh panel to apply loaded cache to current flow
                self._updateSidePanel()

        result = tr('project.restore.success', count=loaded_count)
        if failed_files:
            result += '\n\n' + tr('project.restore.failed_files', files='\n'.join(failed_files))
        q.QMessageBox.information(self, tr('project.restore.title'), result)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def renameFlow(self) -> None:
        if not self.flow or not self.flow.flowchart or not self._current_entry:
            return
        text, ok = q.QInputDialog.getText(
            self, tr('dialog.rename'), tr('dialog.rename_prompt'),
            q.QLineEdit.Normal, self.flow.name,
        )
        if not ok or not text:
            return
        self.flow.name = text
        self.flow.flowchart.name = text
        self._current_entry.name = text
        self.flow_tab_bar.update_name(self._current_idx, text)
        self.flow_data.flowDataChanged.emit(FlowDataChangeReason.EventFlowRename)

    def _addFlow(self, name: str, flow_path: str = '', flow: EventFlow = None) -> int:
        """Create a FlowEntry, add to list and tab bar. Returns the index."""
        if self.flow_tab_bar.count >= FlowTabBar.MAX_TABS:
            return -1
        entry = FlowEntry()
        entry.flow_data.text_database = self.text_database
        entry.name = name
        entry.flow_path = flow_path
        if flow:
            entry.flow_data.setFlow(flow)
        self._flows.append(entry)
        tab_idx = self.flow_tab_bar.add_tab(name)
        if tab_idx >= 0:
            self._switchToFlow(tab_idx)
            self._startAutoSaveTimer()
        return tab_idx

    def readFlow(self, path: str) -> bool:
        try:
            flow = EventFlow()
            util.read_flow(path, flow)
            basename = os.path.splitext(os.path.basename(path))[0]
            flow.name = basename
            if flow.flowchart:
                flow.flowchart.name = basename
            self.project.save_event_flow_to_mod(path)
            idx = self._addFlow(basename, flow_path=path, flow=flow)
            if idx >= 0:
                self._autoBackup()
            return idx >= 0
        except Exception:
            traceback.print_exc()
            q.QMessageBox.critical(self, tr('dialog.open'), tr('dialog.open_failed'))
            return False

    def writeFlow(self, path: str) -> bool:
        if not self.flow or not path:
            return False

        try:
            util.write_flow(path, self.flow)
            self.flow_path = path
            self.unsaved = False
            self.updateTitleAndActions()
            return True
        except Exception:
            traceback.print_exc()
            q.QMessageBox.critical(self, tr('dialog.save'), tr('dialog.save_failed'))
            return False

    def onNewFile(self) -> bool:
        """Create a new empty flow — auto-saved to Mod/Event, backed up via JSON system."""
        name, ok = q.QInputDialog.getText(
            self, tr('flow_tab.new_title'),
            tr('flow_tab.new_prompt'),
            q.QLineEdit.Normal, tr('flow_tab.new_default'))
        if not ok or not name:
            return False

        flow = evfl.EventFlow()
        flow.name = name
        flow.flowchart = evfl.Flowchart()
        flow.flowchart.name = name

        # Auto-save to Mod/Event/<name>.bfevfl
        path = ''
        if self.project.is_open:
            path = self.project.save_flow_to_mod(flow, name)

        idx = self._addFlow(name, flow_path=path, flow=flow)
        if idx >= 0:
            self._autoBackup()
        return idx >= 0

    def onOpenFile(self, default_directory='', name_filter='Flowchart (*.bfevfl)') -> bool:
        default_directory_ = default_directory if default_directory else self.flow_path
        path = q.QFileDialog.getOpenFileName(
            self, tr('dialog.open_file_dialog'), default_directory_, name_filter)[0]
        if path:
            return self.readFlow(path)
        return False

    def onSaveFile(self) -> None:
        self.writeFlow(self.flow_path)

    def onSaveAsFile(self) -> None:
        path = q.QFileDialog.getSaveFileName(
            self, tr('dialog.save_as'), '', 'Flowchart (*.bfevfl)')[0]
        self.writeFlow(path)

    # ------------------------------------------------------------------
    # JSON import (from reference material — user's own code)
    # ------------------------------------------------------------------

    def onImportGraph(self) -> None:
        settings = qc.QSettings()
        last_dir = settings.value('paths/last_json_dir', '')

        path = q.QFileDialog.getOpenFileName(
            self, tr('flowchart.import.dialog_title'), last_dir, 'JSON (*.json)')[0]
        if not path:
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            q.QMessageBox.critical(
                self, tr('flowchart.import.title'),
                tr('flowchart.import.read_error', error=str(e)))
            return

        errors = validate_flow_dict(data)
        if errors:
            error_text = ''
            for i, err in enumerate(errors, 1):
                error_text += f'{i}. {err}\n'
            q.QMessageBox.critical(
                self, tr('flowchart.import.import_failed'),
                tr('flowchart.import.validation_failed', errors=error_text))
            return

        settings.setValue('paths/last_json_dir', os.path.dirname(path))

        try:
            flow = self._json_to_eventflow(data)
            if flow:
                # Save full EventFlow JSON backup (Format A — the original validated data)
                flow_dict = flow_to_dict(flow)
                self.project.save_original_json(flow_dict, flow.name)
                # Save to Mod
                self.project.save_flow_to_mod(flow, flow.name)
                # Add as new tab
                idx = self._addFlow(flow.name, flow=flow)
                if idx >= 0:
                    q.QMessageBox.information(
                        self, tr('flowchart.import.title'),
                        tr('flowchart.import.success'))
                    self._autoBackup()
                else:
                    q.QMessageBox.warning(
                        self, tr('flowchart.import.import_failed'),
                        tr('flowchart.import.max_tabs'))
            else:
                q.QMessageBox.warning(
                    self, tr('flowchart.import.import_failed'),
                    tr('flowchart.import.warn_failed'))
        except Exception as e:
            traceback.print_exc()
            q.QMessageBox.critical(
                self, tr('flowchart.import.import_error'),
                tr('flowchart.import.error', error=str(e)))

    def _rebuild_flow_from_json(self, data: dict) -> typing.Optional[EventFlow]:
        graph_data = data.get('graph', data) if isinstance(data, dict) else data

        if not isinstance(graph_data, list):
            return None

        flow = EventFlow()
        flow.name = 'ImportedFlow'
        flow.flowchart = Flowchart()
        flow.flowchart.name = 'ImportedFlow'
        flow.flowchart.actors = []

        nodes = {}
        edges = []

        for element in graph_data:
            if element.get('type') == 'node':
                node_id = element['id']
                node_type = element['node_type']
                node_data = element.get('data', {})
                nodes[node_id] = {'node_type': node_type, 'data': node_data}
            elif element.get('type') == 'edge':
                edges.append({
                    'source': element['source'],
                    'target': element['target'],
                    'data': element.get('data', {}),
                })

        actor_ids = set()
        for node_id, node_info in nodes.items():
            ntype = node_info['node_type']
            ndata = node_info['data']
            if ntype in ('action', 'switch'):
                if 'actor' in ndata and ndata['actor']:
                    actor_ids.add(ndata['actor'])

        actor_actions = {}
        actor_queries = {}
        for node_id, node_info in nodes.items():
            ntype = node_info['node_type']
            ndata = node_info['data']
            if ntype == 'action':
                aid = ndata.get('actor', '')
                action = ndata.get('action', '')
                if aid and action:
                    if aid not in actor_actions:
                        actor_actions[aid] = set()
                    actor_actions[aid].add(action)
            elif ntype == 'switch':
                aid = ndata.get('actor', '')
                query = ndata.get('query', '')
                if aid and query:
                    if aid not in actor_queries:
                        actor_queries[aid] = set()
                    actor_queries[aid].add(query)

        actor_map = {}
        for aid in actor_ids:
            try:
                actor = Actor()
                try:
                    actor.identifier.name = aid
                except Exception:
                    pass
                if aid in actor_actions:
                    for act in actor_actions[aid]:
                        try:
                            exists = any(str(x) == act for x in actor.actions)
                            if not exists:
                                actor.actions.append(StringHolder(act))
                        except Exception:
                            pass
                if aid in actor_queries:
                    for q in actor_queries[aid]:
                        try:
                            exists = any(str(x) == q for x in actor.queries)
                            if not exists:
                                actor.queries.append(StringHolder(q))
                        except Exception:
                            pass
                flow.flowchart.actors.append(actor)
                actor_map[aid] = actor
            except Exception:
                pass

        event_map = {}
        entry_events = []
        join_events_needed = []

        for node_id, node_info in nodes.items():
            if node_info['node_type'] == 'entry':
                entry_name = node_info['data'].get('name', f'Entry_{abs(node_id)}')
                ep = EntryPoint(entry_name)
                flow.flowchart.entry_points.append(ep)
                entry_events.append((node_id, ep))
            elif node_info['node_type'] in ('action', 'switch', 'fork', 'join', 'sub_flow'):
                event = Event()
                event.name = node_info['data'].get('name', f'Event{len(event_map)}')

                if node_info['node_type'] == 'action':
                    event.data = ActionEvent()
                    if not event.data.params:
                        event.data.params = Container()
                    actor_id = node_info['data'].get('actor', '')
                    if actor_id and actor_id in actor_map:
                        try:
                            ri = RequiredIndex()
                            ri.v = actor_map[actor_id]
                            event.data.actor = ri
                        except Exception:
                            pass
                    action = node_info['data'].get('action', '')
                    if action:
                        try:
                            sh = StringHolder(action)
                            if actor_id and actor_id in actor_map:
                                exists = any(str(x) == action for x in actor_map[actor_id].actions)
                                if not exists:
                                    actor_map[actor_id].actions.append(sh)
                            ri_action = RequiredIndex()
                            ri_action.v = sh
                            event.data.actor_action = ri_action
                        except Exception:
                            pass

                elif node_info['node_type'] == 'switch':
                    event.data = SwitchEvent()
                    if not event.data.params:
                        event.data.params = Container()
                    actor_id = node_info['data'].get('actor', '')
                    if actor_id and actor_id in actor_map:
                        try:
                            ri = RequiredIndex()
                            ri.v = actor_map[actor_id]
                            event.data.actor = ri
                        except Exception:
                            pass
                    query = node_info['data'].get('query', '')
                    if query:
                        try:
                            sh = StringHolder(query)
                            if actor_id and actor_id in actor_map:
                                exists = any(str(x) == query for x in actor_map[actor_id].queries)
                                if not exists:
                                    actor_map[actor_id].queries.append(sh)
                            ri_query = RequiredIndex()
                            ri_query.v = sh
                            event.data.actor_query = ri_query
                        except Exception:
                            pass

                elif node_info['node_type'] == 'fork':
                    event.data = ForkEvent()
                    join_events_needed.append(node_id)

                elif node_info['node_type'] == 'join':
                    event.data = JoinEvent()

                elif node_info['node_type'] == 'sub_flow':
                    event.data = SubFlowEvent()
                    if not event.data.params:
                        event.data.params = Container()
                    event.data.res_flowchart_name = node_info['data'].get('res_flowchart_name', '')
                    event.data.entry_point_name = node_info['data'].get('entry_point_name', '')

                params = node_info['data'].get('params')
                if params and hasattr(event.data, 'params'):
                    try:
                        if not event.data.params:
                            event.data.params = Container()
                        event.data.params.data = params
                    except Exception:
                        pass

                flow.flowchart.events.append(event)
                event_map[node_id] = event

        for fork_nid in join_events_needed:
            if fork_nid not in event_map:
                continue
            fork_event = event_map[fork_nid]
            has_join = False
            try:
                has_join = (fork_event.data.join is not None
                            and hasattr(fork_event.data.join, 'v'))
            except Exception:
                pass
            if has_join:
                continue
            join_ev = Event()
            join_ev.data = JoinEvent()
            join_ev.name = f'Join_{fork_event.name}'
            flow.flowchart.events.append(join_ev)
            ri = RequiredIndex()
            ri.v = join_ev
            fork_event.data.join = ri

        entry_node_ids = {nid for nid, _ in entry_events}
        for edge in edges:
            source_id = edge['source']
            target_id = edge['target']
            edge_data = edge.get('data', {})

            target_event = event_map.get(target_id)
            if not target_event:
                continue

            if source_id in entry_node_ids:
                for node_id, ep in entry_events:
                    if node_id == source_id:
                        try:
                            ri = RequiredIndex()
                            ri.v = target_event
                            ep.main_event = ri
                        except Exception:
                            pass
                        break
            elif source_id in event_map:
                source_event = event_map[source_id]
                source_data = source_event.data

                if isinstance(source_data, ActionEvent) or isinstance(source_data, JoinEvent) or isinstance(source_data, SubFlowEvent):
                    if not edge_data.get('virtual', False):
                        try:
                            ri = RequiredIndex()
                            ri.v = target_event
                            source_data.nxt = ri
                        except Exception:
                            pass

                elif isinstance(source_data, SwitchEvent):
                    value = edge_data.get('value')
                    if value is not None and not edge_data.get('virtual', False):
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            pass
                        try:
                            ri = RequiredIndex()
                            ri.v = target_event
                            source_data.cases[value] = ri
                        except Exception:
                            pass

                elif isinstance(source_data, ForkEvent):
                    if not edge_data.get('virtual', False):
                        try:
                            ri = RequiredIndex()
                            ri.v = target_event
                            source_data.forks.append(ri)
                        except Exception:
                            pass

        return flow

    # ------------------------------------------------------------------
    # Tab / View events
    # ------------------------------------------------------------------

    def onTabChanged(self, idx: int) -> None:
        self.flowchart_view.setIsCurrentView(
            self.tab_widget.widget(idx) == self.flowchart_view)

    def onViewReady(self) -> None:
        self.centralWidget().setHidden(False)
        self.onEventNameVisibilityChanged()
        self.onEventParamVisibilityChanged()
        self.onNotesDisplayChanged()

    def _onGraphEmptyContextMenu(self) -> None:
        """Show flowchart tools menu on right-click in empty graph space."""
        menu = q.QMenu(self)
        menu.addAction(self.reload_graph_action)
        menu.addSeparator()
        menu.addAction(self.export_graph_action)
        menu.addAction(self.import_graph_action)
        menu.addAction(self.export_definitions_action)
        menu.addAction(self.reorder_event_parameters_action)
        menu.addSeparator()
        menu.addAction(self.add_event_action)
        menu.addAction(self.add_fork_action)
        menu.exec_(qg.QCursor.pos())

    def onEventSelected(self, event_idx: int) -> None:
        self.event_view.selectEvent(event_idx)
        self._updateOptionPoolPanel(event_idx)

    def _toggleSidePanel(self) -> None:
        """Toggle the left side panel (N key).

        If the option pool panel (M) is open, close it first so the two
        side panels are never visible at the same time.
        """
        if self.option_pool_panel.isVisible():
            self.option_pool_panel.hide()
        self.side_panel.toggle()

    def _toggleOptionPoolPanel(self) -> None:
        """Toggle the option pool panel (M key).

        If the side panel (N) is open, close it first so the two side
        panels are never visible at the same time.
        """
        if self.side_panel.isVisible():
            self.side_panel.hide()
        self.option_pool_panel.toggle()
        if self.option_pool_panel.isVisible():
            # Refresh with currently selected event
            selected = self.flowchart_view.selected_event
            if selected and self.flow and self.flow.flowchart:
                try:
                    idx = self.flow.flowchart.events.index(selected)
                    self._updateOptionPoolPanel(idx)
                except ValueError:
                    pass

    def _find_flow_msyt_path(self, flow: 'EventFlow') -> str:
        """Find the MSYT path from any MessageId in *flow*."""
        if not hasattr(flow, 'flowchart') or not flow.flowchart:
            return ''
        for event in flow.flowchart.events:
            data = event.data
            if not isinstance(data, ActionEvent):
                continue
            msg_id = _msg_id_from_action(data)
            if msg_id and ':' in msg_id:
                path_part = msg_id.rsplit(':', 1)[0]
                if path_part.endswith('.msbt'):
                    path_part = path_part[:-5]
                elif path_part.endswith('.msyt'):
                    path_part = path_part[:-5]
                return path_part + '.msyt'
        return ''

    def _updateOptionPoolPanel(self, event_idx: int) -> None:
        """Update the option pool panel when a flowchart node is selected.

        Button pool is always shown (derived from the current flow's MSYT).
        Choice config only shows for GeneralChoice nodes.
        """
        panel = self.option_pool_panel
        if not panel.isVisible():
            return

        flow = self.flow
        if not flow or not flow.flowchart or event_idx < 0:
            return

        try:
            event = flow.flowchart.events[event_idx]
        except (IndexError, TypeError):
            return

        msyt_path = self._find_flow_msyt_path(flow)
        db = self.text_database

        # ---- GeneralChoice node ----
        count = _extract_choice_count(event)
        if count is not None:
            # Collect all parent MessageIds
            if isinstance(event.data, ActionEvent):
                msg_id = _msg_id_from_action(event.data)
                msg_ids = [msg_id] if msg_id else _find_all_parent_talk_msg_ids(flow, event)
            else:
                msg_ids = _find_all_parent_talk_msg_ids(flow, event)

            if msg_ids:
                parent_msyt = _msg_id_to_msyt_path(msg_ids[0])
                if parent_msyt:
                    msyt_path = parent_msyt

            # Collect raw entries for ALL parent messages.
            # Use ensure_message_entry so the choice control can be
            # written even for entries not yet in the text database.
            raw_entries: typing.List[dict] = []
            first_label = ''
            for mid in msg_ids:
                if not mid or ':' not in mid:
                    continue
                label = mid.rsplit(':', 1)[-1]
                entry = db.lookup_by_message_id(mid) if db else None
                if entry:
                    if not first_label:
                        first_label = entry.label
                    raw_entry = db._msyt_data.get(entry.msbt_file, {}).get(entry.label)
                    if raw_entry:
                        raw_entries.append(raw_entry)
                elif db:
                    # Parent message not in DB yet — create an empty entry
                    parent_msyt = _msg_id_to_msyt_path(mid) or msyt_path
                    if not parent_msyt:
                        continue
                    raw_entry = db.ensure_message_entry(parent_msyt, label)
                    raw_entries.append(raw_entry)
                    if not first_label:
                        first_label = label

            # Also look up the first entry for display label
            first_entry = db.lookup_by_message_id(msg_ids[0]) if db and msg_ids else None
            display_label = first_entry.label if first_entry else first_label

            if raw_entries:
                has_control = any(
                    TextDatabase.get_choice_control(re) for re in raw_entries
                )
                panel.set_context(msyt_path, display_label, raw_entries,
                                  default_choice_count=0 if has_control else count)
            else:
                panel.set_context(msyt_path, display_label, [],
                                  default_choice_count=count)
            return

        # ---- Talk node — always show single_choice config ----
        if isinstance(event.data, ActionEvent):
            msg_id = _msg_id_from_action(event.data)
            if msg_id and db and msyt_path and ':' in msg_id:
                label = msg_id.rsplit(':', 1)[-1]
                raw_entry = db.ensure_message_entry(msyt_path, label)
                display_label = label
                # Try to get the real label from an existing entry
                entry = db.lookup_by_message_id(msg_id)
                if entry:
                    display_label = entry.label
                panel.set_context(msyt_path, display_label, [raw_entry],
                                  single_choice_label=0)
                return

        # ---- Other node — keep pool visible, hide config ----
        if msyt_path:
            panel.set_context(msyt_path, '', [])
        else:
            panel.set_context('', '', [])

    def onJumpToEventsRequested(self, filter_str: str = '') -> None:
        self.tab_widget.setCurrentWidget(self.event_view)
        if filter_str:
            self.event_view.search_bar.setValue(filter_str)
            self.event_view.search_bar.show()

    def onJumpToFlowchartRequested(self, idx: int) -> None:
        """Request a node select in the flowchart webview. Negative indices are used for entry points."""
        self.tab_widget.setCurrentWidget(self.flowchart_view)
        self.flowchart_view.selectRequested.emit(idx)

    def onEventNameVisibilityChanged(self) -> None:
        visible = self.event_name_visible_action.isChecked()
        self.flowchart_view.eventNameVisibilityChanged.emit(visible)

    def onEventParamVisibilityChanged(self) -> None:
        visible = self.event_param_visible_action.isChecked()
        self.flowchart_view.eventParamVisibilityChanged.emit(visible)

    def onNotesDisplayChanged(self) -> None:
        enabled = self.notes_display_action.isChecked()
        self.flow_data.set_notes_display(enabled)


def main() -> None:
    qc.QCoreApplication.setOrganizationName(ORG_NAME)
    qc.QCoreApplication.setApplicationName(APP_NAME)
    qc.QSettings.setDefaultFormat(qc.QSettings.IniFormat)

    # Required before QApplication construction when CrEventor hosts more
    # than one QWebEngineView (flowchart + modern text editor).  The standalone
    # TextEditor already did this; without it the second Chromium surface can
    # remain an all-white, never-painted widget on Windows.
    q.QApplication.setAttribute(qc.Qt.AA_ShareOpenGLContexts)

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = argparse.ArgumentParser(
        prog='eventeditor-dx',
        description='CrEventor — Breath of the Wild event flow editor',
    )
    parser.add_argument('event_flow_file', nargs='?', help='Event flow file to open')
    parser.add_argument('--debug', action='store_true',
                        help='keep console open and print QtWebEngine diagnostics')
    args, _ = parser.parse_known_args()

    app = q.QApplication(sys.argv)
    if os.name == 'nt' and not args.debug:
        # Detach from console so it closes with the app.
        # Must reopen stdout/stderr FIRST — FreeConsole invalidates them.
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            if kernel32.GetConsoleWindow():
                kernel32.FreeConsole()
        except Exception:
            pass

        # Show unhandled exceptions in a message box (no console visible)
        def _excepthook(exc_type, exc_value, exc_tb):
            msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
            q.QMessageBox.critical(None, 'CrEventor — Error', msg)
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        sys.excepthook = _excepthook
        app_font = app.font()
        app_font.setFamily('Segoe UI')
        app_font.setPointSize(int(qg.QFontInfo(app_font).pointSize() * 1.20))
        app.setFont(app_font)

    # Initialize Tr singleton before creating window
    Tr()

    win = MainWindow(args)
    win.show()
    ret = app.exec_()
    sys.exit(ret)


if __name__ == '__main__':
    main()
