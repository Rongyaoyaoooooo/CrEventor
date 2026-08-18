"""Game text support — built-in BCML-format texts, language selection, path resolution.

The tool ships with built-in texts files for the Chinese (CNzh) language.
When a different game text language is selected, no built-in data is available
unless the user has loaded additional texts.

Texts are platform-split:
  - Switch: resources/texts/switch/CNzh.json  (top key: CNzh)
  - WiiU:   resources/texts/wiiu/JPja.json    (top key: JPja)
"""

import os
import typing

# Canonical BOTW language list (same as bcml.mergers.texts.LANGUAGES)
GAME_LANGUAGES: typing.List[str] = [
    "USen", "EUen", "USfr", "USes",
    "EUde", "EUes", "EUfr", "EUit",
    "EUnl", "EUru", "CNzh", "JPja",
    "KRko", "TWzh",
]

# Human-readable names for each game language code
GAME_LANGUAGE_NAMES: typing.Dict[str, str] = {
    "USen": "English (US)",
    "EUen": "English (EU)",
    "USfr": "French (US)",
    "USes": "Spanish (US)",
    "EUde": "German (EU)",
    "EUes": "Spanish (EU)",
    "EUfr": "French (EU)",
    "EUit": "Italian (EU)",
    "EUnl": "Dutch (EU)",
    "EUru": "Russian (EU)",
    "CNzh": "Chinese (CN)",
    "JPja": "Japanese (JP)",
    "KRko": "Korean (KR)",
    "TWzh": "Chinese (TW)",
}

# Default game text language
DEFAULT_TEXT_LANGUAGE: str = "CNzh"


def get_texts_root() -> str:
    """Return the absolute path to the resources/texts/ directory."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'resources', 'texts')


def get_builtin_texts_path(platform: str, language: str) -> str:
    """Resolve the path to the built-in texts JSON file for the given platform and language.

    The built-in texts file name is always the *first* language embedded in the tool
    (currently CNzh for Switch, JPja for WiiU). The `language` parameter determines
    which language's data to extract from the file at runtime.

    Returns the file path, or empty string if no built-in file exists.
    """
    root = get_texts_root()
    # Both platforms use the same file name CNzh.json.
    # Internal top key differs: Switch→CNzh, WiiU→JPja.
    filename = 'CNzh.json'

    platform_dir = os.path.join(root, platform)
    path = os.path.join(platform_dir, filename)
    if os.path.isfile(path):
        return path
    return ''


def get_texts_file_path(platform: str, language: str) -> str:
    """Resolve the texts JSON file path.

    Priority:
      1. Built-in texts file (if it matches or can serve as fallback)
      2. (future) External texts file

    Returns the file path, or empty string if none found.
    """
    return get_builtin_texts_path(platform, language)


def load_texts(platform: str, language: str) -> typing.Dict[str, dict]:
    """Load texts for the given platform and language from the built-in file.

    Returns a dict like {"EventFlowMsg/Actor.msyt": {...}, ...} for the
    requested language, or an empty dict if no data is available.
    """
    import json

    path = get_builtin_texts_path(platform, language)
    if not path:
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Extract the requested language from the top-level dict
        # Built-in file has structure {"CNzh": {...}} or {"JPja": {...}}
        if isinstance(data, dict):
            # Try the requested language first, then fall back to whatever key exists
            if language in data:
                return data[language]
            # Fallback: return the first available language
            for key in data:
                if isinstance(data[key], dict):
                    return data[key]
                break
        return {}
    except Exception:
        return {}
