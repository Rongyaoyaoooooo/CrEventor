"""Analyze eventflow for sub_flow dependencies → sbeventpack file list.

Based on spec_eventinfo.yaml rules:
  - All SubFlowEvent with non-empty res_flowchart_name → add to list
  - If InitTalk.bfevfl is in list → also add Common.bfevfl (97% rule)
  - Common.bfevfl is always included (nearly every flow needs it)
"""

import typing

from evfl import EventFlow
from evfl.event import SubFlowEvent


def _ensure_bfevfl(name: str) -> str:
    """确保名称有且仅有一个 .bfevfl 后缀。"""
    name = name.strip()
    if not name.endswith('.bfevfl'):
        name += '.bfevfl'
    return name


def analyze_sbeventpack(flow: EventFlow) -> typing.List[str]:
    """Return sorted list of .bfevfl files that should be packed together
    in the sbeventpack for this flow. Common.bfevfl is always included."""
    if not flow or not flow.flowchart:
        return []

    deps: typing.Set[str] = set()
    deps.add('Common.bfevfl')  # always needed

    for event in flow.flowchart.events:
        if not isinstance(event.data, SubFlowEvent):
            continue
        fname = event.data.res_flowchart_name
        if fname and fname.strip():
            deps.add(_ensure_bfevfl(fname))

    # Rule: if InitTalk.bfevfl is a dependency, Common.bfevfl must also be present
    # (already handled by always including Common)
    if 'InitTalk.bfevfl' in deps:
        deps.add('Common.bfevfl')

    return sorted(deps)
