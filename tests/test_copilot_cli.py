"""
Copilot CLI Tests
====================

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
from usage_monitor_for_copilot.platforms import no_window_kwargs
from unittest.mock import MagicMock, patch

from usage_monitor_for_copilot import copilot_cli
from usage_monitor_for_copilot.copilot_cli import (
    CopilotInstallation,
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

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which')
    def test_uses_which_when_found(self, mock_which):
        """shutil.which hit returns the discovered path directly."""
        with TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'copilot.cmd'
            fake.touch()
            mock_which.return_value = str(fake)
            self.assertEqual(copilot_cli._discover_cli_path(), fake)

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which')
    def test_substitutes_cmd_for_ps1(self, mock_which):
        """When which returns a .ps1 shim, sibling .cmd is preferred."""
        with TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / 'copilot.ps1'
            cmd = Path(tmp) / 'copilot.cmd'
            ps1.touch()
            cmd.touch()
            mock_which.return_value = str(ps1)
            self.assertEqual(copilot_cli._discover_cli_path(), cmd)

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which')
    def test_substitutes_exe_for_ps1_when_no_cmd(self, mock_which):
        """When which returns .ps1 with no .cmd sibling, .exe is preferred."""
        with TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / 'copilot.ps1'
            exe = Path(tmp) / 'copilot.exe'
            ps1.touch()
            exe.touch()
            mock_which.return_value = str(ps1)
            self.assertEqual(copilot_cli._discover_cli_path(), exe)

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which')
    def test_returns_ps1_if_no_sibling_exists(self, mock_which):
        """Without a .cmd/.exe sibling, the .ps1 is returned (caller's is_file check handles it)."""
        with TemporaryDirectory() as tmp:
            ps1 = Path(tmp) / 'copilot.ps1'
            ps1.touch()
            mock_which.return_value = str(ps1)
            self.assertEqual(copilot_cli._discover_cli_path(), ps1)

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which', return_value=None)
    def test_falls_back_to_appdata_npm(self, _mock_which):
        """When which finds nothing, use the standard npm location."""
        with TemporaryDirectory() as tmp:
            npm_dir = Path(tmp) / 'npm'
            npm_dir.mkdir()
            cmd = npm_dir / 'copilot.cmd'
            cmd.touch()
            with patch.dict(os.environ, {'APPDATA': str(tmp)}, clear=False):
                self.assertEqual(copilot_cli._discover_cli_path(), cmd)

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which', return_value=None)
    def test_appdata_npm_prefers_cmd_over_exe(self, _mock_which):
        """When both .cmd and .exe exist in npm dir, .cmd is preferred (typical npm shim)."""
        with TemporaryDirectory() as tmp:
            npm_dir = Path(tmp) / 'npm'
            npm_dir.mkdir()
            cmd = npm_dir / 'copilot.cmd'
            exe = npm_dir / 'copilot.exe'
            cmd.touch()
            exe.touch()
            with patch.dict(os.environ, {'APPDATA': str(tmp)}, clear=False):
                self.assertEqual(copilot_cli._discover_cli_path(), cmd)

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which', return_value=None)
    def test_last_resort_returns_default_when_nothing_found(self, _mock_which):
        """No CLI anywhere -> return the bash-installer default so callers fail gracefully."""
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch('usage_monitor_for_copilot.copilot_cli.Path.home', return_value=home), \
                 patch.dict(os.environ, {'APPDATA': str(tmp)}, clear=False):
                result = copilot_cli._discover_cli_path()
            self.assertEqual(result, home / '.local' / 'bin' / 'copilot')
            self.assertFalse(result.is_file())

    @patch('usage_monitor_for_copilot.copilot_cli.shutil.which', return_value=None)
    def test_no_appdata_falls_through_to_default(self, _mock_which):
        """Without APPDATA set at all, the npm lookup is skipped without raising."""
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch('usage_monitor_for_copilot.copilot_cli.Path.home', return_value=home), \
                 patch.dict(os.environ, {}, clear=True):
                result = copilot_cli._discover_cli_path()
            self.assertEqual(result, home / '.local' / 'bin' / 'copilot')


# ---------------------------------------------------------------------------
# cli_version
# ---------------------------------------------------------------------------

class TestCliVersion(unittest.TestCase):
    """Tests for cli_version()."""

    def setUp(self):
        copilot_cli._version_cache.clear()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_parses_real_cli_version_string(self, _mock_stat, mock_run):
        """Extracts '1.0.84' from the real `copilot --version` output, including
        the trailing '-1' build suffix and period that follow the X.Y.Z part."""
        mock_run.return_value = MagicMock(
            stdout="GitHub Copilot CLI 1.0.84-1.\nRun 'copilot update' to check for updates.\n",
            returncode=0,
        )
        self.assertEqual(cli_version(Path('/fake/copilot')), '1.0.84')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_version_only(self, _mock_stat, mock_run):
        """Handles bare version string without suffix."""
        mock_run.return_value = MagicMock(stdout='3.0.0\n', returncode=0)
        self.assertEqual(cli_version(Path('/fake/copilot')), '3.0.0')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_empty_output(self, _mock_stat, mock_run):
        """Returns empty string when output is empty."""
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        self.assertEqual(cli_version(Path('/fake/copilot')), '')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_non_version_output(self, _mock_stat, mock_run):
        """Returns empty string for non-version output."""
        mock_run.return_value = MagicMock(stdout='error: something wrong', returncode=1)
        self.assertEqual(cli_version(Path('/fake/copilot')), '')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_timeout_returns_empty(self, _mock_stat, mock_run):
        """Returns empty string on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='copilot', timeout=10)
        self.assertEqual(cli_version(Path('/fake/copilot')), '')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_os_error_returns_empty(self, _mock_stat, mock_run):
        """Returns empty string on OSError (binary not found)."""
        mock_run.side_effect = OSError('not found')
        self.assertEqual(cli_version(Path('/fake/copilot')), '')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_passes_correct_args(self, _mock_stat, mock_run):
        """Calls subprocess with correct arguments."""
        mock_run.return_value = MagicMock(stdout='1.0.84\n', returncode=0)
        path = Path('/fake/copilot')
        cli_version(path)
        mock_run.assert_called_once_with(
            [str(path), '--version'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=10, **no_window_kwargs(),
        )

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_cache_hit_skips_subprocess(self, _mock_stat, mock_run):
        """Second call with same mtime returns cached version without subprocess."""
        mock_run.return_value = MagicMock(stdout='1.0.84-1.\n', returncode=0)
        path = Path('/fake/copilot')
        self.assertEqual(cli_version(path), '1.0.84')
        self.assertEqual(cli_version(path), '1.0.84')
        mock_run.assert_called_once()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_cache_invalidated_on_mtime_change(self, mock_run):
        """Changed mtime triggers a new subprocess call."""
        mock_run.return_value = MagicMock(stdout='1.0.84-1.\n', returncode=0)
        path = Path('/fake/copilot')
        with patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0)):
            self.assertEqual(cli_version(path), '1.0.84')
        mock_run.return_value = MagicMock(stdout='1.0.85-1.\n', returncode=0)
        with patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=2000.0)):
            self.assertEqual(cli_version(path), '1.0.85')
        self.assertEqual(mock_run.call_count, 2)

    def test_stat_failure_returns_empty(self):
        """Returns empty string when stat() fails (file deleted)."""
        with patch('pathlib.Path.stat', side_effect=OSError('not found')):
            self.assertEqual(cli_version(Path('/fake/copilot')), '')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_lost_output_returns_empty_uncached(self, _mock_stat, mock_run):
        """A lost stream returns '' and is not cached, so the next call retries."""
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        path = Path('/fake/copilot')
        self.assertEqual(cli_version(path), '')
        self.assertNotIn(path, copilot_cli._version_cache)

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('pathlib.Path.stat', return_value=MagicMock(st_mtime=1000.0))
    def test_recovers_after_lost_output(self, _mock_stat, mock_run):
        """A lost stream must not pin an empty version until the binary changes."""
        path = Path('/fake/copilot')
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(cli_version(path), '')
        mock_run.return_value = MagicMock(stdout="GitHub Copilot CLI 1.0.84-1.\n", stderr='', returncode=0)
        self.assertEqual(cli_version(path), '1.0.84')


# ---------------------------------------------------------------------------
# find_installations
# ---------------------------------------------------------------------------

class TestFindInstallations(unittest.TestCase):
    """Tests for find_installations()."""

    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {})
    def test_no_installations_found(self, mock_cli_path, _mock_version):
        """Returns empty list when nothing is installed."""
        mock_cli_path.is_file.return_value = False
        result = find_installations()
        self.assertEqual(result, [])

    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='1.0.84')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {})
    def test_cli_only(self, mock_cli_path, _mock_version):
        """Returns CLI installation when binary exists."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'CLI')
        self.assertEqual(result[0].version, '1.0.84')

    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {})
    def test_cli_exists_but_version_fails(self, mock_cli_path, _mock_version):
        """CLI binary exists but version command fails - not included."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# refresh_token
# ---------------------------------------------------------------------------

class TestRefreshToken(unittest.TestCase):
    """Tests for the no-op login-state probe exposed as refresh_token().

    There is no confirmed ``copilot login status``-equivalent subcommand, so
    this never shells out - it only reports whether the native binary is
    present, which is the shape cache.py's token-refresh path expects.
    """

    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    def test_cli_not_found(self, mock_path):
        """Returns error when CLI binary doesn't exist."""
        mock_path.is_file.return_value = False
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'CLI not found')

    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    def test_cli_found(self, mock_path):
        """Reports success with no version change when the binary is present."""
        mock_path.is_file.return_value = True
        result = refresh_token()
        self.assertTrue(result.success)
        self.assertFalse(result.updated)
        self.assertEqual(result.old_version, '')
        self.assertEqual(result.new_version, '')
        self.assertEqual(result.error, '')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    def test_never_shells_out(self, mock_path, mock_run):
        """refresh_token() never spawns a subprocess - no confirmed status subcommand exists."""
        mock_path.is_file.return_value = True
        refresh_token()
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# cli_command (custom / WSL CLI)
# ---------------------------------------------------------------------------

