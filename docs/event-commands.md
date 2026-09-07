# Event commands

The monitor can launch local commands when usage resets, a threshold is crossed, the first successful poll completes, or the user invokes the tray quick action.

## Settings

Add one or more of these keys to `usage-monitor-settings.json`:

| Key | Trigger |
|---|---|
| `on_reset_command` | A monitored rate-limit window resets |
| `on_threshold_command` | Usage crosses a configured alert threshold |
| `on_startup_command` | The first successful usage update after launch |
| `quick_action_command` | Double-click on Windows or **Run Quick Action** on Linux |

Each value can be one command string or an array of command strings. Commands run asynchronously with the same operating-system permissions as the monitor. Relative paths are resolved from the executable folder, or the project root when running from source.

```json
{
  "on_threshold_command": "powershell -NoProfile -Command \"[console]::beep(900,250)\"",
  "quick_action_command": "codex"
}
```

Automatic event commands run without a visible console and discard output. A user-triggered quick action reports an immediate startup failure. Use the tray menu's **Test event commands** submenu to exercise configured commands with sample data.

## Environment variables

Every event receives contextual environment variables:

| Variable | Meaning |
|---|---|
| `USAGE_MONITOR_EVENT` | `reset`, `threshold`, `startup`, or `quick_action` |
| `USAGE_MONITOR_QUOTA` | Normalized quota field, such as `five_hour` or `seven_day` |
| `USAGE_MONITOR_USAGE` | Current percentage used, when applicable |
| `USAGE_MONITOR_PREVIOUS_USAGE` | Previous percentage used, when applicable |
| `USAGE_MONITOR_THRESHOLD` | Crossed threshold, when applicable |
| `USAGE_MONITOR_RESETS_AT` | ISO reset timestamp, when available |

The application may expose additional backward-compatible variables. Treat all values as untrusted input when passing them into another shell or script.

## Security

Event commands are intentionally powerful. Configure only commands you trust, avoid interpolating environment variables directly into shell syntax, and prefer a dedicated script when the action is more than a simple executable invocation.
