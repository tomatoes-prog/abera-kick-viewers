# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['kick_viewers_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/viewer_join.wav', 'assets'),
        ('INSTRUCCIONES.txt', '.'),
    ],
    hiddenimports=['winotify'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy',
        'pandas',
        'matplotlib',
        'PIL',
        'IPython',
        'pytest',
        'unittest',
        'tkinter.test',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KickViewerMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='KickViewerMonitor',
)
