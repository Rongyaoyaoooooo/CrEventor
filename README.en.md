# CrEventor

<p align="center">
  <img src="docs/logo.png" alt="CrEventor Logo" width="240">
</p>

> A comprehensive EventFlow development tool for *The Legend of Zelda: Breath of the Wild* modding.

**Repository**: https://github.com/Rongyaoyaoooooo/CrEventor

[简体中文](./README.md) · English

CrEventor is a deeply customized fork of [leoetlino/event-editor](https://github.com/leoetlino/event-editor) for editing *Breath of the Wild* EventFlow files. It retains the original flowchart-based visual editing while adding **Chinese localization**, **gamedata / savedata generation**, **eventinfo registration**, **deep advanced editing of text with `control` fields**, and an **option pool (GeneralChoice)** editor — all geared toward **systematic mod creation**.

> **The default UI language is Simplified Chinese (`zh_CN`).** You can switch to English at runtime from the **Language** menu.

![Main window](docs/main.png)

---

## About AI-Assisted Development

The development of CrEventor has made extensive use of AI assistance, including code writing, feature implementation, and the AI EventFlow generation feature planned for future releases.

I am not a professional programmer, so I will not hide the messiness and complexity in the code. CrEventor was not originally created to show off programming skills, nor to become the best editor out there. It came from a real need I encountered while making *Breath of the Wild* mods: I wanted a tool that brings EventFlow, text editing, GameData, SaveData, and EventInfo together, while minimizing repetitive work and the risk of data loss.

So for this project, my first concern is whether the features work correctly, whether the actual workflow is convenient, and whether your data is safe. The project is still in development; code quality and program stability may be lacking, and I will not hide that. Actual bugs, error output, data anomalies, and technical suggestions that can improve the project are all welcome via Issues.

However, if you are against using AI to write software, if you think AI-assisted projects are not worth using, or if you simply dislike CrEventor's design philosophy, then this project may not be for you.

That is completely fine.

The BotW mod community already has other excellent EventFlow and text editing tools. Please choose the tool you trust, like, and that fits your workflow.

CrEventor does not try to replace them, and it does not require anyone to use it.

I will keep deciding what CrEventor should become based on my own mod-making needs and development philosophy. I welcome questions and feedback from any creator who wants an easier way to start making mods.

---

## Features

- **Multi-flow tabbed workspace**: open multiple EventFlow files (`.bfevfl`) simultaneously, with close / rename / drag-to-reorder support.
- **Lossless JSON round-trip serialization**: EventFlow can be converted to JSON and rebuilt back to binary (`.bfevfl`), ideal for version control and manual editing.
- **Chinese localization (CNzh)**: built for Chinese story/dialogue authoring, with text extraction, editing, and independent overlay saving.
  > Note: for copyright reasons, releases **do not bundle any in-game text**. Please provide your own text data extracted from the game (see Tutorial below).
- **Advanced text editing**: visual editing of MSBT `control` fields, covering `set_colour` / `font` / `text_size` / `sound` / `pause` / `choice` and over a dozen control types.

  ![Text editor](docs/text_editor.png)

- **Option Pool / GeneralChoice editor**: manage the dialogue button library per MSBT, configuring buttons, cursor, and cancel items for each dialogue node.
  - Automatically detects `GeneralChoice{N}` nodes (SwitchEvent / ActionEvent / ForkEvent forms).
  - The `unknown = 2n + 2` field formula, validated against 2400+ real samples.
  - Option configuration is automatically written to all parent Talk messages pointing to the same option node.

  ![Option pool M panel](docs/panel_m.png)

- **gamedata & savedata generation**: extract and generate game data, save data, and other artifacts from the EventFlow.
- **eventinfo registration**: generate event information for registering and identifying event flows.
- **Game data editing (sbeventpack + flags)**: event pack dependency analysis, interactive Bool / S32 / String flag card editing.

  ![Game data N panel](docs/panel_n.png)

- **Project management**: create / open projects, periodic auto-save, automatic backups on key operations, with manual and automatic backup restoration.
- **Bilingual UI (zh_CN / en_US)**: fully internationalized menus, panels, and dialogs, switchable at runtime.
- **Platform / language switching**: Switch / WiiU platform switching and in-game text language selection.

---

## Important Notice (please read)

> **This project is built from personal modding experience and does NOT represent a standard mod creation workflow.**

Before using this tool, please read the [Zeldamods Wiki](https://zeldamods.org/) basics to make sure you understand the BOTW mod project structure, the purpose of each file, and the relevant conventions, and that you have some modding experience. Again: this tool was made for personal workflow and development simplicity, and **does not represent a standard mod creation workflow**.

- **Copyright**: releases **do not bundle any in-game text** to avoid copyright issues.
- **Not fully tested**: this tool has not been fully tested on large projects. Please back up manually and often. If you encounter any bug, please record and report it.
- **Every save is a backup**: each save creates a backup and **never overwrites previous saves**. Locate backups by their save time; restore from the menu if needed. When creating a manual backup, you can **set a custom name** to record and track project progress.

  ![Backup & restore](docs/backup.png)

- **Backup JSON is deprecated**: the backup JSON only backs up the EventFlow JSON. For various reasons this feature is currently deprecated and may be reworked and re-enabled later. We are **not responsible** for any data loss caused by using the deprecated "Backup JSON" feature.

---

## Mod Packaging

Files generated by this project must be packaged manually into the final mod:

1. Manually pack the generated EventFlow files into an **sbeventpack** according to their dependencies.
2. Use [BCML](https://github.com/NiceneNerd/BCML) to pack it into a **BNP**.
3. **Extract** the BNP.
4. Place the files from the project's `logs/` folder into the extracted BNP.
5. The result is the **complete mod file**.

---

## Companion Tools

- **QuestEditor**: a companion quest editor, currently **in testing**, will be released separately when complete.

---

## Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.11 |
| GUI | PyQt5 + PyQtWebEngine (flowchart rendering) |
| EventFlow parsing | [evfl](https://github.com/leoetlino/evfl) 1.2.0 |
| Binary I/O | aamp / byml / rstb / oead |
| Serialization | msgpack / PyYAML |
| Base framework | [leoetlino/event-editor](https://github.com/leoetlino/event-editor) (GPL-2.0-or-later) |

---

## Directory Structure

```
CrEventor/
├── launch.py                   # Entry point (Qt DLL fix + import paths → main())
├── requirements.txt            # Runtime dependencies
├── CrEventor/                  # ★ All custom code
│   ├── __main__.py             # Main window (hub)
│   ├── option_pool_panel.py    # M panel: option pool + dialogue options
│   ├── side_panel.py           # N panel: sbeventpack + game data
│   ├── text_database.py        # Text database: load / merge / save / query
│   ├── project_manager.py      # Project lifecycle + backup management
│   ├── flow_tab_bar.py         # Multi-flow tabs
│   ├── export_utils.py         # EventInfo / GameData / SaveData export
│   ├── sbeventpack_analyzer.py # Event pack dependency analysis
│   ├── gamedata_editor.py      # Flag card editor
│   ├── text_editor_dialog.py   # Advanced text editing (control fields)
│   ├── i18n/                   # Internationalization (zh_CN / en_US)
│   └── resources/texts/        # Text resources (no built-in game text)
├── TextEditor/                 # ProseMirror-based message editor
├── event-editor-master/        # Upstream base framework (do not modify)
└── docs/                       # Screenshots
```

> Releases do not include text resources; please obtain them yourself.

---

## Quick Start (Windows)

### Option 1: Download the release (recommended)

1. Download the latest `CrEventor-*.zip` from [Releases](https://github.com/Rongyaoyaoooooo/CrEventor/releases).
2. Extract it to any folder (a path without non-ASCII characters or spaces is recommended).
3. Run `CrEventor.exe` from the extracted folder.

### Option 2: Run from source

#### Requirements

- Windows (a project path without non-ASCII characters or spaces is recommended to avoid Qt DLL issues)
- Python 3.11 (64-bit)

#### Install

```powershell
# 1. Enter the project directory
cd "project-path"

# 2. Create a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

> Note: `aamp` / `byml` / `rstb` / `oead` are platform-specific binary packages (some as `.whl` / `.pyd`); install them from your existing venv or the corresponding wheel files if `pip` cannot resolve them.

#### Run

```powershell
# Direct run
.\venv\Scripts\python.exe launch.py

# Or run as a module
.\venv\Scripts\python.exe -m CrEventor
```

---

## Tutorial

### What is CrEventor?

CrEventor stands for "Creator's Event Editor", not a tech geek's toy. The original intent is to help creators with less experience realize their ideas.

### How do I get started?

This tool aims to fully handle the complete workflow of event-based mods, so you can consider keeping all the event flows a mod needs in a single project. Before you start, first create or open a project (see the project folder convention in "Project Data Directory Convention" below).

### How do I create an event flow?

Create or open an event flow from the **File** menu, or import a JSON in the flowchart; structurally invalid JSON will be rejected.

### How do I switch between multiple event flows?

Loaded event flows appear on the left side of the screen; up to ten can be edited at the same time. Click to switch.

### How do I edit text?

Select a node containing a MessageId, right-click, and choose **Edit Text** to enter the text editor.

You can right-click at the cursor to insert a control module, or select a piece of text and right-click to set its color, font, and size.

### How do I edit options?

Select a GeneralChoice node and press `M` to open the option editor, which edits the option pool in this event flow's text and the option configuration for the upstream text of that GeneralChoice node.

Select a node containing a MessageId and open the `M` menu to add a SingleChoice and configure it.

### How do I edit flags?

Press `N` to open the left-side menu, where you can view all flags in this event flow except the vanilla flags. Set them from a template or manually.

### How do I view event flow dependencies?

Also in the `M` menu, the dependencies required by this event flow are shown, reminding you which dependency event flow files you need when packaging an sbeventpack.

### How do I back up my project?

You can save your project from the project menu and customize the save name; a new save does not overwrite the previous one. If something goes wrong, you can restore a backup from the project menu.

### How do I import the text needed by vanilla event flows?

This version does not yet support dumping from the original game. You need to provide a BCML-format `texts.json` and place it in the `resource` folder, making sure the texts naming matches the game text language in Settings. Then click **Extract Game Text** to import the vanilla text.

### Project Data Directory Convention

```
{project}/
├── project.json                # Project metadata
├── Texts/                      # Extracted raw text (read-only baseline)
├── Original Json/              # All modifications + backups
│   ├── {datetime}/             # Manual backups
│   ├── AutoBackup{...}/        # Operation-triggered backups
│   └── Auto{date}/             # Periodic auto-saves
├── Mod/                        # BCML-compatible output
└── logs/                       # Exported artifacts (eventinfo / gamedata / savedata / texts)
```

![Project root structure](docs/project.png)

---

## FAQ

- **Qt DLL not found / non-ASCII path errors**: `launch.py` already fixes this via `os.add_dll_directory()`; moving the project to a path without non-ASCII characters is recommended.
- **QWebEngine crash / blank screen**: `QTWEBENGINE_DISABLE_SANDBOX=1` is already set; add `--debug` when debugging to enable remote debugging (port 9222).
- **Missing `_version.py`**: this module is auto-generated by versioneer; if missing, create a minimal version module manually.

---

## License

This project is derived from [leoetlino/event-editor](https://github.com/leoetlino/event-editor) (GNU GPL v2 or later) and is therefore also licensed under the **GNU General Public License v2 or later (GPL v2+)**. See [LICENSE](./LICENSE).

Third-party libraries and their licenses and acknowledgements are listed in [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md).

## Modifications to Upstream

The following key changes were made to the upstream [leoetlino/event-editor](https://github.com/leoetlino/event-editor) source (all released under GPL v2+):

- Chinese localization (zh_CN) with Simplified Chinese as the default UI language, switchable at runtime
- Full JSON round-trip serialization (`flow_serialize.py`)
- Deep dialogue text editing integration (MessageId mapping, MSBT `control` field editing, node dialogue preview)
- Multi-flow tab workspace
- Flowchart notes display (Chinese glosses for keys / actions / queries)
- Option pool (GeneralChoice) editor
- PyInstaller frozen path adaptation

---

## Acknowledgements

- [leoetlino/event-editor](https://github.com/leoetlino/event-editor): original EventFlow editor framework
- [leoetlino/evfl](https://github.com/leoetlino/evfl): EventFlow parsing library
- [ProseMirror](https://prosemirror.net/) (MIT License): underlying text editor framework
- [Zeldamods Wiki](https://zeldamods.org/): modding documentation and conventions
- and the developers of aamp / byml / rstb / oead and other Nintendo binary I/O libraries
