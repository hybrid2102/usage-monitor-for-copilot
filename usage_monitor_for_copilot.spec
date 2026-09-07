# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Usage Monitor for Copilot.

Build:
  pyinstaller usage_monitor_for_copilot.spec
"""

a = Analysis(
    ['usage_monitor_for_copilot/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('locale/*.json', 'locale'),
        ('usage_monitor_for_copilot/notification_logo.ico', 'usage_monitor_for_copilot'),
        ('usage_monitor_for_copilot/popup/popup.html', 'usage_monitor_for_copilot/popup'),
        ('usage_monitor_for_copilot/popup/popup.css', 'usage_monitor_for_copilot/popup'),
        ('usage_monitor_for_copilot/popup/popup.js', 'usage_monitor_for_copilot/popup'),
    ],
    hiddenimports=[
        'usage_monitor_for_copilot.platforms.win32',
        'usage_monitor_for_copilot.platforms.instance_win32',
        'usage_monitor_for_copilot.platforms.popup_win32',
        'pystray._win32',
        'pystray._util',
        'pystray._util.win32',
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        'bottle',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # The platform layer dispatches on sys.platform, but PyInstaller walks
        # both branches.  Excluding the Linux backends keeps the EXE small and
        # avoids pulling in POSIX-only modules such as fcntl and gi.
        'usage_monitor_for_copilot.platforms.linux',
        'usage_monitor_for_copilot.platforms.instance_linux',
        'usage_monitor_for_copilot.platforms.popup_linux',
        'fcntl', 'gi',
        'unittest', 'test',
        'xmlrpc', 'pydoc',
        'tkinter', '_tkinter',
        'PIL._avif', 'PIL._webp',
        'PIL._imagingcms', 'PIL._imagingmath', 'PIL._imagingtk', 'PIL._imagingmorph',
        'setuptools', '_distutils_hack',
        'asyncio', 'concurrent',
        'multiprocessing',
        'xml', 'tomllib',
        'sqlite3',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UsageMonitorForCopilot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='usage_monitor_for_copilot.ico',
    version='version_info.py',
)
