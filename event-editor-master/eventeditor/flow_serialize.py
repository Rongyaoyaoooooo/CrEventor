import typing
from evfl import Container, Flowchart, Actor, Event, EventFlow, ActionEvent, SwitchEvent, ForkEvent, JoinEvent, SubFlowEvent
from evfl.common import Index, RequiredIndex, StringHolder, ActorIdentifier, Argument
from evfl.entry_point import EntryPoint
from evfl.enums import EventType

# ---------------------------------------------------------------------------
# Serialization: EventFlow -> dict (for JSON export with full roundtrip fidelity)
# ---------------------------------------------------------------------------

def _actor_identifier_to_dict(aid: ActorIdentifier) -> dict:
    return {'name': aid.name, 'sub_name': aid.sub_name}

def _container_item_to_dict(value):
    if isinstance(value, ActorIdentifier):
        return {'__type__': 'ActorIdentifier', **_actor_identifier_to_dict(value)}
    if isinstance(value, Argument):
        return {'__type__': 'Argument', 'value': str(value)}
    if isinstance(value, list):
        return {'__type__': 'list', 'items': list(value)}
    return value

def _container_to_dict(container: typing.Optional[Container]) -> typing.Optional[dict]:
    if container is None or not container.data:
        return None
    out = {}
    for k, v in container.data.items():
        out[k] = _container_item_to_dict(v)
    return out

def _actor_to_dict(actor: Actor, entry_points: typing.List[EntryPoint]) -> dict:
    arg_ep_name = ''
    if actor.argument_entry_point and actor.argument_entry_point._idx < len(entry_points):
        try:
            arg_ep_name = entry_points[actor.argument_entry_point._idx].name
        except Exception:
            pass
    return {
        'identifier': _actor_identifier_to_dict(actor.identifier),
        'argument_name': actor.argument_name,
        'argument_entry_point': arg_ep_name,
        'actions': [s.v for s in actor.actions],
        'queries': [s.v for s in actor.queries],
        'params': _container_to_dict(actor.params),
        'concurrent_clips': actor.concurrent_clips,
    }

def _event_to_dict(event: Event, actors: typing.List[Actor], events: typing.List[Event],
                   entry_points: typing.List[EntryPoint]) -> dict:
    base = {'name': event.name}
    data = event.data

    if isinstance(data, ActionEvent):
        actor_name = ''
        action_name = ''
        try:
            if data.actor and data.actor.v is not None:
                actor_name = str(data.actor.v.identifier)
        except Exception:
            pass
        try:
            if data.actor_action and data.actor_action.v is not None:
                action_name = str(data.actor_action.v)
        except Exception:
            pass
        nxt_name = ''
        try:
            if data.nxt and data.nxt.v is not None:
                nxt_name = data.nxt.v.name
        except Exception:
            pass
        base.update({
            'type': 'action',
            'actor': actor_name,
            'action': action_name,
            'nxt': nxt_name,
            'params': _container_to_dict(data.params),
        })

    elif isinstance(data, SwitchEvent):
        actor_name = ''
        query_name = ''
        try:
            if data.actor and data.actor.v is not None:
                actor_name = str(data.actor.v.identifier)
        except Exception:
            pass
        try:
            if data.actor_query and data.actor_query.v is not None:
                query_name = str(data.actor_query.v)
        except Exception:
            pass
        cases = {}
        for value, case in data.cases.items():
            case_name = ''
            try:
                if case and case.v is not None:
                    case_name = case.v.name
            except Exception:
                pass
            cases[str(value)] = case_name
        base.update({
            'type': 'switch',
            'actor': actor_name,
            'query': query_name,
            'cases': cases,
            'params': _container_to_dict(data.params),
        })

    elif isinstance(data, ForkEvent):
        join_name = ''
        try:
            if data.join and data.join.v is not None:
                join_name = data.join.v.name
        except Exception:
            pass
        forks = []
        for fork in data.forks:
            try:
                if fork and fork.v is not None:
                    forks.append(fork.v.name)
            except Exception:
                pass
        base.update({
            'type': 'fork',
            'join': join_name,
            'forks': forks,
        })

    elif isinstance(data, JoinEvent):
        nxt_name = ''
        try:
            if data.nxt and data.nxt.v is not None:
                nxt_name = data.nxt.v.name
        except Exception:
            pass
        base.update({
            'type': 'join',
            'nxt': nxt_name,
        })

    elif isinstance(data, SubFlowEvent):
        nxt_name = ''
        try:
            if data.nxt and data.nxt.v is not None:
                nxt_name = data.nxt.v.name
        except Exception:
            pass
        base.update({
            'type': 'sub_flow',
            'res_flowchart_name': data.res_flowchart_name,
            'entry_point_name': data.entry_point_name,
            'nxt': nxt_name,
            'params': _container_to_dict(data.params),
        })

    return base

