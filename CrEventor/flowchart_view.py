"""CrEventor-specific FlowchartView integration.

Keeps upstream event-editor-master untouched while routing every existing
MessageId, including an entry with no text yet, through the modern editor.
"""

import os
import sys

from PyQt5 import QtCore as qc
from PyQt5 import QtWidgets as q

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UPSTREAM_DIR = os.path.join(_PROJECT_ROOT, 'event-editor-master')
if _UPSTREAM_DIR not in sys.path:
    sys.path.insert(0, _UPSTREAM_DIR)

from eventeditor.flow_data import FlowDataChangeReason
from eventeditor.flowchart_view import (
    FlowchartView as UpstreamFlowchartView,
    _get_message_id,
    _is_talk_event,
    _msg_id_to_msyt_path,
)

from CrEventor.i18n import tr


class FlowchartView(UpstreamFlowchartView):
    """Flowchart view with the modern MessageId text editor."""

    @staticmethod
    def _text_attribute_from_event(event) -> str:
        """Return the speaker ActorIdentifier name used by MSYT attributes."""
        try:
            actor = event.data.actor.v
            identifier = actor.identifier
            return str(identifier.name or '')
        except (AttributeError, TypeError):
            return ''

    def _open_modern_text_editor(self, text_db, label: str, msbt_file: str,
                                 event=None):
        from CrEventor.text_editor_dialog import TextEditorIntegrationDialog

        dialog = TextEditorIntegrationDialog(
            self, text_db, label, msbt_file,
            attributes=self._text_attribute_from_event(event) if event else None,
        )
        dialog.textSaved.connect(
            lambda _label, _contents: self.flow_data.dialogueDataChanged.emit()
        )
        dialog.exec_()

    def webEditDialogue(self, idx: int) -> None:
        """Return from the flowchart WebChannel call before opening WebEngine."""
        if idx < 0:
            return
        if getattr(self, '_dialogue_open_pending', False):
            return
        self._dialogue_open_pending = True
        qc.QTimer.singleShot(0, lambda event_idx=idx: self._open_dialogue_deferred(event_idx))

    def _open_dialogue_deferred(self, idx: int) -> None:
        """Open after Chromium's synchronous QWebChannel slot has returned."""
        self._dialogue_open_pending = False

        assert self.flow_data.flow and self.flow_data.flow.flowchart
        event = self.flow_data.flow.flowchart.events[idx]
        if not _is_talk_event(event):
            return

        text_db = self.flow_data.text_database
        if text_db is None:
            q.QMessageBox.information(
                self, tr('dialogue.title'), tr('dialogue.reload_failed'),
            )
            return

        message_id = _get_message_id(event)
        if message_id:
            entry = text_db.lookup_by_message_id(message_id)
            if entry is None:
                msbt_file = _msg_id_to_msyt_path(message_id)
                label = message_id.rsplit(':', 1)[-1]
                if msbt_file:
                    text_db.ensure_message_entry(msbt_file, label)
                    entry = text_db.lookup_by_message_id(message_id)
            if entry is not None:
                self._open_modern_text_editor(
                    text_db, entry.label, entry.msbt_file, event,
                )
                return

        # A node with no MessageId still needs the small identity dialog to
        # define its label/MSBT path.  Once created, immediately open it in the
        # modern editor instead of leaving the user in the legacy text box.
        from CrEventor.message_creator import MessageCreatorDialog

        flow_name = self.flow_data.flow.name if self.flow_data.flow else 'Unknown'
        default_msbt = ''
        if message_id and ':' in message_id:
            default_msbt = f'{message_id.rsplit(":", 1)[0]}.msbt'
        dialog = MessageCreatorDialog(
            self, text_db, flow_name, event, idx, default_msbt,
        )
        if message_id:
            dialog._label_edit.setText(message_id.rsplit(':', 1)[-1])
        if dialog.exec_() != q.QDialog.Accepted:
            return

        self.flow_data.flowDataChanged.emit(FlowDataChangeReason.EventParameters)
        self.flow_data.dialogueDataChanged.emit()
        new_message_id = _get_message_id(event)
        new_entry = text_db.lookup_by_message_id(new_message_id) if new_message_id else None
        if new_entry is not None:
            self._open_modern_text_editor(
                text_db, new_entry.label, new_entry.msbt_file, event,
            )
