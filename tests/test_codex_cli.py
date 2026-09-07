"""
Codex CLI Tests
==================

Unit tests for _discover_cli_path(), find_installations(), refresh_token(),
cli_version(), and _run_cli().
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from usage_monitor_for_codex.platforms import no_window_kwargs
from unittest.mock import MagicMock, patch

from usage_monitor_for_codex import codex_cli
from usage_monitor_for_codex.codex_cli import (
    CodexInstallation,
    RefreshResult,
    cli_version,
    find_installations,
    refresh_token,
)


# ---------------------------------------------------------------------------
# _discover_cli_path
# ---------------------------------------------------------------------------

class TestDiscoverCliPath(unittest.TestCase):
    """Tests for _discover_cli_path()."""

    @patch('usage_monitor_for_codex.codex_cli.shutil.which')
    def test_uses_which_when_found(self, mock_which):
        """shutil.which hit returns the discovered path directly."""
        with TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'codex.cmd'
            fake.touch()
            mock_which.return_value = str(fake)
            self.assertEqual(codex_cli._discover_cli_path(), fake)

    @patch('usage_monitor_for_codex.codex_cli.shutil.which')
    def test_substitutes_cmd_for_ps1(self, mock_which):
        """When which returns a .ps1 shim, sibling .cmd is preferred."""
        with TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / 'codex.ps1'
            cmd = Path(tmp) / 'codex.cmd'
            ps1.touch()
            cmd.touch()
            mock_which.return_value = str(ps1)
            self.assertEqual(codex_cli._discover_cli_path(), cmd)

    @patch('usage_monitor_for_codex.codex_cli.shutil.which')
    def test_substitutes_exe_for_ps1_when_no_cmd(self, mock_which):
        """When which returns .ps1 with no .cmd sibling, .exe is preferred."""
        with TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / 'codex.ps1'
            exe = Path(tmp) / 'codex.exe'
            ps1.touch()
            exe.touch()
            mock_which.return_value = str(ps1)
            self.assertEqual(codex_cli._discover_cli_path(), exe)

    @patch('usage_monitor_for_codex.codex_cli.shutil.which')
    def test_returns_ps1_if_no_sibling_exists(self, mock_which):
        """Without a .cmd/.exe sibling, the .ps1 is returned (caller's is_file check handles it)."""
        with TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / 'codex.ps1'
            ps1.touch()
            mock_which.return_value = str(ps1)
            self.assertEqual(codex_cli._discover_cli_path(), ps1)

    @patch('usage_monitor_for_codex.codex_cli.shutil.which', return_value=None)
    def test_falls_back_to_appdata_npm(self, _mock_which):
        """When which finds nothing, use the standard npm location."""
        with TemporaryDirectory() as tmp:
            npm_dir = Path(tmp) / 'npm'
            npm_dir.mkdir()
            cmd = npm_dir / 'codex.cmd'
            cmd.touch()
            with patch.dict(os.environ, {'APPDATA': str(tmp)}, clear=False):
                self.assertEqual(codex_cli._discover_cli_path(), cmd)

    @patch('usage_monitor_for_codex.codex_cli.shutil.which', return_value=None)
    def test_appdata_npm_prefers_cmd_over_exe(self, _mock_which):
        """When both .cmd and .exe exist in npm dir, .cmd is preferred (typical npm shim)."""
        with TemporaryDirectory() as tmp:
            npm_dir = Path(tmp) / 'npm'
            npm_dir.mkdir()
            cmd = npm_dir / 'codex.cmd'
            exe = npm_dir / 'codex.exe'
            cmd.touch()
            exe.touch()
            with patch.dict(os.environ, {'APPDATA': str(tmp)}, clear=False):
                self.assertEqual(codex_cli._discover_cli_path(), cmd)

    @patch('usage_monitor_for_codex.codex_cli.shutil.which', return_value=None)
    def test_last_resort_returns_default_when_nothing_found(self, _mock_which):
        """No CLI anywhere -> return the default path so callers fail gracefully."""
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch('usage_monitor_for_codex.codex_cli.Path.home', return_value=home), \
                 patch.dict(os.environ, {'APPDATA': str(tmp), 'LOCALAPPDATA': str(tmp)}, clear=False):
                result = codex_cli._discover_cli_path()
            self.assertEqual(result, home / '.local' / 'bin' / 'codex.exe')
            self.assertFalse(result.is_file())


# ---------------------------------------------------------------------------
# cli_version
# ---------------------------------------------------------------------------

class TestCliVersion(unittest.TestCase):
    """Tests for cli_version()."""

    def setUp(self):
        codex_cli._version_cache.clear()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_parses_version_string(self, _mock_stat, mock_run):
        """Extracts version from '2.1.69 (Codex)' output."""
        mock_run.return_value = MagicMock(stdout='2.1.69 (Codex)\n', returncode=0)
        self.assertEqual(cli_version(Path('/fake/codex.exe')), '2.1.69')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_version_only(self, _mock_stat, mock_run):
        """Handles bare version string without suffix."""
        mock_run.return_value = MagicMock(stdout='3.0.0\n', returncode=0)
        self.assertEqual(cli_version(Path('/fake/codex.exe')), '3.0.0')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_empty_output(self, _mock_stat, mock_run):
        """Returns empty string when output is empty."""
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        self.assertEqual(cli_version(Path('/fake/codex.exe')), '')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_non_version_output(self, _mock_stat, mock_run):
        """Returns empty string for non-version output."""
        mock_run.return_value = MagicMock(stdout='error: something wrong', returncode=1)
        self.assertEqual(cli_version(Path('/fake/codex.exe')), '')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_timeout_returns_empty(self, _mock_stat, mock_run):
        """Returns empty string on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='codex', timeout=10)
        self.assertEqual(cli_version(Path('/fake/codex.exe')), '')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_os_error_returns_empty(self, _mock_stat, mock_run):
        """Returns empty string on OSError (binary not found)."""
        mock_run.side_effect = OSError('not found')
        self.assertEqual(cli_version(Path('/fake/codex.exe')), '')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_passes_correct_args(self, _mock_stat, mock_run):
        """Calls subprocess with correct arguments."""
        mock_run.return_value = MagicMock(stdout='2.1.69\n', returncode=0)
        path = Path('/fake/codex.exe')
        cli_version(path)
        mock_run.assert_called_once_with(
            [str(path), '--version'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=10, **no_window_kwargs(),
        )

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_cache_hit_skips_subprocess(self, _mock_stat, mock_run):
        """Second call with same mtime returns cached version without subprocess."""
        mock_run.return_value = MagicMock(stdout='2.1.69\n', returncode=0)
        path = Path('/fake/codex.exe')
        self.assertEqual(cli_version(path), '2.1.69')
        self.assertEqual(cli_version(path), '2.1.69')
        mock_run.assert_called_once()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_cache_invalidated_on_mtime_change(self, mock_run):
        """Changed mtime triggers a new subprocess call."""
        mock_run.return_value = MagicMock(stdout='2.1.69\n', returncode=0)
        path = Path('/fake/codex.exe')
        with patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0)):
            self.assertEqual(cli_version(path), '2.1.69')
        mock_run.return_value = MagicMock(stdout='3.0.0\n', returncode=0)
        with patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=2000.0)):
            self.assertEqual(cli_version(path), '3.0.0')
        self.assertEqual(mock_run.call_count, 2)

    def test_stat_failure_returns_empty(self):
        """Returns empty string when stat() fails (file deleted)."""
        with patch('pathlib.Path.stat', side_effect=OSError('not found')):
            self.assertEqual(cli_version(Path('/fake/codex.exe')), '')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_lost_output_returns_empty_uncached(self, _mock_stat, mock_run):
        """A lost stream returns '' and is not cached, so the next call retries."""
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        path = Path('/fake/codex.exe')
        self.assertEqual(cli_version(path), '')
        self.assertNotIn(path, codex_cli._version_cache)

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_recovers_after_lost_output(self, _mock_stat, mock_run):
        """A lost stream must not pin an empty version until the binary changes."""
        path = Path('/fake/codex.exe')
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(cli_version(path), '')
        mock_run.return_value = MagicMock(stdout='2.1.69 (Codex)\n', stderr='', returncode=0)
        self.assertEqual(cli_version(path), '2.1.69')


# ---------------------------------------------------------------------------
# find_installations
# ---------------------------------------------------------------------------

class TestFindInstallations(unittest.TestCase):
    """Tests for find_installations()."""

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_no_installations_found(self, mock_cli_path, _mock_version):
        """Returns empty list when nothing is installed."""
        mock_cli_path.is_file.return_value = False
        result = find_installations()
        self.assertEqual(result, [])

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='2.1.69')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_cli_only(self, mock_cli_path, _mock_version):
        """Returns CLI installation when binary exists."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'CLI')
        self.assertEqual(result[0].version, '2.1.69')

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_cli_exists_but_version_fails(self, mock_cli_path, _mock_version):
        """CLI binary exists but version command fails - not included."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual(result, [])

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_vscode_extension(self, mock_cli_path, _mock_version):
        """Finds VS Code extension and extracts version from directory name."""
        mock_cli_path.is_file.return_value = False
        with TemporaryDirectory() as tmp:
            ext_dir = Path(tmp)
            (ext_dir / 'openai.chatgpt-2.1.69-win32-x64').mkdir()
            with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', ext_dir)]):
                result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'VS Code')
        self.assertEqual(result[0].version, '2.1.69')

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_picks_highest_version(self, mock_cli_path, _mock_version):
        """When multiple extension versions exist, picks the highest."""
        mock_cli_path.is_file.return_value = False
        with TemporaryDirectory() as tmp:
            ext_dir = Path(tmp)
            (ext_dir / 'openai.chatgpt-2.1.63-win32-x64').mkdir()
            (ext_dir / 'openai.chatgpt-2.1.69-win32-x64').mkdir()
            (ext_dir / 'openai.chatgpt-2.1.66-win32-x64').mkdir()
            with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', ext_dir)]):
                result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].version, '2.1.69')

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_ignores_non_codex_extensions(self, mock_cli_path, _mock_version):
        """Ignores directories that don't match the Codex extension prefix."""
        mock_cli_path.is_file.return_value = False
        with TemporaryDirectory() as tmp:
            ext_dir = Path(tmp)
            (ext_dir / 'some-other-extension-1.0.0').mkdir()
            (ext_dir / 'openai.chatgpt-2.1.69-win32-x64').mkdir()
            with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', ext_dir)]):
                result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].version, '2.1.69')

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_nonexistent_extension_dir_skipped(self, mock_cli_path, _mock_version):
        """Extension directories that don't exist are silently skipped."""
        mock_cli_path.is_file.return_value = False
        with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', Path('/nonexistent'))]):
            result = find_installations()
        self.assertEqual(result, [])

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_unreadable_extension_dir_skipped(self, mock_cli_path, _mock_version):
        """A directory that exists but cannot be enumerated (ACL denial, broken
        junction) is skipped instead of crashing the popup threads."""
        mock_cli_path.is_file.return_value = False

        denied_dir = MagicMock()
        denied_dir.is_dir.return_value = True
        denied_dir.iterdir.side_effect = PermissionError(13, 'Access is denied')

        with TemporaryDirectory() as tmp:
            ext_dir = Path(tmp)
            (ext_dir / 'openai.chatgpt-2.1.69-win32-x64').mkdir()
            with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', denied_dir), ('Cursor', ext_dir)]):
                result = find_installations()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'Cursor')

    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='2.1.69')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_cli_and_extensions_combined(self, mock_cli_path, _mock_version):
        """Returns both CLI and extension installations."""
        mock_cli_path.is_file.return_value = True
        with TemporaryDirectory() as tmp:
            ext_dir = Path(tmp)
            (ext_dir / 'openai.chatgpt-2.1.68-win32-x64').mkdir()
            with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', ext_dir)]):
                result = find_installations()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, 'CLI')
        self.assertEqual(result[1].name, 'VS Code')


