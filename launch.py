"""EventEditor DX 启动脚本。"""

import importlib.util
import os
import sys


# ---- Debug mode (must configure Chromium before importing QtWebEngine) ----
if '--debug' in sys.argv:
    os.environ.setdefault('QTWEBENGINE_REMOTE_DEBUGGING', '9222')
    os.environ.setdefault(
        'QTWEBENGINE_CHROMIUM_FLAGS',
        '--enable-logging=stderr --v=0',
    )
    os.environ.setdefault(
        'QT_LOGGING_RULES',
        'qt.webenginecontext.debug=true;qt.webengine*.warning=true',
    )


# ---- Qt DLL 修复 ----
_spec = importlib.util.find_spec('PyQt5')
if _spec and _spec.origin:
    _qt_bin = os.path.join(os.path.dirname(_spec.origin), 'Qt5', 'bin')
    if os.path.isdir(_qt_bin):
        os.add_dll_directory(_qt_bin)

# ---- QWebEngine 缓存 ----
os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'

# ---- Qt 平台插件路径 ----
if _spec and _spec.origin:
    _plugins = os.path.join(os.path.dirname(_spec.origin), 'Qt5', 'plugins', 'platforms')
    if os.path.isdir(_plugins):
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = _plugins

# ---- import 路径 ----
_src = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_src, 'event-editor-master'))
sys.path.insert(0, _src)

# ---- 启动 ----
from CrEventor.__main__ import main
main()
