# Configuration

All settings work out of the box - no configuration file is needed. To customize behavior, create a file called `usage-monitor-settings.json` with only the keys you want to change:

```json
{
  "poll_interval": 180,
  "bar_fg": "#00cc66",
  "bar_fg_warn": "#ff6600"
}
```

The app searches for this file in these locations (first match wins):

1. **`$COPILOT_HOME/usage-monitor-settings.json`** (only if a custom config directory is set via `--config-dir` or `COPILOT_HOME` and differs from `~/.copilot/`) - so each instance can have its own settings
2. **Next to the EXE** (or project root when running from source)
3. **`~/.copilot/usage-monitor-settings.json`**

The app never creates or modifies this file. Settings are read at startup - after editing the file, use the **Restart** option in the tray context menu to apply changes.

## Alert thresholds

Configure usage percentage thresholds that trigger desktop notifications. Set to an empty array `[]` to disable alerts for a specific quota field.

| Key | Default | Description |
|-----|---------|-------------|
| `alert_thresholds_premium_interactions` | `[50, 80, 95]` | Thresholds (%) for the `premium_interactions` quota |

Threshold lookup uses a fallback chain: exact match on the field name, then no alerts. Unlike the Claude and Codex monitors, Copilot's quota field names (`chat`, `completions`, `premium_interactions`, ...) carry no period suffix to fall back to, so there is no further fallback step. Configure a threshold for any other field the same way, by name:

```json
{
    "alert_thresholds_chat": [80, 95]
}
```

## Copilot CLI command

The popup lists the Copilot version of the natively installed CLI. Installs it cannot see - most commonly a Copilot CLI running inside WSL - are missing from that list. Use `cli_command` to have their versions reported as well.

The value is an object mapping a display name to the base command as an array of arguments (the app appends `--version` itself). Each entry is listed in the popup under the name you give it, **in addition to** the native CLI.

| Key | Default | Description |
|-----|---------|-------------|
| `cli_command` | *(none)* | Object mapping a display name to a base command (array of strings) whose Copilot version is reported alongside the auto-detected native CLI, e.g. a WSL install |

```json
{
    "cli_command": {
        "WSL": ["wsl", "/home/<user>/.local/bin/copilot"]
    }
}
```

An entry only appears once its command reports a version, so if it stays missing, run the command yourself in a terminal - `wsl /home/<user>/.local/bin/copilot --version` has to print a version number (e.g. `GitHub Copilot CLI 1.0.84-1.`).

- **This setting is display only.** Authentication always stays in the natively installed CLI; the monitor never reads its credentials.
- **The version is read once per app start.** After updating Copilot inside WSL, restart the app to see the new version.

## Tooltip fields

The tray tooltip shows a quick usage summary when you hover over the icon. By default, it displays the `premium_interactions` quota - the one quota type that is consistently metered across plan tiers (`chat` and `completions` are frequently unlimited on paid plans). Use `tooltip_fields` to choose which usage fields appear in the tooltip.

| Key | Default | Description |
|-----|---------|-------------|
| `tooltip_fields` | `["premium_interactions"]` | Which usage fields to show in the tray tooltip, in order |

Must be an array of non-empty strings. Duplicates are silently removed. An empty array `[]` is valid (tooltip shows only the title, no usage fields). Unknown field names are accepted - if a field is missing from the API response (or not part of the current plan), it is simply skipped.

**Common field names:** `chat`, `completions`, `premium_interactions`, plus any additional quota key GitHub adds to the API later.

**Example** - show chat and premium interactions in the tooltip:

```json
{
    "tooltip_fields": ["chat", "premium_interactions"]
}
```

## Popup fields

The popup shows usage bars for all active quota types by default. Use `popup_fields` to control which bars appear and in what order.

| Key | Default | Description |
|-----|---------|-------------|
| `popup_fields` | `["*"]` | Which usage fields to show in the popup, in order. `"*"` is a wildcard meaning "all remaining non-null fields, in the order the API reports them" |

