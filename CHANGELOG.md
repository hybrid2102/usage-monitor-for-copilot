# Changelog

All notable changes to Usage Monitor for Codex are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-09-07

### Added

- Initial Codex-focused fork of Usage Monitor for Claude.
- Credential-free integration with `codex app-server --stdio`.
- ChatGPT account and plan discovery through `account/read`.
- Primary, secondary, and named rate-limit bucket support through `account/rateLimits/read`.
- Short retries for transient Codex usage-service failures and user-safe error messages.
- Distinct terminal-prompt tray, application, and notification icons.
- Windows executable packaging and Linux source launcher.
- Automated tests, Windows/Linux CI, and tagged Windows release builds.

### Security

- The monitor never reads or stores Codex access tokens, refresh tokens, credential files, or browser cookies.

## Upstream history

This project derives from [Usage Monitor for Claude](https://github.com/jens-duttke/usage-monitor-for-claude). Its earlier history remains available in Git and its copyright notice remains in the MIT license.

[Unreleased]: https://github.com/hybrid2102/usage-monitor-for-codex/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hybrid2102/usage-monitor-for-codex/releases/tag/v0.1.0
