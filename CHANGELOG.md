# Changelog

All notable changes to Usage Monitor for Copilot are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/hybrid2102/usage-monitor-for-copilot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hybrid2102/usage-monitor-for-copilot/releases/tag/v0.1.0
