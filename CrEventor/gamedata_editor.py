"""Modular gamedata flag editor — per-event cards, collapsible, vertical layout.

Each card represents one flag reference from one event.
Cards sharing the same flag name share the same underlying gamedata fields.
Flags are only obtained by scanning eventflow (no manual add).

Based on spec_gamedata_savedata.yaml verified templates.
"""

import typing
import zlib

from evfl import EventFlow
from evfl.event import ActionEvent, SwitchEvent
from PyQt5 import QtCore as qc
from PyQt5 import QtGui as qg
from PyQt5 import QtWidgets as q

from CrEventor.i18n import tr, Tr
from CrEventor.whitelist_loader import is_vanilla_gamedata

# ---------------------------------------------------------------------------
# Flag templates
# ---------------------------------------------------------------------------

TEMPLATE_A = {
    'InitValue': 0, 'IsEventAssociated': False, 'IsOneTrigger': True,
    'IsProgramReadable': True, 'IsProgramWritable': True, 'IsSave': True,
    'MaxValue': True, 'MinValue': False, 'ResetType': 0,
}

TEMPLATE_B = {
    'InitValue': 0, 'IsEventAssociated': False, 'IsOneTrigger': False,
    'IsProgramReadable': False, 'IsProgramWritable': False, 'IsSave': False,
    'MaxValue': True, 'MinValue': False, 'ResetType': 2,
}

TEMPLATE_QUEST = {
    'InitValue': 0, 'IsEventAssociated': False, 'IsOneTrigger': True,
    'IsProgramReadable': False, 'IsProgramWritable': False, 'IsSave': True,
    'MaxValue': True, 'MinValue': False, 'ResetType': 0,
}

TEMPLATES = {
    'A': TEMPLATE_A,
    'B': TEMPLATE_B,
    'Quest': TEMPLATE_QUEST,
}
TEMPLATE_KEYS = list(TEMPLATES.keys())

_TEMPLATE_NAME_KEYS = {
    'A': 'gamedata.template_a',
    'B': 'gamedata.template_b',
    'Quest': 'gamedata.template_quest',
}


def flag_hash(name: str) -> int:
    """Signed 32-bit CRC32 of flag name."""
    crc = zlib.crc32(name.encode('utf-8'))
    return crc - 2 ** 32 if crc >= 2 ** 31 else crc


def scan_flag_events(flow: EventFlow) -> typing.List[typing.Tuple[str, str, str]]:
    """Scan flow and return list of (event_name, action_type, flag_name)."""
    results: typing.List[typing.Tuple[str, str, str]] = []
    if not flow or not flow.flowchart or not flow.flowchart.events:
        return results

    for event in flow.flowchart.events:
        try:
            data = event.data
            if isinstance(data, ActionEvent):
                action_v = data.actor_action
                if action_v is not None:
                    action_name = str(action_v.v) if hasattr(action_v, 'v') else str(action_v)
                    if action_name in ('Demo_FlagON', 'Demo_FlagOFF'):
                        if data.params and data.params.data:
                            flag = data.params.data.get('FlagName')
                            if flag and isinstance(flag, str) and flag.strip():
                                results.append((event.name, action_name, flag.strip()))
            elif isinstance(data, SwitchEvent):
                query_v = data.actor_query
                if query_v is not None:
                    query_name = str(query_v.v) if hasattr(query_v, 'v') else str(query_v)
                    if query_name == 'CheckFlag':
                        if data.params and data.params.data:
                            flag = data.params.data.get('FlagName')
                            if flag and isinstance(flag, str) and flag.strip():
                                results.append((event.name, query_name, flag.strip()))
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# FlagCard — one card per event reference
# ---------------------------------------------------------------------------

