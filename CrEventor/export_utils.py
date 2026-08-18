"""Export gamedata.yml, savedata.yml, eventinfo.yml to logs/ directory.

Merges all open flows into three clean output files with no dates or comments.
Based on spec_eventinfo.yaml and spec_gamedata_savedata.yaml.

eventinfo format: {FlowName}<{EntryPoint}> with subfile list in {file: x.bfevfl} form.
"""

import os
import typing

from CrEventor.sbeventpack_analyzer import analyze_sbeventpack
from CrEventor.whitelist_loader import is_vanilla_gamedata, is_vanilla_eventinfo


def generate_gamedata_yml(flag_data: dict) -> str:
    """Generate gamedata.yml — all flags, no comments, no date suffix.
    自动过滤原版白名单中的 flag。"""
    if not flag_data:
        return 'bool_data:\n  add: {}\n  del: []\n'

    lines = ['bool_data:', '  add:']
    for flag_name in sorted(flag_data.keys()):
        if is_vanilla_gamedata(flag_name):
            continue
        fields = flag_data[flag_name]
        lines.append(f'    {flag_name}:')
        lines.append(f'      DataName: {flag_name}')
        lines.append( '      DeleteRev: -1')
        lines.append(f'      HashValue: {fields.get("HashValue", 0)}')
        lines.append(f'      InitValue: {int(fields.get("InitValue", 0))}')
        lines.append(f'      IsEventAssociated: {_bool_str(fields.get("IsEventAssociated", False))}')
        lines.append(f'      IsOneTrigger: {_bool_str(fields.get("IsOneTrigger", True))}')
        lines.append(f'      IsProgramReadable: {_bool_str(fields.get("IsProgramReadable", True))}')
        lines.append(f'      IsProgramWritable: {_bool_str(fields.get("IsProgramWritable", True))}')
        lines.append(f'      IsSave: {_bool_str(fields.get("IsSave", True))}')
        lines.append(f'      MaxValue: {_bool_str(fields.get("MaxValue", True))}')
        lines.append(f'      MinValue: {_bool_str(fields.get("MinValue", False))}')
        lines.append(f'      ResetType: {fields.get("ResetType", 0)}')
    lines.append('  del: []')
    return '\n'.join(lines) + '\n'


def generate_savedata_yml(flag_data: dict) -> str:
    """Generate savedata.yml — only IsSave:true flags, no comments, no date suffix.
    自动过滤原版白名单中的 flag。"""
    saved = [(n, f) for n, f in sorted(flag_data.items())
             if f.get('IsSave', True) and not is_vanilla_gamedata(n)]
    if not saved:
        return 'add: []\ndel: []\n'

    lines = ['add:']
    for flag_name, fields in saved:
        lines.append(f'  - {{DataName: {flag_name}, HashValue: {fields.get("HashValue", 0)}}}')
    lines.append('del: []')
    return '\n'.join(lines) + '\n'


def generate_eventinfo_yml(flows: typing.List[typing.Tuple[str, object]]) -> str:
    """Generate eventinfo.yml for all flows. No comments, no date suffix.
    自动过滤原版白名单中的条目。

    flows: list of (flow_name, EventFlow) tuples.
    """
    if not flows:
        return '{}\n'

    lines = []
    for flow_name, flow in flows:
        if not flow or not flow.flowchart:
            continue
        deps = analyze_sbeventpack(flow)
        subfile_lines = ['    - {file: ' + d + '}' for d in deps]

        # Each entry point becomes a key
        eps = getattr(flow.flowchart, 'entry_points', None)
        if not eps:
            continue
        for ep in eps:
            ep_name = ep.name if hasattr(ep, 'name') else str(ep)
            key = f'{flow_name}<{ep_name}>'

            # 跳过原版白名单中的条目
            if is_vanilla_eventinfo(key):
                continue

            if not subfile_lines:
                # Compact inline format when no subfiles
                lines.append(f'{key}: '
                             '{exist_enable_camera_input: true,'
                             'is_timeline: false,'
                             'mode: Seamless}')
            else:
                lines.append(f'{key}:')
                lines.append('  exist_enable_camera_input: true')
                lines.append('  is_timeline: false')
                lines.append('  mode: Seamless')
                lines.append('  subfile:')
                lines.extend(subfile_lines)

    if not lines:
        return '{}\n'
    return '\n'.join(lines) + '\n'


def _bool_str(value) -> str:
    return 'true' if value else 'false'


# ---------------------------------------------------------------------------
# Backup helpers (separate from clean output)
# ---------------------------------------------------------------------------

import json as _json


def save_gamedata_to_json(flag_data: dict, path: str) -> None:
    """Save gamedata flag metadata as a JSON file for backup purposes."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        _json.dump(flag_data, f, ensure_ascii=False, indent=2)


def load_gamedata_from_json(path: str) -> dict:
    """Load gamedata flag metadata from a JSON backup."""
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return _json.load(f)
