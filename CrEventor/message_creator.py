"""New message creation dialog for EventEditor DX.

Triggered when double-clicking a Talk node that has no MessageId
parameter.  Auto-generates a label from the EventFlow name and
node index, creates the MessageId parameter in the EventFlow event,
and adds the entry to the TextDatabase.
"""

import typing

import PyQt5.QtCore as qc  # type: ignore
import PyQt5.QtWidgets as q  # type: ignore

from evfl import Container
import evfl.event

from CrEventor.text_database import TextDatabase
from CrEventor.i18n import tr


# Talk-related action names
TALK_ACTION_KEYWORDS = frozenset({
    'Talk',
    'EventTalk',
    'DemoTalk',
    'NpcTalk',
    'GeneralTalk',
    'MessageDialog',
    'OpenMessageDialog',
})


def is_talk_event(event: evfl.event.Event) -> bool:
    """Return True if this event is a Talk-type dialogue node."""
    data = event.data
    if isinstance(data, evfl.event.ActionEvent):
        action_name = str(data.actor_action.v) if data.actor_action.v else ''
        return any(kw in action_name for kw in TALK_ACTION_KEYWORDS)
    return False


def get_message_id(event: evfl.event.Event) -> typing.Optional[str]:
    """Extract the MessageId parameter from an event, if present."""
    data = event.data
    if not hasattr(data, 'params') or not data.params:
        return None
    return data.params.data.get('MessageId')


def generate_message_label(flow_name: str, event_index: int) -> str:
    """Auto-generate a MessageId label.

    Format: {EventFlowName}_{NodeIndex:03d}
    Example: Demo103_0_042
    """
    return f'{flow_name}_{event_index:03d}'


class MessageCreatorDialog(q.QDialog):
    """Dialog for creating a new MessageId on a Talk node."""

    messageCreated = qc.pyqtSignal(str, str)  # (label, text)

    def __init__(
        self,
        parent: typing.Optional[q.QWidget],
        text_db: TextDatabase,
        flow_name: str,
        event: evfl.event.Event,
        event_index: int,
        default_msbt: str = '',
    ) -> None:
        super().__init__(
            parent,
            qc.Qt.WindowTitleHint | qc.Qt.WindowSystemMenuHint,
        )
        self.setWindowTitle(tr('dialogue.title'))
        self.setMinimumWidth(450)
        self._text_db = text_db
        self._event = event
        self._event_index = event_index

        suggested_label = generate_message_label(flow_name, event_index)

        # Default MSBT path uses .msyt internally but presents .msbt to user
        if not default_msbt:
            default_msbt = f'EventFlowMsg/{flow_name}.msbt'

        layout = q.QVBoxLayout(self)

        form = q.QFormLayout()

        self._label_edit = q.QLineEdit(suggested_label)
        form.addRow(tr('dialogue.label'), self._label_edit)

        self._msbt_edit = q.QLineEdit(default_msbt)
        form.addRow(tr('dialogue.msbt_file'), self._msbt_edit)

        self._text_edit = q.QPlainTextEdit()
        self._text_edit.setPlaceholderText(tr('dialogue.unsaved_prompt'))
        self._text_edit.setMinimumHeight(100)
        form.addRow(tr('dialogue.char_count'), self._text_edit)

        layout.addLayout(form)

        btn_box = q.QDialogButtonBox(
            q.QDialogButtonBox.Ok | q.QDialogButtonBox.Cancel,
        )
        btn_box.accepted.connect(self._on_create)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_create(self) -> None:
        label = self._label_edit.text().strip()
        msbt_file = self._msbt_edit.text().strip()
        text = self._text_edit.toPlainText()

        if not label:
            q.QMessageBox.critical(self, tr('flowchart.import.error'), 'Message ID cannot be empty.')
            return
        if not msbt_file:
            q.QMessageBox.critical(self, tr('flowchart.import.error'), 'MSBT file path cannot be empty.')
            return

        # Convert .msbt to .msyt for internal BCML storage
        msyt_file = msbt_file
        if msyt_file.endswith('.msbt'):
            msyt_file = msyt_file[:-5] + '.msyt'

        # Check per-MSBT file, not globally (different MSBTs can share labels)
        if msyt_file in self._text_db._msyt_data:
            if label in self._text_db._msyt_data[msyt_file]:
                q.QMessageBox.critical(
                    self, tr('flowchart.import.error'),
                    f"Message ID '{label}' already exists in this file.",
                )
                return

        # Create entry in TextDatabase
        self._text_db.create(label, text, msyt_file)

        # Add MessageId parameter to the EventFlow event
        event_data = self._event.data
        if hasattr(event_data, 'params'):
            if not event_data.params:
                event_data.params = Container()

            # Use .msbt root in the MessageId format for EventFlow
            msbt_root = msbt_file
            if msbt_root.endswith('.msbt'):
                msbt_root = msbt_root[:-5]
            full_message_id = f'{msbt_root}:{label}'

            event_data.params.data['MessageId'] = full_message_id

        self.messageCreated.emit(label, text)
        self.accept()
