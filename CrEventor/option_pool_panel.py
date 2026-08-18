"""Option pool panel — M key to toggle, left side dock.

Sections (top to bottom):
  1. Context: preceding dialogue text for the selected generalchoice node
  2. Button library: option pool entries (0000+) for the MSYT file
  3. Choice config: per-dialogue button selection, cursor, cancel index
"""

import typing

from PyQt5 import QtCore as qc
from PyQt5 import QtGui as qg
from PyQt5 import QtWidgets as q

from CrEventor.text_database import TextDatabase
from CrEventor.i18n import tr, Tr


def _tr(key: str, fallback: str = '') -> str:
    val = tr('option_pool.' + key)
    return val if val else fallback


class OptionEntryWidget(q.QWidget):
    """A single row in the option pool list: key + text + edit/delete buttons."""

    textChanged = qc.pyqtSignal(str, str)  # key, new_text
    deleteRequested = qc.pyqtSignal(str)   # key

    def __init__(self, key: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._key = key

        layout = q.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Key label (e.g., "0000")
        self._key_label = q.QLabel(key)
        self._key_label.setFixedWidth(50)
        self._key_label.setStyleSheet('font-family: monospace; font-weight: bold;')
        layout.addWidget(self._key_label)

        # Text entry
        self._edit = q.QLineEdit(text)
        self._edit.setPlaceholderText(_tr('text_placeholder'))
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit, stretch=1)

        # Delete button
        delete_btn = q.QPushButton('✕')
        delete_btn.setFixedWidth(28)
        delete_btn.setToolTip(_tr('delete_tooltip'))
        delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self._key))
        layout.addWidget(delete_btn)

    @property
    def text(self) -> str:
        return self._edit.text()

    def _on_text_changed(self) -> None:
        self.textChanged.emit(self._key, self._edit.text())


