"""Codex App Server client and response normalization.

The monitor never reads Codex credentials. It delegates authentication and
token refresh to the installed Codex CLI and communicates with
``codex app-server --stdio`` using its documented JSONL protocol.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import queue
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .codex_cli import CODEX_CLI_PATH
from .i18n import T
from .platforms import no_window_kwargs

__all__ = [
    'CodexAppServerClient', 'CodexAppServerError', 'api_headers', 'close_client',
    'fetch_prepaid_credits', 'fetch_profile', 'fetch_usage', 'is_authenticated',
    'normalize_rate_limits', 'read_access_token',
]

_NUMBER_WORDS = {
    1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
    7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve',
}
_CLIENT_NAME = 'usage-monitor-for-codex'
_CLIENT_VERSION = '0.1.0'
_RATE_LIMIT_RETRY_DELAYS = (0.25, 0.75)

log = logging.getLogger(__name__)


class CodexAppServerError(RuntimeError):
    """Failure while starting or communicating with Codex App Server."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class CodexAppServerClient:
    """Small, serialized JSONL client for ``codex app-server --stdio``."""

    def __init__(self, cli_path: str | None = None) -> None:
        self.cli_path = cli_path or str(CODEX_CLI_PATH)
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._next_id = 0
        self._account_key: str | None = None
        self._account_revision = 0

    @property
    def account_marker(self) -> str | None:
        """Opaque account-state marker; never contains an access token."""
        with self._lock:
            if self._account_key is None:
                return None
            return f'{self._account_key}:{self._account_revision}'

    def request(self, method: str, params: Any = None, *, timeout: float = 15.0) -> dict[str, Any]:
        """Send one request, restarting the subprocess once on transport failure."""
        last_error: CodexAppServerError | None = None
        for attempt in range(2):
            with self._lock:
                try:
                    self._ensure_started_locked(timeout=min(timeout, 10.0))
                    return self._request_locked(method, params, timeout=timeout)
                except CodexAppServerError as exc:
                    last_error = exc
                    # A JSON-RPC error is an application response from a healthy
                    # App Server process. Keep the process alive so callers can
                    # retry transient upstream failures without reinitializing it.
                    if exc.code is not None:
                        raise
                    self._stop_locked()
                    if attempt:
                        raise
        raise last_error or CodexAppServerError('Codex App Server request failed')

    def note_account(self, account: Any) -> None:
        """Update the non-secret identity marker from an ``account/read`` result."""
        if not isinstance(account, dict):
            key = None
        else:
            material = '|'.join(str(account.get(k) or '') for k in ('type', 'email', 'planType'))
            key = hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]

        with self._lock:
            if key != self._account_key:
                self._account_key = key
                self._account_revision += 1

    def close(self) -> None:
        with self._lock:
            self._stop_locked()

    def _ensure_started_locked(self, *, timeout: float) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if not self.cli_path:
            raise CodexAppServerError('Codex CLI not found')

        self._messages = queue.Queue()
        try:
            self._process = subprocess.Popen(
                [self.cli_path, 'app-server', '--stdio'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
                **no_window_kwargs(),
            )
        except OSError as exc:
            raise CodexAppServerError(f'Could not start Codex CLI: {exc}') from exc

        threading.Thread(target=self._read_stdout, args=(self._process,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(self._process,), daemon=True).start()
        self._request_locked(
            'initialize',
            {
                'clientInfo': {'name': _CLIENT_NAME, 'version': _CLIENT_VERSION},
                'capabilities': {'experimentalApi': False},
            },
            timeout=timeout,
        )

    def _request_locked(self, method: str, params: Any, *, timeout: float) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise CodexAppServerError('Codex App Server is not running')

        self._next_id += 1
        request_id = self._next_id
        payload: dict[str, Any] = {'id': request_id, 'method': method}
        if params is not None:
            payload['params'] = params

        try:
            process.stdin.write(json.dumps(payload, separators=(',', ':')) + '\n')
            process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise CodexAppServerError('Lost connection to Codex App Server') from exc

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAppServerError(f'Codex App Server timed out during {method}')
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise CodexAppServerError(f'Codex App Server timed out during {method}') from exc
            if message is None:
                raise CodexAppServerError('Codex App Server stopped unexpectedly')

            if 'method' in message and 'id' not in message:
                self._handle_notification(message)
                continue
            if message.get('id') != request_id:
                continue
            if 'error' in message:
                error = message.get('error') or {}
                if isinstance(error, dict):
                    detail = str(error.get('message') or 'Codex App Server error')
                    code = error.get('code') if isinstance(error.get('code'), int) else None
                else:
                    detail, code = str(error), None
                raise CodexAppServerError(detail, code=code)

            result = message.get('result')
            return result if isinstance(result, dict) else {}

    def _handle_notification(self, message: dict[str, Any]) -> None:
        if message.get('method') == 'account/updated':
            params = message.get('params')
            if isinstance(params, dict) and params.get('authMode') is None:
                self.note_account(None)

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        stdout = process.stdout
        if stdout is None:
            self._messages.put(None)
            return
        try:
            for line in stdout:
                try:
                    message = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(message, dict):
                    self._messages.put(message)
        finally:
            self._messages.put(None)

    @staticmethod
    def _drain_stderr(process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for _line in process.stderr:
            pass

    def _stop_locked(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
        except OSError:
            pass


_CLIENT = CodexAppServerClient()
atexit.register(_CLIENT.close)


def close_client() -> None:
    """Stop the shared App Server subprocess."""
    _CLIENT.close()


def read_access_token() -> str | None:
    """Return a non-secret marker used by legacy account-switch handling."""
    return _CLIENT.account_marker


def api_headers() -> dict[str, str] | None:
    """Backward-compatible readiness probe used by the tray startup path."""
    return {'Transport': 'Codex-App-Server'} if is_authenticated() else None


def is_authenticated() -> bool:
    """Return whether Codex is signed in with a ChatGPT-backed identity."""
    profile = fetch_profile()
    return bool(profile and (profile.get('account') or {}).get('auth_type') == 'chatgpt')


def fetch_profile() -> dict[str, Any] | None:
    """Fetch and normalize the active Codex account without reading credentials."""
    try:
        result = _CLIENT.request('account/read', {'refreshToken': False})
    except CodexAppServerError:
        return None

    account = result.get('account')
    _CLIENT.note_account(account)
    if not isinstance(account, dict):
        return None

    auth_type = str(account.get('type') or 'unknown')
    email = account.get('email') if isinstance(account.get('email'), str) else ''
    plan = account.get('planType') if isinstance(account.get('planType'), str) else auth_type
    marker = hashlib.sha256(f'{auth_type}|{email}|{plan}'.encode('utf-8')).hexdigest()[:20]
    return {
        'account': {'uuid': marker, 'email': email, 'auth_type': auth_type},
        'organization': {'organization_type': plan},
    }


def fetch_usage() -> dict[str, Any]:
    """Fetch ChatGPT-backed Codex rate-limit windows and normalize them for the UI."""
    try:
        account_result = _CLIENT.request('account/read', {'refreshToken': False})
        account = account_result.get('account')
        _CLIENT.note_account(account)
        if not isinstance(account, dict):
            return {'error': T['no_token'], 'auth_error': True}
        if account.get('type') != 'chatgpt':
            return {
                'error': 'Codex rate limits require Sign in with ChatGPT; API-key usage is not supported.',
                'auth_error': True,
            }

        result = _read_rate_limits()
        data = normalize_rate_limits(result)
        if not any(isinstance(value, dict) and 'utilization' in value for value in data.values()):
            return {'error': 'Codex returned no rate-limit windows.'}
        return data
    except CodexAppServerError as exc:
        message = str(exc).strip() or T['connection_error']
        lower = message.lower()
        auth_error = any(word in lower for word in ('auth', 'login', 'sign in', 'unauthorized'))
        rate_limited = exc.code == 429 or any(
            phrase in lower for phrase in ('rate limit exceeded', 'too many requests', 'http 429')
        )
        transient = _is_transient_backend_error(exc)
        if transient:
            log.warning('Codex rate-limit service unavailable after retries: %s', message)
        return {
            'error': T['connection_error'] if transient else message,
            **({'auth_error': True} if auth_error else {}),
            **({'rate_limited': True} if rate_limited else {}),
        }


def fetch_prepaid_credits(_org_uuid: Any) -> None:
    """Compatibility hook; Codex credit balance is part of the rate-limit snapshot."""
    return None


def _read_rate_limits() -> dict[str, Any]:
    """Read limits, retrying brief upstream transport failures in place."""
    for attempt in range(len(_RATE_LIMIT_RETRY_DELAYS) + 1):
        try:
            return _CLIENT.request('account/rateLimits/read', timeout=20.0)
        except CodexAppServerError as exc:
            if not _is_transient_backend_error(exc) or attempt >= len(_RATE_LIMIT_RETRY_DELAYS):
                raise
            time.sleep(_RATE_LIMIT_RETRY_DELAYS[attempt])
    raise AssertionError('unreachable')


def _is_transient_backend_error(exc: CodexAppServerError) -> bool:
    message = str(exc).lower()
    return any(phrase in message for phrase in (
        'error sending request for url',
        'failed to fetch codex rate limits',
        'connection closed',
        'connection reset',
        'temporarily unavailable',
        'timed out',
    ))


def normalize_rate_limits(payload: Any) -> dict[str, Any]:
    """Convert App Server rate-limit snapshots to the monitor's quota format."""
    if not isinstance(payload, dict):
        return {}

    raw_by_id = payload.get('rateLimitsByLimitId')
    if isinstance(raw_by_id, dict) and raw_by_id:
        buckets = [(str(key), value) for key, value in raw_by_id.items() if isinstance(value, dict)]
    else:
        fallback = payload.get('rateLimits')
        buckets = [('codex', fallback)] if isinstance(fallback, dict) else []

    normalized: dict[str, Any] = {}
    for bucket_id, bucket in buckets:
        slug = _slug(bucket.get('limitName') or bucket.get('limitId') or bucket_id)
        is_default = bucket_id == 'codex' or len(buckets) == 1
        for position in ('primary', 'secondary'):
            window = bucket.get(position)
            if not isinstance(window, dict) or isinstance(window.get('usedPercent'), bool):
                continue
            used = window.get('usedPercent')
            if not isinstance(used, (int, float)):
                continue
            base = _window_field(window.get('windowDurationMins'), position)
            field = base if is_default else f'{base}_{slug}'
            if field in normalized:
                field = f'{base}_{slug}'
            normalized[field] = {
                'utilization': float(used),
                'resets_at': _reset_iso(window.get('resetsAt')),
            }

    default_bucket = next((value for key, value in buckets if key == 'codex'), buckets[0][1] if buckets else {})
    credits = default_bucket.get('credits') if isinstance(default_bucket, dict) else None
    if isinstance(credits, dict):
        normalized['_credits'] = {
            'has_credits': bool(credits.get('hasCredits')),
            'unlimited': bool(credits.get('unlimited')),
            'balance': credits.get('balance'),
        }
    normalized['_account_id'] = payload.get('accountId')
    normalized['_rate_limit_reached_type'] = default_bucket.get('rateLimitReachedType') if isinstance(default_bucket, dict) else None
    return normalized


def _window_field(duration_mins: Any, position: str) -> str:
    if isinstance(duration_mins, bool) or not isinstance(duration_mins, (int, float)) or duration_mins <= 0:
        return f'{position}_limit'
    minutes = int(duration_mins)
    if minutes % (24 * 60) == 0:
        amount, unit = minutes // (24 * 60), 'day'
    elif minutes % 60 == 0:
        amount, unit = minutes // 60, 'hour'
    else:
        return f'{position}_limit'
    word = _NUMBER_WORDS.get(amount)
    return f'{word}_{unit}' if word else f'{position}_limit'


def _reset_iso(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ''
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ''


def _slug(value: Any) -> str:
    text = re.sub(r'[^a-z0-9]+', '_', str(value).lower()).strip('_')
    return text or 'codex'
