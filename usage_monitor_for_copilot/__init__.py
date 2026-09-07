"""
Usage Monitor for Copilot
=========================

Displays current GitHub Copilot usage as a system tray icon.
Left-click the icon to see a detailed usage popup.

Authentication is delegated to the installed Copilot CLI through
the Copilot CLI's ``--server`` mode. The monitor never reads credential files.
"""
from __future__ import annotations

__version__ = '0.1.0'
