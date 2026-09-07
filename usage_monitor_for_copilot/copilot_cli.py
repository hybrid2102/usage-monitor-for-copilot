"""
Copilot CLI
=============

Discovers GitHub Copilot CLI installations on the system. Authentication is
owned by the Copilot CLI; this module never reads credentials.
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
    """Discover the GitHub Copilot CLI binary path.

    Strategy
    --------
    1. ``shutil.which('copilot')`` - respects PATH and PATHEXT.  A typical
       npm install resolves to ``copilot.cmd`` in ``%APPDATA%\\npm`` because
       ``.CMD`` is in the default PATHEXT.
    2. If the result is a ``.ps1`` shim (uncommon - happens when the user
       has added ``.PS1`` to PATHEXT), substitute the sibling ``.cmd`` or
       ``.exe``; subprocess cannot directly execute PowerShell scripts.
    3. Fall back to the standard npm location at ``%APPDATA%\\npm``.
    4. Last resort: return GitHub's documented bash-installer path
       (``~/.local/bin/copilot``, no extension - that installer targets
       macOS/Linux) so callers' ``is_file()`` checks fail gracefully on
       Windows instead of raising.
    """
    found = shutil.which('copilot')
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
        for name in ('copilot.cmd', 'copilot.exe'):
            candidate = Path(appdata) / 'npm' / name
            if candidate.is_file():
                return candidate

    return Path.home() / '.local' / 'bin' / 'copilot'


# Resolved at import time. The CLI path doesn't move during runtime.
COPILOT_CLI_PATH = _discover_cli_path()

# TODO: IDE-extension scanning (VS Code "GitHub.copilot" / "GitHub.copilot-chat")
# is intentionally omitted for this first version. Codex's twin matches a
# lowercased "publisher.name-X.Y.Z" directory prefix for its own IDE
# extensions, and GitHub Copilot's two extensions would very likely follow
# the same on-disk convention - but that has not been verified against a
# real install, and this codebase's policy is to encode only verified
# facts. Add it once someone can check an actual extensions directory.

CHANGELOG_URL = 'https://github.com/github/copilot-cli/releases'
PROJECT_URL = 'https://github.com/hybrid2102/usage-monitor-for-copilot'

__all__ = ['COPILOT_CLI_PATH', 'CHANGELOG_URL', 'PROJECT_URL', 'CopilotInstallation', 'RefreshResult', 'cli_version', 'find_installations', 'refresh_token']

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
class CopilotInstallation:
    """A discovered GitHub Copilot CLI installation."""

    name: str
    version: str
    path: Path


@dataclass
class RefreshResult:
    """Legacy result shape for the Copilot CLI login-state probe."""

    success: bool
    updated: bool
    old_version: str
    new_version: str
    error: str


def find_installations() -> list[CopilotInstallation]:
    """Discover GitHub Copilot CLI installations on the system.

    Checks the native CLI path and any ``cli_command`` configured by the
    user (e.g. a WSL install). This listing is **display only** and must
    never take part in authentication - see ``refresh_token()``. CLI
    versions are read via ``copilot --version``.

    Returns
    -------
    list[CopilotInstallation]
        Found installations, native CLI first, then configured commands.
    """
    results: list[CopilotInstallation] = []

    # Native CLI
    if COPILOT_CLI_PATH.is_file():
        version = cli_version(COPILOT_CLI_PATH)
        if version:
            results.append(CopilotInstallation('CLI', version, COPILOT_CLI_PATH))

    # Configured commands - listed in addition to the native CLI, which stays
    # visible because it is the install this app authenticates and refreshes with
    for name, command in CLI_COMMAND.items():
        version = _command_version(command)
        if version:
            # A custom command has no single binary path; its last argument
            # is the closest match (e.g. the copilot path behind ``wsl``).
            results.append(CopilotInstallation(name, version, Path(command[-1])))

    return results


def refresh_token() -> RefreshResult:
    """Report whether the Copilot CLI is present, without probing or refreshing login state.

    No subcommand equivalent to ``codex login status`` is confirmed to exist
    for the GitHub Copilot CLI - ``copilot --help`` lists a ``login``
    subcommand but no status check, and inventing one would encode a guess
    as fact. This function stays a thin no-op purely so the cache's
    token-refresh path keeps the ``RefreshResult`` shape it expects;
    ``account.getQuota`` in api.py is the actual liveness/auth probe, and its
    error text is classified defensively (case-insensitively, for
    'auth'/'login'/'token'/'unauthorized'/'unauthenticated') rather than on a
    specific error code.

    Returns
    -------
    RefreshResult
        ``success=True`` when the native binary is present; ``updated`` is
        always ``False`` since this never changes any credential.
    """
    if not COPILOT_CLI_PATH.is_file():
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error='CLI not found')

    return RefreshResult(success=True, updated=False, old_version='', new_version='', error='')


def cli_version(path: Path) -> str:
    """Run ``copilot --version`` and return the version string, or ``''``.

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
    """Run a Copilot CLI command and capture its output as UTF-8 text.

    The Copilot CLI is a Node application and writes UTF-8 whatever the
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

    Output format: ``"GitHub Copilot CLI 1.0.84-1.\\nRun 'copilot update' to
    check for updates."`` - the negative lookahead stops at the digits
    before the ``-1`` build suffix, so it still matches ``"1.0.84"``.
    """
    match = re.search(r'(?<!\d)(\d+\.\d+\.\d+)(?!\d)', output.strip())
    return match.group(1) if match else ''
