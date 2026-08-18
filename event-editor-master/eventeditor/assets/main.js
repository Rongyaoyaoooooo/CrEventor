const T = (k, fallback) => (window.TR && window.TR[k]) || fallback;

let graph;
let widget;
let eventNamesVisible = false;
let eventParamVisible = false;
let actionsProhibited = false;
let isDeleting = false;
let notesVisible = false;
let translations = { keys: {}, actions: {}, queries: {}, types: {} };
let dialogueTexts = {};

const WHITELISTED_PARAMS = new Set(['MessageId', 'ASName']);

function translateKey(key) {
  if (window.LANG === 'en_US' || !notesVisible || !translations.keys || !translations.keys[key]) return key;
  return `${key} -- ${translations.keys[key]}`;
}

function translateAction(name) {
  if (window.LANG === 'en_US' || !notesVisible || !translations.actions || !translations.actions[name]) return name;
  return `${name} -- ${translations.actions[name]}`;
}

function translateQuery(name) {
  if (window.LANG === 'en_US' || !notesVisible || !translations.queries || !translations.queries[name]) return name;
  return `${name} -- ${translations.queries[name]}`;
}

function formatDialoguePreview(text) {
  if (!text) return '';
  const maxLines = 3;
  const maxChars = 40;
  const lines = text.split('\n');
  const result = [];
  for (let i = 0; i < lines.length && result.length < maxLines; i++) {
    let line = lines[i];
    if (line.length > maxChars) line = line.substring(0, maxChars) + '...';
    result.push(line);
  }
  if (lines.length > maxLines) result.push('...');
  return result.join('\n');
}

function getNodeLabel(node) {
  const prefix = eventNamesVisible ? `${node.data.name}\n` : '';
  let label = node.id;

  if (node.node_type === 'entry') {
    label = `${node.data.name}`;
  }
  else if (node.node_type === 'action') {
    const actionStr = translateAction(node.data.action);
    label = `${prefix}${node.data.actor}\n${actionStr}`;
  }
  else if (node.node_type === 'switch') {
    const queryStr = translateQuery(node.data.query);
    label = `${prefix}${node.data.actor}\n${queryStr}`;
  }
  else if (node.node_type === 'fork') {
    label = `${prefix}Fork`;
  }
  else if (node.node_type === 'join') {
    label = `${prefix}Join`;
  }
  else if (node.node_type === 'sub_flow') {
    label = `${prefix}${node.data.res_flowchart_name}\n<${node.data.entry_point_name}>`;
  }

  if (eventParamVisible && node.data.params) {
    let i = 0;
    let hasMore = false;
    for (const [key, value] of Object.entries(node.data.params)) {
      if (key === 'IsWaitFinish') {
        continue;
      }
      const isWhitelisted = WHITELISTED_PARAMS.has(key);
      if (!isWhitelisted && i >= 5) {
        hasMore = true;
      } else {
        const keyStr = translateKey(key);
        const valueStr = typeof value === 'number' ? value.toFixed(6).replace(/\.?0*$/, '') : value;
        label += `\n${keyStr}: ${valueStr}`;
      }
      i++;
    }
    if (hasMore) {
      label += '\n...';
    }
  }

  // Append dialogue text preview for nodes with MessageId
  if (node.data.params && node.data.params.MessageId) {
    const msgId = node.data.params.MessageId;
    const dialogueText = dialogueTexts[msgId];
    if (dialogueText) {
      const preview = formatDialoguePreview(dialogueText);
      label += `\n───\n${preview}`;
    }
  }

  return label;
}