def _entry_point_to_dict(ep: EntryPoint, events: typing.List[Event]) -> dict:
    main_event_name = ''
    try:
        if ep.main_event and ep.main_event.v is not None:
            main_event_name = ep.main_event.v.name
    except Exception:
        pass
    return {
        'name': ep.name,
        'main_event': main_event_name,
        'sub_flow_event_indices': list(ep._sub_flow_event_indices or []),
    }

def flow_to_dict(flow: EventFlow) -> dict:
    """Serialize an EventFlow to a JSON-serializable dict with full fidelity."""
    if not flow.flowchart:
        return {'name': flow.name, 'flowchart': None}

    fc = flow.flowchart
    actors = fc.actors
    events = fc.events
    entry_points = fc.entry_points

    return {
        'name': flow.name,
        'flowchart_name': fc.name,
        'actors': [_actor_to_dict(a, entry_points) for a in actors],
        'events': [_event_to_dict(e, actors, events, entry_points) for e in events],
        'entry_points': [_entry_point_to_dict(ep, events) for ep in entry_points],
    }

# ---------------------------------------------------------------------------
# Deserialization: dict -> EventFlow (for JSON import)
# ---------------------------------------------------------------------------

def _dict_to_actor_identifier(d: dict) -> ActorIdentifier:
    return ActorIdentifier(name=d.get('name', ''), sub_name=d.get('sub_name', ''))

def _dict_to_container_item(value):
    if isinstance(value, dict) and '__type__' in value:
        t = value['__type__']
        if t == 'ActorIdentifier':
            return _dict_to_actor_identifier(value)
        if t == 'Argument':
            return Argument(value.get('value', ''))
        if t == 'list':
            return list(value.get('items', []))
    if isinstance(value, list):
        return list(value)
    return value

def _dict_to_container(d: typing.Optional[dict]) -> typing.Optional[Container]:
    if d is None:
        return None
    if not isinstance(d, dict) or len(d) == 0:
        return None
    container = Container()
    for k, v in d.items():
        container.data[k] = _dict_to_container_item(v)
    return container

def _build_actor(d: dict, entry_point_map: typing.Dict[str, EntryPoint]) -> Actor:
    actor = Actor()
    identifier_data = d.get('identifier', {})
    actor.identifier = _dict_to_actor_identifier(identifier_data)
    actor.argument_name = d.get('argument_name', '')
    arg_ep_name = d.get('argument_entry_point', '')
    if arg_ep_name and arg_ep_name in entry_point_map:
        actor.argument_entry_point = Index()
        actor.argument_entry_point.v = entry_point_map[arg_ep_name]
    actor.actions = [StringHolder(a) for a in d.get('actions', [])]
    actor.queries = [StringHolder(q) for q in d.get('queries', [])]
    actor.params = _dict_to_container(d.get('params'))
    actor.concurrent_clips = d.get('concurrent_clips', 0xFFFF)
    return actor

def _lookup_actor_by_identifier_str(actors: typing.List[Actor], identifier_str: str):
    for a in actors:
        if str(a.identifier) == identifier_str:
            return a
    # Try name-only match
    for a in actors:
        if a.identifier.name == identifier_str:
            return a
    return None