Must be an array of non-empty strings. `"*"` may appear at most once. Duplicates are silently removed. Unknown field names are accepted - if a field is missing from the API response, it is simply skipped.

**Common field names:** `chat`, `completions`, `premium_interactions`. Additional quota keys GitHub adds later are included automatically by `"*"`.

**Default order** (used for `"*"` and when no setting is present): the order the API reports in `quotaSnapshots`. Unlike the Claude and Codex monitors' field names, Copilot's carry no encoded time period (`five_hour`, `seven_day`) to sort by - each bar's label is instead humanized generically from the field name, e.g. `premium_interactions` renders as "Premium Interactions (Monthly)".

**Examples:**

| Setting | Result |
|---------|--------|
| *(not set)* | All non-null fields in the order the API reports |
| `["premium_interactions", "*"]` | Premium Interactions first, then all remaining fields |
| `["chat", "premium_interactions"]` | Only these two, everything else hidden |
| `["*"]` | Same as not set |

```json
{
    "popup_fields": ["premium_interactions", "*"]
}
```

## Compact pinned view

The detail popup can be pinned open (pin button in the header) so it stays visible and can be dragged anywhere. Use `compact_hide` to strip the pinned popup down to just the usage bars you care about - the entries listed here are hidden **only while the popup is pinned**, and reappear when you unpin it.

| Key | Default | Description |
|-----|---------|-------------|
| `compact_hide` | `[]` | Sections and usage bars to hide while the popup is pinned |

Must be an array of non-empty strings. Duplicates are silently removed. Unknown names are accepted and simply have no effect. With the default empty list, pinning changes nothing about what is shown.

Entries can be either a **section key** or a **usage field name**:

**Section keys:** `copilot_code` (installed CLI version), `status` (the footer with the update time). The usage bar section itself cannot be hidden as a whole - hide individual bars by their field name instead. When nothing but the usage bars is left, the "Usage" heading is dropped automatically.

