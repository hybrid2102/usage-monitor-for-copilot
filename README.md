<p align="center"><img src="docs/icon.png" width="128" alt="Usage Monitor for Codex icon"></p>

# Usage Monitor for Codex

[![CI](https://github.com/hybrid2102/usage-monitor-for-codex/actions/workflows/ci.yml/badge.svg)](https://github.com/hybrid2102/usage-monitor-for-codex/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/hybrid2102/usage-monitor-for-codex?display_name=tag)](https://github.com/hybrid2102/usage-monitor-for-codex/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Unofficial system-tray monitor for ChatGPT Codex usage limits, available for Windows and experimentally for Linux.

## Features

- Primary and secondary Codex rate-limit windows, normally 5 hours and 7 days
- Named additional rate-limit buckets when provided by Codex App Server
- Reset times, usage percentages, time-aware warnings, and desktop notifications
- Active ChatGPT account and plan
- Codex CLI and IDE extension versions
- Configurable popup, tray fields, autostart, and local event commands
- Short retries and privacy-safe messages for transient usage-service failures

## Privacy-first integration

The monitor launches `codex app-server --stdio` and requests:

- `account/read` for the active account and plan;
- `account/rateLimits/read` for current usage windows.

Authentication and token refresh stay entirely inside the official Codex process. The monitor does not read `auth.json`, access tokens, refresh tokens, or browser cookies. See [Privacy and security](PRIVACY.md).

API-key logins are not supported because ChatGPT subscription limits are account-scoped.

## Install on Windows

1. Install Codex and sign in with ChatGPT using `codex login`.
2. Download `UsageMonitorForCodex.exe` from the [latest release](https://github.com/hybrid2102/usage-monitor-for-codex/releases/latest).
3. Run the executable; no Python installation is required.

The initial executable is unsigned, so Windows SmartScreen may display a warning. Verify its SHA-256 against the checksum attached to the same GitHub release.

## Run from source

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m usage_monitor_for_codex
```

On Linux, use the equivalent virtual-environment activation command and install the desktop packages required by `pystray` and `pywebview`. The Linux launcher is `usage-monitor-for-codex`.

## Development

```powershell
python -m unittest discover -s tests -q
python -m compileall -q usage_monitor_for_codex
python build.py
```

See [configuration](docs/configuration.md), [event commands](docs/event-commands.md), [App Server integration](docs/api-reference.md), and [contributing](CONTRIBUTING.md).

## Current limitations

- Windows is the primary tested platform; Linux support is experimental.
- Codex App Server evolves with the Codex CLI, so a recent CLI version is recommended.
- The executable is not code-signed.

## Attribution

Derived from [Usage Monitor for Claude](https://github.com/jens-duttke/usage-monitor-for-claude). Its Git history and original MIT copyright notice are preserved.

This independent community project is not created, endorsed, or supported by OpenAI.