function handleNodeContextMenu(id) {
  const actions = [];

  const idx = parseInt(id, 10);
  const node = graph.g.node(id);
  const prevNodes = [...(new Set(graph.g.inEdges(id).filter(e => !graph.g.edge(e).virtual).map(e => parseInt(e.v, 10))))];
  const nextNodes = [...(new Set(graph.g.outEdges(id).filter(e => !graph.g.edge(e).virtual).map(e => parseInt(e.w, 10))))];
  const classes = node.class.split(' ');

  const addAction = (name, fn) => actions.push({ title: name, action: () => { setTimeout(fn, 60) } });

  if (!actionsProhibited) {
    if (idx >= 0) { // Event actions
      if (!classes.includes('fork') && !classes.includes('join')) {
        addAction(T('edit_event', 'Edit event...'), () => widget.editEvent(idx));
      }
      if (classes.includes('action')) {
        if (node.data.params && node.data.params.MessageId) {
          addAction(T('edit_dialogue', 'Edit dialogue text...'), () => widget.editDialogue(idx));
        } else {
          addAction(T('add_dialogue', 'Add dialogue text...'), () => widget.editDialogue(idx));
        }
      }
      if (classes.includes('switch')) {
        addAction(T('edit_cases', 'Edit cases...'), () => widget.editSwitchBranches(idx));
      }
      if (classes.includes('fork')) {
        addAction(T('edit_branches', 'Edit branches...'), () => widget.editForkBranches(idx));
      }
      if (!classes.includes('join')) {
        actions.push({ divider: true });
      }

      addAction(T('add_entry_point', 'Add entry point here...'), () => widget.addEntryPoint(idx));
      actions.push({ divider: true });

      if (!classes.includes('join')) {
        addAction(T('add_parent', 'Add new parent...'), () => widget.addEventAbove(prevNodes, idx));
      }

      if (classes.includes('action') || classes.includes('sub_flow') || classes.includes('join')) {
        addAction(T('add_child', 'Add new child...'), () => widget.addEventBelow(idx));
        if (nextNodes.length) {
          addAction(T('unlink_child', 'Unlink child'), () => widget.unlink(idx));
        } else {
          addAction(T('link_event', 'Link to event...'), () => widget.link(idx));
        }
      }

      const oneBranchSwitchOrFork =
          nextNodes.length <= 1 && (classes.includes('fork') || classes.includes('switch'));
      const isOnlyEventInEntry =
          nextNodes.length === 0 && prevNodes.length === 1 && parseInt(prevNodes[0], 10) <= -1000;

      if (!isOnlyEventInEntry && (classes.includes('action') || classes.includes('sub_flow') || oneBranchSwitchOrFork)) {
        actions.push({ divider: true });
        addAction(T('remove_event', 'Remove event'), () => {
          isDeleting = true;
          widget.removeEvent(prevNodes, idx);
        });
      }

    } else { // Entry point actions
      addAction(T('remove_entry_point', 'Remove entry point'), () => widget.removeEntryPoint(idx));
    }

    actions.push({ divider: true });
  }

  if (graph.persistentWhitelist) {
    addAction(T('show_all', 'Show all events'), () => graph.renderOnlyConnected());
  } else {
    addAction(T('show_connected', 'Show only connected events'), () => graph.renderOnlyConnected(id));
  }

  return actions;
}

class Renderer {
  constructor() {
    this.svg = d3.select('svg');
    this.svgGroup = d3.select('svg g');

    this.nodeWhitelist = null;

    this.zoom = d3.behavior.zoom();
    this.lastZoomEventStart = null;
    this.svg.call(this.zoom.on('zoom', () => this.updateTransform()));
    this.svg.call(this.zoom.on('zoomstart', () => this.lastZoomEventStart = new Date()));

    // Reset selection on click.
    // Unfortunately we need to do some extra work to determine whether the click event is caused
    // by zooming or is a simple click.
    this.svg.on('click', () => {
      // The zoom lasted more than 100 ms, so it's likely a zoom.
      if ((new Date() - this.lastZoomEventStart) >= 100) {
        return;
      }
      this.clearSelection();
    });

    // Empty-space right-click → show flowchart tools menu (Python side)
    this.svg.on('contextmenu', () => {
      if (d3.event.target === this.svg.node() ||
          d3.event.target.tagName === 'svg') {
        d3.event.preventDefault();
        widget.graphEmptySpaceContextMenu();
      }
    });
  }

