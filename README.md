# Usage Monitor for Copilot

[![CI](https://github.com/hybrid2102/usage-monitor-for-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/hybrid2102/usage-monitor-for-copilot/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/hybrid2102/usage-monitor-for-copilot?display_name=tag)](https://github.com/hybrid2102/usage-monitor-for-copilot/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Unofficial system-tray monitor for GitHub Copilot usage quotas, available for Windows and experimentally for Linux.

## Features

- Per-category Copilot quota usage - chat, code completions, and premium requests, whichever categories your plan includes - with unlimited entitlements shown as such instead of a meaningless percentage
- Tray icon focused on premium-request usage by default, since chat and code-completion quotas are frequently unlimited on paid plans while premium requests are the one most likely to run out
- Usage percentages and desktop notifications when a quota crosses a configured threshold
- GitHub Copilot CLI version
- Configurable popup, tray fields, autostart, and local event commands
- Short retries and privacy-safe messages for transient Copilot CLI failures

## Privacy-first integration

The monitor launches `copilot --server` with a random connection token set only in the subprocess's environment, completes the CLI's `connect` handshake with that token, and requests:

- `account.getQuota` for the current chat, code-completion, and premium-request usage snapshot.

Authentication stays entirely inside the official Copilot CLI. The monitor does not read Copilot credential files, access tokens, or browser cookies. See [Privacy and security](PRIVACY.md).

Only the Copilot CLI's own sign-in is supported; this monitor never accepts, stores, or reads an API key or personal access token.

## Install on Windows

1. Install the GitHub Copilot CLI and sign in with `copilot login`.
2. Download `UsageMonitorForCopilot.exe` from the [latest release](https://github.com/hybrid2102/usage-monitor-for-copilot/releases/latest).
3. Run the executable; no Python installation is required.

The initial executable is unsigned, so Windows SmartScreen may display a warning. Verify its SHA-256 against the checksum attached to the same GitHub release.

## Run from source

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m usage_monitor_for_copilot
```

On Linux, use the equivalent virtual-environment activation command and install the desktop packages required by `pystray` and `pywebview`. The Linux launcher is `usage-monitor-for-copilot`.

## Development

```powershell
python -m unittest discover -s tests -q
python -m compileall -q usage_monitor_for_copilot
python build.py
```

See [configuration](docs/configuration.md), [event commands](docs/event-commands.md), [Copilot CLI integration](docs/api-reference.md), and [contributing](CONTRIBUTING.md).

## Current limitations

- Windows is the primary tested platform; Linux support is experimental.
- The Copilot CLI's `--server` mode is not publicly documented, so its protocol may change between CLI releases.
- No reset countdown is shown for Copilot quotas: the CLI's own reset timestamp was found to track the moment of the request rather than a real billing-cycle boundary, so it cannot be trusted until GitHub's API reports a reliable one.
- The executable is not code-signed.

## Attribution

Derived from [Usage Monitor for Claude](https://github.com/jens-duttke/usage-monitor-for-claude). Its Git history and original MIT copyright notice are preserved.

This independent community project is not created, endorsed, or supported by GitHub or Microsoft.