class FlagCard(q.QFrame):
    """Collapsible card for one flag reference from one event.

    Collapsed: 3 lines (event info, flag name, hash + template summary)
    Expanded:  each detail field on its own line.
    """

    CARD_STYLE = (
        'FlagCard { border: 1px solid #ccc; border-radius: 4px; '
        'background: #fafafa; margin: 2px 4px; }'
    )
    HEADER_STYLE = 'background: #e8e8e8; border-radius: 3px; padding: 2px 6px;'
    FIELD_STYLE = 'background: white; border: 1px solid #ddd; border-radius: 2px; padding: 2px 6px;'

    removed = qc.pyqtSignal()        # card-level (key) removal
    changed = qc.pyqtSignal()

    def __init__(self, flag_name: str, fields: dict, parent=None) -> None:
        super().__init__(parent)
        self._flag_name = flag_name
        self._fields = fields       # shared dict! not a copy
        self._expanded = False
        self._suppress = False
        self._detail_widgets: typing.Dict[str, q.QWidget] = {}  # field → widget

        self.setStyleSheet(self.CARD_STYLE)
        self.setSizePolicy(q.QSizePolicy.Expanding, q.QSizePolicy.Fixed)

        self._outer = q.QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # ---- Header bar (2-line clickable) ----
        self._header = q.QWidget()
        self._header.setStyleSheet(self.HEADER_STYLE)
        self._header.setCursor(qc.Qt.PointingHandCursor)
        self._header.mousePressEvent = self._onHeaderClick
        hv = q.QVBoxLayout(self._header)
        hv.setContentsMargins(4, 2, 4, 2)
        hv.setSpacing(1)

        # Row 1: arrow + flag name + X
        h1 = q.QHBoxLayout()
        h1.setSpacing(4)
        self._arrow = q.QLabel('▶')
        self._arrow.setFixedWidth(14)
        h1.addWidget(self._arrow)

        self._header_label = q.QLabel(flag_name)
        self._header_label.setStyleSheet('font-weight: bold;')
        h1.addWidget(self._header_label)

        h1.addStretch()

        self._del_btn = q.QPushButton('✕')
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setStyleSheet(
            'QPushButton { border: none; color: #c44; font-weight: bold; }'
            'QPushButton:hover { color: #f00; }')
        self._del_btn.clicked.connect(lambda: self.removed.emit())
        h1.addWidget(self._del_btn)
        hv.addLayout(h1)

        # Row 2: hash
        h2 = q.QHBoxLayout()
        h2.setSpacing(4)
        h2.addSpacing(18)  # align with text after arrow
        h2.addWidget(q.QLabel('Hash:'))
        self._hash_label = q.QLabel()
        self._hash_label.setStyleSheet('color: #787878; font-family: Consolas;')
        h2.addWidget(self._hash_label)
        h2.addStretch()
        hv.addLayout(h2)

        self._outer.addWidget(self._header)

        # ---- Body (always visible: template only) ----
        self._body = q.QWidget()
        bl = q.QVBoxLayout(self._body)
        bl.setContentsMargins(6, 3, 6, 3)
        bl.setSpacing(2)

        row_tmpl = q.QHBoxLayout()
        row_tmpl.addWidget(q.QLabel(tr('gamedata.col.template') + ':'))
        self._template_combo = q.QComboBox()
        for key in TEMPLATE_KEYS:
            self._template_combo.addItem(
                tr(_TEMPLATE_NAME_KEYS.get(key, '')), key)
        self._template_combo.currentIndexChanged.connect(self._onTemplateChanged)
        row_tmpl.addWidget(self._template_combo)
        row_tmpl.addStretch()
        bl.addLayout(row_tmpl)

        self._outer.addWidget(self._body)

        # ---- Detail (collapsible) ----
        self._detail = q.QWidget()
        self._detail.setVisible(False)
        dl = q.QVBoxLayout(self._detail)
        dl.setContentsMargins(4, 0, 4, 4)
        dl.setSpacing(2)

        # Separator line
        sep = q.QFrame()
        sep.setFrameShape(q.QFrame.HLine)
        sep.setFrameShadow(q.QFrame.Sunken)
        dl.addWidget(sep)

        self._build_detail_rows(dl)
        self._outer.addWidget(self._detail)

        self._refresh_display()

    def _build_detail_rows(self, layout: q.QVBoxLayout) -> None:
        """Each detail field on its own row."""
        fields_info = [
            ('InitValue',        self._make_spin_row('InitValue', 0, 1, 'InitValue')),
            ('IsOneTrigger',     self._make_check_row('IsOneTrigger', 'IsOneTrigger')),
            ('IsSave',           self._make_check_row('IsSave', 'IsSave')),
            ('ResetType',        self._make_spin_row('ResetType', 0, 99, 'ResetType')),
            ('IsProgramReadable',self._make_check_row('IsProgramReadable', 'IsProgramReadable')),
            ('IsProgramWritable',self._make_check_row('IsProgramWritable', 'IsProgramWritable')),
            ('IsEventAssociated',self._make_check_row('IsEventAssociated', 'IsEventAssociated')),
        ]
        for field_name, (label, widget) in fields_info:
            self._detail_widgets[field_name] = widget
            row = q.QHBoxLayout()
            row.addWidget(label)
            row.addWidget(widget)
            row.addStretch()
            layout.addLayout(row)

    def _make_spin_row(self, field: str, lo: int, hi: int, label_text: str
                       ) -> typing.Tuple[q.QLabel, q.QSpinBox]:
        lbl = q.QLabel(label_text + ':')
        spin = q.QSpinBox()
        spin.setRange(lo, hi)
        spin.valueChanged.connect(lambda v, f=field: self._update_field(f, v))
        return lbl, spin

    def _make_check_row(self, field: str, label_text: str
                        ) -> typing.Tuple[q.QLabel, q.QCheckBox]:
        lbl = q.QLabel(label_text + ':')
        chk = q.QCheckBox()
        chk.toggled.connect(lambda v, f=field: self._update_field(f, v))
        return lbl, chk

    def _onHeaderClick(self, event) -> None:
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)
        self._arrow.setText('▼' if self._expanded else '▶')

    def _onTemplateChanged(self, idx: int) -> None:
        if self._suppress:
            return
        key = TEMPLATE_KEYS[idx]
        template_fields = TEMPLATES[key]
        self._fields.update(template_fields)
        self._fields['Template'] = key
        self._fields['HashValue'] = flag_hash(self._flag_name)
        self._refresh_display()
        self.changed.emit()

    def _update_field(self, field: str, value) -> None:
        if self._suppress:
            return
        self._fields[field] = value
        self.changed.emit()

    def _refresh_display(self) -> None:
        self._suppress = True

        self._header_label.setText(self._flag_name)
        self._hash_label.setText(str(self._fields.get('HashValue',
                                                     flag_hash(self._flag_name))))

        tmpl = self._fields.get('Template', 'A')
        if tmpl in TEMPLATE_KEYS:
            self._template_combo.setCurrentIndex(TEMPLATE_KEYS.index(tmpl))

        # Update detail widgets from fields
        for field_name, widget in self._detail_widgets.items():
            value = self._fields.get(field_name)
            if isinstance(widget, q.QSpinBox):
                widget.setValue(int(value) if value is not None else 0)
            elif isinstance(widget, q.QCheckBox):
                widget.setChecked(bool(value))

        self._suppress = False

    def _update_texts(self) -> None:
        """Refresh template combo items when language changes."""
        self._suppress = True
        current_key = TEMPLATE_KEYS[self._template_combo.currentIndex()]
        self._template_combo.clear()
        for key in TEMPLATE_KEYS:
            self._template_combo.addItem(
                tr(_TEMPLATE_NAME_KEYS.get(key, '')), key)
        idx = TEMPLATE_KEYS.index(current_key) if current_key in TEMPLATE_KEYS else 0
        self._template_combo.setCurrentIndex(idx)
        self._suppress = False

    @property
    def flag_name(self) -> str:
        return self._flag_name

    @property
    def fields(self) -> dict:
        return self._fields