def _build_event(d: dict,
                 actor_map: typing.Dict[str, Actor],
                 event_map: typing.Dict[str, Event]) -> Event:
    event = Event()
    event.name = d.get('name', '')
    etype = d.get('type', 'action')

    if etype == 'action':
        data = ActionEvent()
        actor_id_str = d.get('actor', '')
        actor = actor_map.get(actor_id_str) or _lookup_actor_by_identifier_str(list(actor_map.values()), actor_id_str)
        if actor is not None:
            data.actor = RequiredIndex()
            data.actor.v = actor
            action_name = d.get('action', '')
            if action_name:
                try:
                    action_sh = actor.find_action(action_name)
                except ValueError:
                    action_sh = StringHolder(action_name)
                    actor.actions.append(action_sh)
                data.actor_action = RequiredIndex()
                data.actor_action.v = action_sh
        nxt_name = d.get('nxt', '')
        if nxt_name and nxt_name in event_map:
            data.nxt = Index()
            data.nxt.v = event_map[nxt_name]
        data.params = _dict_to_container(d.get('params'))
        event.data = data

    elif etype == 'switch':
        data = SwitchEvent()
        actor_id_str = d.get('actor', '')
        actor = actor_map.get(actor_id_str) or _lookup_actor_by_identifier_str(list(actor_map.values()), actor_id_str)
        if actor is not None:
            data.actor = RequiredIndex()
            data.actor.v = actor
            query_name = d.get('query', '')
            if query_name:
                try:
                    query_sh = actor.find_query(query_name)
                except ValueError:
                    query_sh = StringHolder(query_name)
                    actor.queries.append(query_sh)
                data.actor_query = RequiredIndex()
                data.actor_query.v = query_sh
        cases = d.get('cases', {}) or {}
        for str_value, case_name in cases.items():
            if isinstance(case_name, str) and case_name in event_map:
                try:
                    int_value = int(str_value)
                except (ValueError, TypeError):
                    continue
                ri = RequiredIndex()
                ri.v = event_map[case_name]
                data.cases[int_value] = ri
        data.params = _dict_to_container(d.get('params'))
        event.data = data

    elif etype == 'fork':
        data = ForkEvent()
        join_name = d.get('join', '')
        if join_name and join_name in event_map:
            data.join = RequiredIndex()
            data.join.v = event_map[join_name]
        forks = d.get('forks', []) or []
        for fork_name in forks:
            if isinstance(fork_name, str) and fork_name in event_map:
                ri = RequiredIndex()
                ri.v = event_map[fork_name]
                data.forks.append(ri)
        event.data = data

    elif etype == 'join':
        data = JoinEvent()
        nxt_name = d.get('nxt', '')
        if nxt_name and nxt_name in event_map:
            data.nxt = Index()
            data.nxt.v = event_map[nxt_name]
        event.data = data

    elif etype == 'sub_flow':
        data = SubFlowEvent()
        data.res_flowchart_name = d.get('res_flowchart_name', '')
        data.entry_point_name = d.get('entry_point_name', '')
        nxt_name = d.get('nxt', '')
        if nxt_name and nxt_name in event_map:
            data.nxt = Index()
            data.nxt.v = event_map[nxt_name]
        data.params = _dict_to_container(d.get('params'))
        event.data = data

    else:
        data = ActionEvent()
        event.data = data

    return event

def _build_entry_point(d: dict, event_map: typing.Dict[str, Event]) -> EntryPoint:
    ep = EntryPoint(d.get('name', ''))
    main_event_name = d.get('main_event', '')
    if main_event_name and main_event_name in event_map:
        ep.main_event = Index()
        ep.main_event.v = event_map[main_event_name]
    sf_indices = d.get('sub_flow_event_indices', []) or []
    ep._sub_flow_event_indices = [int(i) for i in sf_indices]
    return ep

