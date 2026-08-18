import enum
import json
import os
from eventeditor.actor_model import ActorModel
from eventeditor.autosave import AutoSaveSystem
from eventeditor.entry_point_model import EntryPointModel
from eventeditor.event_model import EventModel
import eventeditor.util as util
from evfl import EventFlow
import PyQt5.QtCore as qc # type: ignore
import re
import typing

class FlowDataChangeReason(enum.Flag):
    Unknown = enum.auto()
    Reset = enum.auto()
    Actors = enum.auto()
    Events = enum.auto()
    EventParameters = enum.auto()
    EventFlowRename = enum.auto()


def _get_translations_path() -> str:
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'translations.json')


def load_translations() -> typing.Dict[str, typing.Dict[str, str]]:
    path = _get_translations_path()
    if not os.path.isfile(path):
        return {'keys': {}, 'actions': {}, 'queries': {}, 'types': {}, 'actors': {}, 'actor_subnames': {}}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            'keys': data.get('keys', {}),
            'actions': data.get('actions', {}),
            'queries': data.get('queries', {}),
            'types': data.get('types', {}),
            'actors': data.get('actors', {}),
            'actor_subnames': data.get('actor_subnames', {}),
        }
    except Exception:
        return {'keys': {}, 'actions': {}, 'queries': {}, 'types': {}, 'actors': {}, 'actor_subnames': {}}


class FlowData(qc.QObject):
    flowDataChanged = qc.pyqtSignal(FlowDataChangeReason)
    fileLoaded = qc.pyqtSignal(EventFlow)
    notesDisplayChanged = qc.pyqtSignal(bool)
    dialogueDataChanged = qc.pyqtSignal()  # emitted when dialogue text is loaded or edited

    def __init__(self) -> None:
        super().__init__()

        self.auto_save = AutoSaveSystem()
        self.fileLoaded.connect(lambda: self.auto_save.reset())
        self.flowDataChanged.connect(lambda reason: self.auto_save.save(self.flow))

        self.flow: typing.Optional[EventFlow] = None

        # Dialogue text integration — shared TextDatabase, set by MainWindow
        self.text_database: typing.Optional[typing.Any] = None

        self.actor_model = ActorModel()
        self.entry_point_model = EntryPointModel()
        self.event_model = EventModel()

        util.connect_model_change_signals(self.actor_model, self, FlowDataChangeReason.Actors)
        util.connect_model_change_signals(self.entry_point_model, self, FlowDataChangeReason.Events)
        util.connect_model_change_signals(self.event_model, self, FlowDataChangeReason.Events)

        self._next_event_idx = 0

        # Translations cache for notes (注释)
        self._translations_cache: typing.Optional[typing.Dict[str, typing.Dict[str, str]]] = None

        # Notes (注释) display toggle
        self._notes_display = False

    def setFlow(self, flow: typing.Optional[EventFlow]) -> None:
        self.flow = flow
        self.actor_model.set(flow)
        self.entry_point_model.set(flow)
        self.event_model.set(flow)
        self.flowDataChanged.emit(FlowDataChangeReason.Reset)
        self.fileLoaded.emit(flow)

        self._next_event_idx = self.computeNextEventIdx()

    def computeNextEventIdx(self) -> int:
        if not self.flow or not self.flow.flowchart:
            return -1
        pattern = re.compile(r'^Event(\d+)$')
        max_id = 0
        for event in self.flow.flowchart.events:
            match = pattern.match(event.name)
            if match:
                max_id = max(max_id, int(match[1]))
        return max_id + 1

    def generateEventName(self) -> str:
        name = f'Event{self._next_event_idx}'
        self._next_event_idx += 1
        return name

    # ---- Notes (注释) ----

    def get_notes_display(self) -> bool:
        return self._notes_display

    def set_notes_display(self, enabled: bool) -> None:
        if self._notes_display == enabled:
            return
        self._notes_display = enabled
        self.notesDisplayChanged.emit(enabled)

    def get_translations(self) -> typing.Dict[str, typing.Dict[str, str]]:
        if self._translations_cache is None:
            self._translations_cache = load_translations()
        return self._translations_cache

    # ---- Dialogue text (对话文本) ----

    def get_dialogue_text(self, message_id: str) -> typing.Optional[str]:
        """Look up dialogue text for a given MessageId."""
        if self.text_database:
            entry = self.text_database.lookup_by_message_id(message_id)
            if entry:
                return entry.text
        return None

    def get_dialogue_texts_map(self) -> typing.Dict[str, str]:
        """Build a dict of MessageId -> preview_text for flowchart display."""
        if not self.text_database:
            return {}
        return self.text_database.get_dialogue_texts_map()

    def get_dialogue_texts_for_labels(self, labels: typing.Set[str]) -> typing.Dict[str, str]:
        """Build dialogueTexts dict for specific labels only (filtered for performance)."""
        if not self.text_database or not labels:
            return {}
        result: typing.Dict[str, str] = {}
        for label in labels:
            entry = self.text_database.lookup(label)
            if entry:
                result[label] = entry.text
                msbt_root = entry.msbt_file
                if msbt_root.endswith('.msyt'):
                    msbt_root = msbt_root[:-5]
                result[f'{msbt_root}:{label}'] = entry.text
        return result
