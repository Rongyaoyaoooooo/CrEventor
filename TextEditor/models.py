"""
TextEditor 数据模型
定义 texts.json 的内存表示结构
"""

from typing import Any

# ── Control 类型枚举 ─────────────────────────────────

CONTROL_KINDS = [
    "set_colour", "reset_colour",
    "font", "text_size",
    "pause",
    "sound", "sound2",
    "icon",
    "variable",
    "animation",
    "auto_advance",
    "choice", "single_choice",
    "raw",
]

# 持续型 control（作用于一段文本区间，在渲染中体现为富文本样式）
PERSISTENT_KINDS = {"set_colour", "reset_colour", "font", "text_size"}

# 内联型 control（插入到句子中间，跟文本一样渲染，不与前后文本行合并）
INLINE_KINDS = {"variable", "icon"}

# 瞬时/单次触发型 control（在流中作为标记点出现）
INSTANT_KINDS = {"pause", "sound", "sound2", "icon",
                 "animation", "auto_advance", "choice", "single_choice", "raw"}


# ── Control 默认结构工厂 ──────────────────────────────

DEFAULT_CONTROL_TEMPLATES = {
    "set_colour":   {"kind": "set_colour", "colour": "blue"},
    "reset_colour": {"kind": "reset_colour"},
    "font":         {"kind": "font", "font_kind": "normal"},
    "text_size":    {"kind": "text_size", "percent": 100},
    "pause":        {"kind": "pause", "length": "short"},
    # 6 = normal voice with sound; the second value is 0 for the documented
    # emotion/voice mapping.  Existing controls retain their explicit values.
    "sound":        {"kind": "sound", "unknown": [6, 0]},
    "sound2":       {"kind": "sound2", "unknown": [0, 205]},
    "icon":         {"kind": "icon", "icon": "right_arrow"},
    "variable":     {"kind": "variable", "variable_kind": 1, "name": ""},
    "animation":    {"kind": "animation", "name": "Greeting_00"},
    "auto_advance": {"kind": "auto_advance", "frames": 30},
    "choice":       {"kind": "choice",
                     "choice_labels": [],
                     "selected_index": 0,
                     "cancel_index": 0,
                     "unknown": 2},
    "single_choice":{"kind": "single_choice", "label": 0},
    "raw":          {"kind": "raw", "one": {"two": {"field_1": 0}}},
}


# ── Control 编辑字段定义（供对话框动态生成）───────────

CONTROL_FIELDS = {
    "set_colour": [
        ("colour", "颜色", "combo",
         ["blue", "red", "grey", "light_green1", "light_green4",
          "light_grey", "orange"]),
    ],
    "reset_colour": [],
    "font": [
        ("font_kind", "字体类型", "combo", [("正常", "normal"), ("粗体 (海利亚)", "hylian")]),
    ],
    "text_size": [
        ("percent", "字号(%)", "combo", ["80", "100", "125"]),
    ],
    "pause": [
        ("_pause_mode", "模式", "combo", [("预设长度", "length"), ("自定义帧数", "frames")]),
        ("length", "长度", "combo", [("短", "short"), ("长", "long"), ("更长", "longer")]),
        ("frames", "帧数", "int", None),
    ],
    "sound": [
        ("unknown[0]", "情绪编码", "combo",
         [("0: 普通(无声)", 0), ("1: 开心(无声)", 1), ("2: 生气(无声)", 2),
          ("3: 悲伤(无声)", 3), ("4: 惊讶(无声)", 4), ("5: 沉思(无声)", 5),
          ("6: 普通(有声)", 6), ("7: 开心(有声)", 7), ("8: 生气(有声)", 8),
          ("9: 悲伤(有声)", 9), ("10: 惊讶(有声)", 10), ("11: 沉思(有声)", 11)]),
        ("unknown[1]", "附加参数", "int", None),
    ],
    "sound2": [
        ("unknown[0]", "参数", "int", None),
    ],
    "icon": [
        ("icon", "图标", "combo",
         ["right_arrow", "left_arrow", "up_arrow",
          "a:10", "a:11", "b", "x:12", "x:37", "x:38", "y",
          "l", "r", "zl:14", "zl:15",
          "l_stick_press", "l_stick_forward", "l_stick_back",
          "r_stick_press",
          "d_pad_down", "d_pad_left", "d_pad_up", "d_pad_right",
          "plus", "minus",
          "l_stick_left", "l_stick_right",
          "r_stick_vertical", "r_stick_horizontal",
          "gamepad"]),
    ],
    "variable": [
        ("variable_kind", "类型", "combo",
         [("1: 字符串", 1), ("9: 浮点(距离)", 9), ("11: 字符串(物品名)", 11),
          ("12: 字符串(物品名2)", 12), ("14: 整数(计数)", 14),
          ("15: 整数(计数)", 15), ("16: 整数(价格)", 16),
          ("17: 整数(卢比/计分)", 17), ("18: 整数(卢比/总计)", 18)]),
        ("name", "变量名", "str", None),
    ],
    "animation": [
        ("name", "动画名", "combo",
         ["Greeting_00", "Greeting_01", "Happy_00", "Happy_01",
          "Humming_00", "Ease_00", "Ease_01",
          "CustomGreeting", "CustomHappy", "CustomSurpriseL",
          "CustomSurpriseS", "CustomPanic", "CustomLaugh",
          "CustomPose", "CustomCold", "CustomHot", "CustomInjury",
          "QuestionNormal_01"]),
    ],
    "auto_advance": [
        ("frames", "帧数", "int", None),
    ],
    "choice": [
        ("choice_labels", "选项编号(逗号分隔)", "int_list", None),
        ("cancel_index", "取消索引", "int", None),
    ],
    "single_choice": [
        ("label", "选项编号", "int", None),
    ],
    "raw": [],
}