def dict_to_flow(d: dict) -> typing.Optional[EventFlow]:
    """Deserialize a dict (created by flow_to_dict) back to an EventFlow."""
    if not isinstance(d, dict):
        return None
    if 'actors' not in d and 'events' not in d and 'entry_points' not in d:
        return None

    flow = EventFlow()
    flow.name = d.get('name', 'ImportedFlow')
    flow.flowchart = Flowchart()
    flow.flowchart.name = d.get('flowchart_name', flow.name)

    # Step 1: Create entry point shells (we need them for actor argument_entry_point references)
    ep_dicts = d.get('entry_points', []) or []
    ep_shells = {}
    for epd in ep_dicts:
        name = epd.get('name', '')
        ep = EntryPoint(name)
        ep_shells[name] = ep

    # Step 2: Create actors (may reference entry points via argument_entry_point)
    actor_dicts = d.get('actors', []) or []
    actors = []
    actor_by_idstr = {}
    for ad in actor_dicts:
        actor = _build_actor(ad, ep_shells)
        actors.append(actor)
        actor_by_idstr[str(actor.identifier)] = actor
        # Also index by name only for convenience
        if actor.identifier.name and actor.identifier.name not in actor_by_idstr:
            actor_by_idstr[actor.identifier.name] = actor

    # Step 3: Create event shells (need to resolve references between events)
    evt_dicts = d.get('events', []) or []
    event_shells = {}
    events_list = []
    for evd in evt_dicts:
        ev = Event()
        ev.name = evd.get('name', '')
        events_list.append(ev)
        if ev.name:
            event_shells[ev.name] = ev

    # Step 4: Populate event data (may reference actors and other events)
    for evd, ev in zip(evt_dicts, events_list):
        tmp_event = _build_event(evd, actor_by_idstr, event_shells)
        ev.data = tmp_event.data

    # Step 5: Populate entry points
    entry_points = []
    for epd in ep_dicts:
        ep = ep_shells[epd.get('name', '')]
        tmp_ep = _build_entry_point(epd, event_shells)
        ep.main_event = tmp_ep.main_event
        ep._sub_flow_event_indices = tmp_ep._sub_flow_event_indices
        entry_points.append(ep)

    flow.flowchart.actors = actors
    flow.flowchart.events = events_list
    flow.flowchart.entry_points = entry_points
    return flow

# ---------------------------------------------------------------------------
# Validation: check JSON structure before import
# ---------------------------------------------------------------------------

EVENT_TYPES = ('action', 'switch', 'fork', 'join', 'sub_flow')

