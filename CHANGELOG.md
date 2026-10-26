# Changelog

All notable changes to Usage Monitor for Copilot are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [0.3.3] - 2026-10-26

### Fixed

- The displayed usage still stopped updating until a restart, despite 0.3.2. Newer Copilot CLIs (verified on 1.0.103) answer `account.getQuota` from an on-disk cache (`copilot-user-cache.json`) that they never refresh, so even a freshly started server returned the old numbers. The monitor now runs the CLI with its own cache directory under the local app-data folder and clears that cache before every poll; the user's own Copilot CLI cache is left untouched. The first poll after installing or updating the CLI takes a few extra seconds while the CLI unpacks itself (about 200 MB) into that directory.

## [0.3.2] - 2026-09-17

### Fixed

- The displayed usage stopped updating while the app was running: usage made elsewhere (another machine, the IDE) only showed up after a restart. `copilot --server` answers `account.getQuota` from a snapshot taken once at process start and never refreshes it, so the monitor now stops the server after every poll and starts a fresh one for the next, at the cost of about two seconds of subprocess startup per poll.

## [0.3.1] - 2026-09-14

### Fixed

- A `copilot --server` subprocess that goes unresponsive without exiting could block the polling thread forever with no visible error, freezing the displayed usage until the app was restarted. A watchdog now force-disconnects a stuck request after its timeout elapses, so the failure surfaces and the client reconnects on its own.
- The app version shown in the popup footer had been stuck at `0.1.0` since the 0.2.0 release; it now reports the actual running version.

## [0.3.0] - 2026-09-09

### Added

- Monthly pace markers and countdowns for all Copilot quota bars, based on the elapsed portion of the local calendar month.
- Time-aware warning colors when quota consumption is ahead of the monthly pace, plus the synthesized reset timestamp in event-command variables.

### Changed

- The monitor continues to ignore Copilot CLI `resetDate` values because they reflect the request time; it now derives the next local month boundary instead.

## [0.1.0] - 2026-09-07

### Added

- Initial GitHub Copilot-focused fork of Usage Monitor for Claude.
- Credential-free integration with `copilot --server`, authenticated locally with a random connection token generated fresh for every run.
- Per-category Copilot quota discovery (chat, code completions, premium requests, and any further category GitHub adds) through `account.getQuota`.
- GitHub Copilot CLI version detection.
- Distinct wing/chevron application and notification icons, set apart from the Claude ("C") and Codex (">") monitors', plus a green tray-icon palette.
- Windows executable packaging and Linux source launcher.
- Automated tests, Windows/Linux CI, and tagged Windows release builds.

### Security

- The monitor never reads or stores Copilot access tokens, refresh tokens, credential files, or browser cookies.
- Each run generates its own random connection token and hands it to the `copilot --server` subprocess only through its environment, closing the open local port the CLI otherwise leaves for any local process to connect to.

## Upstream history

This project derives from [Usage Monitor for Claude](https://github.com/jens-duttke/usage-monitor-for-claude). Its earlier history remains available in Git and its copyright notice remains in the MIT license.

[Unreleased]: https://github.com/hybrid2102/usage-monitor-for-copilot/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/hybrid2102/usage-monitor-for-copilot/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/hybrid2102/usage-monitor-for-copilot/compare/v0.2.0...v0.3.0
[0.1.0]: https://github.com/hybrid2102/usage-monitor-for-copilot/releases/tag/v0.1.0