# ── Contents 辅助 ──────────────────────────────────────

def get_control_kind(control: dict) -> str:
    """从 control dict 中提取 kind"""
    return control.get("kind", "")


def is_text_item(item: dict) -> bool:
    return "text" in item


def is_control_item(item: dict) -> bool:
    return "control" in item


def make_text_item(text: str) -> dict:
    return {"text": text}


def make_control_item(kind: str) -> dict:
    """创建指定 kind 的 control dict（使用默认值）"""
    import copy
    template = DEFAULT_CONTROL_TEMPLATES.get(kind)
    if template is None:
        raise ValueError(f"Unknown control kind: {kind}")
    return {"control": copy.deepcopy(template)}


def normalize_control(kind: str, params: dict) -> dict:
    """Return a complete control using the canonical template for *kind*.

    Existing/unknown fields are preserved.  Missing nested fields and missing
    list elements are filled from the template, so e.g. a damaged
    ``sound: {unknown: []}`` becomes the documented neutral voiced default
    ``unknown: [6, 0]``.
    """
    import copy

    template = DEFAULT_CONTROL_TEMPLATES.get(kind, {"kind": kind})

    def merge(default, value):
        if isinstance(default, dict):
            result = copy.deepcopy(default)
            if isinstance(value, dict):
                for key, child in value.items():
                    result[key] = merge(default.get(key), child) if key in default else copy.deepcopy(child)
            return result
        if isinstance(default, list):
            if not isinstance(value, list):
                return copy.deepcopy(default)
            result = copy.deepcopy(value)
            for index in range(len(result), len(default)):
                result.append(copy.deepcopy(default[index]))
            return result
        return copy.deepcopy(value) if value is not None else copy.deepcopy(default)

    result = merge(template, params if isinstance(params, dict) else {})
    result["kind"] = kind
    # Pause supports two mutually exclusive representations.  A frames-based
    # pause must not acquire the template's preset length during normalization.
    if kind == "pause" and isinstance(params, dict) and "frames" in params:
        result.pop("length", None)
    return result


def describe_control(control: dict) -> str:
    """生成 control 的简短描述文本"""
    kind = control.get("kind", "?")
    if kind == "set_colour":
        return f"颜色: {control.get('colour', '?')}"
    if kind == "reset_colour":
        return "重置颜色"
    if kind == "font":
        return f"字体: {control.get('font_kind', '?')}"
    if kind == "text_size":
        return f"字号: {control.get('percent', '?')}%"
    if kind == "pause":
        length = control.get("length", control.get("frames", "?"))
        return f"停顿: {length}"
    if kind == "sound":
        return f"音效: [{control['unknown'][0]}, {control['unknown'][1]}]"
    if kind == "sound2":
        return f"音效2: [{control['unknown'][0]}]"
    if kind == "icon":
        return f"图标: {control.get('icon', '?')}"
    if kind == "variable":
        return f"变量: {control.get('name', '?')}"
    if kind == "animation":
        return f"动画: {control.get('name', '?')}"
    if kind == "auto_advance":
        return f"自动推进: {control.get('frames', '?')}帧"
    if kind == "choice":
        n = len(control.get("choice_labels", []))
        return f"选项 ({n}个)"
    if kind == "single_choice":
        return f"单选项: label={control.get('label', '?')}"
    if kind == "raw":
        return "消息延续"
    return f"未知: {kind}"