  getSelection() {
    const selected = d3.select('.selected');
    return selected.empty() ? -1 : parseInt(selected.attr('id').slice(1), 10);
  }

  clearSelection() {
    widget.emitEventSelectedSignal(-1);
    this.clearSelectionWithoutEmittingSignal();
  }

  clearSelectionWithoutEmittingSignal() {
    const selected = this.getSelection();
    if (selected !== -1) {
      const node = graph.g.node(selected);
      node.class = node.class.replace(/\bselected\b/, '');
    }
    for (const cl of ['selected', 'selected-in-edge', 'selected-out-edge', 'selected-in-edge-label', 'selected-out-edge-label']) {
      d3.selectAll('.' + cl).classed(cl, false);
    }
  }

  select(id, g) {
    this.clearSelectionWithoutEmittingSignal();
    d3.select(`#n${id}`).classed('selected', true);
    g.node(id).class += ' selected';
    g.inEdges(id).forEach((e) => {
      d3.selectAll(`.edge-${e.v}-${e.w}`).classed('selected-in-edge', true);
      d3.select(`#label-${e.name}`).classed('selected-in-edge-label', true);
    });
    g.outEdges(id).forEach((e) => {
      d3.selectAll(`.edge-${e.v}-${e.w}`).classed('selected-out-edge', true);
      d3.select(`#label-${e.name}`).classed('selected-out-edge-label', true);
    });
    widget.emitEventSelectedSignal(parseInt(id, 10));
  }

  getElement(id) {
    const element = d3.select(`#n${id}`);
    return element.empty() ? null : element;
  }

  scrollTo(id, center=false, duration=1000) {
    const element = this.getElement(id);
    if (!element) {
      return false;
    }
    const t = d3.transform(element.attr('transform'));
    const [x, y] = t.translate;
    const scale = this.zoom.scale();
    const newY = y*-scale + (center ? (window.innerHeight/2) : 60);
    this.svg.transition().duration(duration)
      .call(this.zoom.translate([x*-scale + window.innerWidth/2, newY]).event);
    return true;
  }

  render(g) {
    const visibleGraph = new graphlib.Graph({ multigraph: true });
    visibleGraph.setGraph({});
    visibleGraph.graph().transition = (selection) => {
      return selection.transition().duration(500);
    };

    for (const v of g.nodes()) {
      if (!this.nodeWhitelist || this.nodeWhitelist.has(v)) {
        visibleGraph.setNode(v, g.node(v));
      }
    }
    for (const e of g.edges()) {
      if (!this.nodeWhitelist || this.nodeWhitelist.has(e.v)) {
        visibleGraph.setEdge(e, g.edge(e));
      }
    }

    const render = dagreD3.render();
    this.svgGroup.call(render, visibleGraph);
    this.svgGroup.selectAll('.node')
      .on('click', (id) => {
        this.select(id, g);
        d3.event.stopPropagation();
      })
      .on('dblclick', (id) => {
        if (actionsProhibited) {
          d3.event.stopPropagation();
          return;
        }

        const node = g.node(id);
        const classes = node.class.split(' ');
        if (classes.includes('fork')) {
          widget.editForkBranches(parseInt(id, 10));
        } else {
          widget.editEvent(parseInt(id, 10));
        }
        d3.event.stopPropagation();
      })
      .on('contextmenu', d3.contextMenu(handleNodeContextMenu));
  }

  setScale(scale) { this.zoom.scale(scale); this.updateTransform(); }
  setTranslate(translate) { this.zoom.translate(translate); this.updateTransform(); }

  updateTransform() {
    this.svgGroup.attr('transform', `translate(${this.zoom.translate()})scale(${this.zoom.scale()})`);
  }
}