# ---------------------------------------------------------------------------
# GamedataSection — per-event cards, shared flag data
# ---------------------------------------------------------------------------

class GamedataSection(q.QWidget):
    """Scrollable vertical list of FlagCards, one per event reference.

    Cards for the same flag name share the same fields dict.
    No manual add — flags come from eventflow scanning only."""

    gamedataChanged = qc.pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._flags: typing.Dict[str, dict] = {}   # flag_name → shared fields
        self._cards: list = []                      # list of FlagCard
        self._card_keys: typing.Set[str] = set()
        self._current_flow: typing.Optional[EventFlow] = None

        layout = q.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar (rescan only, no add)
        tb = q.QHBoxLayout()
        self._rescan_btn = q.QPushButton(tr('gamedata.rescan'))
        self._rescan_btn.clicked.connect(self._onRescan)
        tb.addWidget(self._rescan_btn)
        tb.addStretch()
        layout.addLayout(tb)

        # Scroll area for cards
        self._scroll = q.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet('QScrollArea { border: none; }')

        self._card_container = q.QWidget()
        self._card_layout = q.QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(2, 2, 2, 2)
        self._card_layout.setSpacing(3)
        self._card_layout.addStretch()
        self._scroll.setWidget(self._card_container)

        layout.addWidget(self._scroll, 1)

        # Update button text and card templates when language changes
        Tr.instance.languageChanged.connect(self._update_texts)

    @property
    def flags(self) -> typing.Dict[str, dict]:
        return self._flags

    @flags.setter
    def flags(self, value: typing.Dict[str, dict]) -> None:
        self._flags = value

    def _update_texts(self, _lang: str = '') -> None:
        """Update rescan button and all flag card template names."""
        self._rescan_btn.setText(tr('gamedata.rescan'))
        for card in self._cards:
            card._update_texts()

    def set_flow(self, flow: typing.Optional[EventFlow]) -> None:
        """Scan flow, deduplicate flags by name, rebuild cards."""
        self._current_flow = flow
        if not flow:
            self._flags.clear()
            self._rebuild_cards([])
            return

        # Scan events → deduplicate to unique flag names (过滤原版白名单)
        event_refs = scan_flag_events(flow)
        unique_flags = [fn for fn in dict.fromkeys(fn for _, _, fn in event_refs)
                        if not is_vanilla_gamedata(fn)]

        # Ensure shared data exists for each flag
        for flag_name in unique_flags:
            if flag_name not in self._flags:
                self._flags[flag_name] = dict(TEMPLATE_A, HashValue=flag_hash(flag_name),
                                              Template='A')
            if 'HashValue' not in self._flags[flag_name]:
                self._flags[flag_name]['HashValue'] = flag_hash(flag_name)
            if 'Template' not in self._flags[flag_name]:
                self._flags[flag_name]['Template'] = 'A'

        self._rebuild_cards(unique_flags)

    def _rebuild_cards(self, flag_names: list) -> None:
        """Rebuild FlagCards from unique flag names."""
        # Remove existing cards
        for card in self._cards:
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._card_keys.clear()

        # Remove stretch if present
        count = self._card_layout.count()
        if count > 0:
            item = self._card_layout.takeAt(count - 1)
            if item:
                del item

        for flag_name in flag_names:
            if flag_name in self._card_keys:
                continue
            self._card_keys.add(flag_name)
            shared_fields = self._flags[flag_name]
            card = FlagCard(flag_name, shared_fields)
            card.removed.connect(self._make_remove_handler(flag_name, card))
            card.changed.connect(self.gamedataChanged.emit)
            self._cards.append(card)
            self._card_layout.addWidget(card)

        self._card_layout.addStretch()

    def _make_remove_handler(self, key: str, card: FlagCard):
        """Remove just this card, not the shared flag data."""
        def handler():
            self._card_keys.discard(key)
            self._cards.remove(card)
            self._card_layout.removeWidget(card)
            card.deleteLater()
            self.gamedataChanged.emit()
        return handler

    def _onRescan(self) -> None:
        if self._current_flow:
            self.set_flow(self._current_flow)
            self.gamedataChanged.emit()