class ChoiceConfigWidget(q.QWidget):
    """Per-dialogue choice configuration: button selection, cursor, cancel."""

    configChanged = qc.pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pool_keys: typing.List[str] = []
        self._choice_labels: typing.List[int] = []
        self._selected_index = 0
        self._cancel_index = 1
        self._unknown: typing.Any = None
        self._combo_widgets: typing.List[q.QComboBox] = []
        self._init_ui()

    def _init_ui(self) -> None:
        layout = q.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Button selection area
        self._btn_label = q.QLabel(f'<b>{_tr("choice_buttons")}</b>')
        layout.addWidget(self._btn_label)

        self._btn_container = q.QWidget()
        self._btn_layout = q.QVBoxLayout(self._btn_container)
        self._btn_layout.setContentsMargins(0, 0, 0, 0)
        self._btn_layout.setSpacing(3)
        layout.addWidget(self._btn_container)

        self._add_btn = q.QPushButton(f'+ {_tr("add_button")}')
        self._add_btn.clicked.connect(self._add_button_slot)
        layout.addWidget(self._add_btn)

        line = q.QFrame()
        line.setFrameShape(q.QFrame.HLine)
        line.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(line)

        # Cursor / cancel
        cfg_layout = q.QFormLayout()
        cfg_layout.setSpacing(4)

        self._cursor_combo = q.QComboBox()
        self._cursor_combo.currentIndexChanged.connect(self._emit_changed)
        self._cursor_label = q.QLabel(_tr('cursor_label'))
        cfg_layout.addRow(self._cursor_label, self._cursor_combo)

        self._cancel_combo = q.QComboBox()
        self._cancel_combo.currentIndexChanged.connect(self._emit_changed)
        self._cancel_label = q.QLabel(_tr('cancel_label'))
        cfg_layout.addRow(self._cancel_label, self._cancel_combo)

        layout.addLayout(cfg_layout)

    # ---- Public API ----

    def set_pool_keys(self, keys: typing.List[str]) -> None:
        """Update the available pool keys for combo boxes."""
        self._pool_keys = list(keys)
        self._rebuild_combos()

    def set_default_empty(self, option_count: int) -> None:
        """Create *option_count* empty button rows with default settings.

        Used when a GeneralChoice node is selected but no text DB entry
        has been configured yet.  The user fills in the buttons manually.
        """
        self._choice_labels = [0] * option_count
        self._selected_index = 0
        self._cancel_index = max(0, option_count - 1)
        self._unknown = TextDatabase.choice_unknown_value(option_count)

        # Rebuild button rows
        while self._btn_layout.count():
            item = self._btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._combo_widgets = []
        for i in range(option_count):
            row = q.QWidget()
            row_layout = q.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            idx_label = q.QLabel(f'{_tr("button")} {i + 1}:')
            row_layout.addWidget(idx_label)

            combo = q.QComboBox()
            combo.currentIndexChanged.connect(self._on_button_combo_changed)
            self._combo_widgets.append(combo)
            self._setup_combo_items(combo, 0)
            row_layout.addWidget(combo, stretch=1)

            remove_btn = q.QPushButton('✕')
            remove_btn.setFixedWidth(28)
            remove_btn.clicked.connect(lambda checked, idx=i: self._remove_button(idx))
            row_layout.addWidget(remove_btn)

            self._btn_layout.addWidget(row)

        self._rebuild_combos()
        self._btn_layout.addStretch()

    def load_config(
        self,
        choice_labels: typing.List[int],
        selected_index: int,
        cancel_index: int,
        unknown: typing.Any = None,
    ) -> None:
        """Load existing choice configuration. ``unknown`` is preserved as-is."""
        self._choice_labels = list(choice_labels)
        self._selected_index = selected_index
        self._cancel_index = cancel_index
        self._unknown = unknown

        # Rebuild button rows
        while self._btn_layout.count():
            item = self._btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._combo_widgets = []
        for i, label_val in enumerate(choice_labels):
            row = q.QWidget()
            row_layout = q.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            idx_label = q.QLabel(f'{_tr("button")} {i + 1}:')
            row_layout.addWidget(idx_label)

            combo = q.QComboBox()
            combo.currentIndexChanged.connect(self._on_button_combo_changed)
            self._combo_widgets.append(combo)
            self._setup_combo_items(combo, label_val)
            row_layout.addWidget(combo, stretch=1)

            remove_btn = q.QPushButton('✕')
            remove_btn.setFixedWidth(28)
            remove_btn.clicked.connect(lambda checked, idx=i: self._remove_button(idx))
            row_layout.addWidget(remove_btn)

            self._btn_layout.addWidget(row)

        self._rebuild_combos()
        self._btn_layout.addStretch()

    def get_config(self) -> dict:
        """Return the current config as a dict."""
        return {
            'choice_labels': list(self._choice_labels),
            'selected_index': self._selected_index,
            'cancel_index': self._cancel_index,
            'unknown': self._unknown,
        }

    # ---- Internal ----

    def _setup_combo_items(
        self, combo: q.QComboBox, current_label: int,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        has_current = False
        for idx, key in enumerate(self._pool_keys):
            combo.addItem(key, int(key))
            if int(key) == current_label:
                combo.setCurrentIndex(idx)
                has_current = True
        if not has_current and self._pool_keys:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _on_button_combo_changed(self) -> None:
        self._rebuild_choice_labels()
        self._rebuild_combos()
        self._emit_changed()

    def _rebuild_choice_labels(self) -> None:
        self._choice_labels = [
            int(cb.currentData())
            for cb in self._combo_widgets
        ]

    def _rebuild_combos(self) -> None:
        """Rebuild cursor/cancel combos based on current button count."""
        self._rebuild_choice_labels()
        count = len(self._choice_labels)

        self._cursor_combo.blockSignals(True)
        self._cursor_combo.clear()
        for i in range(count):
            self._cursor_combo.addItem(
                f'{_tr("button")} {i + 1} ({self._choice_labels[i]:04d})', i,
            )
        if self._selected_index < count:
            self._cursor_combo.setCurrentIndex(self._selected_index)
        self._cursor_combo.blockSignals(False)

        self._cancel_combo.blockSignals(True)
        self._cancel_combo.clear()
        for i in range(count):
            self._cancel_combo.addItem(
                f'{_tr("button")} {i + 1} ({self._choice_labels[i]:04d})', i,
            )
        self._cancel_combo.addItem(_tr('no_cancel', 'No cancel'), count)
        if 0 <= self._cancel_index <= count:
            self._cancel_combo.setCurrentIndex(
                self._cancel_combo.findData(self._cancel_index))
        else:
            self._cancel_combo.setCurrentIndex(self._cancel_combo.findData(count))
        self._cancel_combo.blockSignals(False)

    def _add_button_slot(self) -> None:
        """Add a new button selection row."""
        old_count = len(self._combo_widgets)
        had_no_cancel = self._cancel_index == old_count
        row = q.QWidget()
        row_layout = q.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        i = len(self._combo_widgets)
        idx_label = q.QLabel(f'{_tr("button")} {i + 1}:')
        row_layout.addWidget(idx_label)

        combo = q.QComboBox()
        self._setup_combo_items(combo, 0)
        combo.currentIndexChanged.connect(self._on_button_combo_changed)
        self._combo_widgets.append(combo)
        row_layout.addWidget(combo, stretch=1)

        remove_btn = q.QPushButton('✕')
        remove_btn.setFixedWidth(28)
        remove_btn.clicked.connect(lambda checked, idx=i: self._remove_button(idx))
        row_layout.addWidget(remove_btn)

        # Insert before the stretch
        self._btn_layout.takeAt(self._btn_layout.count() - 1)
        self._btn_layout.addWidget(row)
        self._btn_layout.addStretch()

        if had_no_cancel:
            self._cancel_index = old_count + 1

        self._rebuild_choice_labels()
        self._rebuild_combos()
        self._emit_changed()

    def _remove_button(self, idx: int) -> None:
        """Remove a button selection row."""
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

    def _emit_changed(self) -> None:
        self._selected_index = self._cursor_combo.currentData()
        self._cancel_index = self._cancel_combo.currentData()
        self._rebuild_choice_labels()
        self.configChanged.emit()

    def _update_texts(self) -> None:
        """Refresh all labels when language changes."""
        self._btn_label.setText(f'<b>{_tr("choice_buttons")}</b>')
        self._add_btn.setText(f'+ {_tr("add_button")}')
        self._cursor_label.setText(_tr('cursor_label'))
        self._cancel_label.setText(_tr('cancel_label'))
        # Rebuild button combo items (button labels)
        self._rebuild_combos()

        # Update button row labels
        for i, cb in enumerate(self._combo_widgets):
            row = self._btn_layout.itemAt(i)
            if row and row.widget():
                row_w = row.widget()
                row_layout = row_w.layout()
                if row_layout and row_layout.count() > 0:
                    idx_label = row_layout.itemAt(0)
                    if idx_label and idx_label.widget():
                        idx_label.widget().setText(f'{_tr("button")} {i + 1}:')


class SingleChoiceConfigWidget(q.QWidget):
    """Per-dialogue single_choice configuration: enable toggle + one button label."""

    configChanged = qc.pyqtSignal()
    toggleChanged = qc.pyqtSignal(bool)  # True = enabled, False = disabled

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pool_keys: typing.List[str] = []
        self._label: int = 0
        self._enabled: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = q.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Enable toggle
        self._enable_check = q.QCheckBox(_tr('single_choice_enable'))
        self._enable_check.toggled.connect(self._on_toggled)
        layout.addWidget(self._enable_check)

        # Label selection (initially disabled)
        self._label_container = q.QWidget()
        clayout = q.QVBoxLayout(self._label_container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(4)

        self._label_tag = q.QLabel(f'<b>{_tr("single_choice_label")}</b>')
        clayout.addWidget(self._label_tag)

        self._label_combo = q.QComboBox()
        self._label_combo.currentIndexChanged.connect(self._on_label_changed)
        clayout.addWidget(self._label_combo)

        hint = q.QLabel(f'<i>{_tr("single_choice_hint")}</i>')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #888; font-size: 11px;')
        clayout.addWidget(hint)

        self._label_container.hide()
        layout.addWidget(self._label_container)
        layout.addStretch()

    # ---- Public API ----

    def set_pool_keys(self, keys: typing.List[str]) -> None:
        """Update the available pool keys for the combo box."""
        self._pool_keys = list(keys)
        self._setup_combo()

    def load_config(self, label: int, enabled: bool) -> None:
        """Load existing single_choice config."""
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
        """Return the current label value."""
        return self._label

    # ---- Internal ----

    def _setup_combo(self) -> None:
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

    def _on_toggled(self, checked: bool) -> None:
        self._enabled = checked
        self._label_container.setVisible(checked)
        self.toggleChanged.emit(checked)
        self.configChanged.emit()

    def _on_label_changed(self) -> None:
        self._label = self._label_combo.currentData()
        self.configChanged.emit()

    def _update_texts(self) -> None:
        """Refresh all labels when language changes."""
        self._enable_check.setText(_tr('single_choice_enable'))
        self._label_tag.setText(f'<b>{_tr("single_choice_label")}</b>')


class OptionPoolPanel(q.QDockWidget):
    """Left-docked panel for option pool and generalchoice configuration."""

    PANEL_WIDTH = 840

    def __init__(self, parent=None) -> None:
        super().__init__(_tr('title'), parent)
        self.setAllowedAreas(qc.Qt.LeftDockWidgetArea | qc.Qt.RightDockWidgetArea)
        self.setFeatures(q.QDockWidget.DockWidgetClosable
                         | q.QDockWidget.DockWidgetMovable)
        self.setMinimumWidth(450)

        # Update title when language changes
        Tr.instance.languageChanged.connect(self._update_texts)

        self._text_db: typing.Optional[TextDatabase] = None
        self._current_msyt_path = ''
        self._current_entry_label = ''
        self._current_raw_entries: typing.List[dict] = []
        self._pool_widgets: typing.Dict[str, OptionEntryWidget] = {}

        scroll = q.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea { border: none; }')

        content = q.QWidget()
        layout = q.QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # ---- Section 1: Current context info ----
        self._msyt_info = q.QLabel()
        self._msyt_info.setWordWrap(True)
        self._msyt_info.setStyleSheet('color: #888; font-size: 11px;')
        layout.addWidget(self._msyt_info)

        # ---- Separator ----
        line1 = q.QFrame()
        line1.setFrameShape(q.QFrame.HLine)
        line1.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(line1)

        # ---- Section 2: Option pool (button library) ----
        pool_header = q.QHBoxLayout()
        self._pool_title = q.QLabel(f'<b>{_tr("pool_title")}</b>')
        pool_header.addWidget(self._pool_title)
        pool_header.addStretch()

        self._add_manual_btn = q.QPushButton(f'+ {_tr("add_btn")}')
        self._add_manual_btn.clicked.connect(self._add_manual_slot)
        pool_header.addWidget(self._add_manual_btn)

        layout.addLayout(pool_header)

        self._pool_container = q.QWidget()
        self._pool_layout = q.QVBoxLayout(self._pool_container)
        self._pool_layout.setContentsMargins(0, 0, 0, 0)
        self._pool_layout.setSpacing(2)
        layout.addWidget(self._pool_container)

        # ---- Separator ----
        line2 = q.QFrame()
        line2.setFrameShape(q.QFrame.HLine)
        line2.setFrameShadow(q.QFrame.Sunken)
        layout.addWidget(line2)

        # ---- Section 3: Choice config ----
        self._config_title = q.QLabel(f'<b>{_tr("config_title")}</b>')
        layout.addWidget(self._config_title)

        self._config_no_selection = q.QLabel(
            f'<i>{_tr("no_selection_hint")}</i>'
        )
        self._config_no_selection.setWordWrap(True)
        layout.addWidget(self._config_no_selection)

        self._choice_config = ChoiceConfigWidget()
        self._choice_config.configChanged.connect(self._on_config_changed)
        self._choice_config.hide()
        layout.addWidget(self._choice_config)

        self._single_choice_config = SingleChoiceConfigWidget()
        self._single_choice_config.configChanged.connect(self._on_single_config_changed)
        self._single_choice_config.hide()
        layout.addWidget(self._single_choice_config)

        layout.addStretch()

        scroll.setWidget(content)
        self.setWidget(scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        """Toggle panel visibility."""
        self.setVisible(not self.isVisible())

    def _update_texts(self, _lang: str = '') -> None:
        """Update all labels when language changes."""
        self.setWindowTitle(_tr('title'))
        self._pool_title.setText(f'<b>{_tr("pool_title")}</b>')
        self._add_manual_btn.setText(f'+ {_tr("add_btn")}')
        self._config_title.setText(f'<b>{_tr("config_title")}</b>')
        # Update dynamic hint text
        if self._choice_config.isVisible() or self._single_choice_config.isVisible():
            # Config is active — hint hidden
            pass
        elif not self._text_db or not self._current_msyt_path:
            self._config_no_selection.setText(f'<i>{_tr("no_msyt_selected")}</i>')
        elif self._current_entry_label:
            self._config_no_selection.setText(f'<i>{_tr("no_choice_control")}</i>')
        else:
            self._config_no_selection.setText(f'<i>{_tr("no_selection_hint")}</i>')
        self._choice_config._update_texts()
        self._single_choice_config._update_texts()
        # Rebuild pool widgets to update their labels
        self._refresh_pool()

    def set_text_database(self, db: typing.Optional[TextDatabase]) -> None:
        self._text_db = db

    def set_context(
        self,
        msyt_path: str,
        label: str,
        raw_entries: typing.Optional[typing.List[dict]],
        default_choice_count: int = 0,
        single_choice_label: typing.Optional[int] = None,
    ) -> None:
        """Update panel state when a node is selected.

        - *msyt_path* is always derived from the current flow.
        - *raw_entries* list contains all parent message raw entries.
          The first one (if any) is used to load the existing config;
          ALL entries are written to on config changes.
        - If *default_choice_count* > 0, create empty config for a
          GeneralChoice with that many options.
        - If *single_choice_label* is not None, show single_choice config
          with the given label value (or 0 as default for new config).
        - Otherwise (non-GeneralChoice), hide the choice config section
          but keep the button pool visible.
        """
        if msyt_path:
            self._current_msyt_path = msyt_path
            self._current_entry_label = label
            self._current_raw_entries = raw_entries if raw_entries else []

        self._msyt_info.setText(
            f'{self._current_msyt_path}  /  {self._current_entry_label}'
            if self._current_entry_label else self._current_msyt_path
        )

        # Load pool FIRST so _pool_keys is populated before load_config
        self._refresh_pool()

        # Hide both configs initially
        self._choice_config.hide()
        self._single_choice_config.hide()

        # ---- single_choice ----
        if single_choice_label is not None:
            self._config_no_selection.hide()
            self._single_choice_config.show()
            # Load existing or set default (disabled by default)
            raw_entries_list = self._current_raw_entries
            if raw_entries_list:
                first_raw = raw_entries_list[0]
                control = TextDatabase.get_single_choice_control(first_raw)
                if control:
                    self._single_choice_config.load_config(
                        control.get('label', single_choice_label),
                        enabled=True
                    )
                else:
                    self._single_choice_config.load_config(
                        single_choice_label, enabled=False
                    )
            else:
                self._single_choice_config.load_config(
                    single_choice_label, enabled=False
                )
            self._single_choice_config.set_pool_keys(
                list(self._text_db.get_option_pool(self._current_msyt_path).keys())
                if self._text_db and self._current_msyt_path
                and self._text_db.get_option_pool(self._current_msyt_path)
                else ['0000']
            )
            return

        # ---- choice (GeneralChoice) ----
        raw_entries_list = self._current_raw_entries
        if raw_entries_list:
            first_raw = raw_entries_list[0]
            control = TextDatabase.get_choice_control(first_raw)
            if control:
                self._config_no_selection.hide()
                self._choice_config.show()
                self._choice_config.load_config(
                    choice_labels=control.get('choice_labels', []),
                    selected_index=control.get('selected_index', 0),
                    cancel_index=control.get('cancel_index', 1),
                    unknown=control.get('unknown'),
                )
            elif default_choice_count > 0:
                # Has parent raw entries but no choice control yet —
                # show empty config for the user to fill in.
                self._config_no_selection.hide()
                self._choice_config.show()
                self._choice_config.set_default_empty(default_choice_count)
            else:
                self._no_choice_control()
        elif default_choice_count > 0:
            # GeneralChoice without any parent message entries —
            # create default config (no raw entries to write to yet).
            self._config_no_selection.hide()
            self._choice_config.show()
            self._choice_config.set_default_empty(default_choice_count)
        else:
            self._no_choice_control()

    def _no_choice_control(self) -> None:
        """Hide config section and show the appropriate hint."""
        self._choice_config.hide()
        self._single_choice_config.hide()
        self._config_no_selection.setText(
            f'<i>{_tr("no_choice_control")}</i>'
        )
        self._config_no_selection.show()

    def _refresh_pool(self) -> None:
        """Rebuild the option pool list."""
        # Clear existing
        for widget in self._pool_widgets.values():
            widget.deleteLater()
        self._pool_widgets.clear()

        while self._pool_layout.count():
            item = self._pool_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._text_db or not self._current_msyt_path:
            placeholder = q.QLabel(
                f'<i>{_tr("no_msyt_selected")}</i>'
            )
            self._pool_layout.addWidget(placeholder)
            return

        pool = self._text_db.get_option_pool(self._current_msyt_path)
        if not pool:
            placeholder = q.QLabel(
                f'<i>{_tr("empty_pool")}</i>'
            )
            self._pool_layout.addWidget(placeholder)
        else:
            for key, text in pool.items():
                widget = OptionEntryWidget(key, text)
                widget.textChanged.connect(self._on_pool_text_changed)
                widget.deleteRequested.connect(self._on_pool_delete)
                self._pool_widgets[key] = widget
                self._pool_layout.addWidget(widget)

        # Update choice config combos
        keys = list(pool.keys()) if pool else ['0000']
        self._choice_config.set_pool_keys(keys)
        self._single_choice_config.set_pool_keys(keys)

    # ---- Slots ----

    def _on_pool_text_changed(self, key: str, text: str) -> None:
        if self._text_db and self._current_msyt_path:
            self._text_db.set_pool_entry_text(self._current_msyt_path, key, text)

    def _on_pool_delete(self, key: str) -> None:
        if not self._text_db or not self._current_msyt_path:
            return
        reply = q.QMessageBox.question(
            self,
            _tr('delete_confirm_title'),
            _tr('delete_confirm_text').format(key=key),
            q.QMessageBox.Yes | q.QMessageBox.No,
        )
        if reply != q.QMessageBox.Yes:
            return
        self._text_db.delete_pool_entry(self._current_msyt_path, key)
        self._refresh_pool()

    def _add_manual_slot(self) -> None:
        """Add a new button to the pool at the next available index."""
        if not self._text_db or not self._current_msyt_path:
            return
        # Find next free index
        pool = self._text_db.get_option_pool(self._current_msyt_path)
        if pool:
            next_idx = max(int(k) for k in pool) + 1
        else:
            next_idx = 0
        key = str(next_idx).zfill(4)
        self._text_db.set_pool_entry_text(self._current_msyt_path, key, '')
        self._refresh_pool()

    def _on_config_changed(self) -> None:
        """User changed the per-dialogue choice configuration.

        Writes the choice control to ALL parent message raw entries
        so that every Talk node leading into this GeneralChoice gets
        the same choice config in the saved JSON.
        """
        if not self._text_db or not self._current_raw_entries:
            return
        config = self._choice_config.get_config()
        for raw_entry in self._current_raw_entries:
            TextDatabase.update_choice_control(
                raw_entry,
                choice_labels=config['choice_labels'],
                selected_index=config['selected_index'],
                cancel_index=config['cancel_index'],
                unknown=config.get('unknown'),
            )
        # Mark all parent entries as modified
        for label in [self._current_entry_label] if self._current_entry_label else []:
            entry = self._text_db.lookup(label)
            if entry:
                entry.modified = True

    def _on_single_config_changed(self) -> None:
        """User toggled or changed the per-dialogue single_choice config."""
        if not self._text_db or not self._current_raw_entries:
            return
        enabled = self._single_choice_config.is_enabled()
        label = self._single_choice_config.get_label()
        for raw_entry in self._current_raw_entries:
            if enabled:
                TextDatabase.update_single_choice_control(raw_entry, label=label)
            else:
                TextDatabase.remove_single_choice_control(raw_entry)
        # Mark all parent entries as modified
        for label_str in [self._current_entry_label] if self._current_entry_label else []:
            entry = self._text_db.lookup(label_str)
            if entry:
                entry.modified = True
