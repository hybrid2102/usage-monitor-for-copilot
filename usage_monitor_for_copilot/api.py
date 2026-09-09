"""
GitHub Copilot CLI server client and response normalization.

The monitor never reads Copilot credentials or config files. It spawns
``copilot --server`` as a subprocess and speaks its JSON-RPC-over-TCP
protocol directly, delegating authentication and token refresh entirely to
the installed Copilot CLI.

Security note - this is the only module that may spawn ``copilot --server``,
and it must always do so the way it does here: left unconfigured, that
server accepts connections from ANY local process that can reach its TCP
port and lets it drive the Copilot agent (shell commands, file edits) as the
logged-in user. Setting ``COPILOT_CONNECTION_TOKEN`` in the child's
environment and completing the resulting ``connect`` handshake before any
other call closes that local security hole on every single invocation; it
is not an optional nicety.
"""
from __future__ import annotations

import atexit
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, BinaryIO

from .copilot_cli import COPILOT_CLI_PATH
from .i18n import T
from .platforms import no_window_kwargs

__all__ = [
    'CopilotServerClient', 'CopilotServerError', 'api_headers', 'close_client', 'encode_frame',
    'fetch_prepaid_credits', 'fetch_profile', 'fetch_usage', 'is_authenticated',
    'monthly_reset_at', 'normalize_quota_snapshots', 'read_access_token', 'read_frame',
]

_PORT_PATTERN = re.compile(r'listening on port (\d+)')