class Graph {
  constructor() {
    this.g = null;
    this.data = null;
    this.renderer = new Renderer();
    this.persistentWhitelist = null;
  }

  update(data) {
    this.data = data;
    this.g = new graphlib.Graph({ multigraph: true });
    this.g.setGraph({});

    // Talk action keywords for dialogue node detection
    const talkKeywords = ['Talk', 'EventTalk', 'DemoTalk', 'NpcTalk', 'GeneralTalk'];

    for (const entry of data) {
      if (entry.type === 'node') {
        let nodeClass = entry.node_type;

        // Detect dialogue nodes: action nodes with Talk-related actions
        if (entry.node_type === 'action' && entry.data.action) {
          const action = entry.data.action;
          const isTalk = talkKeywords.some(kw => action.includes(kw));
          if (isTalk) {
            nodeClass += ' dialogue';
          }
        }

        // Build tooltip with full dialogue text
        let tooltip = '';
        if (entry.data.params && entry.data.params.MessageId) {
          const msgId = entry.data.params.MessageId;
          const fullText = dialogueTexts[msgId];
          if (fullText) {
            tooltip = `${msgId}\n\n${fullText}`;
          }
        }

        this.g.setNode(entry.id, {
          label: getNodeLabel(entry),
          'class': nodeClass,
          id: `n${entry.id}`,
          idx: entry.id,
          name: entry.data.name,
          tooltip: tooltip,
          data: entry.data,
        });
      } else if (entry.type === 'edge') {
        this.g.setEdge(entry.source, entry.target, {
          labelType: 'html',
          label: `<span id="label-edge-${entry.source}-${entry.target}-${entry.data.value}">${entry.data.value == null ? '' : entry.data.value}</span>`,
          'class': `edge-${entry.source}-${entry.target}`,
          virtual: !!entry.data.virtual,
        }, `edge-${entry.source}-${entry.target}-${entry.data.value}`);
      }
    }
  }

  refresh() {
    if (this.data && Object.keys(this.data).length > 0) {
      this.update(this.data);
    }
  }

  render() {
    if (this.persistentWhitelist) {
      this.renderer.nodeWhitelist = new Set(this.g.nodes()
        .map(idx => this.g.node(idx))
        .filter(node => this.persistentWhitelist.has(node.name))
        .map(node => node.idx.toString())
      );
    } else {
      this.renderer.nodeWhitelist = null;
    }

    this.renderer.render(this.g);
  }

  renderOnlyConnected(v) {
    const selected = this.renderer.getSelection();
    this.persistentWhitelist = this.findNodeComponent(v);
    this.render();
    if (v != null) {
      setTimeout(() => this.renderer.scrollTo(v), 500);
    } else if (selected !== -1) {
      setTimeout(() => this.renderer.scrollTo(selected), 500);
    }
  }

  /// Returns a set of connected events: {"Event123", "Event125", "EntryPoint", ...}
  findNodeComponent(v) {
    const components = graphlib.alg.components(this.g);
    const c = components.find((component) => component.includes(v));
    if (!c) {
      return null;
    }
    return new Set(c.map(idx => this.g.node(idx).name));
  }
}

graph = new Graph();

