"""Text database — extracts MSBT files from built-in BCML data, loads/saves
extracted texts, and provides O(1) lookup with modification tracking.

Architecture:
  1. User triggers "提取文本" → extract_from_builtin() reads built-in data,
     extracts full MSYT files for all MessageIds used in open flows.
  2. Each flow's texts are saved as Texts/{flow_name}.json.
  3. On project load, load_extracted() reads from Texts/.
  4. All editing goes through update()/create()/option pool methods.
  5. On save, per-flow texts are written back to Texts/ and backup folder.

Key invariant: each extracted file contains the COMPLETE MSYT file
(all entries), not just modified ones.  This ensures a coherent MSBT
that works with BCML.
"""

import json
import os
import re
import typing

from dataclasses import dataclass, field

from CrEventor import texts as game_texts


@dataclass
class TextEntry:
    """A single dialogue text entry from a BCML MSYT file."""

    label: str
    text: str              # first text segment (preview)
    msbt_file: str          # e.g. "EventFlowMsg/Demo103_0.msyt"
    modified: bool = False
    is_new: bool = False
    # Full BCML entry: {"attributes": "Npc_Hylia", "contents": [...]}
    _raw_entry: dict = field(default_factory=dict, repr=False)


class TextDatabase:
    """Fast-lookup text database with modification tracking.

    Loads from built-in texts JSON on demand.  Keyed by label for
    O(1) lookup; also indexes by MSBT path for batch queries.
    """

    def __init__(self) -> None:
        self._entries: typing.Dict[str, TextEntry] = {}
        self._msyt_data: typing.Dict[str, dict] = {}  # msyt_path -> {label: raw_entry}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Extraction from built-in (manual trigger only)
    # ------------------------------------------------------------------

    def extract_from_builtin(
        self, msyt_paths: typing.Set[str], platform: str, language: str = '',
    ) -> int:
        """Extract FULL MSYT files from the built-in texts JSON.

        This is the ONLY place that reads the built-in data.  It extracts
        every entry from each requested MSYT file and populates both
        ``_entries`` and ``_msyt_data``.

        Any existing data is cleared first.

        Returns the number of entries loaded.
        """
        path = game_texts.get_builtin_texts_path(platform, language)
        if not path:
            return 0

        with open(path, 'r', encoding='utf-8') as f:
            source = json.load(f)

        lang_key = language or ('CNzh' if platform == 'switch' else 'JPja')
        if lang_key not in source:
            for k in source:
                if isinstance(source[k], dict):
                    lang_key = k
                    break

        all_texts = source.get(lang_key, {})
        if not isinstance(all_texts, dict):
            return 0

        if msyt_paths:
            self._entries.clear()
            self._msyt_data.clear()

        count = 0
        for msyt_path in msyt_paths:
            entries = all_texts.get(msyt_path)
            if not isinstance(entries, dict):
                continue
            # Deep-copy — do NOT share references with the source dict.
            # This ensures modifications to the database never leak back
            # into the built-in data.
            copied_entries = {k: dict(v) for k, v in entries.items()}
            self._msyt_data[msyt_path] = copied_entries
            for label, raw_entry in copied_entries.items():
                if not isinstance(raw_entry, dict):
                    continue
                text_preview = self._extract_text(raw_entry)
                self._entries[label] = TextEntry(
                    label=label,
                    text=text_preview,
                    msbt_file=msyt_path,
                    _raw_entry=raw_entry,
                )
                count += 1

        if count:
            self._loaded = True
        return count

    def load_extracted(self, texts_dir: str, language: str,
                       clear_first: bool = True) -> int:
        """Load texts from previously extracted per-flow JSON files.

        Reads all .json files in *texts_dir*, merges their MSYT entries
        into ``_msyt_data`` and ``_entries``.

        When *clear_first* is True (default), existing data is cleared
        before loading.  Set to False when merging backups on top of a
        baseline that was already loaded from built-in data.
        """
        if clear_first:
            self._entries.clear()
            self._msyt_data.clear()
            self._loaded = False

        if not os.path.isdir(texts_dir):
            return 0

        count = 0
        for fname in sorted(os.listdir(texts_dir)):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(texts_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            texts = data.get(language, {})
            if not isinstance(texts, dict):
                continue

            for msyt_path, entries in texts.items():
                if not isinstance(entries, dict):
                    continue
                if msyt_path not in self._msyt_data:
                    self._msyt_data[msyt_path] = {}
                target = self._msyt_data[msyt_path]
                for label, raw_entry in entries.items():
                    if not isinstance(raw_entry, dict):
                        continue
                    target[label] = raw_entry
                    self._entries[label] = TextEntry(
                        label=label,
                        text=self._extract_text(raw_entry),
                        msbt_file=msyt_path,
                        _raw_entry=raw_entry,
                    )
                    count += 1

        if count:
            self._loaded = True
        return count

    def merge_backup_dir(self, backup_dir: str, language: str) -> int:
        """Merge all .texts.json files from *backup_dir* onto the current
        database without clearing.  Returns count of entries merged.

        Used to overlay user modifications (pool entries, choice controls,
        edited texts) from a backup folder on top of the baseline that was
        loaded from the Texts/ directory.
        """
        if not os.path.isdir(backup_dir):
            return 0

        count = 0
        for fname in sorted(os.listdir(backup_dir)):
            if not fname.endswith('.texts.json'):
                continue
            fpath = os.path.join(backup_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            texts = data.get(language, {})
            if not isinstance(texts, dict):
                continue

            for msyt_path, entries in texts.items():
                if not isinstance(entries, dict):
                    continue
                if msyt_path not in self._msyt_data:
                    self._msyt_data[msyt_path] = {}
                target = self._msyt_data[msyt_path]
                for label, raw_entry in entries.items():
                    if not isinstance(raw_entry, dict):
                        continue
                    target[label] = raw_entry
                    # Update or create the TextEntry
                    if label in self._entries:
                        self._entries[label].text = self._extract_text(raw_entry)
                        self._entries[label]._raw_entry = raw_entry
                    else:
                        self._entries[label] = TextEntry(
                            label=label,
                            text=self._extract_text(raw_entry),
                            msbt_file=msyt_path,
                            _raw_entry=raw_entry,
                        )
                    count += 1

        if count:
            self._loaded = True
        return count

    def save_for_flow(self, msyt_paths: typing.Set[str], language: str) -> dict:
        """Return export dict containing only the specified MSYT paths.

        Returns {language: {msyt_path: {label: raw_entry}}}.
        Pool entries (0000-9999) are placed at the start of each MSBT.
        """
        result: dict = {}
        for msyt_path in sorted(msyt_paths):
            msyt = self._msyt_data.get(msyt_path)
            if msyt:
                ordered: dict = {}
                for key in self._sorted_msyt_keys(msyt):
                    ordered[key] = self._clean_for_export(msyt[key])
                result[msyt_path] = ordered
        return {language: result}

    @staticmethod
    def _extract_text(raw_entry: dict) -> str:
        """Extract ALL text segments (concatenated) from a BCML entry for preview.
        
        Control items are skipped; text items are concatenated directly.
        Real newline characters (\n) in text items are preserved as-is.
        """
        contents = raw_entry.get('contents', [])
        texts = []
        for item in contents:
            if isinstance(item, dict) and 'text' in item:
                texts.append(str(item['text']))
        return ''.join(texts)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup(self, label: str) -> typing.Optional[TextEntry]:
        """Fast O(1) lookup by label."""
        return self._entries.get(label)

    def has(self, label: str) -> bool:
        return label in self._entries

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def all_labels(self) -> typing.List[str]:
        return list(self._entries.keys())

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # MessageId-aware lookup (handles split-MSBT concern)
    # ------------------------------------------------------------------

    def lookup_by_message_id(self, message_id: str) -> typing.Optional[TextEntry]:
        """Look up text by full MessageId from EventFlow.

        Per spec, MessageId format is:
            "EventFlowMsg/{msyt_name}:{key}"
        where {msyt_name} has NO extension.  The MSYT path in texts.json is:
            "EventFlowMsg/{msyt_name}.msyt"

        Matching strategy (in order):
          1. Exact match on the key within the target MSYT file.
          2. Prefix match: key starts with search_key + '_' boundary
             (handles suffix variations like Talk_40 → Talk_40_NPC_RFancier).
          3. Zero-padded numeric match: e.g. Talk_40 matches Talk_0040.
        """
        if not message_id or ':' not in message_id:
            return None

        path_part, search_key = message_id.rsplit(':', 1)

        # Strip any existing extension (.msbt, .msyt)
        if path_part.endswith('.msyt'):
            path_part = path_part[:-5]
        elif path_part.endswith('.msbt'):
            path_part = path_part[:-5]

        msyt_path = path_part + '.msyt'
        msyt_entries = self._msyt_data.get(msyt_path)
        if not msyt_entries:
            return None

        # Build candidate keys: original + zero-padded numeric variant
        candidates = [search_key]
        padded = self._pad_number(search_key)
        if padded != search_key:
            candidates.append(padded)

        for candidate in candidates:
            # 1) Exact match
            raw_entry = msyt_entries.get(candidate)
            if isinstance(raw_entry, dict):
                return TextEntry(
                    label=candidate, text=self._extract_text(raw_entry),
                    msbt_file=msyt_path, _raw_entry=raw_entry,
                )

            # 2) Prefix match – key starts with candidate followed by '_'
            for key, raw_entry in msyt_entries.items():
                if not isinstance(raw_entry, dict):
                    continue
                if (key.startswith(candidate)
                        and len(key) > len(candidate)
                        and key[len(candidate)] == '_'):
                    return TextEntry(
                        label=key, text=self._extract_text(raw_entry),
                        msbt_file=msyt_path, _raw_entry=raw_entry,
                    )

        return None

    @staticmethod
    def _pad_number(key: str) -> str:
        """Zero-pad the numeric portion of a key for matching.

        E.g. 'Talk_40' → 'Talk_0040'
             'Talk_40_NPC_RFancier' → 'Talk_0040_NPC_RFancier'
             'MDQ_Open' → 'MDQ_Open' (no digits, returned as-is)
        """
        m = re.match(r'^(.+_)(\d+)(_.*)?$', key)
        if m:
            prefix = m.group(1)
            num = m.group(2)
            suffix = m.group(3) or ''
            return prefix + num.zfill(4) + suffix
        return key

    def find_all_by_label(self, label: str) -> typing.List[TextEntry]:
        """Find ALL entries matching the given label across ALL MSYT files.

        Returns a list because texts from the same original MSBT may have
        been split into multiple .msyt keys in the BCML format.
        """
        entry = self._entries.get(label)
        if entry:
            return [entry]
        return []

    # ------------------------------------------------------------------
    # Modification
    # ------------------------------------------------------------------

    def update(self, label: str, text: str, msbt_file: str = '') -> None:
        """Update text for an existing entry and mark it as modified.

        When ``msbt_file`` is given, patches the raw entry in the correct
        MSYT file directly (via ``_msyt_data``).  This avoids collisions
        when different MSBT files share the same label.
        """
        raw_entry = None
        if msbt_file and msbt_file in self._msyt_data:
            raw_entry = self._msyt_data[msbt_file].get(label)

        if raw_entry is None:
            # Fallback: global _entries lookup
            entry = self._entries.get(label)
            if entry is None:
                raise KeyError(f"Label not found in TextDatabase: {label}")
            raw_entry = entry._raw_entry

        # Extract current text via _extract_text on the raw entry
        current_text = self._extract_text(raw_entry)
        if current_text == text:
            return

        # Patch the first text item in-place
        contents = raw_entry.get('contents', [])
        for item in contents:
            if isinstance(item, dict) and 'text' in item:
                item['text'] = text
                break
        else:
            contents.insert(0, {'text': text})

        # Sync _entries for consistency
        entry = self._entries.get(label)
        if entry:
            entry.text = text
            entry.modified = True

    def create(self, label: str, text: str, msbt_file: str) -> TextEntry:
        """Create a brand-new text entry (new MessageId).

        Checks for duplicates within the same MSBT file only (different
        MSBT files may legitimately share the same label).
        """
        if msbt_file in self._msyt_data and label in self._msyt_data[msbt_file]:
            raise ValueError(
                f"Label '{label}' already exists in {msbt_file}")
        entry = TextEntry(
            label=label,
            text=text,
            msbt_file=msbt_file,
            modified=True,
            is_new=True,
            _raw_entry={'contents': [{'text': text}]},
        )
        self._entries[label] = entry
        # Also register in msyt_data for path-based lookup
        if msbt_file not in self._msyt_data:
            self._msyt_data[msbt_file] = {}
        self._msyt_data[msbt_file][label] = entry._raw_entry
        return entry

    def get_raw_entry(self, label: str, msbt_file: str = '') -> typing.Optional[dict]:
        """Return the raw BCML entry dict for a label (NOT a copy – 
        modifications to the returned dict affect the database)."""
        if msbt_file and msbt_file in self._msyt_data:
            return self._msyt_data[msbt_file].get(label)
        entry = self._entries.get(label)
        if entry:
            return entry._raw_entry
        return None

    def update_full_contents(self, label: str, msbt_file: str,
                             contents: list, attributes: str = '') -> None:
        """Replace the entire contents array (text + controls) for an entry.

        This is the main integration point for the standalone TextEditor:
        after editing text with controls, the full contents array is written
        back via this method.
        """
        raw_entry = None
        if msbt_file and msbt_file in self._msyt_data:
            raw_entry = self._msyt_data[msbt_file].get(label)
        if raw_entry is None:
            entry = self._entries.get(label)
            if entry is None:
                raise KeyError(f"Label not found in TextDatabase: {label}")
            raw_entry = entry._raw_entry

        raw_entry['contents'] = contents
        # ``attributes`` is part of every complete MSYT entry.  In the
        # CrEventor integration it is synchronized from the Talk Event actor;
        # write it even when empty so stale speaker data can be cleared.
        raw_entry['attributes'] = attributes

        # Sync _entries
        entry = self._entries.get(label)
        if entry:
            entry.text = self._extract_text(raw_entry)
            entry.modified = True
            entry._raw_entry = raw_entry

    def update_attributes_by_message_id(self, message_id: str,
                                        attributes: str) -> bool:
        """Synchronize one MSYT entry's speaker attribute from EventFlow."""
        entry = self.lookup_by_message_id(message_id)
        if entry is None:
            return False
        raw_entry = self.get_raw_entry(entry.label, entry.msbt_file)
        if raw_entry is None:
            return False
        value = str(attributes or '')
        if raw_entry.get('attributes') != value:
            raw_entry['attributes'] = value
            entry.modified = True
            entry._raw_entry = raw_entry
        return True

    # ------------------------------------------------------------------
    # Incremental save helpers
    # ------------------------------------------------------------------

    def get_modified_msbt_files(self) -> typing.Set[str]:
        """Return the set of MSBT file paths that contain modified entries."""
        return {
            entry.msbt_file
            for entry in self._entries.values()
            if entry.modified
        }

    def get_entries_for_msbt(self, msbt_file: str) -> typing.List[TextEntry]:
        """Return all entries belonging to a given MSBT file."""
        return [
            entry
            for entry in self._entries.values()
            if entry.msbt_file == msbt_file
        ]

    def mark_saved(self) -> None:
        """Clear the modified flag on all entries after a successful save."""
        for entry in self._entries.values():
            entry.modified = False
            entry.is_new = False

    # ------------------------------------------------------------------
    # Flowchart display helpers
    # ------------------------------------------------------------------

    def get_dialogue_texts_map(self) -> typing.Dict[str, str]:
        """Build a dict of MessageId -> preview_text for flowchart display.

        Returns both label-only keys and 'msbt_root:label' keys to
        match the MessageId format used in EventFlow params.
        """
        result: typing.Dict[str, str] = {}
        for label, entry in self._entries.items():
            result[label] = entry.text
            msbt_root = entry.msbt_file
            if msbt_root.endswith('.msyt'):
                msbt_root = msbt_root[:-5]
            result[f'{msbt_root}:{label}'] = entry.text
        return result

    # ------------------------------------------------------------------
    # Serialization (for future save-to-JSON functionality)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the full database to BCML-compatible JSON dict."""
        result: dict = {}
        for msyt_path, entries in self._msyt_data.items():
            result[msyt_path] = {}
            for label, raw_entry in entries.items():
                result[msyt_path][label] = raw_entry
        return result

    # ------------------------------------------------------------------
    # Option pool & choice control helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_pool_key(key: str) -> bool:
        """Return True if key is a numeric option-pool entry (4-digit string)."""
        return key.isdigit() and len(key) == 4

    @staticmethod
    def _sorted_msyt_keys(entries: typing.Dict[str, dict]) -> typing.List[str]:
        """Return keys sorted so that pool entries (0000-9999) come first."""
        pool_keys = sorted(
            [k for k in entries if TextDatabase.is_pool_key(k)],
            key=lambda k: int(k),
        )
        other_keys = sorted(k for k in entries if not TextDatabase.is_pool_key(k))
        return pool_keys + other_keys

    def get_option_pool(
        self, msyt_path: str,
    ) -> typing.Dict[str, str]:
        """Get all numeric option-pool entries for a given MSYT file.

        Returns {key: text_preview} where key is a 4-digit string like '0000'.
        Keys are sorted numerically.
        """
        entries = self._msyt_data.get(msyt_path, {})
        result: typing.Dict[str, str] = {}
        for key, raw_entry in entries.items():
            if isinstance(raw_entry, dict) and self.is_pool_key(key):
                result[key] = self._extract_text(raw_entry)
        return dict(sorted(result.items(), key=lambda x: int(x[0])))

    def get_or_create_pool_entry(
        self, msyt_path: str, key: str,
    ) -> typing.Optional[dict]:
        """Get a pool entry's raw dict, creating if it doesn't exist."""
        key = key.zfill(4)
        if msyt_path not in self._msyt_data:
            self._msyt_data[msyt_path] = {}
        entries = self._msyt_data[msyt_path]
        if key not in entries:
            entries[key] = {'attributes': '', 'contents': [{'text': ''}]}
        return entries[key]

    def set_pool_entry_text(
        self, msyt_path: str, key: str, text: str,
    ) -> None:
        """Set the text for a pool entry. Creates the entry if it doesn't exist.

        Patches the first text item in-place to preserve any control items.
        """
        raw = self.get_or_create_pool_entry(msyt_path, key)
        # Patch first text item in-place
        contents = raw.get('contents', [])
        for item in contents:
            if isinstance(item, dict) and 'text' in item:
                item['text'] = text
                break
        else:
            contents.insert(0, {'text': text})
        # Update _entries index too
        entry_key = key.zfill(4)
        for label, entry in list(self._entries.items()):
            if entry.msbt_file == msyt_path and label == entry_key:
                entry.text = text
                entry.modified = True
                entry._raw_entry = raw
                return
        # Not in _entries yet — add it
        self._entries[entry_key] = TextEntry(
            label=entry_key,
            text=text,
            msbt_file=msyt_path,
            modified=True,
            is_new=True,
            _raw_entry=raw,
        )

    def ensure_message_entry(self, msyt_path: str, label: str) -> dict:
        """Get or create a raw entry for a dialogue message label.

        Unlike pool entries (0000-9999), this creates a proper message entry
        with an empty text content so that choice controls can be attached.
        """
        if msyt_path not in self._msyt_data:
            self._msyt_data[msyt_path] = {}
        entries = self._msyt_data[msyt_path]
        if label not in entries:
            entries[label] = {'contents': [{'text': ''}]}
        raw = entries[label]
        # Also register in _entries
        if label not in self._entries:
            self._entries[label] = TextEntry(
                label=label,
                text=self._extract_text(raw),
                msbt_file=msyt_path,
                modified=True,
                is_new=True,
                _raw_entry=raw,
            )
        return raw

    def delete_pool_entry(self, msyt_path: str, key: str) -> bool:
        """Delete a pool entry. Returns True if successful."""
        key = key.zfill(4)
        entries = self._msyt_data.get(msyt_path)
        if not entries or key not in entries:
            return False
        del entries[key]
        self._entries.pop(key, None)
        return True

    @staticmethod
    def get_choice_control(raw_entry: dict) -> typing.Optional[dict]:
        """Extract the choice control from an entry's contents, if present."""
        contents = raw_entry.get('contents', [])
        for item in contents:
            if isinstance(item, dict) and 'control' in item:
                control = item['control']
                if isinstance(control, dict) and control.get('kind') == 'choice':
                    return control
        return None

    @staticmethod
    def get_single_choice_control(raw_entry: dict) -> typing.Optional[dict]:
        """Extract the single_choice control from an entry's contents, if present."""
        contents = raw_entry.get('contents', [])
        for item in contents:
            if isinstance(item, dict) and 'control' in item:
                control = item['control']
                if isinstance(control, dict) and control.get('kind') == 'single_choice':
                    return control
        return None

    @staticmethod
    def get_preceding_text(raw_entry: dict) -> str:
        """Get all text content BEFORE the first control in an entry."""
        contents = raw_entry.get('contents', [])
        texts = []
        for item in contents:
            if isinstance(item, dict):
                if 'text' in item:
                    texts.append(item['text'])
                elif 'control' in item:
                    break
        return '\n'.join(texts)

    @staticmethod
    def choice_unknown_value(choice_count: int) -> int:
        """Return the ``unknown`` field value for a choice control.

        Verified against 2405 real-world samples (0 exceptions):
            unknown = 2n + 2   where n = number of choice_labels.
        """
        return 2 * choice_count + 2

    @staticmethod
    def update_choice_control(
        raw_entry: dict,
        choice_labels: typing.List[int],
        selected_index: int = 0,
        cancel_index: int = 1,
        unknown: typing.Any = None,
    ) -> None:
        """Update or create the choice control in an entry's contents.

        The ``unknown`` field:
        - If explicitly provided, uses that value.
        - If None and the control already exists, preserves the existing value.
        - If None for a new control, computes ``unknown = 2n + 2``.
        """
        contents = raw_entry.get('contents', [])
        n = len(choice_labels)
        for item in contents:
            if isinstance(item, dict) and 'control' in item:
                control = item['control']
                if isinstance(control, dict) and control.get('kind') == 'choice':
                    control['choice_labels'] = choice_labels
                    control['selected_index'] = selected_index
                    control['cancel_index'] = cancel_index
                    if unknown is not None:
                        control['unknown'] = unknown
                    elif 'unknown' not in control:
                        control['unknown'] = TextDatabase.choice_unknown_value(n)
                    return
        # No existing choice control — append one
        new_control: dict = {
            'kind': 'choice',
            'choice_labels': choice_labels,
            'selected_index': selected_index,
            'cancel_index': cancel_index,
        }
        if unknown is not None:
            new_control['unknown'] = unknown
        else:
            new_control['unknown'] = TextDatabase.choice_unknown_value(n)
        contents.append({'control': new_control})
        raw_entry['contents'] = contents

    @staticmethod
    def update_single_choice_control(
        raw_entry: dict,
        label: int,
    ) -> None:
        """Update or create the single_choice control in an entry's contents."""
        contents = raw_entry.get('contents', [])
        for item in contents:
            if isinstance(item, dict) and 'control' in item:
                control = item['control']
                if isinstance(control, dict) and control.get('kind') == 'single_choice':
                    control['label'] = label
                    return
        # No existing single_choice control — append one
        contents.append({'control': {'kind': 'single_choice', 'label': label}})
        raw_entry['contents'] = contents

    @staticmethod
    def remove_single_choice_control(raw_entry: dict) -> None:
        """Remove the single_choice control from an entry's contents, if present."""
        contents = raw_entry.get('contents', [])
        for i, item in enumerate(contents):
            if isinstance(item, dict) and 'control' in item:
                control = item['control']
                if isinstance(control, dict) and control.get('kind') == 'single_choice':
                    contents.pop(i)
                    raw_entry['contents'] = contents
                    return

    @staticmethod
    def add_text_line(raw_entry: dict, text: str) -> None:
        """Append a text line to the end of contents (before any controls)."""
        contents = raw_entry.get('contents', [])
        # Find the position before the first control
        insert_at = len(contents)
        for i, item in enumerate(contents):
            if isinstance(item, dict) and 'control' in item:
                insert_at = i
                break
        contents.insert(insert_at, {'text': text})
        raw_entry['contents'] = contents

    # ------------------------------------------------------------------
    # Export / backup
    # ------------------------------------------------------------------

    @property
    def modified_count(self) -> int:
        """Number of entries with unsaved modifications (including new ones)."""
        return sum(1 for e in self._entries.values() if e.modified)

    def get_modified_entries(self) -> typing.List[TextEntry]:
        """Return all entries that have been modified or created."""
        return [e for e in self._entries.values() if e.modified]

    def export_merged(self, language: str) -> dict:
        """Export ALL loaded MSYT data (with modifications) for all files.

        Returns {language: {msyt_path: {label: raw_entry}}}.
        Pool entries (0000-9999) are placed at the start of each MSBT.
        """
        result: dict = {}
        for msyt_path in sorted(self._msyt_data.keys()):
            msyt = self._msyt_data[msyt_path]
            if msyt:
                ordered: dict = {}
                for key in self._sorted_msyt_keys(msyt):
                    ordered[key] = self._clean_for_export(msyt[key])
                result[msyt_path] = ordered
        return {language: result}
    @staticmethod
    def _clean_for_export(value):
        """Deep-copy BCML data and remove editor-only metadata."""
        if isinstance(value, dict):
            # Canonical MSYT entry order is attributes first, contents second.
            # Adding attributes later during Event synchronization must not
            # leave it after contents in the serialized JSON.
            if isinstance(value.get('contents'), list):
                result = {
                    'attributes': TextDatabase._clean_for_export(
                        value.get('attributes', ''),
                    ),
                    'contents': TextDatabase._clean_for_export(
                        value['contents'],
                    ),
                }
                for key, child in value.items():
                    if key not in ('attributes', 'contents', '_cid'):
                        result[key] = TextDatabase._clean_for_export(child)
                return result
            return {
                key: TextDatabase._clean_for_export(child)
                for key, child in value.items()
                if key != '_cid'
            }
        if isinstance(value, list):
            return [TextDatabase._clean_for_export(child) for child in value]
        return value