# ---------------------------------------------------------------------------
# refresh_token
# ---------------------------------------------------------------------------

class TestRefreshToken(unittest.TestCase):
    """Tests for the legacy login-state probe exposed as refresh_token()."""

    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_cli_not_found(self, mock_path):
        """Returns error when CLI binary doesn't exist."""
        mock_path.is_file.return_value = False
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'CLI not found')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_logged_in(self, mock_path, mock_run):
        """A successful ``codex login status`` probe is reported as ready."""
        mock_path.is_file.return_value = True
        mock_run.return_value = MagicMock(stdout='Logged in using ChatGPT\n', stderr='', returncode=0)
        result = refresh_token()
        self.assertTrue(result.success)
        self.assertFalse(result.updated)
        self.assertEqual(result.old_version, '')
        self.assertEqual(result.new_version, '')
        self.assertEqual(result.error, '')
        mock_run.assert_called_once_with(
            [str(mock_path), 'login', 'status'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=15, **no_window_kwargs(),
        )

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_timeout(self, mock_path, mock_run):
        """Returns error on timeout."""
        mock_path.is_file.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='codex', timeout=15)
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'Timeout')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_os_error(self, mock_path, mock_run):
        """Returns error on OSError."""
        mock_path.is_file.return_value = True
        mock_run.side_effect = OSError('Permission denied')
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'Permission denied')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_logged_out(self, mock_path, mock_run):
        """A non-zero status keeps the CLI's concise diagnostic."""
        mock_path.is_file.return_value = True
        mock_run.return_value = MagicMock(stdout='', stderr='Not logged in', returncode=1)
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'Not logged in')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_error_message_truncated(self, mock_path, mock_run):
        """Long error output is truncated to 200 characters."""
        mock_path.is_file.return_value = True
        mock_run.return_value = MagicMock(stdout='X' * 300, stderr='', returncode=1)
        result = refresh_token()
        self.assertEqual(len(result.error), 200)

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    def test_lost_output_reports_error(self, mock_path, mock_run):
        """A lost stream is reported instead of crashing the poll thread."""
        mock_path.is_file.return_value = True
        mock_run.return_value = MagicMock(
            stdout='Logged in using ChatGPT', stderr=None, returncode=0,
        )
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'CLI output could not be captured')


