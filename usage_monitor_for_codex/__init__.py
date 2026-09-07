"""
Usage Monitor for Codex
=========================

Displays current ChatGPT Codex usage as a system tray icon.
Left-click the icon to see a detailed usage popup.

Authentication is delegated to the installed Codex CLI through
``codex app-server``. The monitor never reads credential files.
"""
from __future__ import annotations

__version__ = '0.1.0'
