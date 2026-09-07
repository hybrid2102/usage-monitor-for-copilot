# GitHub Copilot CLI server integration

The monitor spawns `copilot --server` and speaks its JSON-RPC-over-TCP protocol directly. Authentication remains in the Copilot CLI; the monitor never reads its credentials.

**This protocol is not officially documented by GitHub.** Everything below was reverse-engineered by shallow-cloning the open-source [github/copilot-sdk](https://github.com/github/copilot-sdk) and reading its Python client (`python/copilot/client.py`, method `_verify_protocol_version`), then confirmed against a live, installed GitHub Copilot CLI (version 1.0.84-1, on Windows). Unlike Codex's `app-server`, which is documented upstream, a future Copilot CLI release can change this protocol without notice - treat this integration as carrying more protocol-drift risk than its siblings.

## Transport

The monitor starts the server with:

```
copilot --server
```

Not `--acp`: that flag starts the standard Agent Client Protocol over stdio, and it does not expose `account.getQuota` - calling it there returns `-32601 Method not found`.

`--server` prints exactly one line to its stdout early on:

```
CLI server listening on port 54321
```

The monitor parses this line for the port number (`listening on port (\d+)`) and keeps draining stdout afterward so the pipe buffer never fills up and blocks the process. When `COPILOT_CONNECTION_TOKEN` is absent from the environment, the CLI also prints a warning to stdout:

```
Warning: No COPILOT_CONNECTION_TOKEN was set, so connections will be accepted from any client
```

The monitor always sets that variable (see [Handshake](#handshake) below), so this warning should never appear in its own output.

## Framing

Once the port is known, the monitor opens a plain TCP socket to `127.0.0.1:<port>`. There is no HTTP and no WebSocket upgrade - messages in both directions are JSON-RPC 2.0 bodies framed LSP-style:

```
Content-Length: <N>\r\n\r\n<N bytes of UTF-8 JSON>
```

A raw HTTP or WebSocket handshake attempt against this port gets back a well-formed JSON-RPC parse-error response (`-32700`), which is how the framing was confirmed: the parser reads every line as an LSP-style header, not an HTTP request line.

## Handshake

There is no generic `initialize` method - calling it returns `-32601 Unhandled method initialize`. The real handshake method is `connect`.

Before connecting, the monitor generates a random token (`secrets.token_hex(16)`) and passes it to the spawned subprocess as `COPILOT_CONNECTION_TOKEN` in the child's environment (copied from the parent, with only that one key added). The token is never persisted to disk and never logged.

**Why this matters:** left unconfigured, `copilot --server` accepts connections from any local process that can reach its TCP port and lets it drive the Copilot agent - shell commands, file edits - as the logged-in user. Setting `COPILOT_CONNECTION_TOKEN` and completing the `connect` handshake before any other call closes that local security hole on every invocation; it is not an optional nicety.

As the first message on the socket, the monitor sends:

```json
{"jsonrpc":"2.0","id":1,"method":"connect","params":{"supportedTaskKinds":[],"token":"<token>"}}
```

`supportedTaskKinds` lists the agentic task kinds the client is willing to run. The official SDK defaults to `["agent","client","shell"]` because it wants full agent capability; this monitor never starts a session and only ever calls `account.getQuota`, so it requests the empty list `[]` for least privilege. (If a future CLI version rejects an empty list, the fallback is the smallest accepted value, with a comment in the code citing what was observed - it must never be silently widened.)

On success, the result looks like:

```json
{"ok": true, "protocolVersion": 3, "version": "1.0.84-1", "taskKinds": ["agent", "client", "shell"]}
```

Two error cases were reproduced directly against the live CLI:

| Situation | Error |
|---|---|
| Wrong or missing token on `connect` | `{"code": -32002, "message": "AUTHENTICATION_FAILED"}` |
| Any other method called before a successful `connect` (when a token is configured) | `{"code": -32001, "message": "AUTHENTICATION_REQUIRED"}` |

## account.getQuota

Called right after a successful `connect` - no `session/session.new` or equivalent is needed, this is a server-scoped call. Parameters are an empty object:

```json
{"jsonrpc":"2.0","id":2,"method":"account.getQuota","params":{}}
```

The result carries one entry per quota type, keyed by an opaque name:

```json
{"quotaSnapshots": {"<key>": {
  "isUnlimitedEntitlement": false,
  "entitlementRequests": 3000,
  "usedRequests": 912,
  "usageAllowedWithExhaustedQuota": false,
  "overage": 0,
  "overageAllowedWithExhaustedQuota": false,
  "overageEntitlement": 0,
  "remainingPercentage": 69.6,
  "resetDate": "<ISO 8601 string>",
  "hasQuota": true,
  "tokenBasedBilling": false
}}}
```

Keys observed across two real accounts so far: `chat`, `completions`, `premium_interactions`. The monitor iterates `quotaSnapshots` generically instead of hardcoding these three - a key GitHub adds later flows through automatically, matching this codebase's existing rule against hardcoding quota field names.

Two real measurements informed the normalization in `api.py`:

- A personal/free account: `chat` (`entitlementRequests: 200, usedRequests: 0`), `completions` (`entitlementRequests: 2000, usedRequests: 0`), `premium_interactions` (`hasQuota: false` - not part of that plan).
- A business account: `chat` and `completions` both unlimited (`isUnlimitedEntitlement: true`), `premium_interactions` at `entitlementRequests: 3000, usedRequests: 912, remainingPercentage: 69.6` - a 30.4% used figure that matched what the account holder independently reported seeing elsewhere as "30% consumed".

A key is included in the monitor's normalized usage dict only when `hasQuota` is true (a `false` value means the quota type does not apply to the current plan). For an included key, `utilization` is `0.0` when `isUnlimitedEntitlement` is true, otherwise `max(0.0, 100.0 - remainingPercentage)`; `unlimited: true` is added only when the entitlement is unlimited.

### resetDate is not a reliable reset time

Calling `account.getQuota` twice, 20 seconds apart, produced two `resetDate` values that were themselves about 20 seconds apart - on two separate accounts. The field tracks the wall-clock moment of the call, not any real monthly billing-cycle boundary. The monitor never surfaces `resetDate` as a countdown: every normalized quota field's `resets_at` is always the empty string `''`, regardless of what `resetDate` reports.

### Overage fields are not yet surfaced

`overage`, `overageEntitlement`, and `overageAllowedWithExhaustedQuota` exist per quota key in the response, unlike the Claude and Codex monitors' single top-level "extra usage" meter. Multiple Copilot quota fields could be in overage at once, and collapsing that onto one UI slot is a product decision rather than a mechanical port - these fields are read by nothing in this first version.

## CLI facts

The binary is named `copilot` (not `copilot-cli`). `copilot --version` prints:

```
GitHub Copilot CLI 1.0.84-1.
Run 'copilot update' to check for updates.
```

Note the trailing `-1` build suffix and the period immediately after the `X.Y.Z` part. The version regex `(?<!\d)(\d+\.\d+\.\d+)(?!\d)` matches `1.0.84` and stops there, since `-` is not a digit.

The login subcommand is `copilot login` (confirmed via `copilot --help`: "login \[options\]  Authenticate with Copilot"). No `copilot login status`-equivalent subcommand is confirmed to exist, so the monitor does not invent one. Instead, `account.getQuota` itself - called right after a normal `connect` - serves as the liveness/authentication probe: a JSON-RPC error from it is classified defensively by looking case-insensitively for `auth`, `login`, `token`, `unauthorized`, or `unauthenticated` in the error message, the same way opaque CLI error text is classified elsewhere in this codebase. The exact error an unauthenticated server returns from `account.getQuota` was not captured during the protocol spike (the CLI under test was always already logged in), so this path is handled defensively, not verified against a logged-out CLI.

## Home directory

The GitHub Copilot CLI honors a `COPILOT_HOME` environment variable (default `~/.copilot`) the same way the Codex CLI honors `CODEX_HOME`. Unlike the rest of this protocol, this is documented upstream, so the monitor treats it as a settled fact rather than a reverse-engineered guess.

## Errors and lifecycle

Requests are serialized over one TCP socket to one subprocess. The client ignores messages whose `id` does not match the pending request (stale responses, notifications) while waiting for its answer, enforces a timeout per request, and restarts `copilot --server` once after a transport failure (a lost socket or a process that exited) before giving up. A JSON-RPC error response - as opposed to a transport failure - is treated as a healthy reply from a healthy process: the numeric error code is preserved so the caller can classify authentication and other failures for the UI, and the subprocess is kept alive rather than restarted.
