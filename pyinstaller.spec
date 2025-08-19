# -*- mode: python ; coding: utf-8 -*-

# https://github.com/enthought/pyface/issues/350#issuecomment-962895036
import pyface.ui.qt as pyface_qt
import pyface.timer as pyface_timer
import traitsui.qt as traitsui
from pathlib import Path
import os
hiddenimports = []

def collect_imports(path, prefix):
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
collect_imports(str(Path(traitsui.__file__).parent), 'traitsui.qt')

import teensy_minimal_rpc

datas = []
datas.append((Path(teensy_minimal_rpc.__file__).parent / "static", "teensy_minimal_rpc/static"))

a = Analysis(
    ['examples/run_device_viewer_pluggable.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
coll = COLLECT(
    exe,
    a.binaries, a.zipfiles, a.datas,
    name='microdrop',
)