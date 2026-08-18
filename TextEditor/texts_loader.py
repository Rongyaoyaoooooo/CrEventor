"""
Texts Loader — 加载/保存 texts.json（BCML 语言文本格式）
"""

import json
import os
from typing import Optional

# BotW 标准语言列表（同 bcml.mergers.texts.LANGUAGES）
GAME_LANGUAGES = [
    "USen", "EUen", "USfr", "USes",
    "EUde", "EUes", "EUfr", "EUit",
    "EUnl", "EUru", "CNzh", "JPja",
    "KRko", "TWzh",
]


class TextsLoader:
    """管理整个 texts.json 的加载、查询、修改和保存"""

    def __init__(self):
        # data["<language>"] = {"EventFlowMsg/xxx.msyt": {label: {attributes, contents}}}
        self._data: dict = {}
        self._source_path: Optional[str] = None
        self._dirty: bool = False

    # ── 加载 / 保存 ──────────────────────────────────

    def load(self, path: str) -> bool:
        """加载并校验 texts.json 文件，校验失败抛出 ValueError"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._validate(data)
        self._data = data
        self._source_path = path
        self._dirty = False
        return True

    @staticmethod
    def _validate(data: dict):
        """校验 texts.json 是否符合 BCML 格式"""
        errors = []

        # 1. 顶层必须是 dict
        if not isinstance(data, dict):
            raise ValueError("顶层必须是 JSON 对象(dict)，不能是数组或标量")

        # 2. 查找有效的语言键
        lang_keys = [k for k in data if k in GAME_LANGUAGES]
        if not lang_keys:
            raise ValueError(
                f"未找到任何有效的 BotW 语言键。\n"
                f"合法语言键: {', '.join(GAME_LANGUAGES)}\n"
                f"文件中找到的键: {', '.join(repr(k) for k in list(data.keys())[:10])}"
                + (f" ... 还有 {len(data) - 10} 个" if len(data) > 10 else "")
            )

        # 3. 逐语言、逐 MSBT、逐 entry 校验
        for lang_key in data:
            # 跳过非语言键（如 _meta 等），不报错
            if lang_key not in GAME_LANGUAGES:
                continue

            msbt_dict = data[lang_key]
            if not isinstance(msbt_dict, dict):
                errors.append(
                    f"[{lang_key}] 的值必须是对象(dict)，"
                    f"实际类型: {type(msbt_dict).__name__}"
                )
                continue

            for msbt_path, entries in msbt_dict.items():
                if not isinstance(msbt_path, str):
                    errors.append(
                        f"[{lang_key}] MSBT 路径必须是字符串，"
                        f"发现: {type(msbt_path).__name__}"
                    )
                    continue
                if not msbt_path.endswith(".msyt"):
                    errors.append(
                        f"[{lang_key}] 路径 '{msbt_path}' 不以 .msyt 结尾"
                    )

                if not isinstance(entries, dict):
                    errors.append(
                        f"[{lang_key}] '{msbt_path}' 的值必须是对象(dict)"
                    )
                    continue

                for label, entry in entries.items():
                    prefix = f"[{lang_key}] '{msbt_path}' / '{label}'"

                    if not isinstance(label, str):
                        errors.append(
                            f"{prefix} — entry key 必须是字符串，"
                            f"发现: {repr(label)}"
                        )
                    if not isinstance(entry, dict):
                        errors.append(f"{prefix} — entry 值必须是对象(dict)")
                        continue

                    # attributes 字段（可选，但如存在必须是字符串）
                    if "attributes" in entry and not isinstance(entry["attributes"], str):
                        errors.append(
                            f"{prefix} — 'attributes' 必须是字符串，"
                            f"实际: {type(entry['attributes']).__name__}"
                        )

                    # contents 字段
                    if "contents" not in entry:
                        errors.append(f"{prefix} — 缺少 'contents' 字段")
                    elif not isinstance(entry["contents"], list):
                        errors.append(
                            f"{prefix} — 'contents' 必须是数组，"
                            f"实际: {type(entry['contents']).__name__}"
                        )
                    else:
                        for ci, item in enumerate(entry["contents"]):
                            c_prefix = f"{prefix} contents[{ci}]"
                            if not isinstance(item, dict):
                                errors.append(
                                    f"{c_prefix} — 必须是对象(dict)"
                                )
                            elif "text" not in item and "control" not in item:
                                errors.append(
                                    f"{c_prefix} — 既无 'text' 也无 'control'，"
                                    f"每条必须是 {{\"text\": ...}} 或 "
                                    f"{{\"control\": {{...}}}}"
                                )
                            elif "text" in item and "control" in item:
                                errors.append(
                                    f"{c_prefix} — 不能同时包含 'text' 和 'control'"
                                )

        if errors:
            error_list = errors[:15]
            suffix = f"\n... 还有 {len(errors) - 15} 个错误" if len(errors) > 15 else ""
            raise ValueError(
                "文件结构不符合 BCML texts.json 格式:\n"
                + "\n".join(f"  - {e}" for e in error_list)
                + suffix
            )

    def save(self, path: Optional[str] = None) -> bool:
        """保存到指定路径（默认覆盖原文件）"""
        target = path or self._source_path
        if not target:
            raise ValueError("No save path specified")

        def export_value(value):
            """Copy data while removing editor-only positioning metadata."""
            if isinstance(value, dict):
                if isinstance(value.get("contents"), list):
                    result = {
                        "attributes": export_value(value.get("attributes", "")),
                        "contents": export_value(value["contents"]),
                    }
                    for key, child in value.items():
                        if key not in ("attributes", "contents", "_cid"):
                            result[key] = export_value(child)
                    return result
                return {
                    key: export_value(child)
                    for key, child in value.items()
                    if key != "_cid"
                }
            if isinstance(value, list):
                return [export_value(child) for child in value]
            return value

        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(export_value(self._data), f, ensure_ascii=False, indent=2)
        self._dirty = False
        return True

    def is_dirty(self) -> bool:
        return self._dirty

    def _lang(self) -> str:
        """返回当前数据中第一个有效的语言键"""
        for k in GAME_LANGUAGES:
            if k in self._data:
                return k
        # 回退：用第一个非特殊的键
        for k in self._data:
            if isinstance(self._data[k], dict):
                return k
        return "JPja"

    # ── 数据访问 ──────────────────────────────────────

    def get_msbt_paths(self) -> list[str]:
        """返回所有 msbt 文件路径列表（如 'EventFlowMsg/Npc_Kakariko002.msyt'）"""
        lang_data = self._data.get(self._lang(), {})
        return sorted(lang_data.keys())

    def get_entries(self, msbt_path: str) -> dict:
        """返回某个 msbt 文件的所有 entries"""
        return self._data.get(self._lang(), {}).get(msbt_path, {})

    def get_entry(self, msbt_path: str, label: str) -> Optional[dict]:
        """获取单条 entry"""
        return self._data.get(self._lang(), {}).get(msbt_path, {}).get(label)

    def get_entry_labels(self, msbt_path: str) -> list[str]:
        """返回某 msbt 文件的所有 label"""
        entries = self.get_entries(msbt_path)
        # 排序：数字池在前，具名消息在后
        pools = sorted([k for k in entries if k.isdigit()])
        named = sorted([k for k in entries if not k.isdigit()])
        return pools + named

    def get_pool_keys(self, msbt_path: str) -> list[str]:
        """仅返回数字池 key 列表（排序）"""
        entries = self.get_entries(msbt_path)
        return sorted([k for k in entries if k.isdigit()])

    def get_named_keys(self, msbt_path: str) -> list[str]:
        """仅返回具名 key 列表（排序）"""
        entries = self.get_entries(msbt_path)
        return sorted([k for k in entries if not k.isdigit()])

    # ── 数据修改 ──────────────────────────────────────

    def set_entry(self, msbt_path: str, label: str, entry: dict):
        """设置/更新某条 entry"""
        lang = self._lang()
        lang_data = self._data.setdefault(lang, {})
        msbt = lang_data.setdefault(msbt_path, {})
        msbt[label] = entry
        self._dirty = True

    def delete_entry(self, msbt_path: str, label: str):
        """删除某条 entry"""
        lang_data = self._data.get(self._lang(), {})
        msbt = lang_data.get(msbt_path, {})
        if label in msbt:
            del msbt[label]
            self._dirty = True

    def rename_entry(self, msbt_path: str, old_label: str, new_label: str):
        """重命名 label"""
        entry = self.get_entry(msbt_path, old_label)
        if entry is not None and old_label != new_label:
            self.set_entry(msbt_path, new_label, entry)
            self.delete_entry(msbt_path, old_label)
            self._dirty = True

    def get_max_pool_number(self, msbt_path: str) -> int:
        """获取某 msbt 文件中数字池的最大编号"""
        pools = self.get_pool_keys(msbt_path)
        if not pools:
            return -1
        return max(int(k) for k in pools)

    def allocate_pool_key(self, msbt_path: str) -> str:
        """分配一个新的数字池 key（4位补零）"""
        max_num = self.get_max_pool_number(msbt_path)
        return f"{max_num + 1:04d}"

    def ensure_entry(self, msbt_path: str, label: str, attributes: str = ""):
        """确保某 label 存在（不存在则创建空 entry）"""
        entry = self.get_entry(msbt_path, label)
        if entry is None:
            self.set_entry(msbt_path, label, {
                "attributes": attributes,
                "contents": [],
            })
        return self.get_entry(msbt_path, label)

    def mark_dirty(self):
        self._dirty = True
