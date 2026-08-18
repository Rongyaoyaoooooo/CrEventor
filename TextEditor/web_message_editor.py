"""
WebMessageEditor — WebEngine 驱动的消息编辑器

编辑格式（与原始 _contents 分离）：
  _text:        连续文本字符串，\n 为换行，\uE000-\uE0FF 为控件标记
  _annotations: 控件描述列表，含位置/范围和参数
    - 点控件 (pos+marker): {"kind":"pause","pos":5,"marker":"\uE000","params":{...}}
    - 范围控件 (start+end): {"kind":"set_colour","start":0,"end":10,"params":{"colour":"red"}}

导出 _rebuild_contents() 将 _text+_annotations 转回标准 _contents
导入 _parse_contents()   将标准 _contents 转为 _text+_annotations

三控制（set_colour / font / text_size）为范围注解，不影响文本标记。
"""
import copy
import os

from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import (
    QWebEnginePage, QWebEngineView, QWebEngineSettings,
)
from PyQt5.QtCore import (
    Qt, QUrl, QTimer, pyqtSignal, pyqtSlot, QObject,
)
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel,
)

from models import (
    CONTROL_KINDS, PERSISTENT_KINDS, INSTANT_KINDS,
    describe_control, is_text_item, is_control_item,
    make_control_item, normalize_control,
)
from option_pool_widget import OptionPoolWidget

COLOUR_CSS = {
    "red": "#ff4444", "blue": "#4488ff", "yellow": "#ffff44",
    "green": "#44cc44", "orange": "#ff9944",
    "grey": "#999999", "light_green1": "#66ff66",
    "light_green4": "#44cc44", "light_grey": "#aaaaaa",
}


# ═══════════════════════════════════════════════════════════════
# Python ↔ JS 桥接对象
# ═══════════════════════════════════════════════════════════════

class DiagnosticWebPage(QWebEnginePage):
    """Forward JavaScript errors to the visible Qt editor UI."""

    console_message = pyqtSignal(str)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        level_name = {0: "INFO", 1: "WARN", 2: "ERROR"}.get(int(level), "JS")
        source = os.path.basename(source_id) if source_id else "inline"
        formatted = f"{level_name}: {message} ({source}:{line_number})"
        print(f"[TextEditor JS] {formatted}", flush=True)
        self.console_message.emit(formatted)
        super().javaScriptConsoleMessage(level, message, line_number, source_id)