def validate_flow_dict(d: dict) -> typing.List[str]:
    """Validate a flow JSON dict. Returns a list of error messages (empty = valid)."""
    errors = []

    if not isinstance(d, dict):
        return ['JSON root must be an object/dict']

    # Determine format
    flow_meta = d.get('flow_meta')
    if flow_meta:
        data = flow_meta
    elif 'actors' in d or 'events' in d or 'entry_points' in d:
        data = d
    else:
        errors.append('JSON must contain "flow_meta" or be a flow dict with "actors"/"events"/"entry_points"')
        return errors

    # --- Top-level ---
    if 'actors' not in data:
        errors.append('Missing top-level field: "actors"')
    if 'events' not in data:
        errors.append('Missing top-level field: "events"')
    if 'entry_points' not in data:
        errors.append('Missing top-level field: "entry_points"')
    if errors:
        return errors

    actors = data['actors']
    events = data['events']
    entry_points = data['entry_points']

    if not isinstance(actors, list):
        errors.append('"actors" must be a list')
    if not isinstance(events, list):
        errors.append('"events" must be a list')
    if not isinstance(entry_points, list):
        errors.append('"entry_points" must be a list')
    if errors:
        return errors

    # --- Actors ---
    actor_ids = set()
    for i, actor in enumerate(actors):
        prefix = f'actors[{i}]'
        if not isinstance(actor, dict):
            errors.append(f'{prefix}: must be an object')
            continue
        ident = actor.get('identifier')
        if not isinstance(ident, dict):
            errors.append(f'{prefix}: missing or invalid "identifier" object')
        else:
            if 'name' not in ident:
                errors.append(f'{prefix}.identifier: missing "name"')
            elif not isinstance(ident['name'], str):
                errors.append(f'{prefix}.identifier.name: must be a string')
            else:
                if ident['name']:
                    if ident['name'] in actor_ids:
                        errors.append(f'{prefix}.identifier.name: duplicate actor name "{ident["name"]}"')
                    else:
                        actor_ids.add(ident['name'])
            if 'sub_name' not in ident:
                errors.append(f'{prefix}.identifier: missing "sub_name"')
            elif not isinstance(ident['sub_name'], str):
                errors.append(f'{prefix}.identifier.sub_name: must be a string')

        if 'actions' not in actor:
            errors.append(f'{prefix}: missing "actions" list')
        elif not isinstance(actor['actions'], list):
            errors.append(f'{prefix}.actions: must be a list')
        else:
            for j, act in enumerate(actor['actions']):
                if not isinstance(act, str):
                    errors.append(f'{prefix}.actions[{j}]: must be a string, got {type(act).__name__}')

        if 'queries' not in actor:
            errors.append(f'{prefix}: missing "queries" list')
        elif not isinstance(actor['queries'], list):
            errors.append(f'{prefix}.queries: must be a list')
        else:
            for j, q in enumerate(actor['queries']):
                if not isinstance(q, str):
                    errors.append(f'{prefix}.queries[{j}]: must be a string, got {type(q).__name__}')

        cc = actor.get('concurrent_clips')
        if cc is not None and not isinstance(cc, int):
            errors.append(f'{prefix}.concurrent_clips: must be an integer')

        arg_ep = actor.get('argument_entry_point', '')
        if arg_ep and not isinstance(arg_ep, str):
            errors.append(f'{prefix}.argument_entry_point: must be a string')

    # --- Events ---
    event_names = set()
    for i, ev in enumerate(events):
        prefix = f'events[{i}]'
        if not isinstance(ev, dict):
            errors.append(f'{prefix}: must be an object')
            continue
        if 'name' not in ev:
            errors.append(f'{prefix}: missing "name"')
        elif not isinstance(ev['name'], str):
            errors.append(f'{prefix}.name: must be a string')
        elif not ev['name']:
            errors.append(f'{prefix}.name: cannot be empty string')
        else:
            if ev['name'] in event_names:
                errors.append(f'{prefix}.name: duplicate event name "{ev["name"]}"')
            else:
                event_names.add(ev['name'])

        if 'type' not in ev:
            errors.append(f'{prefix}: missing "type" field')
            continue
        etype = ev['type']
        if not isinstance(etype, str):
            errors.append(f'{prefix}.type: must be a string')
            continue
        if etype not in EVENT_TYPES:
            errors.append(f'{prefix}.type: invalid type "{etype}", must be one of {EVENT_TYPES}')
            continue

        # Type-specific checks
        if etype == 'action':
            actor_ref = ev.get('actor', '')
            if not isinstance(actor_ref, str):
                errors.append(f'{prefix}.actor: must be a string')
            elif actor_ref and actor_ref not in actor_ids:
                errors.append(f'{prefix}.actor: references unknown actor "{actor_ref}"')

            action = ev.get('action', '')
            if not isinstance(action, str):
                errors.append(f'{prefix}.action: must be a string')

            nxt = ev.get('nxt', '')
            if nxt:
                if not isinstance(nxt, str):
                    errors.append(f'{prefix}.nxt: must be a string')
                elif nxt not in event_names and nxt != ev.get('name'):
                    # nxt may reference an event that appears later in the list
                    pass  # forward references allowed

        elif etype == 'switch':
            actor_ref = ev.get('actor', '')
            if not isinstance(actor_ref, str):
                errors.append(f'{prefix}.actor: must be a string')
            elif actor_ref and actor_ref not in actor_ids:
                errors.append(f'{prefix}.actor: references unknown actor "{actor_ref}"')

            query = ev.get('query', '')
            if not isinstance(query, str):
                errors.append(f'{prefix}.query: must be a string')

            cases = ev.get('cases', {})
            if not isinstance(cases, dict):
                errors.append(f'{prefix}.cases: must be an object/dict')
            else:
                for case_key, case_val in cases.items():
                    if not isinstance(case_key, str) or not case_key.isdigit():
                        errors.append(f'{prefix}.cases: key "{case_key}" is not a non-negative integer string')
                    if not isinstance(case_val, str):
                        errors.append(f'{prefix}.cases[{case_key}]: value must be a string')

        elif etype == 'fork':
            join_name = ev.get('join', '')
            if join_name:
                if not isinstance(join_name, str):
                    errors.append(f'{prefix}.join: must be a string')

            forks = ev.get('forks', [])
            if not isinstance(forks, list):
                errors.append(f'{prefix}.forks: must be a list')
            else:
                for j, fork_ref in enumerate(forks):
                    if not isinstance(fork_ref, str):
                        errors.append(f'{prefix}.forks[{j}]: must be a string')

        elif etype == 'join':
            nxt = ev.get('nxt', '')
            if nxt:
                if not isinstance(nxt, str):
                    errors.append(f'{prefix}.nxt: must be a string')

        elif etype == 'sub_flow':
            res_name = ev.get('res_flowchart_name', '')
            if not isinstance(res_name, str):
                errors.append(f'{prefix}.res_flowchart_name: must be a string')

            ep_name = ev.get('entry_point_name', '')
            if not isinstance(ep_name, str):
                errors.append(f'{prefix}.entry_point_name: must be a string')

            nxt = ev.get('nxt', '')
            if nxt:
                if not isinstance(nxt, str):
                    errors.append(f'{prefix}.nxt: must be a string')

        # params check
        params = ev.get('params')
        if params is not None and not isinstance(params, dict):
            errors.append(f'{prefix}.params: must be an object or null')

    # --- Entry Points ---
    for i, ep in enumerate(entry_points):
        prefix = f'entry_points[{i}]'
        if not isinstance(ep, dict):
            errors.append(f'{prefix}: must be an object')
            continue
        if 'name' not in ep:
            errors.append(f'{prefix}: missing "name"')
        elif not isinstance(ep['name'], str):
            errors.append(f'{prefix}.name: must be a string')

        main_event = ep.get('main_event', '')
        if main_event:
            if not isinstance(main_event, str):
                errors.append(f'{prefix}.main_event: must be a string')
            elif main_event not in event_names:
                errors.append(f'{prefix}.main_event: references unknown event "{main_event}"')

        sf_indices = ep.get('sub_flow_event_indices', [])
        if not isinstance(sf_indices, list):
            errors.append(f'{prefix}.sub_flow_event_indices: must be a list')
        else:
            for j, idx in enumerate(sf_indices):
                if not isinstance(idx, int):
                    errors.append(f'{prefix}.sub_flow_event_indices[{j}]: must be an integer')

    # --- Cross-reference checks (deferred for forward references) ---
    # Collect all referenced event names
    referenced_events = set()
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        etype = ev.get('type', '')
        if etype == 'action':
            nxt = ev.get('nxt', '')
            if nxt:
                referenced_events.add(nxt)
        elif etype == 'switch':
            cases = ev.get('cases', {})
            if isinstance(cases, dict):
                for v in cases.values():
                    if isinstance(v, str) and v:
                        referenced_events.add(v)
        elif etype == 'fork':
            join_name = ev.get('join', '')
            if join_name:
                referenced_events.add(join_name)
            forks = ev.get('forks', [])
            if isinstance(forks, list):
                for f in forks:
                    if isinstance(f, str) and f:
                        referenced_events.add(f)
        elif etype == 'join':
            nxt = ev.get('nxt', '')
            if nxt:
                referenced_events.add(nxt)
        elif etype == 'sub_flow':
            nxt = ev.get('nxt', '')
            if nxt:
                referenced_events.add(nxt)

    # Check that all referenced events exist
    for ref in referenced_events:
        if ref and ref not in event_names:
            errors.append(f'Event references unknown event "{ref}"')

    # Check entry point main_event references
    for i, ep in enumerate(entry_points):
        if not isinstance(ep, dict):
            continue
        main_event = ep.get('main_event', '')
        if main_event and main_event not in event_names:
            errors.append(f'entry_points[{i}].main_event: references unknown event "{main_event}"')

    # Check actor argument_entry_point references
    for i, actor in enumerate(actors):
        if not isinstance(actor, dict):
            continue
        arg_ep = actor.get('argument_entry_point', '')
        if arg_ep:
            ep_names = {ep.get('name', '') for ep in entry_points if isinstance(ep, dict)}
            if arg_ep not in ep_names:
                errors.append(f'actors[{i}].argument_entry_point: references unknown entry point "{arg_ep}"')

    return errors
