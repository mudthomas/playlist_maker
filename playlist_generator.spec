# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# pkg_resources vendors jaraco.text/jaraco.functools/etc internally, and
# PyInstaller's default analysis misses those vendored submodules and their
# package metadata - collect_all grabs everything setuptools/pkg_resources
# needs so we don't have to hand-list individual jaraco.* modules (which
# vary by setuptools version).
datas, binaries, hiddenimports = collect_all('setuptools')

a = Analysis(
    ['playlist_generator.py'],
    pathex=[],
    binaries=binaries,
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
    name='playlist_generator',
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