class TextEditorWebObject(QObject):
    blocksChanged = pyqtSignal()

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._e = editor

    @pyqtSlot()
    def ready(self):
        self._e._page_ready = True
        self._e._push_pm_document()

    @pyqtSlot(float)
    def setZoom(self, factor: float):
        """Shift+滚轮缩放"""
        self._e._web_view.setZoomFactor(factor)

    @pyqtSlot(str)
    def onDocumentChanged(self, json_str: str):
        """JS 端文档变更 → 转为 MSBT _contents 并保存"""
        import json
        doc = json.loads(json_str)
        self._e._contents = self._e._pm_doc_to_contents(doc)
        self._e._save_raw()
        self._e.data_changed.emit()

    @pyqtSlot(str)
    def logDebug(self, msg: str):
        """JS 端调试信息直出到终端"""
        print(f"[JS DEBUG] {msg}")

    @pyqtSlot(result=str)
    def getBlocks(self) -> str:
        import json
        return json.dumps(self._e._build_block_data(), ensure_ascii=False)

    @pyqtSlot(result=str)
    def getDebugInfo(self) -> str:
        """返回调试信息"""
        import json
        info = {
            "text": self._e._text,
            "annotations": self._e._annotations,
            "contents_len": len(self._e._contents),
        }
        return json.dumps(info, ensure_ascii=False, indent=2)

    # ── 位置转换辅助 ──

    def _text_replace(self, start, end, new_text):
        """替换 _text[start:end] 为 new_text，调整注解位置"""
        old_len = end - start
        delta = len(new_text) - old_len

        # 收集 [start, end) 内的点注解，按原 pos 排序 → 顺序匹配
        affected = sorted(
            [a for a in self._e._annotations if "pos" in a and start <= a["pos"] < end],
            key=lambda a: a["pos"]
        )
        new_markers = [(i, ch) for i, ch in enumerate(new_text) if 0xE000 <= ord(ch) <= 0xF8FF]

        affected_ids = set()
        for ann, (offset, ch) in zip(affected, new_markers):
            ann["pos"] = start + offset
            ann["marker"] = ch
            affected_ids.add(id(ann))
        for extra in affected[len(new_markers):]:
            self._e._annotations.remove(extra)

        self._e._text = self._e._text[:start] + new_text + self._e._text[end:]

        for ann in self._e._annotations:
            if "pos" in ann:
                if id(ann) in affected_ids:
                    continue
                if ann["pos"] >= end:
                    ann["pos"] += delta
            elif "start" in ann:
                if ann["start"] >= end:
                    ann["start"] += delta
                    ann["end"] += delta
                elif ann["start"] >= start:
                    ann["start"] = start
                    if ann["end"] > end:
                        ann["end"] += delta
                    elif ann["end"] > start:
                        ann["end"] = start

    def _text_insert(self, pos, s):
        """在 _text[pos] 处插入 s，调整后续注解位置"""
        self._e._text = self._e._text[:pos] + s + self._e._text[pos:]
        d = len(s)
        for ann in self._e._annotations:
            if "pos" in ann and ann["pos"] >= pos:
                ann["pos"] += d
            elif "start" in ann:
                if ann["start"] >= pos:
                    ann["start"] += d
                if ann["end"] >= pos:
                    ann["end"] += d

    def _text_delete(self, pos, count=1):
        """删除 _text[pos:pos+count]，调整后续注解位置"""
        self._e._text = self._e._text[:pos] + self._e._text[pos + count:]
        for ann in self._e._annotations:
            if "pos" in ann and ann["pos"] >= pos + count:
                ann["pos"] -= count
            elif "start" in ann:
                if ann["start"] >= pos + count:
                    ann["start"] -= count
                if ann["end"] >= pos + count:
                    ann["end"] -= count

    # ── 文本 ──

    @pyqtSlot(int, str)
    def updateText(self, ti: int, text: str):
        """编辑文本行：JS 发来的 text 含 \uE000 标记（inline badge）"""
        n = self._e._num_lines()
        if ti < 0 or ti >= n:
            return
        old_start = self._e._line_start(ti)
        old_end = self._e._line_end(ti)
        self._text_replace(old_start, old_end, text)
        self._e._rebuild_and_save()
        self._e.data_changed.emit()

    @pyqtSlot(int)
    def backspaceAtLineStart(self, ti: int):
        """行首退格：删除 ti-1 和 ti 之间的 \n，合并两行"""
        n = self._e._num_lines()
        if ti <= 0 or ti >= n:
            return
        nl_pos = self._e._line_end(ti - 1)
        if nl_pos >= len(self._e._text) or self._e._text[nl_pos] != '\n':
            return
        print(f"[backspaceAtLineStart] ti={ti} removing \\n at pos={nl_pos}")
        self._text_delete(nl_pos)
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, int)
    def splitLineAt(self, ti: int, pos: int):
        """行中回车：在 absolute pos 插入 \n"""
        n = self._e._num_lines()
        if ti < 0 or ti >= n:
            return
        abs_pos = self._e._line_start(ti) + pos
        if abs_pos < 0 or abs_pos > len(self._e._text):
            return
        print(f"[splitLineAt] ti={ti} pos={pos} abs_pos={abs_pos}")
        self._text_insert(abs_pos, '\n')
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, str)
    def updateMergedText(self, ti: int, segments_json: str):
        """合并块编辑：用 segments 重建该行文本"""
        import json
        segs = json.loads(segments_json)
        # 用 segments 中的 text 重建该行
        new_text = ''.join(s.get('text', '') for s in segs if s.get('text'))
        # 保留 PUA 标记：从旧文本中提取
        old_start = self._e._line_start(ti)
        old_end = self._e._line_end(ti)
        old_text = self._e._text[old_start:old_end]
        markers = ''.join(ch for ch in old_text if 0xE000 <= ord(ch) <= 0xF8FF)
        # 交错插入标记（简化：放在文本末尾）
        self._text_replace(old_start, old_end, new_text + markers)
        self._e._rebuild_and_save()
        self._e.data_changed.emit()

    # ── Slot control ──

    @pyqtSlot(int, str)
    def addControl(self, si: int, kind: str):
        import json
        if kind in ("choice", "single_choice"):
            if self._e._choice_managed_by_host:
                return
            ctrl = make_control_item(kind)
            if ctrl is None:
                return
            self._e._call_js("addChoice", kind, json.dumps(ctrl["control"], ensure_ascii=False))
            return
        ctrl = make_control_item(kind)
        if ctrl is None:
            return
        ctrl["control"]["_user"] = True
        self._e._call_js("insertInlineCtrl", si, 0, kind, json.dumps(ctrl["control"], ensure_ascii=False))

    def _add_control_at_slot(self, si, ctrl_data):
        """在 slot 位置 si 插入控件（PUA 标记 + 注解）"""
        marker = self._e._alloc_marker()
        kind = ctrl_data.get("kind", "")

        n = self._e._num_lines()
        if si <= 0:
            insert_pos = 0
        elif si >= n:
            insert_pos = len(self._e._text)
        else:
            insert_pos = self._e._line_end(si - 1)

        self._text_insert(insert_pos, marker)
        self._e._annotations.append({
            "kind": kind, "pos": insert_pos, "marker": marker,
            "params": dict(ctrl_data),
        })
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, str, str)
    def addParamControl(self, si: int, kind: str, params_json: str):
        """添加带参数的持久型控件（三控制）。"""
        import json
        params = json.loads(params_json) if params_json else {}
        if kind == "set_colour":
            colour = params.get("colour", "")
            if colour:
                self._e._call_js("applyMarkToParagraph", si, "colour", json.dumps({"colour": colour}))
            else:
                self._e._call_js("removeMarkFromParagraph", si, "colour")
        elif kind == "font":
            font_kind = params.get("font_kind", "normal")
            if font_kind and font_kind != "normal":
                self._e._call_js("applyMarkToParagraph", si, "font", json.dumps({"font_kind": font_kind}))
            else:
                self._e._call_js("removeMarkFromParagraph", si, "font")
        elif kind == "text_size":
            pct = params.get("percent", 100)
            if pct != 100:
                self._e._call_js("applyMarkToParagraph", si, "text_size", json.dumps({"percent": pct}))
            else:
                self._e._call_js("removeMarkFromParagraph", si, "text_size")
        else:
            ctrl_data = {"kind": kind, "_user": True}
            ctrl_data.update(params)
            self._e._call_js("insertInlineCtrl", si, 0, kind, json.dumps(ctrl_data, ensure_ascii=False))

    @pyqtSlot(int, int, int, str, str)
    def splitLineForStyle(self, ti: int, start: int, end: int, kind: str, params_json: str):
        """选中部分文本应用样式。"""
        import json
        params = json.loads(params_json) if params_json else {}

        n = self._e._num_lines()
        if ti < 0 or ti >= n:
            return
        line_start = self._e._line_start(ti)
        abs_start = line_start + start
        abs_end = line_start + end
        if abs_start >= abs_end:
            return

        print(f"[splitLineForStyle] ti={ti} start={start} end={end} kind={kind}")

        ctrl_data = {"kind": kind, "_user": True}
        ctrl_data.update(params)

        # 移除范围内已存在的同类型注解
        for ann in list(self._e._annotations):
            if "start" in ann and ann["kind"] == kind:
                if ann["start"] >= abs_start and ann["end"] <= abs_end:
                    self._e._annotations.remove(ann)

        self._e._annotations.append({
            "kind": kind,
            "start": abs_start,
            "end": abs_end,
            "params": dict(ctrl_data),
        })

        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, int, int)
    def moveControl(self, from_si: int, ci: int, to_si: int):
        """移动 slot 控件：找到 from_si 的第 ci 个注解，移到 to_si"""
        # 收集 from_si 位置的注解
        n = self._e._num_lines()
        if from_si < 0 or from_si > n:
            return
        target = None
        idx = 0
        for ann in self._e._annotations:
            if "pos" not in ann:
                continue
            kind = ann.get("kind", "")
            if kind in PERSISTENT_KINDS or kind in ("choice", "single_choice"):
                continue
            if self._ann_slot(ann) == from_si:
                if idx == ci:
                    target = ann
                    break
                idx += 1
        if target is None:
            return
        # 移到 to_si
        old_pos = target["pos"]
        self._text_delete(old_pos)  # 删除标记
        # 插入到新位置
        if to_si <= 0:
            new_pos = 0
        elif to_si >= n:
            new_pos = len(self._e._text)
        else:
            new_pos = self._e._line_end(to_si - 1)
        self._text_insert(new_pos, target["marker"])
        target["pos"] = new_pos
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, int)
    def deleteControl(self, si: int, ci: int):
        """删除内联控件"""
        self._e._call_js("deleteInlineCtrl", si, ci)
        # onDocumentChanged 自动触发保存

    def _ann_slot(self, ann):
        """判断点注解属于哪个 slot。仅边界注解返回 slot 索引，行内注解返回 None。"""
        pos = ann["pos"]
        if pos == 0:
            return 0
        n = self._e._num_lines()
        for li in range(n):
            line_start = self._e._line_start(li)
            line_end = self._e._line_end(li)
            if pos == line_start:
                return li
            if pos == line_end:
                return li + 1
        return None

    @pyqtSlot()
    def deleteChoice(self):
        """删除末尾的 choice / single_choice"""
        if self._e._choice_managed_by_host:
            return
        self._e._call_js("deleteChoice")
        # onDocumentChanged 自动触发保存

    @pyqtSlot()
    def editChoice(self):
        """双击 choice 块 → 编辑参数"""
        if self._e._choice_managed_by_host:
            return
        import json, copy, re
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox,
            QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout)
        from models import CONTROL_FIELDS

        doc = self._e._contents_to_pm_doc(self._e._contents)
        blocks = doc.get("content", [])
        choice_block = None
        for block in blocks:
            if block.get("type") == "choice":
                choice_block = block
                break
        if choice_block is None:
            return

        params = copy.deepcopy(choice_block.get("attrs", {}).get("_params", {}))
        kind = choice_block.get("attrs", {}).get("kind", "choice")
        fields = CONTROL_FIELDS.get(kind, [])
        if not fields:
            return

        dlg = QDialog(self._e)
        dlg.setWindowTitle(f"编辑选项 — {kind}")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet("""
            QDialog { background: #2a2a2a; }
            QLabel { color: #bbb; font-size: 12px; }
            QComboBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; min-width: 180px; }
            QComboBox:hover { border-color: #777; }
            QComboBox QAbstractItemView { background: #333; color: #ddd; selection-background-color: #4a6a4a; border: 1px solid #555; outline: none; }
            QSpinBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QLineEdit { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QPushButton { background: #444; color: #ddd; border: 1px solid #555; padding: 5px 16px; border-radius: 3px; min-width: 64px; }
            QPushButton:hover { background: #555; border-color: #777; }
            QDialogButtonBox QPushButton { background: #4a5a4a; border-color: #5a7a5a; }
            QDialogButtonBox QPushButton:hover { background: #5a7a5a; }
        """)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        widgets = {}

        for path, label, wtype, opts in fields:
            cur = params
            if '[' in path:
                parts = [part for part in re.split(r'[\[\]]', path) if part]
                for pi, p in enumerate(parts):
                    p = p.strip()
                    if not p: continue
                    is_last = (pi == len(parts) - 1)
                    if p.isdigit():
                        try: cur = cur[int(p)]
                        except (IndexError, TypeError): cur = ""
                    else:
                        if not is_last: cur = cur.get(p, "")
            else:
                cur = params.get(path, "")

            if wtype == "combo":
                w = QComboBox()
                for i, o in enumerate(opts):
                    lbl, val = (o[0], o[1]) if isinstance(o, tuple) else (str(o), o)
                    w.addItem(str(lbl), val)
                    if str(val) == str(cur):
                        w.setCurrentIndex(i)
                form.addRow(label, w)
                widgets[path] = ("combo", w)
            elif wtype == "int":
                w = QSpinBox()
                w.setRange(-999999, 999999)
                try: w.setValue(int(cur) if cur != "" else 0)
                except: w.setValue(0)
                form.addRow(label, w)
                widgets[path] = ("int", w)
            elif wtype == "str":
                w = QLineEdit(str(cur) if cur else "")
                form.addRow(label, w)
                widgets[path] = ("str", w)
            elif wtype == "int_list":
                t = ",".join(str(x) for x in cur) if isinstance(cur, list) else str(cur or "")
                w = QLineEdit(t)
                form.addRow(label, w)
                widgets[path] = ("int_list", w)

        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        print(f"  → exec dialog kind={kind}")
        if dlg.exec_() == QDialog.Accepted:
            for path, (wtype, w) in widgets.items():
                if wtype == "combo":
                    val = w.currentData()
                elif wtype == "int":
                    val = w.value()
                elif wtype == "str":
                    val = w.text()
                elif wtype == "int_list":
                    t = w.text().strip()
                    val = [int(x.strip()) for x in t.split(",") if x.strip()] if t else []

                if '[' in path:
                    parts = [part for part in re.split(r'[\[\]]', path) if part]
                    cur = params
                    for pi, p in enumerate(parts):
                        p = p.strip()
                        if not p: continue
                        is_last = (pi == len(parts) - 1)
                        if p.isdigit():
                            idx_n = int(p)
                            if is_last:
                                if not isinstance(cur, list):
                                    break
                                while len(cur) <= idx_n:
                                    cur.append(0)
                                cur[idx_n] = val
                            else:
                                if not isinstance(cur, list):
                                    break
                                while len(cur) <= idx_n:
                                    cur.append({})
                                cur = cur[idx_n]
                        else:
                            if is_last: cur[p] = val
                            else:
                                if p not in cur: cur[p] = []
                                cur = cur[p]
                else:
                    params[path] = val
            self._e._call_js("updateChoice", json.dumps(params, ensure_ascii=False))

    @pyqtSlot(int, int)
    def editControl(self, si: int, ci: int):
        """双击 chip → 编辑 control 参数"""
        target = None
        idx = 0
        for ann in self._e._annotations:
            if "pos" not in ann:
                continue
            kind = ann.get("kind", "")
            if kind in PERSISTENT_KINDS or kind in ("choice", "single_choice"):
                continue
            if self._ann_slot(ann) == si:
                if idx == ci:
                    target = ann
                    break
                idx += 1
        if target is None:
            return
        self._edit_annotation_params(target)

    @pyqtSlot(int, int)
    def editControlAt(self, ti: int, pos: int):
        """双击 inline badge → 编辑注解参数"""
        abs_pos = self._e._line_start(ti) + pos
        for ann in self._e._annotations:
            if ann.get("pos") == abs_pos and "pos" in ann:
                self._edit_annotation_params(ann)
                return

    @pyqtSlot(int, str)
    def editControlByCid(self, cid: int, docJson: str):
        """双击 PM inline badge → 按 _cid 编辑参数"""
        import json, copy
        doc = json.loads(docJson)
        blocks = doc.get("content", [])
        print(f"[editControlByCid] cid={cid} blocks={len(blocks)}")
        kind = None
        params = None
        for block in blocks:
            if block.get("type") != "paragraph":
                continue
            for node in block.get("content", []):
                ntype = node.get("type", "")
                if ntype in self._e._INLINE_CTRL_KINDS:
                    p = node.get("attrs", {}).get("_params", {})
                    if p.get("_cid") == cid:
                        kind = ntype
                        params = copy.deepcopy(p)
                        break
            if params is not None:
                break
        if params is None:
            print(f"  → cid={cid} not found")
            return
        print(f"  → found kind={kind} at cid={cid}")
        self._show_control_dialog(cid, kind, params)

    @pyqtSlot(int)
    def editControlByCidNoDoc(self, cid: int):
        """handleDoubleClick 用（无 docJson，用当前 _contents 重建）"""
        self.editControlByCid(cid, json.dumps(self._e._contents_to_pm_doc(self._e._contents)))

    def _show_control_dialog(self, cid, kind, params):
        """弹出控件参数编辑对话框，accept 时通过 cid 更新"""
        import re, json
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox,
            QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout)
        from models import CONTROL_FIELDS, normalize_control

        kind = params.get("kind", kind)
        params = normalize_control(kind, params)
        fields = CONTROL_FIELDS.get(kind, [])
        if not fields:
            print(f"  → no fields for kind={kind}")
            return

        dlg = QDialog(self._e)
        dlg.setWindowTitle(f"{'Edit' if self._e._host_language == 'en_US' else '编辑'} — {kind}")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet("""
            QDialog { background: #2a2a2a; }
            QLabel { color: #bbb; font-size: 12px; }
            QComboBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; min-width: 180px; }
            QComboBox:hover { border-color: #777; }
            QComboBox QAbstractItemView { background: #333; color: #ddd; selection-background-color: #4a6a4a; border: 1px solid #555; outline: none; }
            QSpinBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QLineEdit { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QPushButton { background: #444; color: #ddd; border: 1px solid #555; padding: 5px 16px; border-radius: 3px; min-width: 64px; }
            QPushButton:hover { background: #555; border-color: #777; }
            QDialogButtonBox QPushButton { background: #4a5a4a; border-color: #5a7a5a; }
            QDialogButtonBox QPushButton:hover { background: #5a7a5a; }
        """)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        widgets = {}

        for path, label, wtype, opts in fields:
            label = self._e._control_field_text(kind, path, label)
            if path == "_pause_mode":
                cur = "frames" if "frames" in params else "length"
            else:
                cur = params
            if path != "_pause_mode" and '[' in path:
                parts = [part for part in re.split(r'[\[\]]', path) if part]
                for pi, p in enumerate(parts):
                    p = p.strip()
                    is_last = (pi == len(parts) - 1)
                    if p.isdigit():
                        try: cur = cur[int(p)]
                        except (IndexError, TypeError): cur = ""
                    else:
                        if not is_last: cur = cur.get(p, "")
            elif path != "_pause_mode":
                cur = params.get(path, "")

            if wtype == "combo":
                w = QComboBox()
                for i, o in enumerate(opts):
                    lbl, val = (o[0], o[1]) if isinstance(o, tuple) else (str(o), o)
                    lbl = self._e._control_option_text(kind, path, val, str(lbl))
                    w.addItem(str(lbl), val)
                    if str(val) == str(cur):
                        w.setCurrentIndex(i)
                form.addRow(label, w)
                widgets[path] = ("combo", w)
            elif wtype == "int":
                w = QSpinBox()
                w.setRange(-999999, 999999)
                try: w.setValue(int(cur) if cur != "" else 0)
                except: w.setValue(0)
                form.addRow(label, w)
                widgets[path] = ("int", w)
            elif wtype == "str":
                w = QLineEdit(str(cur) if cur else "")
                form.addRow(label, w)
                widgets[path] = ("str", w)
            elif wtype == "int_list":
                t = ",".join(str(x) for x in cur) if isinstance(cur, list) else str(cur or "")
                w = QLineEdit(t)
                form.addRow(label, w)
                widgets[path] = ("int_list", w)

        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if self._e._host_language == "en_US":
            btns.button(QDialogButtonBox.Ok).setText("OK")
            btns.button(QDialogButtonBox.Cancel).setText("Cancel")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        print(f"  → exec dialog kind={kind}")
        if dlg.exec_() == QDialog.Accepted:
            for path, (wtype, w) in widgets.items():
                if wtype == "combo":
                    val = w.currentData()
                elif wtype == "int":
                    val = w.value()
                elif wtype == "str":
                    val = w.text()
                elif wtype == "int_list":
                    t = w.text().strip()
                    val = [int(x.strip()) for x in t.split(",") if x.strip()] if t else []

                if '[' in path:
                    parts = [part for part in re.split(r'[\[\]]', path) if part]
                    cur = params
                    for pi, p in enumerate(parts):
                        p = p.strip()
                        is_last = (pi == len(parts) - 1)
                        if p.isdigit():
                            idx_n = int(p)
                            if is_last: cur[idx_n] = val
                            else:
                                if idx_n >= len(cur): cur = ""
                                else: cur = cur[idx_n]
                        else:
                            if is_last: cur[p] = val
                            else:
                                if p not in cur: cur[p] = []
                                cur = cur[p]
                else:
                    params[path] = val
            if kind == "pause":
                mode = params.pop("_pause_mode", "length")
                if mode == "frames":
                    params.pop("length", None)
                else:
                    params.pop("frames", None)
            self._e._call_js("updateInlineCtrlByCid", cid, json.dumps(params, ensure_ascii=False))
            print(f"  → dialog accepted, called updateInlineCtrlByCid")
        else:
            print(f"  → dialog cancelled")

    @pyqtSlot(int, int, str)
    def editControlByIndex(self, ti: int, ci: int, docJson: str):
        """双击 PM inline badge → 编辑参数（直接用 JS 传来的 doc JSON）"""
        import json, copy
        doc = json.loads(docJson)
        blocks = doc.get("content", [])
        print(f"[editControlByIndex] ti={ti} ci={ci} blocks={len(blocks)}")
        if ti >= len(blocks):
            print(f"  → ti out of range")
            return
        block = blocks[ti]
        print(f"  → block type={block.get('type')} content_len={len(block.get('content', []))}")
        if block.get("type") != "paragraph":
            print(f"  → not a paragraph")
            return
        count = 0
        params = None
        kind = None
        for node in block.get("content", []):
            ntype = node.get("type", "")
            if ntype in self._e._INLINE_CTRL_KINDS:
                if count == ci:
                    params = copy.deepcopy(node.get("attrs", {}).get("_params", {}))
                    kind = ntype
                    print(f"  → found kind={kind} params={params}")
                    break
                count += 1
        if params is None:
            print(f"  → params is None (count={count} ci={ci})")
            return
        self._show_control_dialog(params.get("_cid"), kind, params)
        return
        # 内联对话框编辑
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox,
            QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout)
        from models import CONTROL_FIELDS
        import re

        # 复用 _edit_annotation_params 的对话框逻辑（简化版）
        kind = params.get("kind", kind)
        fields = CONTROL_FIELDS.get(kind, [])
        if not fields:
            print(f"  → no fields for kind={kind}")
            return

        dlg = QDialog(self._e)
        dlg.setWindowTitle(f"编辑 — {kind}")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet("""
            QDialog { background: #2a2a2a; }
            QLabel { color: #bbb; font-size: 12px; }
            QComboBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; min-width: 180px; }
            QComboBox:hover { border-color: #777; }
            QComboBox QAbstractItemView { background: #333; color: #ddd; selection-background-color: #4a6a4a; border: 1px solid #555; outline: none; }
            QSpinBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QLineEdit { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QPushButton { background: #444; color: #ddd; border: 1px solid #555; padding: 5px 16px; border-radius: 3px; min-width: 64px; }
            QPushButton:hover { background: #555; border-color: #777; }
            QDialogButtonBox QPushButton { background: #4a5a4a; border-color: #5a7a5a; }
            QDialogButtonBox QPushButton:hover { background: #5a7a5a; }
        """)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        widgets = {}

        for path, label, wtype, opts in fields:
            cur = params
            if '[' in path:
                parts = [part for part in re.split(r'[\[\]]', path) if part]
                for pi, p in enumerate(parts):
                    p = p.strip()
                    if not p: continue
                    is_last = (pi == len(parts) - 1)
                    if p.isdigit():
                        try: cur = cur[int(p)]
                        except (IndexError, TypeError): cur = ""
                    else:
                        if not is_last: cur = cur.get(p, "")
            else:
                cur = params.get(path, "")

            if wtype == "combo":
                w = QComboBox()
                for i, o in enumerate(opts):
                    lbl, val = (o[0], o[1]) if isinstance(o, tuple) else (str(o), o)
                    w.addItem(str(lbl), val)
                    if str(val) == str(cur):
                        w.setCurrentIndex(i)
                form.addRow(label, w)
                widgets[path] = ("combo", w)
            elif wtype == "int":
                w = QSpinBox()
                w.setRange(-999999, 999999)
                try: w.setValue(int(cur) if cur != "" else 0)
                except: w.setValue(0)
                form.addRow(label, w)
                widgets[path] = ("int", w)
            elif wtype == "str":
                w = QLineEdit(str(cur) if cur else "")
                form.addRow(label, w)
                widgets[path] = ("str", w)
            elif wtype == "int_list":
                t = ",".join(str(x) for x in cur) if isinstance(cur, list) else str(cur or "")
                w = QLineEdit(t)
                form.addRow(label, w)
                widgets[path] = ("int_list", w)

        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        print(f"  → exec dialog kind={kind}")
        if dlg.exec_() == QDialog.Accepted:
            for path, (wtype, w) in widgets.items():
                if wtype == "combo":
                    val = w.currentData()
                elif wtype == "int":
                    val = w.value()
                elif wtype == "str":
                    val = w.text()
                elif wtype == "int_list":
                    t = w.text().strip()
                    val = [int(x.strip()) for x in t.split(",") if x.strip()] if t else []

                if '[' in path:
                    parts = [part for part in re.split(r'[\[\]]', path) if part]
                    cur = params
                    for pi, p in enumerate(parts):
                        p = p.strip()
                        if not p: continue
                        is_last = (pi == len(parts) - 1)
                        if p.isdigit():
                            idx_n = int(p)
                            if is_last: cur[idx_n] = val
                            else:
                                if idx_n >= len(cur): cur = ""
                                else: cur = cur[idx_n]
                        else:
                            if is_last: cur[p] = val
                            else:
                                if p not in cur: cur[p] = []
                                cur = cur[p]
                else:
                    params[path] = val
            self._e._call_js("updateInlineCtrl", ti, ci, json.dumps(params, ensure_ascii=False))
            print(f"  → dialog accepted, called updateInlineCtrl")
        else:
            print(f"  → dialog cancelled")

    def _edit_annotation_params(self, target):
        """用表单编辑注解的 params 字段"""
        import re
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox,
            QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout)
        from models import CONTROL_FIELDS

        params = target.get("params", {})
        kind = target.get("kind", "")
        fields = CONTROL_FIELDS.get(kind, [])
        if not fields:
            return

        dlg = QDialog(self._e)
        dlg.setWindowTitle(f"编辑 {describe_control(params)}")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet("""
            QDialog { background: #2a2a2a; }
            QLabel { color: #bbb; font-size: 12px; }
            QComboBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; min-width: 180px; }
            QComboBox:hover { border-color: #777; }
            QComboBox QAbstractItemView { background: #333; color: #ddd; selection-background-color: #4a6a4a; border: 1px solid #555; outline: none; }
            QSpinBox { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QLineEdit { background: #333; color: #ddd; border: 1px solid #555; padding: 2px 6px; border-radius: 3px; }
            QPushButton { background: #444; color: #ddd; border: 1px solid #555; padding: 5px 16px; border-radius: 3px; min-width: 64px; }
            QPushButton:hover { background: #555; border-color: #777; }
            QDialogButtonBox QPushButton { background: #4a5a4a; border-color: #5a7a5a; }
            QDialogButtonBox QPushButton:hover { background: #5a7a5a; }
        """)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        widgets = {}

        for path, label, wtype, opts in fields:
            cur = params
            if '[' in path:
                parts = [part for part in re.split(r'[\[\]]', path) if part]
                for pi, p in enumerate(parts):
                    p = p.strip()
                    if not p: continue
                    is_last = (pi == len(parts) - 1)
                    if p.isdigit():
                        try: cur = cur[int(p)]
                        except (IndexError, TypeError): cur = ""
                    else:
                        if not is_last: cur = cur.get(p, "")
            else:
                cur = params.get(path, "")

            if wtype == "combo":
                w = QComboBox()
                for i, o in enumerate(opts):
                    lbl, val = (o[0], o[1]) if isinstance(o, tuple) else (str(o), o)
                    w.addItem(str(lbl), val)
                    if str(val) == str(cur):
                        w.setCurrentIndex(i)
                form.addRow(label, w)
                widgets[path] = ("combo", w)
            elif wtype == "int":
                w = QSpinBox()
                w.setRange(-999999, 999999)
                try: w.setValue(int(cur) if cur != "" else 0)
                except: w.setValue(0)
                form.addRow(label, w)
                widgets[path] = ("int", w)
            elif wtype == "str":
                w = QLineEdit(str(cur) if cur else "")
                form.addRow(label, w)
                widgets[path] = ("str", w)
            elif wtype == "int_list":
                t = ",".join(str(x) for x in cur) if isinstance(cur, list) else str(cur or "")
                w = QLineEdit(t)
                form.addRow(label, w)
                widgets[path] = ("int_list", w)

        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        print(f"  → exec dialog kind={kind}")
        if dlg.exec_() == QDialog.Accepted:
            for path, (wtype, w) in widgets.items():
                if wtype == "combo":
                    val = w.currentData()
                elif wtype == "int":
                    val = w.value()
                elif wtype == "str":
                    val = w.text()
                elif wtype == "int_list":
                    t = w.text().strip()
                    val = [int(x.strip()) for x in t.split(",") if x.strip()] if t else []

                if '[' in path:
                    parts = [part for part in re.split(r'[\[\]]', path) if part]
                    cur = params
                    for pi, p in enumerate(parts):
                        p = p.strip()
                        if not p: continue
                        is_last = (pi == len(parts) - 1)
                        if p.isdigit():
                            idx_n = int(p)
                            if is_last: cur[idx_n] = val
                            else:
                                if idx_n >= len(cur): cur = ""
                                else: cur = cur[idx_n]
                        else:
                            if is_last: cur[p] = val
                            else:
                                if p not in cur: cur[p] = []
                                cur = cur[p]
                else:
                    params[path] = val

            self._e._rebuild_and_save()
            self._e.data_changed.emit()

    @pyqtSlot(int)
    def addTextLine(self, si: int):
        """在 si 处插入空文本行"""
        self._e._call_js("insertParagraph", si)
        # onDocumentChanged 自动触发保存

    @pyqtSlot(int, int, str)
    def insertInlineAt(self, ti: int, pos: int, kind: str):
        """在行内 pos 插入内联控件"""
        ctrl = make_control_item(kind)
        ctrl_data = ctrl["control"]
        ctrl_data["_user"] = True
        import json
        self._e._call_js("insertInlineCtrl", ti, pos, kind, json.dumps(ctrl_data, ensure_ascii=False))
        # onDocumentChanged 自动触发保存

    @pyqtSlot(int, int, int, int)
    def moveChipToText(self, si: int, ci: int, ti: int, pos: int):
        """slot chip 拖到文字中：转为内联注解"""
        n = self._e._num_lines()
        target = None
        idx = 0
        for ann in self._e._annotations:
            if "pos" not in ann:
                continue
            kind = ann.get("kind", "")
            if kind in PERSISTENT_KINDS or kind in ("choice", "single_choice"):
                continue
            if self._ann_slot(ann) == si:
                if idx == ci:
                    target = ann
                    break
                idx += 1
        if target is None:
            return
        old_pos = target["pos"]
        # 先计算删除后的目标位置
        abs_to_raw = self._e._line_start(ti) + pos
        if old_pos < abs_to_raw:
            abs_to = abs_to_raw - 1
        else:
            abs_to = abs_to_raw
        # 碰撞检测：模拟 _text_delete 后其他注解的位置
        for ann2 in self._e._annotations:
            if ann2 is target:
                continue
            if "pos" not in ann2:
                continue
            ap = ann2["pos"]
            if ap >= old_pos + 1:
                ap -= 1
            if ap in (abs_to, abs_to - 1, abs_to + 1):
                return
        # 安全：碰撞检测通过后才删除
        self._text_delete(old_pos)
        self._text_insert(abs_to, target["marker"])
        target["pos"] = abs_to
        target["params"]["_user"] = True
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, int, int, int)
    def moveInlineAt(self, from_ti: int, from_pos: int, to_ti: int, to_pos: int):
        """移动内联控件"""
        abs_from = self._e._line_start(from_ti) + from_pos
        target = self._e._find_ann_at(abs_from)
        if target is None:
            return
        # 先计算删除后的目标位置
        abs_to_raw = self._e._line_start(to_ti) + to_pos
        if abs_from < abs_to_raw:
            abs_to = abs_to_raw - 1
        else:
            abs_to = abs_to_raw
        # 碰撞检测：模拟 _text_delete 后其他注解的位置
        for ann in self._e._annotations:
            if ann is target:
                continue
            if "pos" not in ann:
                continue
            ap = ann["pos"]
            if ap >= abs_from + 1:
                ap -= 1
            if ap in (abs_to, abs_to - 1, abs_to + 1):
                return
        # 安全：碰撞检测通过后才删除
        self._text_delete(abs_from)
        self._text_insert(abs_to, target["marker"])
        target["pos"] = abs_to
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()

    @pyqtSlot(int, int, int)
    def moveInlineToSlot(self, ti: int, pos: int, to_si: int):
        """内联控件移回 slot"""
        abs_pos = self._e._line_start(ti) + pos
        target = self._e._find_ann_at(abs_pos)
        if target is None:
            return
        self._text_delete(abs_pos)
        self._e._annotations.remove(target)
        # 插入到目标 slot
        n = self._e._num_lines()
        if to_si <= 0:
            new_pos = 0
        elif to_si >= n:
            new_pos = len(self._e._text)
        else:
            new_pos = self._e._line_end(to_si - 1)
        self._text_insert(new_pos, target["marker"])
        target["pos"] = new_pos
        self._e._annotations.append(target)
        self._e._rebuild_and_save()
        self._e._push_data()
        self._e.data_changed.emit()


