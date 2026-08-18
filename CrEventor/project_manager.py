"""Project manager — handles project lifecycle, directory structure, and metadata."""
import datetime
import json
import os
import typing

FLOW_SUBDIR = 'flows'  # eventflow files go here, metadata stays at folder root


class ProjectManager:
    """Manages a single project: its directory structure, project.json, history.json,
    JSON backups, and Mod Event folder exports."""

    def __init__(self) -> None:
        self._project_dir: typing.Optional[str] = None
        self._data: typing.Dict[str, typing.Any] = {}
        self._platform: str = 'switch'

    # -- read-only properties -------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._project_dir is not None

    @property
    def project_dir(self) -> str:
        return self._project_dir or ''

    @property
    def project_name(self) -> str:
        return self._data.get('name', os.path.basename(self._project_dir or ''))

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def mod_event_path(self) -> str:
        """Return the absolute path to the Event folder inside Mod/ for the current platform."""
        if not self._project_dir:
            return ''
        mod_dir = os.path.join(self._project_dir, 'Mod')
        if self._platform == 'wiiu':
            return os.path.join(mod_dir, 'content', 'Event')
        return os.path.join(mod_dir, '01007EF00011E000', 'romfs', 'Event')

    @property
    def original_json_path(self) -> str:
        if not self._project_dir:
            return ''
        return os.path.join(self._project_dir, 'Original Json')

    @property
    def logs_path(self) -> str:
        if not self._project_dir:
            return ''
        return os.path.join(self._project_dir, 'logs')

    @property
    def project_json_path(self) -> str:
        if not self._project_dir:
            return ''
        return os.path.join(self._project_dir, 'project.json')

    @property
    def history_json_path(self) -> str:
        if not self._project_dir:
            return ''
        return os.path.join(self._project_dir, 'history.json')

    # -- project lifecycle ----------------------------------------------------

    def create(self, path: str, platform: str = 'switch') -> bool:
        """Create a new project directory with the required structure."""
        try:
            for subdir in ['Mod', 'logs', 'Original Json']:
                os.makedirs(os.path.join(path, subdir), exist_ok=True)
        except OSError:
            return False

        self._platform = platform
        self._create_mod_event_dir(path)

        self._data = {
            'name': os.path.basename(path),
            'platform': platform,
            'created': datetime.datetime.now().isoformat(),
            'version': 1,
        }
        return self._save_metadata(path)

    def open(self, path: str) -> bool:
        """Open an existing project from a directory."""
        proj_file = os.path.join(path, 'project.json')
        if not os.path.isfile(proj_file):
            return False
        try:
            with open(proj_file, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        except Exception:
            return False

        self._platform = self._data.get('platform', 'switch')
        self._project_dir = path
        return True

    def close(self) -> None:
        """Close the current project."""
        self._project_dir = None
        self._data = {}

    def set_platform(self, platform: str) -> None:
        """Change the platform setting and update Mod folder if needed."""
        if platform not in ('switch', 'wiiu'):
            return
        if self._platform == platform:
            return
        self._platform = platform
        if self._project_dir:
            self._data['platform'] = platform
            self._save_metadata(self._project_dir)
            self._create_mod_event_dir(self._project_dir)

    # -- JSON backup ----------------------------------------------------------

    @staticmethod
    def _now_str() -> str:
        """Return YYYYMMDD-HHMM for folder naming."""
        return datetime.datetime.now().strftime('%Y%m%d-%H%M')

    @staticmethod
    def _timestamp_str() -> str:
        return datetime.datetime.now().strftime('%H%M%S')

    def get_auto_save_folder(self) -> str:
        """Path to today's auto-save folder: Original Json/Auto20260803/"""
        if not self._project_dir:
            return ''
        return os.path.join(self.original_json_path, f'Auto{self._now_str()}')

    def save_original_json(self, data: dict, flow_name: str) -> str:
        """Save JSON to Original Json/flows/ using today's date as folder name.
        Returns the file path on success, empty string on failure."""
        if not self._project_dir:
            return ''
        folder = os.path.join(self.original_json_path, self._now_str(), FLOW_SUBDIR)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'{flow_name}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return path
        except OSError:
            return ''

    def save_original_json_as(self, data: dict, flow_name: str, folder_name: str) -> str:
        """Save JSON to Original Json/folder_name/flows/.
        Returns the file path on success, empty string on failure."""
        if not self._project_dir or not folder_name:
            return ''
        folder = os.path.join(self.original_json_path, folder_name, FLOW_SUBDIR)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'{flow_name}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return path
        except OSError:
            return ''

    def save_json_auto(self, data: dict, flow_name: str) -> str:
        """Auto-save JSON to Original Json/Auto20260803/<flow_name>_HHMMSS.json
        Returns the file path on success, empty string on failure."""
        if not self._project_dir:
            return ''
        folder = self.get_auto_save_folder()
        os.makedirs(folder, exist_ok=True)
        ts = self._timestamp_str()
        path = os.path.join(folder, f'{flow_name}_{ts}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return path
        except OSError:
            return ''

    def save_event_flow_to_mod(self, flow_path: str) -> None:
        """Ensure a .bfevfl file exists in Mod/<platform>/Event/<name>.bfevfl
        by copying the source file or saving the flow there."""
        if not self._project_dir or not flow_path:
            return
        mod_path = os.path.join(self.mod_event_path, os.path.basename(flow_path))
        os.makedirs(self.mod_event_path, exist_ok=True)
        if os.path.abspath(flow_path) == os.path.abspath(mod_path):
            return  # already in mod folder
        import shutil
        try:
            shutil.copy2(flow_path, mod_path)
        except OSError:
            pass

    def save_flow_to_mod(self, flow, flow_name: str) -> str:
        """Save an EventFlow object directly to Mod/<platform>/Event/<name>.bfevfl.
        Returns the saved path on success, empty string on failure."""
        if not self._project_dir:
            return ''
        os.makedirs(self.mod_event_path, exist_ok=True)
        mod_path = os.path.join(self.mod_event_path, f'{flow_name}.bfevfl')
        import eventeditor.util as util
        try:
            util.write_flow(mod_path, flow)
            return mod_path
        except Exception:
            return ''

    def clean_mod_event(self, keep_names: typing.List[str]) -> None:
        """Delete .bfevfl files in Mod/Event/ that are NOT in keep_names."""
        if not self._project_dir:
            return
        evt = self.mod_event_path
        if not os.path.isdir(evt):
            return
        keep_set = {n + '.bfevfl' for n in keep_names}
        for fname in os.listdir(evt):
            if fname.endswith('.bfevfl') and fname not in keep_set:
                try:
                    os.remove(os.path.join(evt, fname))
                except OSError:
                    pass

    # -- load from Original Json ----------------------------------------------

    def get_latest_json_backups(self) -> typing.List[str]:
        """Scan Original Json/flows/ folder and return list of file paths for
        the latest JSON in each MANUAL backup subfolder (non-Auto*),
        sorted by mtime descending."""
        if not self._project_dir:
            return []
        oj = self.original_json_path
        if not os.path.isdir(oj):
            return []

        results = []
        for folder_name in sorted(os.listdir(oj), reverse=True):
            if folder_name.startswith('Auto'):
                continue
            flows_dir = os.path.join(oj, folder_name, FLOW_SUBDIR)
            if not os.path.isdir(flows_dir):
                continue
            best_path = ''
            best_mtime = 0
            for fname in os.listdir(flows_dir):
                if fname.endswith('.json'):
                    fpath = os.path.join(flows_dir, fname)
                    mtime = os.path.getmtime(fpath)
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_path = fpath
            if best_path and best_mtime > 0:
                results.append((best_mtime, best_path))

        # Sort by time descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in results]

    def get_backup_folders(self) -> typing.List[typing.Tuple[str, float]]:
        """Scan Original Json and return list of (folder_name, mtime) for
        non-Auto backup folders, sorted by modification time descending."""
        if not self._project_dir:
            return []
        oj = self.original_json_path
        if not os.path.isdir(oj):
            return []

        results = []
        for folder_name in os.listdir(oj):
            folder_path = os.path.join(oj, folder_name)
            if not os.path.isdir(folder_path):
                continue
            if folder_name.startswith('Auto'):
                continue
            mtime = os.path.getmtime(folder_path)
            results.append((folder_name, mtime))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_auto_backup_folders(self) -> typing.List[typing.Tuple[str, float]]:
        """Scan Original Json and return list of (folder_name, mtime) for
        Auto* backup folders, sorted by modification time descending.
        Used by the restore dialog to allow recovery from auto-backups
        (e.g., after a crash)."""
        if not self._project_dir:
            return []
        oj = self.original_json_path
        if not os.path.isdir(oj):
            return []

        results = []
        for folder_name in os.listdir(oj):
            folder_path = os.path.join(oj, folder_name)
            if not os.path.isdir(folder_path):
                continue
            if not folder_name.startswith('Auto'):
                continue
            mtime = os.path.getmtime(folder_path)
            results.append((folder_name, mtime))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_flow_files_in_folder(self, folder_name: str) -> typing.List[str]:
        """Return list of .bfevfl and .json file paths from folder_name/flows/.
        .bfevfl files take priority; .json files are only included when no
        corresponding .bfevfl exists (avoids double-loading auto-backups)."""
        if not self._project_dir:
            return []
        flows_dir = os.path.join(self.original_json_path, folder_name, FLOW_SUBDIR)
        if not os.path.isdir(flows_dir):
            return []

        bfevfl_files = []
        bfevfl_names = set()
        json_files = []
        for fname in os.listdir(flows_dir):
            fpath = os.path.join(flows_dir, fname)
            if fname.endswith('.bfevfl'):
                bfevfl_files.append(fpath)
                bfevfl_names.add(os.path.splitext(fname)[0])
            elif fname.endswith('.json'):
                json_files.append(fpath)

        # Only include .json files that DON'T have a corresponding .bfevfl
        deduped_json = [
            p for p in json_files
            if os.path.splitext(os.path.basename(p))[0] not in bfevfl_names
        ]
        return bfevfl_files + deduped_json

    def _create_mod_event_dir(self, proj_path: str) -> None:
        mod_dir = os.path.join(proj_path, 'Mod')
        if self._platform == 'wiiu':
            os.makedirs(os.path.join(mod_dir, 'content', 'Event'), exist_ok=True)
        else:
            os.makedirs(os.path.join(mod_dir, '01007EF00011E000', 'romfs', 'Event'),
                        exist_ok=True)

    def _save_metadata(self, proj_path: str) -> bool:
        try:
            proj_file = os.path.join(proj_path, 'project.json')
            with open(proj_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            hist_file = os.path.join(proj_path, 'history.json')
            if not os.path.isfile(hist_file):
                with open(hist_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
            self._project_dir = proj_path
            return True
        except OSError:
            return False