# ---------------------------------------------------------------------------
# cli_command (custom / WSL CLI)
# ---------------------------------------------------------------------------

class TestCommandVersion(unittest.TestCase):
    """Tests for _command_version()."""

    def setUp(self):
        codex_cli._command_version_cache.clear()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_parses_version(self, mock_run):
        """Extracts the version from a custom command's --version output."""
        mock_run.return_value = MagicMock(stdout='2.1.204 (Codex)\n', returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '2.1.204')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_appends_version_flag(self, mock_run):
        """Runs the configured command with --version appended."""
        mock_run.return_value = MagicMock(stdout='2.1.204\n', returncode=0)
        codex_cli._command_version(['wsl', '/home/user/.local/bin/codex'])
        mock_run.assert_called_once_with(
            ['wsl', '/home/user/.local/bin/codex', '--version'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=10, **no_window_kwargs(),
        )

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_cache_hit_skips_subprocess(self, mock_run):
        """A second call with the same command returns the cached version."""
        mock_run.return_value = MagicMock(stdout='2.1.204\n', returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '2.1.204')
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '2.1.204')
        mock_run.assert_called_once()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_exception_returns_empty_uncached(self, mock_run):
        """A failing command returns '' and is not cached, so the next call retries."""
        mock_run.side_effect = OSError('wsl not found')
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '')
        self.assertNotIn(('wsl', 'codex'), codex_cli._command_version_cache)

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_timeout_returns_empty_uncached(self, mock_run):
        """A timeout (e.g. a cold WSL boot) is not cached, so the next call retries."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='wsl', timeout=10)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '')
        self.assertNotIn(('wsl', 'codex'), codex_cli._command_version_cache)

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_unparsable_output_cached(self, mock_run):
        """A command that runs but reports no version caches '' - re-spawning it on
        every poll would keep paying the WSL start cost for a known-bad command."""
        mock_run.return_value = MagicMock(stdout='command not found', returncode=1)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '')
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '')
        mock_run.assert_called_once()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_lost_output_returns_empty_uncached(self, mock_run):
        """A lost stream returns '' and is not cached, so the next call retries."""
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '')
        self.assertNotIn(('wsl', 'codex'), codex_cli._command_version_cache)

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_recovers_after_lost_output(self, mock_run):
        """A lost stream must not pin an empty version for the process lifetime."""
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '')
        mock_run.return_value = MagicMock(stdout='2.1.204 (Codex)\n', stderr='', returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '2.1.204')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_distinct_commands_cached_separately(self, mock_run):
        """Each command gets its own cache entry - one entry must not mask another."""
        mock_run.return_value = MagicMock(stdout='2.1.204\n', returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', 'codex']), '2.1.204')
        mock_run.return_value = MagicMock(stdout='2.1.99\n', returncode=0)
        self.assertEqual(codex_cli._command_version(['wsl', '-d', 'Ubuntu', 'codex']), '2.1.99')
        self.assertEqual(mock_run.call_count, 2)


class TestFindInstallationsCliCommand(unittest.TestCase):
    """Tests for find_installations() with a configured cli_command."""

    def setUp(self):
        codex_cli._command_version_cache.clear()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex']})
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_lost_command_output_does_not_reach_the_popup(self, mock_path, mock_run):
        """A lost stream from a configured command must not break the popup.

        _command_version() parses its output outside the try that guards the
        subprocess, and find_installations() calls it unguarded, so anything
        raised here lands in the popup's update path.
        """
        mock_path.is_file.return_value = False
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(find_installations(), [])

    @patch('usage_monitor_for_codex.codex_cli._command_version', return_value='2.1.204')
    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', '/home/user/.local/bin/codex']})
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_custom_command_listed(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """A configured cli_command appears as an installation under its name."""
        mock_cli_path.is_file.return_value = False
        result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'WSL')
        self.assertEqual(result[0].version, '2.1.204')

    @patch('usage_monitor_for_codex.codex_cli._command_version', return_value='2.1.204')
    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='2.1.177')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex']})
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_listed_in_addition_to_native(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """A cli_command is listed in addition to the native CLI, which stays visible
        because it is the install the app authenticates and refreshes with."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual([(i.name, i.version) for i in result], [('CLI', '2.1.177'), ('WSL', '2.1.204')])

    @patch('usage_monitor_for_codex.codex_cli._command_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='2.1.177')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex']})
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_custom_command_version_fails_native_kept(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """A cli_command whose version cannot be read is skipped without hiding the native CLI."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual([i.name for i in result], ['CLI'])

    @patch('usage_monitor_for_codex.codex_cli._command_version', return_value='2.1.204')
    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex'], 'WSL Ubuntu': ['wsl', '-d', 'Ubuntu', 'codex']})
    @patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [])
    def test_multiple_commands_all_listed(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """Every configured cli_command entry is listed under its own name."""
        mock_cli_path.is_file.return_value = False
        result = find_installations()
        self.assertEqual([i.name for i in result], ['WSL', 'WSL Ubuntu'])

    @patch('usage_monitor_for_codex.codex_cli._command_version', return_value='2.1.204')
    @patch('usage_monitor_for_codex.codex_cli.cli_version', return_value='2.1.177')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex']})
    def test_native_command_and_extensions_all_listed(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """All three sources appear together, native CLI first, then the configured
        command, then IDE extensions."""
        mock_cli_path.is_file.return_value = True
        with TemporaryDirectory() as tmp:
            ext_dir = Path(tmp)
            (ext_dir / 'openai.chatgpt-2.1.68-win32-x64').mkdir()
            with patch('usage_monitor_for_codex.codex_cli._EXTENSION_DIRS', [('VS Code', ext_dir)]):
                result = find_installations()
        self.assertEqual([i.name for i in result], ['CLI', 'WSL', 'VS Code'])


class TestRefreshTokenIgnoresCliCommand(unittest.TestCase):
    """Tests that refresh_token() never runs a configured cli_command.

    The refresh only works as a side effect: the CLI renews the expired token
    in the credentials file this app reads.  A CLI behind cli_command (e.g. a
    WSL install) keeps its own credentials inside WSL, so refreshing through it
    would leave that file untouched and could never renew the token.
    """

    def setUp(self):
        codex_cli._command_version_cache.clear()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', '/home/user/.local/bin/codex']})
    def test_uses_native_binary_despite_cli_command(self, mock_path, mock_run):
        """A configured cli_command must not divert the token refresh to WSL."""
        mock_path.is_file.return_value = True
        mock_path.__str__.return_value = r'C:\npm\codex.cmd'
        mock_run.return_value = MagicMock(stdout='Codex is up to date (2.1.177)', stderr='', returncode=0)
        result = refresh_token()
        self.assertTrue(result.success)
        self.assertEqual(mock_run.call_args[0][0], [r'C:\npm\codex.cmd', 'login', 'status'])

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex']})
    def test_no_native_binary_reports_not_found(self, mock_path, mock_run):
        """Without a native binary the refresh reports 'CLI not found' rather than
        falling back to the cli_command, which owns different credentials."""
        mock_path.is_file.return_value = False
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'CLI not found')
        mock_run.assert_not_called()

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    @patch('usage_monitor_for_codex.codex_cli.CODEX_CLI_PATH')
    @patch('usage_monitor_for_codex.codex_cli.CLI_COMMAND', {'WSL': ['wsl', 'codex']})
    def test_native_update_leaves_command_version_cache(self, mock_path, mock_run):
        """A native update must not touch the custom command's cached version - the
        two installs update independently."""
        mock_path.is_file.return_value = True
        codex_cli._command_version_cache[('wsl', 'codex')] = '2.1.204'
        mock_run.return_value = MagicMock(
            stdout='Successfully updated from 2.1.177 to version 2.1.178', stderr='', returncode=0,
        )
        refresh_token()
        self.assertEqual(codex_cli._command_version_cache[('wsl', 'codex')], '2.1.204')


# ---------------------------------------------------------------------------
# _run_cli (output decoding)
# ---------------------------------------------------------------------------

# Child processes for the decoding tests.  Each writes bytes rather than text so
# the output is fixed by the test and not by the child's own stream encoding:
# the UTF-8 the Codex CLI emits for its progress and npm error glyphs, and a
# byte that is valid UTF-8 nowhere.
_UTF8_CHILD = (
    'import sys;'
    r"sys.stdout.buffer.write('✓ ok\n'.encode('utf-8'));"
    r"sys.stderr.buffer.write('• note\n'.encode('utf-8'))"
)

_INVALID_UTF8_CHILD = r"import sys; sys.stdout.buffer.write(b'\xff bad\n')"


class TestRunCli(unittest.TestCase):
    """Tests for _run_cli(), which owns the module's output decoding.

    The Codex CLI writes UTF-8 whatever the Windows code page is.  Letting
    subprocess decode it with the ambient locale codec instead is what caused
    the crash in issue #80, and that failure happens inside subprocess's pipe
    reader thread - so these tests run real child processes rather than mock
    the mechanism they are about.
    """

    def _run_with_locale_codec(self):
        """Run the UTF-8 child while decoding with a codec that cannot read it."""
        return subprocess.run(
            [sys.executable, '-c', _UTF8_CHILD],
            capture_output=True, text=True, encoding='cp950', timeout=30,
            **no_window_kwargs(),
        )

    @unittest.skipUnless(sys.platform == 'win32', 'only Windows drains pipes on reader threads')
    def test_locale_codec_loses_the_captured_stream(self):
        """Reproduces #80: a locale codec that cannot decode UTF-8 drops the output.

        Naming cp950 explicitly reproduces the reporter's Traditional Chinese
        system on any machine.  Windows drains the pipes on reader threads, so
        the decode failure dies there: both streams come back as None even
        though capture_output was set, and that None is what the crash
        concatenated.
        """
        # The decode failure surfaces as an uncaught exception in subprocess's
        # reader thread; silence its traceback to keep the test output readable.
        with patch('threading.excepthook', lambda args: None):
            proc = self._run_with_locale_codec()
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(proc.stdout)
        self.assertIsNone(proc.stderr)

    @unittest.skipIf(sys.platform == 'win32', 'POSIX decodes on the calling thread')
    def test_locale_codec_raises_on_posix(self):
        """The same misuse loses the output on POSIX too, just louder.

        POSIX drains the pipes with a selector on the calling thread, so the
        decode failure propagates instead of being swallowed into a None
        stream.  Either way the captured output is gone, which is why
        ``_run_cli`` pins UTF-8 rather than trusting the ambient codec.
        """
        with self.assertRaises(UnicodeDecodeError):
            self._run_with_locale_codec()

    def test_pinned_codec_keeps_the_same_output(self):
        """_run_cli decodes the very output the locale codec drops."""
        proc = codex_cli._run_cli([sys.executable, '-c', _UTF8_CHILD], timeout=30)
        self.assertEqual(proc.stdout, '✓ ok\n')
        self.assertEqual(proc.stderr, '• note\n')

    def test_undecodable_bytes_are_replaced(self):
        """Bytes that are not valid UTF-8 are replaced, so no reader thread dies."""
        proc = codex_cli._run_cli([sys.executable, '-c', _INVALID_UTF8_CHILD], timeout=30)
        self.assertEqual(proc.stdout, '\ufffd bad\n')

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_lost_stdout_raises_oserror(self, mock_run):
        """A stream reported as None is an I/O failure, not an empty result."""
        mock_run.return_value = MagicMock(stdout=None, stderr='', returncode=0)
        with self.assertRaises(OSError):
            codex_cli._run_cli(['codex', '--version'], timeout=10)

    @patch('usage_monitor_for_codex.codex_cli.subprocess.run')
    def test_lost_stderr_raises_oserror(self, mock_run):
        """Only the stream carrying the glyph is dropped, so stderr alone can be lost."""
        mock_run.return_value = MagicMock(stdout='2.1.69 (Codex)\n', stderr=None, returncode=0)
        with self.assertRaises(OSError):
            codex_cli._run_cli(['codex', '--version'], timeout=10)


if __name__ == '__main__':
    unittest.main()
