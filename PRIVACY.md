# Privacy and security

Usage Monitor for Copilot is designed to keep authentication inside the official Copilot CLI.

## Authentication and network access

The monitor starts the locally installed `copilot --server` process and completes its `connect` handshake over a local TCP socket, using a random connection token generated fresh for every run. This token is never written to disk and never logged; it is handed to the subprocess only through its environment (`COPILOT_CONNECTION_TOKEN`). Without it, the CLI's server would accept connections from any other local process and let it drive the Copilot agent - shell commands and file edits included - as the logged-in user. Generating and passing this token is the one thing this integration does that the monitor's Claude and Codex counterparts do not need to: those talk to their CLI over standard input/output, which no other process can reach, while `copilot --server` opens a TCP port.

Once connected, the monitor requests `account.getQuota` for the current chat, code-completion, and premium-request usage snapshot.

The monitor itself:

- does not read Copilot credential files (`~/.copilot`, or the directory named by `COPILOT_HOME`);
- does not receive or store access or refresh tokens;
- does not inspect browser cookies;
- does not send telemetry or analytics;
- does not contact GitHub to check for updates.

The Copilot CLI subprocess communicates with GitHub according to its own authentication and privacy behavior.

## Data held in memory

While running, the application may hold per-category quota utilization, unlimited-entitlement flags, and other usage metadata returned by the Copilot CLI. This data is used only to render the tray icon, popup, and optional local notifications. It is not persisted by the monitor. The CLI's own reset timestamp is ignored because it tracks the moment of the request rather than a real billing-cycle boundary; the monitor derives a local calendar-month boundary for its pace marker and countdown.

## Local settings and operating-system integration

Configuration is read from the project settings location, respecting `COPILOT_HOME` when set. If autostart or notification identity is enabled, the application may create the normal Windows registry values or Linux desktop files required for those features. No other persistent write is made: the `copilot --server` subprocess and the connection token generated for it both exist only for the lifetime of that process and are never written to disk.

Optional event commands are executed locally only when explicitly configured by the user. Their privacy and security impact depends on the commands chosen.

## Reporting issues

Do not attach credential files, access tokens, or connection tokens to issue reports. Diagnostic output should be reviewed before sharing because it can contain local paths, software versions, and account metadata.