# ═══════════════════════════════════════════════════════════════
# WebMessageEditor
# ═══════════════════════════════════════════════════════════════

class WebMessageEditor(QWidget):
    data_changed = pyqtSignal()
    pool_toggle_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader = None
        self._current_msbt = ""
        self._current_label = ""
        self._attributes = ""
        self._contents: list = []
        self._text: str = ""           # 连续文本（含 \n 和 PUA 标记）
        self._annotations: list = []   # 控件描述列表
        self._next_marker: int = 0     # PUA 标记分配计数器
        self._page_ready: bool = False
        self._choice_managed_by_host: bool = False
        self._host_language: str = "zh_CN"
        self._setup_ui()

    def set_host_language(self, language: str):
        """Localize only the hosted editor; standalone keeps its own UI."""
        self._host_language = language or "zh_CN"
        if self._page_ready:
            self._call_js("setUiLanguage", self._host_language)

    def _control_field_text(self, kind: str, path: str, fallback: str) -> str:
        if self._host_language != "en_US":
            return fallback
        return {
            ("pause", "_pause_mode"): "Mode",
            ("pause", "length"): "Length",
            ("pause", "frames"): "Frames",
            ("sound", "unknown[0]"): "Emotion / voice",
            ("sound", "unknown[1]"): "Additional parameter",
            ("sound2", "unknown[0]"): "Parameter",
            ("icon", "icon"): "Icon",
            ("variable", "variable_kind"): "Type",
            ("variable", "name"): "Variable name",
            ("animation", "name"): "Animation name",
            ("auto_advance", "frames"): "Frames",
        }.get((kind, path), fallback)

    def _control_option_text(self, kind: str, path: str, value, fallback: str) -> str:
        if self._host_language != "en_US":
            return fallback
        if kind == "pause" and path == "_pause_mode":
            return {"length": "Preset length", "frames": "Custom frames"}.get(value, fallback)
        if kind == "pause" and path == "length":
            return {"short": "Short", "long": "Long", "longer": "Longer"}.get(value, fallback)
        if kind == "sound" and path == "unknown[0]":
            emotions = ["Normal", "Happy", "Angry", "Sad", "Surprised", "Calm"]
            if isinstance(value, int) and 0 <= value <= 11:
                return f"{value}: {emotions[value % 6]} ({'voiced' if value >= 6 else 'silent'})"
        if kind == "variable" and path == "variable_kind":
            return {
                1: "1: String", 9: "9: Float (distance)",
                11: "11: String (item name)", 12: "12: String (item name)",
                14: "14: Integer (count)", 15: "15: Integer (count)",
                16: "16: Integer (price)", 17: "17: Integer (ratio / score)",
                18: "18: Integer (ratio / total)",
            }.get(value, fallback)
        return fallback

    # ── UI ──

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        info = QHBoxLayout()
        self._info_label = QLabel("未加载")
        self._info_label.setStyleSheet("color:#aaa;font-size:11px;padding:2px 6px;")
        info.addWidget(self._info_label)
        info.addStretch()
        self._attr_edit = QLabel("")
        self._attr_edit.setStyleSheet("color:#8af;font-size:11px;padding:2px;")
        info.addWidget(self._attr_edit)
        layout.addLayout(info)

        self._web_view = QWebEngineView()
        self._web_page = DiagnosticWebPage(self._web_view)
        self._web_page.console_message.connect(self._on_js_console_message)
        self._web_view.setPage(self._web_page)
        self._web_view.setMinimumHeight(300)
        self._web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self._web_view.page().setBackgroundColor(QColor("#1e1e1e"))
        self._web_view.page().settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True)

        self._option_pool = OptionPoolWidget()
        self._option_pool.pool_changed.connect(lambda: self.data_changed.emit())
        self._option_pool.choice_config_changed.connect(self._on_choice_config_changed)

        layout.addWidget(self._web_view, 1)

        bottom = QHBoxLayout()
        self._opt_btn = QPushButton("展开选项池")
        self._opt_btn.clicked.connect(self._toggle_pool)
        self._opt_btn.setFixedWidth(100)
        bottom.addWidget(self._opt_btn)
        bottom.addStretch()
        layout.addLayout(bottom)

        os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '9222'
        self._wobj = TextEditorWebObject(self)
        self._channel = QWebChannel()
        self._channel.registerObject('widget', self._wobj)
        self._web_view.page().setWebChannel(self._channel)
        self._web_view.loadFinished.connect(self._on_page_loaded)
        # Do not change/clear the default profile here.  In CrEventor that
        # profile is already serving the flowchart WebEngine; clearing it from
        # a second view can stall navigation for both pages.
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        html_path = os.path.join(assets_dir, "text_editor_v3.html")
        # Use Qt's native local-file URL builder.  Do not inline the 486 KB PM
        # bundle with setHtml(): Qt 5 percent-encodes that into a data URL and
        # can exceed its ~2 MB setHtml limit, leaving loadFinished silent.
        if os.path.isfile(html_path):
            self._editor_page_url = QUrl.fromLocalFile(html_path)
            self._loading_bootstrap = True
            print("[TextEditor] loading bootstrap page", flush=True)
            self._web_view.setHtml(
                "<!doctype html><html><body style='background:#1e1e1e;"
                "color:#aaa'>TextEditor bootstrap...</body></html>"
            )
        else:
            self._loading_bootstrap = False
            exc = FileNotFoundError(html_path)
            self._info_label.setText(f"文本编辑器页面读取失败: {exc}")
            self._web_view.setHtml(
                "<html><body style='background:#1e1e1e;color:#f88'>"
                "无法读取 TextEditor 页面资源。</body></html>"
            )
        self.setEnabled(False)

    def _on_page_loaded(self, ok):
        """Report page failures; successful pages call ready() via WebChannel."""
        phase = "bootstrap" if getattr(self, '_loading_bootstrap', False) else "editor"
        print(f"[TextEditor] loadFinished phase={phase} ok={ok}", flush=True)
        if not ok:
            self._info_label.setText("文本编辑器页面加载失败，请检查 TextEditor/assets")
            print("[TextEditor] QWebEngine failed to load text_editor_v3.html")
            return
        if getattr(self, '_loading_bootstrap', False):
            self._loading_bootstrap = False
            print(
                f"[TextEditor] loading {self._editor_page_url.toEncoded().data().decode()}",
                flush=True,
            )
            self._web_view.setUrl(self._editor_page_url)
            return
        QTimer.singleShot(3000, self._check_page_ready)
        QTimer.singleShot(500, self._probe_frontend)

    def _on_js_console_message(self, message: str):
        if "ERROR:" in message or not self._page_ready:
            self._info_label.setText(f"文本编辑器 JS：{message}")

    def _probe_frontend(self):
        if self._page_ready:
            return
        script = """
        ({
          pm: typeof PM,
          qwebchannel: typeof QWebChannel,
          qt: typeof qt,
          transport: (typeof qt !== 'undefined' && qt.webChannelTransport)
                     ? 'object' : 'missing'
        })
        """
        self._web_view.page().runJavaScript(script, self._show_frontend_probe)

    def _show_frontend_probe(self, result):
        print(f"[TextEditor] frontend probe={result!r}", flush=True)
        if self._page_ready:
            return
        if isinstance(result, dict):
            self._info_label.setText(
                "前端诊断：PM={pm}, QWebChannel={qwebchannel}, "
                "qt={qt}, transport={transport}".format(**result)
            )
        else:
            self._info_label.setText("前端诊断失败：JavaScript 无返回结果")

    def _check_page_ready(self):
        """Expose WebChannel/JavaScript startup failures in the visible UI."""
        if not self._page_ready:
            self._info_label.setText(
                "文本编辑器前端未就绪：QWebEngine 或 JavaScript 初始化失败"
            )

    def _push_pm_document(self):
        """将当前 _contents 转为 ProseMirror JSON 推送到 JS"""
        import json, base64
        self._call_js("setUiLanguage", self._host_language)
        pm_doc = self._contents_to_pm_doc(self._contents)
        raw = json.dumps(pm_doc, ensure_ascii=False)
        encoded = base64.b64encode(raw.encode('utf-8')).decode('ascii')
        self._web_view.page().runJavaScript(
            "loadDocument(JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('"
            + encoded + "'),c=>c.charCodeAt(0)))));"
        )
        # 同步 cidCounter，确保新插入的控件不会冲突
        self._web_view.page().runJavaScript(f"cidCounter = {self._next_cid};")

    def _call_js(self, func_name, *args):
        """调用 JS 全局函数"""
        import json
        parts = []
        for a in args:
            if isinstance(a, str):
                escaped = a.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
                parts.append(f"'{escaped}'")
            elif isinstance(a, bool):
                parts.append("true" if a else "false")
            elif a is None:
                parts.append("null")
            elif isinstance(a, (int, float)):
                parts.append(str(a))
            else:
                parts.append(json.dumps(a, ensure_ascii=False))
        code = f"{func_name}({','.join(parts)});"
        self._web_view.page().runJavaScript(code)

    # ── 公共接口 ──

    # inline 控件 → ProseMirror atom node
    _INLINE_CTRL_KINDS = {"pause", "sound", "sound2", "icon", "variable", "animation", "auto_advance", "raw"}

    def _contents_to_pm_doc(self, contents):
        """MSBT _contents → ProseMirror doc JSON"""
        doc_content = []
        choice_content = []
        current = []
        active_colour = None
        active_font = "normal"
        active_size = 100

        if '_next_cid' not in self.__dict__:
            self._next_cid = 1

        for item in contents:
            if is_control_item(item):
                ctrl = item["control"]
                kind = ctrl.get("kind", "")
                if kind == "set_colour":
                    active_colour = ctrl.get("colour", "")
                elif kind == "reset_colour":
                    active_colour = None
                elif kind == "font":
                    active_font = ctrl.get("font_kind", "normal")
                elif kind == "text_size":
                    active_size = ctrl.get("percent", 100)
                elif kind in ("choice", "single_choice"):
                    # Choice is message-level configuration.  Keep collecting
                    # the surrounding text and append the config after every
                    # paragraph so it can never split or precede body text.
                    choice_content.append({
                        "type": "choice",
                        "attrs": {"kind": kind, "_params": copy.deepcopy(ctrl)},
                    })
                else:
                    # Do not mutate the loader entry merely by rendering it;
                    # otherwise opening and cancelling an editor looks dirty.
                    pm_ctrl = normalize_control(kind, ctrl)
                    if "_cid" not in pm_ctrl:
                        pm_ctrl["_cid"] = self._next_cid
                        self._next_cid += 1
                    current.append({"type": kind, "attrs": {"_params": pm_ctrl}})
            elif is_text_item(item):
                text = item["text"]
                parts = text.split('\n')
                for i, part in enumerate(parts):
                    if part:
                        node = {"type": "text", "text": part}
                        marks = []
                        if active_colour:
                            marks.append({"type": "colour", "attrs": {"colour": active_colour}})
                        if active_font != "normal":
                            marks.append({"type": "font", "attrs": {"font_kind": active_font}})
                        if active_size != 100:
                            marks.append({"type": "text_size", "attrs": {"percent": active_size}})
                        if marks:
                            node["marks"] = marks
                        current.append(node)
                    if i < len(parts) - 1:
                        doc_content.append({"type": "paragraph", "content": current})
                        current = []
        if current or not doc_content:
            doc_content.append({"type": "paragraph", "content": current})
        doc_content.extend(choice_content)
        return {"type": "doc", "content": doc_content}

    def _pm_doc_to_contents(self, doc_json):
        """ProseMirror doc JSON → MSBT _contents"""
        result = []
        choice_controls = []
        prev_colour = None
        prev_font = "normal"
        prev_size = 100
        paragraph_index = 0

        blocks = doc_json.get("content", [])
        for bi, block in enumerate(blocks):
            btype = block.get("type", "")
            if btype == "choice":
                params = block.get("attrs", {}).get("_params", {})
                if not params:
                    params = {"kind": block.get("attrs", {}).get("kind", "choice")}
                choice_controls.append({"control": params})
                continue
            if btype != "paragraph":
                continue

            if paragraph_index > 0:
                if result and "text" in result[-1]:
                    result[-1]["text"] += "\n"
                else:
                    result.append({"text": "\n"})
            paragraph_index += 1

            for node in block.get("content", []):
                ntype = node.get("type", "")
                if ntype == "text":
                    text = node.get("text", "")
                    colour = None
                    font_kind = "normal"
                    size_pct = 100
                    for m in node.get("marks", []):
                        mt = m.get("type", "")
                        if mt == "colour":
                            colour = m.get("attrs", {}).get("colour")
                        elif mt == "font":
                            font_kind = m.get("attrs", {}).get("font_kind", "normal")
                        elif mt == "text_size":
                            size_pct = m.get("attrs", {}).get("percent", 100)
                    if colour != prev_colour:
                        if colour:
                            result.append({"control": {"kind": "set_colour", "colour": colour}})
                        elif prev_colour:
                            result.append({"control": {"kind": "reset_colour"}})
                        prev_colour = colour
                    if font_kind != prev_font:
                        if font_kind != "normal":
                            result.append({"control": {"kind": "font", "font_kind": font_kind}})
                        elif prev_font != "normal":
                            result.append({"control": {"kind": "font", "font_kind": "normal"}})
                        prev_font = font_kind
                    if size_pct != prev_size:
                        if size_pct != 100:
                            result.append({"control": {"kind": "text_size", "percent": size_pct}})
                        elif prev_size != 100:
                            result.append({"control": {"kind": "text_size", "percent": 100}})
                        prev_size = size_pct
                    if text:
                        result.append({"text": text})
                elif ntype in self._INLINE_CTRL_KINDS:
                    params = normalize_control(
                        ntype, node.get("attrs", {}).get("_params", {})
                    )
                    # The ProseMirror node type is authoritative.  Parameter
                    # dialogs may produce a non-empty attrs dict without a
                    # kind; exporting that verbatim creates invalid controls
                    # such as {"length":"short"} or {"unknown":[]}.
                    result.append({"control": params})

        if prev_colour:
            result.append({"control": {"kind": "reset_colour"}})
        if prev_font != "normal":
            result.append({"control": {"kind": "font", "font_kind": "normal"}})
        if prev_size != 100:
            result.append({"control": {"kind": "text_size", "percent": 100}})

        merged = []
        for item in result:
            if merged and is_text_item(merged[-1]) and is_text_item(item):
                merged[-1]["text"] += item["text"]
            else:
                merged.append(item)
        # Normalize message-level choice configuration to the very end.
        merged.extend(choice_controls)
        return merged

    def set_context(self, loader, msbt_path, label):
        self._loader = loader
        self._current_msbt = msbt_path
        self._current_label = label
        self._attributes = ""
        self._load_raw()
        if self._page_ready:
            self._push_pm_document()
        short = msbt_path.split("\\")[-1] if "\\" in msbt_path else msbt_path
        self._info_label.setText(f"{short}  ->  {label}")
        self._attr_edit.setText(f"attributes:{self._attributes}" if self._attributes else "")
        if not self._choice_managed_by_host:
            self._option_pool.set_contents(self._contents)
        self.setEnabled(True)

    def set_choice_managed_by_host(self, enabled: bool = True):
        """Make choice/single_choice read-only for an embedding host.

        CrEventor uses this mode because its original M panel is the sole
        owner of option-pool and Choice configuration.
        """
        self._choice_managed_by_host = bool(enabled)
        self._opt_btn.setVisible(not enabled)
        self._option_pool.setVisible(not enabled)

    def clear_context(self):
        self._loader = None
        self._current_msbt = ""
        self._current_label = ""
        self._attributes = ""
        self._contents = []
        self._text = ""
        self._annotations = []
        self._next_marker = 0
        self._info_label.setText("未加载")
        self._attr_edit.setText("")
        self.setEnabled(False)
        # 推送空文档清空 PM 编辑器
        if self._page_ready:
            self._push_pm_document()

    def refresh_pool_view(self):
        """刷新选项池面板"""
        if self._loader and self._current_msbt:
            self._option_pool.set_context(self._loader, self._current_msbt)
            self._option_pool.set_contents(self._contents)

    # ═══════════════════════════════════════════════
    # 格式转换（编辑格式 ↔ 原始 _contents）
    # ═══════════════════════════════════════════════

    def _load_raw(self):
        entry = self._loader.get_entry(self._current_msbt, self._current_label)
        if entry is None:
            self._contents = [{"text": ""}]
            self._attributes = ""
        else:
            self._contents = entry.get("contents", [])
            self._attributes = entry.get("attributes", "")

    def _parse_contents(self):
        """原始 _contents → _text + _annotations

        - text 项直接拼入 _text
        - 常 control（非三控制）→ 在 _text 中插入 PUA 标记 + 点注解
        - 三控制（set_colour/font/text_size）→ 范围注解，记录 start/end
        - 末尾闭合所有打开的范围
        """
        self._text = ""
        self._annotations = []
        self._next_marker = 0

        # 当前活跃的三控制状态：(value, start_pos)
        active_colour = None        # str | None
        active_colour_start = 0
        active_font = "normal"
        active_font_start = 0
        active_size = 100
        active_size_start = 0

        def _close_ranges(end_pos):
            nonlocal active_colour, active_colour_start
            nonlocal active_font, active_font_start
            nonlocal active_size, active_size_start
            if active_colour is not None and active_colour_start < end_pos:
                self._annotations.append({
                    "kind": "set_colour", "start": active_colour_start,
                    "end": end_pos, "params": {"colour": active_colour},
                })
            if active_font != "normal" and active_font_start < end_pos:
                self._annotations.append({
                    "kind": "font", "start": active_font_start,
                    "end": end_pos, "params": {"font_kind": active_font},
                })
            if active_size != 100 and active_size_start < end_pos:
                self._annotations.append({
                    "kind": "text_size", "start": active_size_start,
                    "end": end_pos, "params": {"percent": active_size},
                })

        for item in self._contents:
            if is_text_item(item):
                self._text += item["text"]
            elif is_control_item(item):
                ctrl = copy.deepcopy(item["control"])
                kind = ctrl.get("kind", "")

                if kind == "set_colour":
                    colour = ctrl.get("colour", "")
                    if active_colour is not None and active_colour_start < len(self._text):
                        self._annotations.append({
                            "kind": "set_colour", "start": active_colour_start,
                            "end": len(self._text), "params": {"colour": active_colour},
                        })
                    active_colour = colour
                    active_colour_start = len(self._text)
                elif kind == "reset_colour":
                    if active_colour is not None and active_colour_start < len(self._text):
                        self._annotations.append({
                            "kind": "set_colour", "start": active_colour_start,
                            "end": len(self._text), "params": {"colour": active_colour},
                        })
                    active_colour = None
                elif kind == "font":
                    font_kind = ctrl.get("font_kind", "normal")
                    if active_font != "normal" and active_font_start < len(self._text):
                        self._annotations.append({
                            "kind": "font", "start": active_font_start,
                            "end": len(self._text), "params": {"font_kind": active_font},
                        })
                    active_font = font_kind
                    active_font_start = len(self._text)
                elif kind == "text_size":
                    percent = ctrl.get("percent", 100)
                    if active_size != 100 and active_size_start < len(self._text):
                        self._annotations.append({
                            "kind": "text_size", "start": active_size_start,
                            "end": len(self._text), "params": {"percent": active_size},
                        })
                    active_size = percent
                    active_size_start = len(self._text)
                else:
                    marker = self._alloc_marker()
                    self._text += marker
                    self._annotations.append({
                        "kind": kind, "pos": len(self._text) - 1,
                        "marker": marker, "params": ctrl,
                    })

        _close_ranges(len(self._text))

        if not self._text:
            self._text = ""

        print(f"[_parse_contents] _text={repr(self._text)}")
        print(f"  _annotations={self._annotations}")
        print(f"  _contents={self._contents}")

    def _rebuild_contents(self):
        """_text + _annotations → 原始 _contents

        点注解 → control 项插入对应位置
        范围注解 → 跟踪当前三控制状态，仅状态变化时输出，避免连续同维度产生多余 reset
        """
        result = []

        events = []
        for ann in self._annotations:
            if "pos" in ann:
                events.append((ann["pos"], "control", ann))
            elif "start" in ann:
                events.append((ann["start"], "range_start", ann))
                events.append((ann["end"], "range_end", ann))

        events.sort(key=lambda e: (e[0], 0 if e[1] == "range_end" else 1 if e[1] == "control" else 2))

        text_pos = 0
        active_colour = None
        active_font = "normal"
        active_size = 100

        for pos, etype, ann in events:
            if pos > text_pos:
                chunk = self._text[text_pos:pos]
                clean = ''.join(ch for ch in chunk if not (0xE000 <= ord(ch) <= 0xF8FF))
                if clean:
                    result.append({"text": clean})

            if etype == "control":
                ctrl = copy.deepcopy(ann["params"])
                ctrl.pop("_user", None)
                result.append({"control": ctrl})
                text_pos = pos + 1
            elif etype == "range_start":
                kind = ann["kind"]
                params = ann["params"]
                if kind == "set_colour":
                    new_colour = params.get("colour", "")
                    if new_colour != active_colour:
                        if active_colour is not None:
                            result.append({"control": {"kind": "reset_colour"}})
                        result.append({"control": {"kind": "set_colour", "colour": new_colour}})
                        active_colour = new_colour
                elif kind == "font":
                    new_font = params.get("font_kind", "normal")
                    if new_font != active_font:
                        if active_font != "normal":
                            result.append({"control": {"kind": "font", "font_kind": "normal"}})
                        if new_font != "normal":
                            result.append({"control": {"kind": "font", "font_kind": new_font}})
                        active_font = new_font
                elif kind == "text_size":
                    new_size = params.get("percent", 100)
                    if new_size != active_size:
                        if active_size != 100:
                            result.append({"control": {"kind": "text_size", "percent": 100}})
                        if new_size != 100:
                            result.append({"control": {"kind": "text_size", "percent": new_size}})
                        active_size = new_size
                text_pos = pos
            elif etype == "range_end":
                kind = ann["kind"]
                if kind == "set_colour":
                    if active_colour is not None:
                        result.append({"control": {"kind": "reset_colour"}})
                        active_colour = None
                elif kind == "font":
                    if active_font != "normal":
                        result.append({"control": {"kind": "font", "font_kind": "normal"}})
                        active_font = "normal"
                elif kind == "text_size":
                    if active_size != 100:
                        result.append({"control": {"kind": "text_size", "percent": 100}})
                        active_size = 100
                text_pos = pos

        # 剩余文本
        if text_pos < len(self._text):
            chunk = self._text[text_pos:]
            clean = ''.join(ch for ch in chunk if not (0xE000 <= ord(ch) <= 0xF8FF))
            if clean:
                result.append({"text": clean})

        # 后处理：合并连续的纯文本项
        merged = []
        for item in result:
            if merged and is_text_item(merged[-1]) and is_text_item(item):
                merged[-1]["text"] += item["text"]
            else:
                merged.append(item)

        self._contents = merged
        print(f"[_rebuild_contents] _text={repr(self._text)}")
        print(f"  _annotations={self._annotations}")
        print(f"  _contents={self._contents}")

    def _save_raw(self):
        if not self._loader or not self._current_label:
            return
        entry = self._loader.get_entry(self._current_msbt, self._current_label)
        if entry is not None:
            entry["contents"] = copy.deepcopy(self._contents)
            entry["attributes"] = self._attributes
            self._loader.mark_dirty()
            print(f"[_save_raw] saved {len(self._contents)} items, loader dirty=True")

    def _rebuild_and_save(self):
        self._rebuild_contents()
        self._save_raw()

    # ── 新数据模型辅助 ──

    def _alloc_marker(self):
        """分配唯一的 PUA 标记字符"""
        marker = chr(0xE000 + self._next_marker)
        self._next_marker += 1
        return marker

    def _find_ann_by_marker(self, marker):
        """按 PUA 标记查找注解"""
        for ann in self._annotations:
            if ann.get("marker") == marker:
                return ann
        return None

    def _find_ann_at(self, pos):
        """查找 pos 处的点注解"""
        for ann in self._annotations:
            if ann.get("pos") == pos:
                return ann
        return None

    def _line_start(self, li):
        """第 li 行在 _text 中的起始位置"""
        if li <= 0:
            return 0
        pos = -1
        for _ in range(li):
            pos = self._text.find('\n', pos + 1)
            if pos < 0:
                return len(self._text)
        return pos + 1

    def _line_end(self, li):
        """第 li 行在 _text 中的结束位置（不含 \n）"""
        start = self._line_start(li)
        end = self._text.find('\n', start)
        if end < 0:
            return len(self._text)
        return end

    def _num_lines(self):
        if not self._text:
            return 1
        return self._text.count('\n') + 1

    def _compute_style_at(self, abs_pos):
        """计算 _text 中 abs_pos 处的累积持久样式"""
        colour = None
        font_kind = "normal"
        size_pct = 100
        for ann in self._annotations:
            if "start" not in ann:
                continue
            s, e = ann["start"], ann["end"]
            if s <= abs_pos < e:
                k = ann["kind"]
                if k == "set_colour":
                    colour = ann["params"].get("colour", "")
                elif k == "font":
                    font_kind = ann["params"].get("font_kind", "normal")
                elif k == "text_size":
                    size_pct = ann["params"].get("percent", 100)
        s = {}
        if colour:
            s["colour"] = COLOUR_CSS.get(colour, None)
        if font_kind != "normal":
            s["font_kind"] = font_kind
        if size_pct != 100:
            s["text_size"] = size_pct
        return s

    # ═══════════════════════════════════════════════
    # 块数据（给 JS 端渲染）
    # ═══════════════════════════════════════════════

    def _build_block_data(self):
        """_text + _annotations → JS blocks

        输出格式与旧版兼容：
        - type: "text"   — 文本块，可选 segments（合并内联 badge）
        - type: "slot"   — 行间 control chip 组
        - type: "choice" — 末尾选项
        """
        print(f"[_build_block_data] _text={repr(self._text)}")
        print(f"  _annotations={self._annotations}")

        result = []
        n_lines = self._num_lines()

        for li in range(n_lines):
            line_start = self._line_start(li)
            line_end = self._line_end(li)
            line_text = self._text[line_start:line_end]

            # 收集该行内的所有点注解（内联 badge）
            # 扁平架构：PUA 标记在文本中即 inline，包括行首/行尾
            inline_anns = []
            for ann in self._annotations:
                if "pos" not in ann:
                    continue
                if ann.get("kind", "") in PERSISTENT_KINDS:
                    continue
                if ann.get("kind", "") in ("choice", "single_choice"):
                    continue
                if line_start <= ann["pos"] < line_end:
                    inline_anns.append(ann)

            # 收集该行范围的持久样式
            line_style = self._compute_style_at(line_start)

            if inline_anns:
                # 有内联 badge：构建 segments
                segs = []
                prev = line_start
                for ann in sorted(inline_anns, key=lambda a: a["pos"]):
                    if ann["pos"] > prev:
                        chunk = self._text[prev:ann["pos"]]
                        clean = ''.join(ch for ch in chunk if not (0xE000 <= ord(ch) <= 0xF8FF))
                        segs.append({"ti": li, "text": clean, "style": line_style})
                    kind = ann.get("kind", "")
                    segs.append({
                        "type": "variable",
                        "kind": kind,
                        "label": describe_control(ann["params"]),
                        "ti": li,
                        "pos": ann["pos"] - line_start,
                        "marker": ann["marker"],
                    })
                    prev = ann["pos"] + 1  # skip marker
                if prev < line_end:
                    chunk = self._text[prev:line_end]
                    clean = ''.join(ch for ch in chunk if not (0xE000 <= ord(ch) <= 0xF8FF))
                    segs.append({"ti": li, "text": clean, "style": line_style})

                clean_line = ''.join(ch for ch in line_text if not (0xE000 <= ord(ch) <= 0xF8FF))
                result.append({
                    "type": "text", "ti": li,
                    "text": clean_line or '',
                    "style": line_style,
                    "segments": segs,
                })
            else:
                clean_line = ''.join(ch for ch in line_text if not (0xE000 <= ord(ch) <= 0xF8FF))
                result.append({
                    "type": "text", "ti": li,
                    "text": clean_line or '',
                    "style": line_style,
                })

        # choice/single_choice
        for ann in self._annotations:
            kind = ann.get("kind", "")
            if kind in ("choice", "single_choice"):
                result.append({
                    "type": "choice",
                    "kind": kind,
                    "label": describe_control(ann["params"]),
                })
                break

        return result

    def _make_slot_block(self, si, annotations):
        """构建 slot 块"""
        controls = []
        for ci, ann in enumerate(annotations):
            controls.append({
                "ci": ci,
                "kind": ann.get("kind", ""),
                "label": describe_control(ann["params"]),
            })
        return {"type": "slot", "si": si, "controls": controls}

    def _push_data(self):
        self._wobj.blocksChanged.emit()

    # ── 选项池 ──

    def _toggle_pool(self):
        self.pool_toggle_requested.emit()

    def _on_choice_config_changed(self, config):
        """choice/single_choice 配置变更 → 更新 _contents → 推送 PM"""
        if self._choice_managed_by_host:
            return
        self._push_pm_document()
        self._save_raw()
        self.data_changed.emit()