class CopilotServerError(RuntimeError):
    """Failure while starting or communicating with the Copilot CLI server."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def encode_frame(payload: dict[str, Any]) -> bytes:
    """Encode one JSON-RPC payload as a Content-Length-framed message.

    Parameters
    ----------
    payload : dict[str, Any]
        The JSON-RPC request or response body.

    Returns
    -------
    bytes
        ``Content-Length: <N>\\r\\n\\r\\n`` followed by the UTF-8 JSON body.
    """
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    header = f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii')
    return header + body


def read_frame(stream: BinaryIO) -> dict[str, Any] | None:
    """Read one Content-Length-framed JSON-RPC message from a binary stream.

    Parameters
    ----------
    stream : BinaryIO
        A readable binary stream (a socket file object in production, a
        :class:`io.BytesIO` in tests).

    Returns
    -------
    dict[str, Any] | None
        The decoded message, or ``None`` at end of stream or on a malformed
        frame (no ``Content-Length`` header, a truncated body, or a body
        that is not a JSON object).
    """
    content_length: int | None = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        name, _, value = line.partition(b':')
        if name.strip().lower() == b'content-length':
            try:
                content_length = int(value.strip())
            except ValueError:
                return None

    if content_length is None:
        return None

    body = stream.read(content_length)
    if len(body) < content_length:
        return None
    try:
        message = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) else None


class CopilotServerClient:
    """Small, serialized JSON-RPC client for ``copilot --server``."""

    def __init__(self, cli_path: str | None = None) -> None:
        self.cli_path = cli_path or str(COPILOT_CLI_PATH)
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._socket: socket.socket | None = None
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._next_id = 0
        self._connected = False

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 15.0) -> dict[str, Any]:
        """Send one request, restarting the subprocess once on transport failure."""
        last_error: CopilotServerError | None = None
        for attempt in range(2):
            with self._lock:
                try:
                    self._ensure_started_locked(timeout=min(timeout, 10.0))
                    return self._request_locked(method, params if params is not None else {}, timeout=timeout)
                except CopilotServerError as exc:
                    last_error = exc
                    # A JSON-RPC error is an application response from a healthy
                    # server process. Keep the process alive so callers can retry
                    # transient upstream failures without reinitializing it.
                    if exc.code is not None:
                        raise
                    self._stop_locked()
                    if attempt:
                        raise
        raise last_error or CopilotServerError('Copilot CLI server request failed')

    def close(self) -> None:
        with self._lock:
            self._stop_locked()

    def _ensure_started_locked(self, *, timeout: float) -> None:
        if self._connected and self._process is not None and self._process.poll() is None:
            return
        self._stop_locked()
        if not self.cli_path:
            raise CopilotServerError('Copilot CLI not found')

        token = secrets.token_hex(16)
        env = dict(os.environ)
        env['COPILOT_CONNECTION_TOKEN'] = token

        try:
            self._process = subprocess.Popen(
                [self.cli_path, '--server'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
                env=env, **no_window_kwargs(),
            )
        except OSError as exc:
            raise CopilotServerError(f'Could not start Copilot CLI: {exc}') from exc

        port_queue: queue.Queue[int | None] = queue.Queue(maxsize=1)
        threading.Thread(target=self._watch_stdout, args=(self._process, port_queue), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(self._process,), daemon=True).start()

        try:
            port = port_queue.get(timeout=timeout)
        except queue.Empty as exc:
            self._stop_locked()
            raise CopilotServerError('Timed out waiting for the Copilot CLI to start its server') from exc
        if port is None:
            self._stop_locked()
            raise CopilotServerError('Copilot CLI exited before starting its server')

        try:
            sock = socket.create_connection(('127.0.0.1', port), timeout=timeout)
            sock.settimeout(None)
        except OSError as exc:
            self._stop_locked()
            raise CopilotServerError(f'Could not connect to the Copilot CLI server: {exc}') from exc

        self._socket = sock
        self._messages = queue.Queue()
        threading.Thread(target=self._read_socket, args=(sock,), daemon=True).start()

        # Sent directly through _request_locked, never through request(), which
        # would call back into this method and recurse. supportedTaskKinds is []
        # (least privilege): this client only ever reads account.getQuota and
        # never starts a session, unlike the official SDK's ['agent', 'client',
        # 'shell'] default for full agent capability.
        result = self._request_locked(
            'connect', {'supportedTaskKinds': [], 'token': token}, timeout=timeout,
        )
        if not result.get('ok'):
            self._stop_locked()
            raise CopilotServerError('Copilot CLI server rejected the connect handshake')
        self._connected = True

    def _request_locked(self, method: str, params: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        sock = self._socket
        if sock is None or self._process is None or self._process.poll() is not None:
            raise CopilotServerError('Copilot CLI server is not running')

        self._next_id += 1
        request_id = self._next_id
        payload = {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}

        try:
            sock.sendall(encode_frame(payload))
        except OSError as exc:
            raise CopilotServerError('Lost connection to the Copilot CLI server') from exc

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CopilotServerError(f'Copilot CLI server timed out during {method}')
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise CopilotServerError(f'Copilot CLI server timed out during {method}') from exc
            if message is None:
                raise CopilotServerError('Copilot CLI server stopped unexpectedly')

            # A message with no id (a notification) or a stale id (a response to an
            # earlier, already-resolved request) is not an answer to this call.
            if message.get('id') != request_id:
                continue
            if 'error' in message:
                error = message.get('error') or {}
                if isinstance(error, dict):
                    detail = str(error.get('message') or 'Copilot CLI server error')
                    code = error.get('code') if isinstance(error.get('code'), int) else None
                else:
                    detail, code = str(error), None
                raise CopilotServerError(detail, code=code)

            result = message.get('result')
            return result if isinstance(result, dict) else {}

    @staticmethod
    def _watch_stdout(process: subprocess.Popen[str], port_queue: queue.Queue[int | None]) -> None:
        """Find the "listening on port <N>" line, then keep draining stdout.

        Draining continues for the life of the process so its stdout pipe
        buffer never fills up and blocks it, even after the port has been
        found and reported.
        """
        stdout = process.stdout
        if stdout is None:
            port_queue.put(None)
            return
        found = False
        try:
            for line in stdout:
                if not found:
                    match = _PORT_PATTERN.search(line)
                    if match:
                        found = True
                        port_queue.put(int(match.group(1)))
        finally:
            if not found:
                port_queue.put(None)

    @staticmethod
    def _drain_stderr(process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for _line in process.stderr:
            pass

    def _read_socket(self, sock: socket.socket) -> None:
        try:
            stream = sock.makefile('rb')
        except OSError:
            self._messages.put(None)
            return
        try:
            while True:
                message = read_frame(stream)
                if message is None:
                    break
                self._messages.put(message)
        finally:
            self._messages.put(None)

    def _stop_locked(self) -> None:
        self._connected = False
        sock, self._socket = self._socket, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
        except OSError:
            pass


_CLIENT = CopilotServerClient()
atexit.register(_CLIENT.close)


def close_client() -> None:
    """Stop the shared Copilot CLI server subprocess."""
    _CLIENT.close()


def read_access_token() -> str | None:
    """Compatibility hook; the Copilot CLI server protocol exposes no marker.

    Codex's twin uses the equivalent of this function to return a non-secret
    hash derived from the signed-in account's identity (email/plan), letting
    ``cache.py``/``app.py`` detect an account switch and a token-changed retry
    by comparing this value across polls. The protocol spike behind this
    module found no equivalent "who am I" RPC for ``copilot --server`` (see
    :func:`fetch_profile`), so there is nothing honest to return here.

    Always returning ``None`` makes every comparison against this value a
    None-vs-None no-op in the account-switch-detection and token-changed-retry
    logic those two modules share with the other twins - correctly and safely
    inert for Copilot (it never fires a spurious "changed" signal) rather than
    raising ``ImportError`` or fabricating a marker with no real meaning.
    """
    return None


def api_headers() -> dict[str, str] | None:
    """Backward-compatible readiness probe used by the tray startup path."""
    return {'Transport': 'Copilot-CLI-Server'} if is_authenticated() else None


def is_authenticated() -> bool:
    """Return whether the Copilot CLI has a usable, signed-in session.

    No verified "who am I" RPC method exists for ``copilot --server`` (see
    :func:`fetch_profile`), so this degrades to: a successful
    ``account.getQuota`` call implies an authenticated CLI.
    """
    try:
        _CLIENT.request('account.getQuota', {})
        return True
    except CopilotServerError:
        return False


def fetch_profile() -> dict[str, Any] | None:
    """Compatibility hook; the Copilot CLI exposes no profile RPC method.

    The protocol spike this client is built from found no "who am I"
    equivalent to `account/read` on Codex's App Server - only
    ``account.getQuota``. Returning ``None`` here is honest about that gap
    rather than inventing an endpoint; callers must not assume a profile is
    ever available.
    """
    return None


def fetch_usage() -> dict[str, Any]:
    """Fetch Copilot quota snapshots and normalize them for the UI."""
    try:
        result = _CLIENT.request('account.getQuota', {})
        data = normalize_quota_snapshots(result)
        if not data:
            return {'error': 'Copilot returned no quota information.'}
        return data
    except CopilotServerError as exc:
        message = str(exc).strip() or T['connection_error']
        lower = message.lower()
        # The CLI under test during the protocol spike was always already
        # logged in, so the exact error account.getQuota returns when signed
        # out was never captured. This keyword classification is therefore
        # defensive, not verified against a logged-out CLI - the same stance
        # the other twins take toward opaque CLI error text.
        auth_error = any(word in lower for word in ('auth', 'login', 'token', 'unauthorized', 'unauthenticated'))
        return {
            'error': message,
            **({'auth_error': True} if auth_error else {}),
        }


def fetch_prepaid_credits(_org_uuid: Any) -> None:
    """Compatibility hook; GitHub Copilot has no prepaid usage-credits balance endpoint."""
    return None


def monthly_reset_at(now: datetime | None = None) -> str:
    """Return the next local calendar-month boundary as an ISO UTC timestamp.

    Copilot's ``resetDate`` reflects the request time rather than the quota
    boundary.  The quota cycle is monthly, so this supplies a stable boundary
    for pace indicators.  ``now`` keeps calendar edge cases testable.
    """
    local_now = (now or datetime.now().astimezone()).astimezone()
    year, month = local_now.year, local_now.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    reset_local = datetime(year, month, 1).astimezone()
    return reset_local.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def normalize_quota_snapshots(payload: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Convert an ``account.getQuota`` result to the monitor's quota format.

    Parameters
    ----------
    payload : Any
        The raw ``account.getQuota`` result.

    Returns
    -------
    dict[str, Any]
        One entry per quota key whose ``hasQuota`` is true, keyed by the raw
        ``quotaSnapshots`` key verbatim (e.g. ``'chat'``, ``'completions'``,
        ``'premium_interactions'``) - no renaming table, so a key GitHub adds
        later flows through automatically. Each entry is
        ``{'utilization': float, 'resets_at': '<next month>'}``, plus
        ``'unlimited': True``
        when the plan grants unlimited entitlement for that key.

        ``resets_at`` is derived from the next local calendar-month boundary,
        rather than copied from the CLI's unreliable ``resetDate`` field.
    """
    if not isinstance(payload, dict):
        return {}
    snapshots = payload.get('quotaSnapshots')
    if not isinstance(snapshots, dict):
        return {}

    reset_at = monthly_reset_at(now)
    normalized: dict[str, Any] = {}
    for field, snapshot in snapshots.items():
        if not isinstance(snapshot, dict) or not snapshot.get('hasQuota'):
            continue

        unlimited = bool(snapshot.get('isUnlimitedEntitlement'))
        if unlimited:
            utilization = 0.0
        else:
            remaining = snapshot.get('remainingPercentage')
            if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
                continue
            utilization = max(0.0, 100.0 - float(remaining))

        # TODO: 'overage' / 'overageEntitlement' / 'overageAllowedWithExhaustedQuota'
        # exist per quota key here, unlike the single top-level 'extra_usage' slot the
        # Claude/Codex twins use. Collapsing several of these onto one slot is a
        # product decision, not a mechanical port, so they are left unread for now.

        entry: dict[str, Any] = {'utilization': utilization, 'resets_at': reset_at}
        if unlimited:
            entry['unlimited'] = True
        normalized[str(field)] = entry

    return normalized
