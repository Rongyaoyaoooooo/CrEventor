# CrEventor

<p align="center">
  <img src="docs/logo.png" alt="CrEventor Logo" width="240">
</p>

> 塞尔达传说：旷野之息（The Legend of Zelda: Breath of the Wild）Mod 制作综合事件流（EventFlow）开发工具

**项目仓库**：https://github.com/Rongyaoyaoooooo/CrEventor

简体中文 · [English](./README.en.md)

CrEventor 是一款基于 [leoetlino/event-editor](https://github.com/leoetlino/event-editor) 深度二次开发的《旷野之息》事件流编辑器。它在保留原版流程图可视化编辑能力的基础上，重点强化了**中文本地化**、**gamedata 与 savedata 生成**、**eventinfo 注册**、**包含 control 字段的文本深度高级编辑**、**选项池（GeneralChoice）** 等能力，面向**系统化 Mod 制作**场景。

![主界面全景](docs/main.png)

---

## 关于 AI 辅助开发

CrEventor 的开发大量使用了 AI 辅助，包括代码编写、功能实现与后续计划中的 AI 事件流生成功能。

我并非专业程序员，因此我不回避代码层面的混乱与繁杂。CrEventor 最初也不是为了展示编程技巧而开发，也不是为了成为最优秀的编辑器而存在，而是源于我在制作《旷野之息》Mod 时遇到的实际需求：我需要一个能够把 EventFlow、文本编辑、GameData、SaveData、EventInfo 等工作整合起来，并尽可能减少重复操作与数据丢失风险的工具。

因此，对这个项目而言，我首先关心的是功能是否正确、实际工作流是否好用，以及用户的数据是否安全。项目仍处于开发阶段，代码质量和程序稳定性可能存在不足，我不会回避这一点。实际的 Bug、错误输出、数据异常以及能够改善项目的技术建议，都欢迎通过 Issues 提交。

但如果你反对使用 AI 编写软件，认为 AI 辅助开发的项目不值得使用，或者单纯不喜欢 CrEventor 的设计理念，那么这个项目可能并不适合你。

这完全没关系。

BotW Mod 社区已经拥有其他优秀的 EventFlow 与文本编辑工具。请选择你信任、喜欢并且适合自己工作流的工具。

CrEventor 不试图取代它们，也不要求任何人使用它。

我会按照自己的 Mod 制作需求和开发理念继续决定 CrEventor 应该成为什么。我欢迎任何希望更轻松地开始制作 Mod 的创作者提出质疑，反馈问题。

---

## 功能特性

- **多流程标签页工作区**：同时打开多个事件流（.bfevfl），支持关闭、重命名、拖拽排序。
- **完整 JSON 往返序列化**：EventFlow 可无损转换为 JSON 并重建为二进制（.bfevfl），便于版本管理与人工作业。
- **中文本地化（CNzh）**：面向中文剧情制作，支持文本提取、编辑与覆盖层独立保存。
  > 注意：发布版出于规避版权问题的考虑，**不内置任何游戏文本**，请自行准备从游戏提取的文本数据（详见下方「教程」）。
- **文本深度高级编辑**：支持对 MSBT 中 `control` 字段的可视化编辑，涵盖 `set_colour` / `font` / `text_size` / `sound` / `pause` / `choice` 等十余种控制类型。

  ![文本编辑窗口](docs/text_editor.png)

- **选项池（Option Pool / GeneralChoice）编辑器**：按 MSBT 管理对话按钮库，支持为每个对话节点配置按钮、光标、取消项。
  - 自动识别 `GeneralChoice{N}` 节点（SwitchEvent / ActionEvent / ForkEvent 三种形态）。
  - `unknown = 2n + 2` 字段公式，经 2400+ 真实样本验证。
  - 选项配置自动写入所有指向同一选项节点的父级 Talk 消息。

  ![选项池 M 面板](docs/panel_m.png)

- **gamedata 与 savedata 生成**：从事件流中提取并生成游戏数据、存档数据等产物。
- **eventinfo 注册**：生成事件信息，便于事件流的注册与识别。
- **游戏数据编辑（sbeventpack + 标志位）**：事件包依赖分析，Bool / S32 / String 标志卡交互式编辑。

  ![游戏数据 N 面板](docs/panel_n.png)

- **项目化管理**：创建 / 打开项目，定时自动保存，关键操作自动备份，支持手动与自动备份恢复。
- **中英双语界面**：菜单、面板、对话框完整国际化（`zh_CN` / `en_US`），运行时切换。
- **平台 / 语言切换**：Switch / WiiU 平台切换，游戏文本语言选择。

---

## 重要声明（请务必阅读）

> **本项目基于个人制作经验开发，不代表标准的 Mod 制作流程。**

在使用本工具之前，请先详细阅读 [Zeldamods Wiki](https://zeldamods.org/) 的基础教程，确保你对《旷野之息》的 Mod 项目结构、各个文件的作用与规范有一定理解，并具备一定制作经验后再使用本工具。再次强调：本工具出于个人使用习惯与开发简易的考虑而制作，**不代表标准 Mod 制作流程**。

- **版权规避**：发布版**不内置任何游戏文本**，以避免版权问题。
- **未完整测试**：本工具尚未进行大型项目的完整测试，建议在使用时勤加手动备份。遇到任何 Bug，欢迎记录并反馈。
- **保存即备份**：任何一次保存都是一次备份，**不会覆盖之前的保存**。请按照保存时间查找备份；如有需要，可在菜单中恢复备份。手动备份时可**自定义备份名称**，用于记录、追踪项目进度。

  ![备份与恢复](docs/backup.png)

- **备份 JSON 已弃用**：备份 JSON 只会备份事件流的 JSON。出于某些原因，该功能现已弃用，后续可能会重新调整其逻辑并重新启用。目前，对于因使用「备份 JSON」功能而导致的数据丢失，我们**不负责任**。

---

## Mod 打包流程

本项目生成的文件需要手动打包为最终 Mod：

1. 将项目内生成的事件流文件，依照所需依赖**手动打包为 sbeventpack**。
2. 使用 [BCML](https://github.com/NiceneNerd/BCML) 将其**打包为 BNP**。
3. 将 BNP **解压缩**。
4. 将项目文件夹 `logs/` 中的文件**置入解压出的 BNP** 中。
5. 得到的即为**完整的 Mod 文件**。

---

## 配套工具

- **QuestEditor**：配套的任务编辑器，目前**尚在测试阶段**，将在开发完毕后另行发布。

---

## 技术栈

| 类别 | 技术 |
|---|---|
| 语言 | Python 3.11 |
| GUI | PyQt5 + PyQtWebEngine（流程图渲染） |
| 事件流解析 | [evfl](https://github.com/leoetlino/evfl) 1.2.0 |
| 二进制 I/O | aamp / byml / rstb / oead |
| 序列化 | msgpack / PyYAML |
| 基础框架 | [leoetlino/event-editor](https://github.com/leoetlino/event-editor)（GPL-2.0-or-later） |

---

## 目录结构

```
CrEventor/
├── launch.py                   # 入口（Qt DLL 修复 + import 路径配置 → main()）
├── requirements.txt            # 运行时依赖
├── CrEventor/          # ★ 所有自定义代码
│   ├── __main__.py             # 主窗口（枢纽）
│   ├── option_pool_panel.py    # M 面板：选项池 + 对话选项配置
│   ├── side_panel.py           # N 面板：sbeventpack + 游戏数据
│   ├── text_database.py        # 文本数据库：加载 / 合并 / 保存 / 查询
│   ├── project_manager.py      # 项目生命周期 + 备份管理
│   ├── flow_tab_bar.py         # 多流程标签页
│   ├── export_utils.py         # EventInfo / GameData / SaveData 导出
│   ├── sbeventpack_analyzer.py # 事件包依赖分析
│   ├── gamedata_editor.py      # 标志卡编辑器
│   ├── text_editor_dialog.py   # 文本高级编辑（control 字段）集成
│   ├── i18n/                   # 国际化（zh_CN / en_US）
│   └── resources/texts/        # 文本资源（发布版不含内置游戏文本）
├── TextEditor/                 # 基于 ProseMirror 的消息编辑器
├── event-editor-master/        # 上游基础框架（勿直接修改）
└── docs/                       # 截图
```

> 发布版不包含文本资源，请自行设法获取。

---

## 快速开始（Windows）

### 方式一：下载发布版（推荐）

1. 前往 [Releases](https://github.com/Rongyaoyaoooooo/CrEventor/releases) 下载最新版 `CrEventor-*.zip`。
2. 解压到任意目录（建议路径不含中文、空格）。
3. 运行解压目录中的 `CrEventor.exe`。

### 方式二：从源码运行

#### 环境要求

- Windows（建议项目路径不含中文、空格，以避免 Qt DLL 加载问题）
- Python 3.11（64 位）

#### 安装

```powershell
# 1. 进入项目目录
cd "项目路径"

# 2. 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt
```

> 说明：`aamp` / `byml` / `rstb` / `oead` 为平台相关二进制包（部分为 `.whl` / `.pyd`），
> 请根据现有 venv 或对应 wheel 文件安装。

#### 启动

```powershell
# 直接运行
.\venv\Scripts\python.exe launch.py

# 以模块方式运行
.\venv\Scripts\python.exe -m CrEventor
```

---

## 教程

### 什么是 CrEventor？

CrEventor 代表 Creator 的 Event Editor，而不是技术宅的玩具。初衷是帮助一些经验没那么丰富的创作者实现自己的想法。

### 如何开始使用？

本工具旨在完整处理事件 Mod 的完整制作，因此，你可以考虑将 Mod 需要的事件流置于一个项目内编辑。开始制作之前，请先新建或打开一个项目（项目的文件夹结构约定见下方「项目数据目录约定」）。

### 如何创建一个事件流？

在「文件」菜单中新建或打开一个事件流，或者在流程图内导入一个 JSON；对于结构不规范的 JSON，工具会进行拦截。

### 如何切换多个事件流？

屏幕左侧会显示已加载的事件流，最多允许十个同时编辑，单击即可切换。

### 如何编辑文本？

选中含有 MessageId 的节点，右键选择「编辑文本」进入文本编辑菜单。

你可以在光标处右键插入一个 control 模块，或者选中某段文字，右键设置其颜色、字体与字号。

### 如何编辑选项？

选中一个 GeneralChoice 节点，按 `M` 键，弹出选项编辑菜单，用来编辑该事件流文本中的选项池，以及该 GeneralChoice 节点上游文本的选项配置。

选中一个含 MessageId 的节点，打开 `M` 键菜单，可以添加 SingleChoice 并进行设置。

### 如何编辑 Flag？

按 `N` 键，在弹出的左侧菜单内，可以查看本事件流中除原版 Flag 外的所有 Flag，可以按照既定模板设置，或手动设置。

### 如何查看事件流依赖？

同样在 `M` 键菜单中，会显示本事件流所需依赖，用来提醒你在打包 sbeventpack 时需要哪些依赖事件流文件。

### 如何备份我的项目？

你可以在项目菜单内保存你的项目，并自定义该保存名称；新的保存不会覆盖前一次的保存。项目出问题时，可以在项目菜单内恢复备份。

### 如何导入原版事件流需要的文本？

本次更新尚未对原版游戏 dump 进行支持，需要你提供 BCML 使用格式的 `texts.json`，并放置于 `resource` 文件夹内，确保 texts 的命名与设置内的游戏文本语言一致。接下来点击「提取游戏文本」，即可导入原版文本。

### 项目数据目录约定

```
{project}/
├── project.json                # 项目元数据
├── Texts/                      # 提取的原始文本（只读基线）
├── Original Json/              # 所有修改 + 备份
│   ├── {datetime}/             # 手动备份
│   ├── AutoBackup{...}/        # 操作触发备份
│   └── Auto{date}/             # 定时自动保存
├── Mod/                        # BCML 兼容输出
└── logs/                       # 导出产物（eventinfo / gamedata / savedata / texts）
```

![项目根目录结构](docs/project.png)

---

## 常见问题

- **Qt DLL 找不到 / 中文路径报错**：`launch.py` 已通过 `os.add_dll_directory()` 修复，建议将项目移动到不含中文的路径。
- **QWebEngine 崩溃 / 白屏**：已设置 `QTWEBENGINE_DISABLE_SANDBOX=1`；调试时可加 `--debug` 参数开启远程调试（端口 9222）。
- **缺少 `_version.py`**：该模块由 versioneer 自动生成，如缺失可手动创建最小版本模块。

---

## 许可证

本项目基于 [leoetlino/event-editor](https://github.com/leoetlino/event-editor)（GNU GPL v2 或更高版本）衍生开发，因此同样采用 **GNU General Public License v2 或更高版本（GPL v2+）** 授权。详见 [LICENSE](./LICENSE)。

本项目所使用的第三方库及其许可证、致谢详见 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)。

## 对上游源码的修改

本项目对 [leoetlino/event-editor](https://github.com/leoetlino/event-editor) 上游源码进行了以下主要修改（均在 GPL v2+ 下发布）：

- 中文本地化（zh_CN），默认界面语言为简体中文，支持运行时切换
- 完整 JSON 往返序列化（`flow_serialize.py`）
- 对话文本深度编辑集成（MessageId 关联、MSBT `control` 字段编辑、节点对话预览）
- 多流程标签页工作区
- 流程图注释显示（keys / actions / queries 中文对照）
- 选项池（GeneralChoice）编辑器
- PyInstaller frozen 打包路径适配

---

## 致谢

- [leoetlino/event-editor](https://github.com/leoetlino/event-editor)：原始事件流编辑器框架
- [leoetlino/evfl](https://github.com/leoetlino/evfl)：EventFlow 解析库
- [ProseMirror](https://prosemirror.net/)（MIT License）：文本编辑器底层框架
- [Zeldamods Wiki](https://zeldamods.org/)：Mod 制作文档与规范
- 以及 aamp / byml / rstb / oead 等 Nintendo 二进制 I/O 库的开发者
