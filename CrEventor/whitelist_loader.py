"""加载原版白名单，用于过滤 eventinfo / gamedata 输出和展示。"""

import os
import sys

_ROOT = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WHITELIST_DIR = os.path.join(_ROOT, '新知识', '白名单')

_eventinfo_vanilla: set = None
_gamedata_vanilla: set = None


def _load_set(filename: str) -> set:
    path = os.path.join(_WHITELIST_DIR, filename)
    result = set()
    if not os.path.isfile(path):
        return result
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                result.add(line)
    return result


def get_eventinfo_vanilla() -> set:
    global _eventinfo_vanilla
    if _eventinfo_vanilla is None:
        _eventinfo_vanilla = _load_set('whitelist_eventinfo_vanilla..txt')
    return _eventinfo_vanilla


def get_gamedata_vanilla() -> set:
    global _gamedata_vanilla
    if _gamedata_vanilla is None:
        _gamedata_vanilla = _load_set('whitelist_gamedata_vanilla..txt')
    return _gamedata_vanilla


def is_vanilla_eventinfo(key: str) -> bool:
    return key in get_eventinfo_vanilla()


def is_vanilla_gamedata(flag_name: str) -> bool:
    return flag_name in get_gamedata_vanilla()
