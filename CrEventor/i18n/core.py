"""Core i18n module for EventEditor DX.

Provides a singleton Tr class that manages the current language and
provides string lookups with optional formatting.

Usage:
    from CrEventor.i18n import tr, Tr

    # Get translated string
    text = tr("menu.file")
    text = tr("dialog.unsaved_changes", name="MyFlow")

    # Change language (emits signal, UI must rebuild)
    Tr.instance.set_language("en_US")
"""

import typing

from PyQt5.QtCore import QObject, pyqtSignal  # type: ignore

from CrEventor.i18n.locales.zh_CN import STRINGS as ZH_CN_STRINGS
from CrEventor.i18n.locales.en_US import STRINGS as EN_US_STRINGS

SUPPORTED_LANGUAGES = {
    "zh_CN": "简体中文",
    "en_US": "English",
}
DEFAULT_LANGUAGE = "zh_CN"

_LOCALES: typing.Dict[str, typing.Dict[str, str]] = {
    "zh_CN": ZH_CN_STRINGS,
    "en_US": EN_US_STRINGS,
}


def _merge_missing(source: dict, target: dict, prefix: str = "") -> int:
    """Copy keys from source into target if missing in target. Returns count added."""
    count = 0
    for key, value in source.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict):
            if key not in target:
                target[key] = {}
            count += _merge_missing(value, target[key], f"{full_key}.")
        elif key not in target:
            target[key] = value
            count += 1
    return count


# Ensure all locales have all keys (fill from zh_CN)
for lang in _LOCALES:
    if lang != "zh_CN":
        _merge_missing(ZH_CN_STRINGS, _LOCALES[lang])


class Tr(QObject):
    """Singleton i18n manager.

    Emits languageChanged when the language is switched.
    """

    instance: typing.Optional["Tr"] = None
    languageChanged = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._language = DEFAULT_LANGUAGE
        Tr.instance = self

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        if value not in _LOCALES:
            return
        if value == self._language:
            return
        self._language = value
        self.languageChanged.emit(value)

    def set_language(self, lang: str) -> None:
        self.language = lang

    def get(self, key: str, **kwargs) -> str:
        """Look up a translated string by key.

        Supports mixed key formats:
          - "app.title" → literal flat key
          - "menu.file.new" → longest prefix match: "menu.file" dict → "new"
          - "menu.file" → tree walk: STRINGS["menu"]["file"]

        Args:
            key: Translation key.
            **kwargs: Format arguments for the string.

        Returns:
            Translated string, or the key itself if not found.
        """
        d: typing.Any = _LOCALES.get(self._language, ZH_CN_STRINGS)

        # Strategy 1: exact literal key (works for "app.title", "dialog.unsaved_changes_text")
        if key in d:
            v = d[key]
            if isinstance(v, str):
                return self._format(v, kwargs)
            # If it's a dict, fall through — the key might be a namespace prefix

        # Strategy 2: longest dotted prefix that maps to a dict,
        # then key the remainder from that dict.
        # e.g. "menu.file.new" → prefix "menu.file" → lookup "new" in it
        parts = key.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in d and isinstance(d[prefix], dict):
                remainder = ".".join(parts[i:])
                v = d[prefix].get(remainder)
                if isinstance(v, str):
                    return self._format(v, kwargs)

        # Strategy 3: tree walk split by dots
        # e.g. "menu.file" → STRINGS["menu"]["file"]
        for part in parts:
            if isinstance(d, dict):
                d = d.get(part)
            else:
                return key
            if d is None:
                return key
        if isinstance(d, str):
            return self._format(d, kwargs)
        return key

    @staticmethod
    def _format(text: str, kwargs: dict) -> str:
        if not kwargs:
            return text
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text


def tr(key: str, **kwargs) -> str:
    """Shortcut to get a translated string from the singleton."""
    if Tr.instance is None:
        Tr()
    return Tr.instance.get(key, **kwargs)
