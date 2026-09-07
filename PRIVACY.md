# Privacy and security

Usage Monitor for Codex is designed to keep authentication inside the official Codex CLI.

## Authentication and network access

The monitor starts the locally installed `codex app-server --stdio` process and exchanges JSONL messages over standard input/output. It requests account metadata and rate-limit snapshots through the documented App Server methods.

The monitor itself:

- does not read Codex credential files;
- does not receive or store access or refresh tokens;
- does not inspect browser cookies;
- does not send telemetry or analytics;
- does not contact GitHub to check for updates.

The Codex subprocess communicates with OpenAI according to the Codex CLI's own authentication and privacy behavior.

## Data held in memory

While running, the application may hold the active account email, plan name, opaque account marker, usage percentages, reset timestamps, and credits metadata returned by App Server. This data is used only to render the tray icon, popup, and optional local notifications. It is not persisted by the monitor.

## Local settings and operating-system integration

Configuration is read from the project settings location, respecting `CODEX_HOME` when set. If autostart or notification identity is enabled, the application may create the normal Windows registry values or Linux desktop files required for those features.

Optional event commands are executed locally only when explicitly configured by the user. Their privacy and security impact depends on the commands chosen.

## Reporting issues

Do not attach credential files or access tokens to issue reports. Diagnostic output should be reviewed before sharing because it can contain local paths, software versions, and account metadata.
