"""
Font Mapper — 系统字体 ↔ 游戏字体的映射关系
由于无法直接提取游戏字库，使用系统自带字体大致模拟视觉效果
"""

from PyQt5.QtGui import QFont, QFontDatabase


# 游戏字体 → 系统字体映射（选视觉差异较大的系统字体）
GAME_TO_SYSTEM = {
    "默认":        "Microsoft YaHei",       # 微软雅黑 — 游戏默认对话字体
    "Hylian":      "SimSun",                # 宋体 — 海利亚古文风格（字形差异大）
    "强调/标题":    "SimHei",                # 黑体 — 加粗醒目
    "手写/日记":    "KaiTi",                 # 楷体 — 手写风格
}

# 系统字体名 → 显示名（中文易读）
SYSTEM_DISPLAY_NAMES = {
    "Microsoft YaHei":  "微软雅黑",
    "SimSun":            "宋体",
    "SimHei":            "黑体",
    "KaiTi":             "楷体",
}


def get_available_font_mapping() -> dict:
    """返回当前系统可用的字体映射（滤掉未安装的）"""
    available = {}
    for game_name, sys_font in GAME_TO_SYSTEM.items():
        if is_font_available(sys_font):
            available[game_name] = sys_font
    return available


def is_font_available(font_name: str) -> bool:
    """检查字体是否在系统中可用"""
    db = QFontDatabase()
    families = db.families()
    return font_name in families


def get_font_for_game(game_font: str, size: int = 12) -> QFont:
    """获取对应游戏字体的 QFont 对象"""
    sys_font = GAME_TO_SYSTEM.get(game_font, GAME_TO_SYSTEM["默认"])
    if not is_font_available(sys_font):
        sys_font = GAME_TO_SYSTEM["默认"]
    font = QFont(sys_font, size)
    if game_font == "强调/标题":
        font.setBold(True)
    elif game_font == "Hylian":
        font.setBold(True)
    return font


def get_legend_text() -> str:
    """生成字体图例文本（显示在 UI 底部）"""
    parts = []
    for game_name, sys_font in GAME_TO_SYSTEM.items():
        display = SYSTEM_DISPLAY_NAMES.get(sys_font, sys_font)
        available = "✓" if is_font_available(sys_font) else "✗"
        parts.append(f"{display} → {game_name} ({available})")
    return "  |  ".join(parts)