**Usage field names:** any quota field returned by the API, for example `chat`, `completions`, or `premium_interactions`. This hides that single bar in the pinned view, independent of [`popup_fields`](#popup-fields) (which controls the normal, unpinned popup).

**Example** - pin to a minimal view with only the premium-interactions bar:

```json
{
    "compact_hide": ["copilot_code", "status", "chat", "completions"]
}
```

## Tray icon bars

The tray icon displays a small progress bar for each field listed in `icon_fields`. By default, this shows only `premium_interactions` - it is the one quota type that is consistently metered/scarce across plan tiers, since `chat` and `completions` are frequently unlimited (`isUnlimitedEntitlement`) on paid plans, so defaulting the icon to either of them would often show a permanently-empty or moot bar. Use `icon_fields` to choose which field(s) are displayed, and `icon_style` to switch the icon layout.

| Key | Default | Description |
|-----|---------|-------------|
| `icon_fields` | `["premium_interactions"]` | Which usage field(s) to show as icon bars. The first entry determines the icon text; a second entry adds a bottom bar |
| `icon_style` | `"number+bars"` | Icon layout: `"number+bars"` shows the first field's percentage above its progress bar(s); `"numbers"` shows each field as a stacked percentage without bars |

Must be an array of non-empty strings. Unknown field names are accepted - if a field is missing from the API response (or not part of the current plan), its bar shows 0%.

**Common field names:** `chat`, `completions`, `premium_interactions`, plus any additional quota key GitHub adds to the API later.

The CLI's `resetDate` is not trustworthy, so the monitor does not use it. Instead it treats Copilot quotas as monthly and places the marker at the percentage of the **local calendar month** that has elapsed. A bar turns to the warning color when usage is ahead of that pace (and at 100%). If GitHub applies a different billing boundary to an account, this indicator is approximate; see [API Reference](api-reference.md#resetdate-is-not-a-reliable-reset-time).

**Example** - show premium interactions and chat as two stacked percentages:

```json
{
    "icon_fields": ["premium_interactions", "chat"],
    "icon_style": "numbers"
}
```

## Event commands

Run a shell command when a usage event occurs. See [Event Commands](event-commands.md) for examples and available environment variables.

| Key | Default | Description |
|-----|---------|-------------|
| `on_reset_command` | *(none)* | Shell command (or array of commands) to run when a quota resets (usage drops) |
| `on_startup_command` | *(none)* | Shell command (or array of commands) to run once after the first successful API update following app start |
| `on_threshold_command` | *(none)* | Shell command (or array of commands) to run when usage crosses a configured alert threshold |
| `quick_action_command` | *(none)* | Shell command (or array of commands) to run when you trigger the quick action. Triggered by a double-click on the tray icon, or by the **Run Quick Action** menu entry where the desktop keeps the click. Formerly `on_double_click_command`, which still works |

## Polling intervals

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval` | `180` | Seconds between API updates |
| `poll_fast` | `120` | Seconds when usage is actively increasing |
| `poll_fast_extra` | `2` | Extra fast polls after usage stops increasing |
| `poll_error` | `30` | Seconds after a transient error (5xx, network). Rate-limit errors (429) use exponential backoff instead |
| `max_backoff` | `900` | Maximum backoff in seconds for rate-limit errors (15 min) |
| `idle_pause` | `300` | Seconds of inactivity before polling slows down to `idle_interval` (0 = disable). A locked workstation slows down immediately. An open detail popup keeps the normal cadence unless the lock screen or a screensaver covers it |
| `idle_interval` | `900` | Seconds between API updates while nobody is at the machine (15 min). Quota resets are still picked up as they happen |

## Language

| Key | Default | Description |
|-----|---------|-------------|
| `language` | *(auto-detected)* | Override the UI language with a language code. Available: `de`, `en`, `es`, `fr`, `hi`, `id`, `it`, `ja`, `ko`, `pt-BR`, `uk`, `zh-CN`, `zh-TW` |

## Time Format

By default, reset times follow your system's clock format (the 24-hour or 12-hour / AM-PM setting from your regional preferences), so no configuration is needed. Set this key to override the auto-detected format.

| Key | Default | Description |
|-----|---------|-------------|
| `time_format` | *(auto-detected from your system)* | Clock format for reset times: `"24h"` (e.g. `14:30`) or `"12h"` (e.g. `2:30 PM`) |

## Tray icon colors

Override individual channels as RGBA arrays `[R, G, B, A]` (0-255). Unspecified keys keep their defaults.

| Key | Default | Description |
|-----|---------|-------------|
| `icon_light` | `{"fg": [255,255,255,255], "fg_half": [255,255,255,80], "fg_dim": [255,255,255,140], "fg_warn": [224,80,80,255]}` | Light icons for dark taskbar |
| `icon_dark` | `{"fg": [0,0,0,255], "fg_half": [0,0,0,80], "fg_dim": [0,0,0,140], "fg_warn": [224,80,80,255]}` | Dark icons for light taskbar |

## Popup colors

| Key | Default | Description |
|-----|---------|-------------|
| `bg` | `"#1e1e1e"` | Background |
| `fg` | `"#cccccc"` | Text |
| `fg_dim` | `"#888888"` | Dimmed text (labels, reset times) |
| `fg_heading` | `"#ffffff"` | Section headings |
| `fg_link` | `"#4a9eff"` | Link text (e.g. changelog) |
| `bar_bg` | `"#333333"` | Progress bar background |
| `bar_fg` | `"#4a9eff"` | Progress bar fill |
| `bar_fg_warn` | `"#e05050"` | Progress bar fill for an exhausted quota, error text |
| `bar_divider` | `"#000c"` | Time dividers on progress bars |
| `bar_marker` | `"#fffc"` | Time-position marker on progress bars |

`bar_marker` colors the local-month time-position marker. `bar_divider` colors the daily dividers in popup bars. Both use the synthesized monthly boundary described in [Tray icon bars](#tray-icon-bars), not the unreliable `resetDate` returned by the CLI.