document.body.addEventListener('keydown', (event) => {
  const key = event.key; // "ArrowRight", "ArrowLeft", "ArrowUp", or "ArrowDown"

  if (key === 'Escape') {
    graph.renderer.clearSelection();
    return;
  }

  // Handle zoom
  if (event.ctrlKey) {
    let scaleMultiplier = 1;
    if (key === 'ArrowUp')
      scaleMultiplier = 1.1;
    else if (key === 'ArrowDown')
      scaleMultiplier = 0.9;
    graph.renderer.setScale(graph.renderer.zoom.scale() * scaleMultiplier);
    if (scaleMultiplier !== 1)
      return;
  }

  // Handle translate / navigation
  const selected = graph.renderer.getSelection();
  if (selected === -1) {
    let vDirection = 0;
    let hDirection = 0;
    switch (key) {
      case 'ArrowUp':
        vDirection = 1;
        break;
      case 'ArrowDown':
        vDirection = -1;
        break;
      case 'ArrowLeft':
        hDirection = 1;
        break;
      case 'ArrowRight':
        hDirection = -1;
        break;
    }
    const [x, y] = graph.renderer.zoom.translate();
    graph.renderer.setTranslate([x + 100 * hDirection, y + 100 * vDirection]);
    return;
  }
  if (key === 'ArrowUp' || key === 'ArrowDown') {
    const nodes = key === 'ArrowUp' ? graph.g.predecessors(selected) : graph.g.successors(selected);
    if (nodes.length > 0) {
      graph.renderer.scrollTo(nodes[0], true, 500);
      graph.renderer.select(nodes[0], graph.g);
    }
  }
});

new QWebChannel(qt.webChannelTransport, (channel) => {
  widget = channel.objects.widget;

  function select(id) {
    if (graph.persistentWhitelist) {
      graph.renderOnlyConnected(id.toString());
      graph.renderer.select(id, graph.g);
    } else {
      graph.renderer.setScale(1);
      graph.renderer.select(id, graph.g);
      graph.renderer.scrollTo(id);
    }
  }

  function load(cb) {
    widget.getJson((data) => {
      if (!data) {
        return;
      }
      let graphData = data;
      if (data && typeof data === 'object' && data.graph !== undefined) {
        graphData = data.graph;
        if (data.notesVisible !== undefined) notesVisible = data.notesVisible;
        if (data.translations) translations = data.translations;
        if (data.dialogueTexts) dialogueTexts = data.dialogueTexts;
      }
      graph.update(graphData);
      graph.render();

      // Add tooltips with full dialogue text to dialogue nodes
      for (const v of graph.g.nodes()) {
        const node = graph.g.node(v);
        if (node && node.tooltip) {
          const el = d3.select(`#n${v}`);
          if (!el.empty()) {
            el.select('title').remove();
            el.append('title').text(node.tooltip);
          }
        }
      }

      const selected = graph.renderer.getSelection();
      if (selected !== -1 && !isDeleting) {
        graph.renderer.scrollTo(selected);
      }
      widget.emitReloadedSignal();
      if (cb) {
        cb(data);
      }
      isDeleting = false;
    });
  }

  widget.flowDataChanged.connect(() => {
    load(() => {
      if (graph.renderer.getSelection() === -1 && !isDeleting) {
        graph.renderer.setTranslate([20, 20]);
      }
    });
  });

  widget.fileLoaded.connect(() => {
    graph.persistentWhitelist = null;
    graph.renderer.clearSelection();
  });

  widget.dialogueTextsChanged.connect(() => {
    // Reload with updated dialogue texts (payload is now filtered, lightweight)
    load();
  });

  widget.selectRequested.connect((id) => {
    select(id);
  });

  widget.eventNameVisibilityChanged.connect((visible) => {
    const previousValue = eventNamesVisible;
    eventNamesVisible = visible;
    if (!graph.g) {
      return;
    }
    if (visible !== previousValue) {
      graph.refresh();
      graph.render();
    }
  });

  widget.eventParamVisibilityChanged.connect((visible) => {
    const previousValue = eventParamVisible;
    eventParamVisible = visible;
    if (!graph.g) {
      return;
    }
    if (visible !== previousValue) {
      graph.refresh();
      graph.render();
    }
  });

  widget.actionProhibitionChanged.connect((value) => {
    actionsProhibited = value;
  });

  widget.notesDisplayChanged.connect((visible) => {
    notesVisible = visible;
    if (!graph.g) {
      return;
    }
    graph.refresh();
    graph.render();
  });

  widget.emitReadySignal();
  load();
});