class TestCommandVersion(unittest.TestCase):
    """Tests for _command_version()."""

    def setUp(self):
        copilot_cli._command_version_cache.clear()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_parses_version(self, mock_run):
        """Extracts the version from a custom command's --version output."""
        mock_run.return_value = MagicMock(stdout='GitHub Copilot CLI 1.0.84-1.\n', returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '1.0.84')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_appends_version_flag(self, mock_run):
        """Runs the configured command with --version appended."""
        mock_run.return_value = MagicMock(stdout='1.0.84\n', returncode=0)
        copilot_cli._command_version(['wsl', '/home/user/.local/bin/copilot'])
        mock_run.assert_called_once_with(
            ['wsl', '/home/user/.local/bin/copilot', '--version'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=10, **no_window_kwargs(),
        )

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_cache_hit_skips_subprocess(self, mock_run):
        """A second call with the same command returns the cached version."""
        mock_run.return_value = MagicMock(stdout='1.0.84\n', returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '1.0.84')
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '1.0.84')
        mock_run.assert_called_once()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_exception_returns_empty_uncached(self, mock_run):
        """A failing command returns '' and is not cached, so the next call retries."""
        mock_run.side_effect = OSError('wsl not found')
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '')
        self.assertNotIn(('wsl', 'copilot'), copilot_cli._command_version_cache)

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_timeout_returns_empty_uncached(self, mock_run):
        """A timeout (e.g. a cold WSL boot) is not cached, so the next call retries."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='wsl', timeout=10)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '')
        self.assertNotIn(('wsl', 'copilot'), copilot_cli._command_version_cache)

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_unparsable_output_cached(self, mock_run):
        """A command that runs but reports no version caches '' - re-spawning it on
        every poll would keep paying the WSL start cost for a known-bad command."""
        mock_run.return_value = MagicMock(stdout='command not found', returncode=1)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '')
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '')
        mock_run.assert_called_once()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_lost_output_returns_empty_uncached(self, mock_run):
        """A lost stream returns '' and is not cached, so the next call retries."""
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '')
        self.assertNotIn(('wsl', 'copilot'), copilot_cli._command_version_cache)

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_recovers_after_lost_output(self, mock_run):
        """A lost stream must not pin an empty version for the process lifetime."""
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '')
        mock_run.return_value = MagicMock(stdout='GitHub Copilot CLI 1.0.84-1.\n', stderr='', returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '1.0.84')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_distinct_commands_cached_separately(self, mock_run):
        """Each command gets its own cache entry - one entry must not mask another."""
        mock_run.return_value = MagicMock(stdout='1.0.84\n', returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', 'copilot']), '1.0.84')
        mock_run.return_value = MagicMock(stdout='1.0.99\n', returncode=0)
        self.assertEqual(copilot_cli._command_version(['wsl', '-d', 'Ubuntu', 'copilot']), '1.0.99')
        self.assertEqual(mock_run.call_count, 2)


class TestFindInstallationsCliCommand(unittest.TestCase):
    """Tests for find_installations() with a configured cli_command."""

    def setUp(self):
        copilot_cli._command_version_cache.clear()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', 'copilot']})
    def test_lost_command_output_does_not_reach_the_popup(self, mock_path, mock_run):
        """A lost stream from a configured command must not break the popup.

        _command_version() parses its output outside the try that guards the
        subprocess, and find_installations() calls it unguarded, so anything
        raised here lands in the popup's update path.
        """
        mock_path.is_file.return_value = False
        mock_run.return_value = MagicMock(stdout=None, stderr=None, returncode=0)
        self.assertEqual(find_installations(), [])

    @patch('usage_monitor_for_copilot.copilot_cli._command_version', return_value='1.0.84')
    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', '/home/user/.local/bin/copilot']})
    def test_custom_command_listed(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """A configured cli_command appears as an installation under its name."""
        mock_cli_path.is_file.return_value = False
        result = find_installations()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'WSL')
        self.assertEqual(result[0].version, '1.0.84')

    @patch('usage_monitor_for_copilot.copilot_cli._command_version', return_value='1.0.84')
    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='1.0.77')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', 'copilot']})
    def test_listed_in_addition_to_native(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """A cli_command is listed in addition to the native CLI, which stays visible
        because it is the install the app authenticates and refreshes with."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual([(i.name, i.version) for i in result], [('CLI', '1.0.77'), ('WSL', '1.0.84')])

    @patch('usage_monitor_for_copilot.copilot_cli._command_version', return_value='')
    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='1.0.77')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', 'copilot']})
    def test_custom_command_version_fails_native_kept(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """A cli_command whose version cannot be read is skipped without hiding the native CLI."""
        mock_cli_path.is_file.return_value = True
        result = find_installations()
        self.assertEqual([i.name for i in result], ['CLI'])

    @patch('usage_monitor_for_copilot.copilot_cli._command_version', return_value='1.0.84')
    @patch('usage_monitor_for_copilot.copilot_cli.cli_version', return_value='')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch(
        'usage_monitor_for_copilot.copilot_cli.CLI_COMMAND',
        {'WSL': ['wsl', 'copilot'], 'WSL Ubuntu': ['wsl', '-d', 'Ubuntu', 'copilot']},
    )
    def test_multiple_commands_all_listed(self, mock_cli_path, _mock_cli_version, _mock_cmd_version):
        """Every configured cli_command entry is listed under its own name."""
        mock_cli_path.is_file.return_value = False
        result = find_installations()
        self.assertEqual([i.name for i in result], ['WSL', 'WSL Ubuntu'])


class TestRefreshTokenIgnoresCliCommand(unittest.TestCase):
    """Tests that refresh_token() never runs a configured cli_command.

    A CLI behind cli_command (e.g. a WSL install) keeps its own credentials
    inside WSL, separate from whatever the native binary uses - refresh_token()
    must never probe or shell out through it.
    """

    def setUp(self):
        copilot_cli._command_version_cache.clear()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', '/home/user/.local/bin/copilot']})
    def test_uses_native_presence_despite_cli_command(self, mock_path, mock_run):
        """A configured cli_command must not divert the presence check to WSL."""
        mock_path.is_file.return_value = True
        result = refresh_token()
        self.assertTrue(result.success)
        mock_run.assert_not_called()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', 'copilot']})
    def test_no_native_binary_reports_not_found(self, mock_path, mock_run):
        """Without a native binary the refresh reports 'CLI not found' rather than
        falling back to the cli_command, which owns different credentials."""
        mock_path.is_file.return_value = False
        result = refresh_token()
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'CLI not found')
        mock_run.assert_not_called()

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    @patch('usage_monitor_for_copilot.copilot_cli.COPILOT_CLI_PATH')
    @patch('usage_monitor_for_copilot.copilot_cli.CLI_COMMAND', {'WSL': ['wsl', 'copilot']})
    def test_native_presence_leaves_command_version_cache(self, mock_path, mock_run):
        """A native presence check must not touch the custom command's cached version - the
        two installs are tracked independently."""
        mock_path.is_file.return_value = True
        copilot_cli._command_version_cache[('wsl', 'copilot')] = '1.0.84'
        refresh_token()
        self.assertEqual(copilot_cli._command_version_cache[('wsl', 'copilot')], '1.0.84')


