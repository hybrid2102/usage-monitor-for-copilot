# Codex App Server integration

The monitor uses `codex app-server --stdio`, a local JSONL/JSON-RPC-style protocol. Authentication remains in the Codex process.

## Session initialization

The first request initializes the client:

```json
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"usage-monitor-for-codex","version":"0.1.0"},"capabilities":{"experimentalApi":false}}}
```

## Account

`account/read` returns the active account, authentication type, email, and ChatGPT plan. The monitor accepts `chatgpt` accounts and derives an opaque local marker from non-secret account metadata. It never requests or parses credentials.

```json
{"id":2,"method":"account/read","params":{"refreshToken":false}}
```

## Rate limits

`account/rateLimits/read` returns one or more rate-limit buckets. Each bucket can contain `primary` and `secondary` windows with:

- `usedPercent`
- `windowDurationMins`
- `resetsAt` (Unix timestamp)

The common 300-minute and 10,080-minute windows are normalized to the existing UI fields `five_hour` and `seven_day`. Named additional buckets receive stable suffixed field names. Credits and rate-limit-reached metadata are retained separately from quota fields.

```json
{"id":3,"method":"account/rateLimits/read"}
```

App Server may also emit `account/rateLimits/updated` and `account/updated` notifications. The current monitor polls the read method on its configured cadence and uses account updates only to invalidate identity state.

## Errors and lifecycle

Requests are serialized over one subprocess. The client ignores unrelated notifications while waiting for a matching response, enforces timeouts, and restarts App Server once after transport failure. JSON-RPC errors preserve numeric error codes so authentication and rate limiting can be classified for the UI.
