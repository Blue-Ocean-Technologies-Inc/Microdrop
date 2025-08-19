# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

ROOT = Path.cwd() # Allow local imports
sys.path.insert(0, str(ROOT))

# Run conda patch script
import conda_patch as patch

patch.main()

# https://github.com/enthought/pyface/issues/350#issuecomment-962895036
import pyface
import pyface.ui.qt as pyface_qt
import pyface.timer as pyface_timer
import pyface.tasks as pyface_tasks
import traitsui.qt as traitsui
import os
hiddenimports = []

def collect_imports(path, prefix): # Recursively import directory
    hiddenimports.append(prefix)
    for file in os.listdir(path):
        if file in {'__pycache__', '__init__.py', 'tests'}:
            continue
        child = f'{prefix}.{file}'
        file_path = os.path.join(path, file)
        if os.path.isdir(file_path):
            collect_imports(file_path, child)
        elif os.path.isfile(file_path) and file.endswith('.py'):
            hiddenimports.append(child[0:-len('.py')])

collect_imports(str(Path(pyface_qt.__file__).parent), 'pyface.ui.qt')
collect_imports(str(Path(pyface_timer.__file__).parent), 'pyface.timer')
collect_imports(str(Path(pyface_tasks.__file__).parent), 'pyface.tasks')
collect_imports(str(Path(traitsui.__file__).parent), 'traitsui.qt')

import teensy_minimal_rpc
import dramatiq

import microdrop_utils
import microdrop_application
import device_viewer
import dropbot_status

datas = []
datas.append((Path(pyface.__file__).parent.parent.parent.parent.parent / "bin" / "redis-server", "."))
datas.append((Path(pyface.__file__).parent / "images", "pyface/images"))
datas.append((Path(teensy_minimal_rpc.__file__).parent / "static", "teensy_minimal_rpc/static"))
datas.append((Path(dramatiq.__file__).parent / "brokers" / "redis" , "dramatiq/brokers/redis")) # Dramatiq redis proxy Lua scripts
datas.append((Path(microdrop_utils.__file__).parent / "redis.conf", "microdrop_utils/redis.conf"))
datas.append((Path(microdrop_application.__file__).parent, "microdrop_application")) # icon + splash + resources
datas.append((Path(device_viewer.__file__).parent, "device_viewer")) # device SVG
datas.append((Path(dropbot_status.__file__).parent, "dropbot_status")) # status images + html
datas.append((Path(ROOT) / "microdrop_style", "microdrop_style")) # fonts
# Kind of lazy to import the whole directory, small file size improvement by importing the resources directly

a = Analysis(
    ['examples/run_device_viewer_pluggable.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["ipython", "pip", "pyinstaller", "pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='run_device_viewer_pluggable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)