# ---------------------------------------------------------------------------
# _run_cli (output decoding)
# ---------------------------------------------------------------------------

# Child processes for the decoding tests.  Each writes bytes rather than text so
# the output is fixed by the test and not by the child's own stream encoding:
# the UTF-8 the Copilot CLI emits for its progress glyphs, and a byte that is
# valid UTF-8 nowhere.
_UTF8_CHILD = (
    'import sys;'
    r"sys.stdout.buffer.write('✓ ok\n'.encode('utf-8'));"
    r"sys.stderr.buffer.write('• note\n'.encode('utf-8'))"
)

_INVALID_UTF8_CHILD = r"import sys; sys.stdout.buffer.write(b'\xff bad\n')"


class TestRunCli(unittest.TestCase):
    """Tests for _run_cli(), which owns the module's output decoding.

    The Copilot CLI is a Node application and writes UTF-8 whatever the
    Windows code page is.  Letting subprocess decode it with the ambient
    locale codec instead can drop the captured output inside subprocess's
    pipe reader thread - so these tests run real child processes rather than
    mock the mechanism they are about.
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
        """A locale codec that cannot decode UTF-8 drops the output.

        Naming cp950 explicitly reproduces a Traditional Chinese system on
        any machine.  Windows drains the pipes on reader threads, so the
        decode failure dies there: both streams come back as None even
        though capture_output was set.
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
        proc = copilot_cli._run_cli([sys.executable, '-c', _UTF8_CHILD], timeout=30)
        self.assertEqual(proc.stdout, '✓ ok\n')
        self.assertEqual(proc.stderr, '• note\n')

    def test_undecodable_bytes_are_replaced(self):
        """Bytes that are not valid UTF-8 are replaced, so no reader thread dies."""
        proc = copilot_cli._run_cli([sys.executable, '-c', _INVALID_UTF8_CHILD], timeout=30)
        self.assertEqual(proc.stdout, '� bad\n')

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_lost_stdout_raises_oserror(self, mock_run):
        """A stream reported as None is an I/O failure, not an empty result."""
        mock_run.return_value = MagicMock(stdout=None, stderr='', returncode=0)
        with self.assertRaises(OSError):
            copilot_cli._run_cli(['copilot', '--version'], timeout=10)

    @patch('usage_monitor_for_copilot.copilot_cli.subprocess.run')
    def test_lost_stderr_raises_oserror(self, mock_run):
        """Only the stream carrying the glyph is dropped, so stderr alone can be lost."""
        mock_run.return_value = MagicMock(stdout='GitHub Copilot CLI 1.0.84-1.\n', stderr=None, returncode=0)
        with self.assertRaises(OSError):
            copilot_cli._run_cli(['copilot', '--version'], timeout=10)


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion(unittest.TestCase):
    """Tests for _parse_version() against real and synthetic CLI output."""

    def test_real_cli_output(self):
        """The exact real string from `copilot --version` parses to '1.0.84'."""
        output = "GitHub Copilot CLI 1.0.84-1.\nRun 'copilot update' to check for updates.\n"
        self.assertEqual(copilot_cli._parse_version(output), '1.0.84')

    def test_bare_version(self):
        """A bare X.Y.Z with no suffix still parses."""
        self.assertEqual(copilot_cli._parse_version('1.2.3'), '1.2.3')

    def test_no_version_present(self):
        """Output with no X.Y.Z pattern returns ''."""
        self.assertEqual(copilot_cli._parse_version('command not found'), '')

    def test_empty_string(self):
        """Empty output returns ''."""
        self.assertEqual(copilot_cli._parse_version(''), '')


if __name__ == '__main__':
    unittest.main()
