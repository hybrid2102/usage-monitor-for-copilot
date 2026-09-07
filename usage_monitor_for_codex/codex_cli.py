"""
Codex CLI
===========

Discovers Codex installations on the system. Authentication is owned by the
Codex CLI/App Server; this module never reads credentials.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .platforms import no_window_kwargs
from .settings import CLI_COMMAND


def _discover_cli_path() -> Path:
    """Discover the Codex CLI binary path.

    Strategy
    --------
    1. ``shutil.which('codex')`` - respects PATH and PATHEXT.  A typical
       npm install resolves to ``codex.cmd`` in ``%APPDATA%\\npm`` because
       ``.CMD`` is in the default PATHEXT.
    2. If the result is a ``.ps1`` shim (uncommon - happens when the user
       has added ``.PS1`` to PATHEXT), substitute the sibling ``.cmd`` or
       ``.exe``; subprocess cannot directly execute PowerShell scripts.
    3. Fall back to the standard npm location at ``%APPDATA%\\npm``.
    4. Check the Codex Desktop managed binary directory.
    5. Last resort: return the native installer path so callers'
       ``is_file()`` checks fail gracefully and produce sensible logs.
    """
    found = shutil.which('codex')
    if found:
        path = Path(found)
        if path.suffix.lower() == '.ps1':
            for ext in ('.cmd', '.exe'):
                alt = path.with_suffix(ext)
                if alt.is_file():
                    return alt
        return path

    appdata = os.environ.get('APPDATA')
    if appdata:
        for name in ('codex.cmd', 'codex.exe'):
            candidate = Path(appdata) / 'npm' / name
            if candidate.is_file():
                return candidate

    local_appdata = os.environ.get('LOCALAPPDATA')
    if local_appdata:
        managed_bin = Path(local_appdata) / 'OpenAI' / 'Codex' / 'bin'
        try:
            candidates = sorted(managed_bin.glob('*/codex.exe'), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                return candidates[0]
        except OSError:
            pass

    return Path.home() / '.local' / 'bin' / 'codex.exe'


# Resolved at import time. The CLI path doesn't move during runtime.
CODEX_CLI_PATH = _discover_cli_path()

_EXTENSION_DIRS: list[tuple[str, Path]] = [
    ('VS Code', Path.home() / '.vscode' / 'extensions'),
    ('VS Code Insiders', Path.home() / '.vscode-insiders' / 'extensions'),
    ('Cursor', Path.home() / '.cursor' / 'extensions'),
    ('Windsurf', Path.home() / '.windsurf' / 'extensions'),
]
_EXTENSION_PREFIXES = ('openai.chatgpt-', 'openai.codex-')

CHANGELOG_URL = 'https://github.com/openai/codex/releases'
PROJECT_URL = 'https://github.com/hybrid2102/usage-monitor-for-codex'

__all__ = ['CODEX_CLI_PATH', 'CHANGELOG_URL', 'PROJECT_URL', 'CodexInstallation', 'RefreshResult', 'cli_version', 'find_installations', 'refresh_token']

# Cache: path → (mtime, version) - avoids re-running subprocess when the binary hasn't changed
_version_cache: dict[Path, tuple[float, str]] = {}

# Cache for a custom cli_command version, keyed by the command tuple.  A custom
# command (e.g. a WSL invocation) has no local file to stat for change
# detection, so its version is cached for the process lifetime: updating that
# CLI is picked up on the next app start.  Spawning it per read is not an
# option - the popup re-reads on every data change, which would boot WSL every
# few minutes.
_command_version_cache: dict[tuple[str, ...], str] = {}


@dataclass
class CodexInstallation:
    """A discovered Codex installation."""

    name: str
    version: str
    path: Path


@dataclass
class RefreshResult:
    """Legacy result shape for the Codex CLI login-state probe."""

    success: bool
    updated: bool
    old_version: str
    new_version: str
    error: str


def find_installations() -> list[CodexInstallation]:
    """Discover Codex installations on the system.

    Checks the native CLI path, any ``cli_command`` configured by the user
    (e.g. a WSL install), and common IDE extension directories.  Extension
    versions are extracted from directory names (no subprocess needed).
    CLI versions are read via ``codex --version``.

    Returns
    -------
    list[CodexInstallation]
        Found installations, native CLI first, then configured commands,
        then IDE extensions.
    """
    results: list[CodexInstallation] = []

    # Native CLI
    if CODEX_CLI_PATH.is_file():
        version = cli_version(CODEX_CLI_PATH)
        if version:
            results.append(CodexInstallation('CLI', version, CODEX_CLI_PATH))

    # Configured commands - listed in addition to the native CLI, which stays
    # visible because it is the install this app authenticates and refreshes with
    for name, command in CLI_COMMAND.items():
        version = _command_version(command)
        if version:
            # A custom command has no single binary path; its last argument
            # is the closest match (e.g. the codex path behind ``wsl``).
            results.append(CodexInstallation(name, version, Path(command[-1])))

    # IDE extensions - extract version from directory name
    for ide_name, ext_dir in _EXTENSION_DIRS:
        try:
            if not ext_dir.is_dir():
                continue

            best_version = ''
            best_parts: tuple[int, ...] = ()
            best_path = None
            for entry in ext_dir.iterdir():
                prefix = next((value for value in _EXTENSION_PREFIXES if entry.name.startswith(value)), None)
                if prefix is None:
                    continue
                # Directory name format: openai.chatgpt-X.Y.Z-win32-x64
                remainder = entry.name[len(prefix):]
                match = re.match(r'(\d+\.\d+\.\d+)', remainder)
                if match:
                    version = match.group(1)
                    parts = tuple(int(x) for x in version.split('.'))
                    if parts > best_parts:
                        best_version = version
                        best_parts = parts
                        best_path = entry
        except OSError:
            # A directory that exists but cannot be enumerated (ACL denial,
            # broken junction, cloud placeholder) must not break the popup.
            continue

        if best_version and best_path:
            results.append(CodexInstallation(ide_name, best_version, best_path))

    return results


def refresh_token() -> RefreshResult:
    """Check the CLI-managed login state.

    Codex App Server refreshes ChatGPT credentials automatically. The legacy
    return type is retained for the existing cache interface.

    Returns
    -------
    RefreshResult
        Outcome of the update attempt.
    """
    if not CODEX_CLI_PATH.is_file():
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error='CLI not found')

    try:
        proc = _run_cli([str(CODEX_CLI_PATH), 'login', 'status'], timeout=15)
    except subprocess.TimeoutExpired:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error='Timeout')
    except OSError as e:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error=str(e))

    output = (proc.stdout + proc.stderr).strip()
    return RefreshResult(
        success=proc.returncode == 0,
        updated=False,
        old_version='',
        new_version='',
        error='' if proc.returncode == 0 else output[:200],
    )


def cli_version(path: Path) -> str:
    """Run ``codex --version`` and return the version string, or ``''``.

    Results are cached by file modification time so the subprocess is
    only spawned once per binary change (i.e. after an update).
    """
    try:
        mtime = path.stat().st_mtime
        cached = _version_cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]

        proc = _run_cli([str(path), '--version'], timeout=10)
        version = _parse_version(proc.stdout)
        _version_cache[path] = (mtime, version)
        return version
    except Exception:
        return ''


def _command_version(command: list[str]) -> str:
    """Run ``<command> --version`` and return the version string, or ``''``.

    Used for a custom ``cli_command`` that has no local file to stat; the
    result is cached per command tuple for the process lifetime.
    """
    key = tuple(command)
    cached = _command_version_cache.get(key)
    if cached is not None:
        return cached

    try:
        proc = _run_cli([*command, '--version'], timeout=10)
    except Exception:
        return ''

    version = _parse_version(proc.stdout)
    _command_version_cache[key] = version
    return version


def _run_cli(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run a Codex CLI command and capture its output as UTF-8 text.

    The Codex CLI writes UTF-8 whatever the
    Windows code page is, so the codec is pinned here instead of inherited
    from the ambient locale.  Decoding UTF-8 with a locale codec that cannot
    represent it - cp950 on a Traditional Chinese system, for example -
    raises inside the reader thread ``subprocess`` uses to drain the pipe;
    that thread then contributes nothing and the stream comes back as
    ``None`` despite ``capture_output=True``.

    Parameters
    ----------
    command : list[str]
        Executable and arguments to run.
    timeout : int
        Seconds to wait for the command to finish.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished process; ``stdout`` and ``stderr`` are always ``str``.

    Raises
    ------
    subprocess.TimeoutExpired
        The command did not finish within *timeout*.
    OSError
        The command could not be started, or a stream was lost.
    """
    proc = subprocess.run(
        command,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=timeout, **no_window_kwargs(),
    )

    # A missing stream means the output was lost, not that it was empty.  An
    # I/O failure is the honest report: each caller's existing error handling
    # then discards the run instead of recording an empty result as fact.
    if proc.stdout is None or proc.stderr is None:
        raise OSError('CLI output could not be captured')

    return proc


def _parse_version(output: str) -> str:
    """Extract a leading ``X.Y.Z`` version from ``--version`` output.

    Output format: ``"codex-cli 0.153.4"``.
    """
    match = re.search(r'(?<!\d)(\d+\.\d+\.\d+)(?!\d)', output.strip())
    return match.group(1) if match else ''
