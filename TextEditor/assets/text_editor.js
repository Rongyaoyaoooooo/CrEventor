var widget = null;
var blocks = [];

// ── QWebChannel ───────────────────────────────────

function initChannel() {
  new QWebChannel(qt.webChannelTransport, function (ch) {
    widget = ch.objects.widget;
    widget.blocksChanged.connect(function () {
      widget.getBlocks(function (raw) {
        blocks = typeof raw === 'string' ? JSON.parse(raw) : raw;
        render();
      });
    });
    widget.ready();
  });
}

// ── Render ────────────────────────────────────────

function render() {
  var c = document.getElementById("blocks-container");
  c.innerHTML = "";
  if (!blocks || blocks.length === 0) return;
  // blocks: [slot0, text0, slot1, text1, ..., textN, slot_{N+1}]
  for (var i = 0; i < blocks.length; i++) {
    var b = blocks[i];
    if (b.type === "slot") {
      c.appendChild(renderSlot(b));
    } else {
      c.appendChild(renderText(b));
    }
  }
}

// ── Text block ────────────────────────────────────

function renderText(b) {
  var w = document.createElement("div");
  w.className = "b-text";

  var s = b.style || {};
  if (s.colour) w.style.color = s.colour;
  if (s.font_kind === "hylian") w.classList.add("font-hylian");
  if (s.text_size) w.style.fontSize = (s.text_size / 100) + "em";

  var el = document.createElement("div");
  el.className = "b-text-inner";
  el.contentEditable = "true";
  el.textContent = b.text;

  el.addEventListener("blur", function () {
    var t = el.textContent || "";
    if (t !== b.text && widget) widget.updateText(b.ti, t);
  });

  w.appendChild(el);
  return w;
}

// ── Slot block ────────────────────────────────────

function renderSlot(b) {
  var w = document.createElement("div");
  w.className = "b-slot";
  w.setAttribute("data-si", b.si);

  // ── 三控制 → 微小色点（可点删）
  if (b.style_ops && b.style_ops.length) {
    var ops = document.createElement("div");
    ops.className = "b-slot-ops";
    for (var i = 0; i < b.style_ops.length; i++) {
      var op = b.style_ops[i];
      ops.appendChild(renderStyleOp(b.si, op.ci, op));
    }
    w.appendChild(ops);
  }

  // ── 瞬时型 → chips（可拖拽）
  if (b.controls && b.controls.length) {
    var chips = document.createElement("div");
    chips.className = "b-slot-chips";
    for (var i = 0; i < b.controls.length; i++) {
      chips.appendChild(renderChip(b.si, b.controls[i].ci, b.controls[i]));
    }
    w.appendChild(chips);
  }

  // ── + 按钮
  var add = document.createElement("button");
  add.className = "b-slot-add";
  add.textContent = "+";
  add.title = "在此添加 control 或三控制";
  add.addEventListener("click", function () { showChooser(b.si); });
  w.appendChild(add);

  setupSlotDrop(w, b.si);
  return w;
}

// ── 三控制色点 ─────────────────────────────────────

var PERSISTENT = {"set_colour":1, "reset_colour":1, "font":1, "text_size":1};

function styleOpColour(kind, ctrl) {
  if (kind === "set_colour") {
    var map = {red:"#f44", blue:"#48f", yellow:"#ff4", green:"#4c4", orange:"#f94", grey:"#999"};
    var col = (ctrl && ctrl.colour) ? ctrl.colour : "";
    return map[col] || "#f44";
  }
  if (kind === "reset_colour") return "#888";
  if (kind === "font") return "#4af";
  if (kind === "text_size") return "#a4f";
  return "#666";
}

function renderStyleOp(si, ci, op) {
  var dot = document.createElement("span");
  dot.className = "b-style-dot";
  dot.title = op.label + " (点击删除)";
  dot.style.background = styleOpColour(op.kind, op);  // only bg, no text col
  dot.addEventListener("click", function () {
    if (widget) widget.deleteControl(si, ci);
  });
  return dot;
}

// ── 瞬时型 chip ────────────────────────────────────

function renderChip(si, ci, ctrl) {
  var chip = document.createElement("span");
  chip.className = "b-chip";
  chip.draggable = true;
  chip.textContent = ctrl.label;

  var x = document.createElement("span");
  x.className = "b-chip-x";
  x.textContent = "x";
  x.addEventListener("click", function (e) {
    e.stopPropagation();
    if (widget) widget.deleteControl(si, ci);
  });
  chip.appendChild(x);

  chip.addEventListener("dragstart", function (e) {
    e.dataTransfer.setData("text/x-ctrl", JSON.stringify({si: si, ci: ci}));
    e.dataTransfer.effectAllowed = "move";
    chip.classList.add("dragging");
  });
  chip.addEventListener("dragend", function () {
    chip.classList.remove("dragging");
    clearDropHL();
  });
  return chip;
}

// ── Slot drop ─────────────────────────────────────

function setupSlotDrop(el, si) {
  el.addEventListener("dragover", function (e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    el.classList.add("drop-hl");
  });
  el.addEventListener("dragleave", function () {
    el.classList.remove("drop-hl");
  });
  el.addEventListener("drop", function (e) {
    e.preventDefault();
    el.classList.remove("drop-hl");
    try {
      var raw = e.dataTransfer.getData("text/x-ctrl");
      if (raw && widget) {
        var info = JSON.parse(raw);
        widget.moveControl(info.si, info.ci, si);
      }
    } catch (ex) {}
  });
}

function clearDropHL() {
  var a = document.querySelectorAll(".drop-hl");
  for (var i = 0; i < a.length; i++) a[i].classList.remove("drop-hl");
}

// ── Chooser ───────────────────────────────────────

var _slot = -1;

function showChooser(si) {
  _slot = si;
  var ov = document.getElementById("ctrl-chooser-overlay");
  var lst = document.getElementById("ctrl-chooser-list");
  lst.innerHTML = "";

  var items = [
    ["pause", "暂停", "3a4a5a"],
    ["sound", "音效", "3a4a5a"],
    ["icon", "图标", "3a4a5a"],
    ["set_colour", "设颜色", "4a3a2a"],
    ["reset_colour", "重置颜色", "4a3a2a"],
    ["font", "字体", "4a3a2a"],
    ["text_size", "字号", "4a3a2a"],
  ];

  for (var i = 0; i < items.length; i++) {
    (function (k, bg) {
      var b = document.createElement("button");
      b.textContent = items[i][1];
      b.style.background = "#" + bg;
      b.addEventListener("click", function () {
        if (widget) widget.addControl(_slot, k);
        ov.style.display = "none";
      });
      lst.appendChild(b);
    })(items[i][0], items[i][2]);
  }
  ov.style.display = "flex";
}

// ── Wheel zoom ────────────────────────────────────

document.addEventListener("wheel", function (e) {
  if (e.shiftKey) {
    e.preventDefault();
    var z = parseFloat(document.documentElement.style.zoom) || 1;
    z = e.deltaY < 0 ? Math.min(3, z * 1.1) : Math.max(0.5, z / 1.1);
    document.documentElement.style.zoom = z;
  }
}, { passive: false });

// ── Init ──────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  initChannel();
  var ov = document.getElementById("ctrl-chooser-overlay");
  if (ov) ov.addEventListener("click", function (e) {
    if (e.target === ov) ov.style.display = "none";
  });
});
