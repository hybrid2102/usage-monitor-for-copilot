"""Tests for the Copilot CLI server transport and response normalization."""
from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from usage_monitor_for_copilot.api import (
    CopilotServerClient,
    CopilotServerError,
    encode_frame,
    fetch_prepaid_credits,
    fetch_profile,
    fetch_usage,
    is_authenticated,
    normalize_quota_snapshots,
    read_frame,
)


def _personal_account_snapshot() -> dict:
    """A real fixture: a personal/free account that has not used any quota yet.

    ``premium_interactions`` is not part of this plan (``hasQuota`` is false).
    """
    return {
        'quotaSnapshots': {
            'chat': {
                'isUnlimitedEntitlement': False, 'entitlementRequests': 200, 'usedRequests': 0,
                'usageAllowedWithExhaustedQuota': False, 'overage': 0, 'overageAllowedWithExhaustedQuota': False,
                'overageEntitlement': 0, 'remainingPercentage': 100, 'resetDate': '2024-01-01T00:00:00Z',
                'hasQuota': True, 'tokenBasedBilling': False,
            },
            'completions': {
                'isUnlimitedEntitlement': False, 'entitlementRequests': 2000, 'usedRequests': 0,
                'usageAllowedWithExhaustedQuota': False, 'overage': 0, 'overageAllowedWithExhaustedQuota': False,
                'overageEntitlement': 0, 'remainingPercentage': 100, 'resetDate': '2024-01-01T00:00:00Z',
                'hasQuota': True, 'tokenBasedBilling': False,
            },
            'premium_interactions': {
                'isUnlimitedEntitlement': False, 'entitlementRequests': 0, 'usedRequests': 0,
                'usageAllowedWithExhaustedQuota': False, 'overage': 0, 'overageAllowedWithExhaustedQuota': False,
                'overageEntitlement': 0, 'remainingPercentage': 0, 'resetDate': '2024-01-01T00:00:00Z',
                'hasQuota': False, 'tokenBasedBilling': False,
            },
        },
    }


def _business_account_snapshot() -> dict:
    """A real fixture: a business account with unlimited chat/completions.

    ``premium_interactions`` is metered and 912/3000 requests used (30.4%).
    The two ``resetDate`` values are 20 seconds apart, as observed in the
    live protocol spike, to document that the field tracks the call's
    wall-clock moment rather than a real billing-cycle boundary.
    """
    return {
        'quotaSnapshots': {
            'chat': {
                'isUnlimitedEntitlement': True, 'entitlementRequests': 0, 'usedRequests': 0,
                'usageAllowedWithExhaustedQuota': True, 'overage': 0, 'overageAllowedWithExhaustedQuota': False,
                'overageEntitlement': 0, 'remainingPercentage': 100, 'resetDate': '2024-02-02T00:00:20Z',
                'hasQuota': True, 'tokenBasedBilling': False,
            },
            'completions': {
                'isUnlimitedEntitlement': True, 'entitlementRequests': 0, 'usedRequests': 0,
                'usageAllowedWithExhaustedQuota': True, 'overage': 0, 'overageAllowedWithExhaustedQuota': False,
                'overageEntitlement': 0, 'remainingPercentage': 100, 'resetDate': '2024-02-02T00:00:40Z',
                'hasQuota': True, 'tokenBasedBilling': False,
            },
            'premium_interactions': {
                'isUnlimitedEntitlement': False, 'entitlementRequests': 3000, 'usedRequests': 912,
                'usageAllowedWithExhaustedQuota': False, 'overage': 0, 'overageAllowedWithExhaustedQuota': False,
                'overageEntitlement': 0, 'remainingPercentage': 69.6, 'resetDate': '2024-02-02T00:01:00Z',
                'hasQuota': True, 'tokenBasedBilling': False,
            },
        },
    }


class TestFraming(unittest.TestCase):
    def test_round_trips_a_json_rpc_payload(self):
        payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'connect', 'params': {'token': 'abc'}}
        self.assertEqual(read_frame(io.BytesIO(encode_frame(payload))), payload)

    def test_encodes_the_exact_content_length_header(self):
        payload = {'id': 1}
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        self.assertEqual(encode_frame(payload), f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii') + body)

    def test_reads_two_consecutive_frames_from_one_stream(self):
        first, second = {'id': 1, 'result': {}}, {'id': 2, 'result': {'ok': True}}
        stream = io.BytesIO(encode_frame(first) + encode_frame(second))

        self.assertEqual(read_frame(stream), first)
        self.assertEqual(read_frame(stream), second)

    def test_returns_none_at_end_of_stream(self):
        self.assertIsNone(read_frame(io.BytesIO(b'')))

    def test_returns_none_when_content_length_header_is_missing(self):
        self.assertIsNone(read_frame(io.BytesIO(b'\r\n{}')))

    def test_returns_none_on_a_truncated_body(self):
        self.assertIsNone(read_frame(io.BytesIO(b'Content-Length: 10\r\n\r\n{}')))


def _started_process(*stdout_lines: str) -> MagicMock:
    process = MagicMock()
    process.poll.return_value = None
    process.stdout = io.StringIO(''.join(stdout_lines))
    process.stderr = io.StringIO('')
    return process


def _connected_socket(*response_frames: dict) -> MagicMock:
    sock = MagicMock()
    sock.makefile.return_value = io.BytesIO(b''.join(encode_frame(frame) for frame in response_frames))
    return sock


class TestConnectHandshake(unittest.TestCase):
    @patch('usage_monitor_for_copilot.api.socket.create_connection')
    @patch('usage_monitor_for_copilot.api.subprocess.Popen')
    def test_successful_connect_marks_the_client_connected(self, popen, create_connection):
        popen.return_value = _started_process('CLI server listening on port 54321\n')
        create_connection.return_value = _connected_socket(
            {'id': 1, 'result': {'ok': True, 'protocolVersion': 3, 'version': '1.0.84-1', 'taskKinds': []}},
        )

        client = CopilotServerClient('copilot')
        client._ensure_started_locked(timeout=2.0)

        self.assertTrue(client._connected)
        sent_body = create_connection.return_value.sendall.call_args.args[0].split(b'\r\n\r\n', 1)[1]
        sent = json.loads(sent_body)
        self.assertEqual(sent['method'], 'connect')
        self.assertEqual(sent['params']['supportedTaskKinds'], [])
        self.assertEqual(len(sent['params']['token']), 32)

        self.assertEqual(popen.call_args.args[0], ['copilot', '--server'])
        self.assertEqual(popen.call_args.kwargs['env']['COPILOT_CONNECTION_TOKEN'], sent['params']['token'])

    @patch('usage_monitor_for_copilot.api.socket.create_connection')
    @patch('usage_monitor_for_copilot.api.subprocess.Popen')
    def test_wrong_token_surfaces_authentication_failed(self, popen, create_connection):
        popen.return_value = _started_process('CLI server listening on port 54321\n')
        create_connection.return_value = _connected_socket(
            {'id': 1, 'error': {'code': -32002, 'message': 'AUTHENTICATION_FAILED'}},
        )

        client = CopilotServerClient('copilot')
        with self.assertRaises(CopilotServerError) as raised:
            client._ensure_started_locked(timeout=2.0)

        self.assertEqual(raised.exception.code, -32002)
        self.assertIn('AUTHENTICATION_FAILED', str(raised.exception))
        self.assertFalse(client._connected)

    def test_method_called_before_connect_surfaces_authentication_required(self):
        # Simulates the documented server behaviour (any method but `connect`
        # fails this way before a successful handshake) without going through
        # _ensure_started_locked, which this client always calls first.
        client = CopilotServerClient('copilot')
        client._process = MagicMock(poll=MagicMock(return_value=None))
        client._socket = MagicMock()
        client._messages.put({'id': 1, 'error': {'code': -32001, 'message': 'AUTHENTICATION_REQUIRED'}})

        with self.assertRaises(CopilotServerError) as raised:
            client._request_locked('account.getQuota', {}, timeout=0.5)

        self.assertEqual(raised.exception.code, -32001)
        self.assertIn('AUTHENTICATION_REQUIRED', str(raised.exception))


class TestNormalizeQuotaSnapshots(unittest.TestCase):
    def test_personal_account_fields_are_at_zero_utilization(self):
        result = normalize_quota_snapshots(_personal_account_snapshot())
        self.assertEqual(result['chat']['utilization'], 0.0)
        self.assertEqual(result['completions']['utilization'], 0.0)

    def test_hasquota_false_field_is_omitted(self):
        result = normalize_quota_snapshots(_personal_account_snapshot())
        self.assertNotIn('premium_interactions', result)

    def test_business_account_premium_interactions_utilization(self):
        result = normalize_quota_snapshots(_business_account_snapshot())
        self.assertAlmostEqual(result['premium_interactions']['utilization'], 30.4, places=1)

    def test_unlimited_fields_get_unlimited_true_and_zero_utilization(self):
        result = normalize_quota_snapshots(_business_account_snapshot())
        self.assertEqual(result['chat'], {'utilization': 0.0, 'resets_at': '', 'unlimited': True})
        self.assertEqual(result['completions'], {'utilization': 0.0, 'resets_at': '', 'unlimited': True})

    def test_metered_field_has_no_unlimited_key(self):
        result = normalize_quota_snapshots(_business_account_snapshot())
        self.assertNotIn('unlimited', result['premium_interactions'])

    def test_resets_at_is_always_empty_never_the_raw_reset_date(self):
        for snapshot in (_personal_account_snapshot(), _business_account_snapshot()):
            for field in normalize_quota_snapshots(snapshot).values():
                self.assertEqual(field['resets_at'], '')

    def test_non_mapping_payload_is_empty(self):
        self.assertEqual(normalize_quota_snapshots(None), {})

    def test_missing_quota_snapshots_key_is_empty(self):
        self.assertEqual(normalize_quota_snapshots({}), {})

    def test_invalid_remaining_percentage_is_skipped(self):
        result = normalize_quota_snapshots({
            'quotaSnapshots': {
                'chat': {'hasQuota': True, 'isUnlimitedEntitlement': False, 'remainingPercentage': 'mostly full'},
            },
        })
        self.assertNotIn('chat', result)


class TestFetchUsage(unittest.TestCase):
    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_normalizes_the_business_account_fixture(self, client):
        client.request.return_value = _business_account_snapshot()

        result = fetch_usage()

        self.assertAlmostEqual(result['premium_interactions']['utilization'], 30.4, places=1)
        client.request.assert_called_once_with('account.getQuota', {})

    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_normalizes_the_personal_account_fixture(self, client):
        client.request.return_value = _personal_account_snapshot()

        result = fetch_usage()

        self.assertEqual(result['chat']['utilization'], 0.0)
        self.assertNotIn('premium_interactions', result)

    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_empty_quota_snapshots_is_reported_as_an_error(self, client):
        client.request.return_value = {'quotaSnapshots': {}}
        self.assertIn('error', fetch_usage())

    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_transport_failure_is_an_error_without_the_auth_flag(self, client):
        client.request.side_effect = CopilotServerError('Lost connection to the Copilot CLI server')

        result = fetch_usage()

        self.assertIn('error', result)
        self.assertNotIn('auth_error', result)

    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_authentication_failed_is_classified_as_an_auth_error(self, client):
        client.request.side_effect = CopilotServerError('AUTHENTICATION_FAILED', code=-32002)
        self.assertTrue(fetch_usage()['auth_error'])

    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_authentication_required_is_classified_as_an_auth_error(self, client):
        client.request.side_effect = CopilotServerError('AUTHENTICATION_REQUIRED', code=-32001)
        self.assertTrue(fetch_usage()['auth_error'])


class TestIsAuthenticated(unittest.TestCase):
    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_successful_quota_call_implies_authenticated(self, client):
        client.request.return_value = {}
        self.assertTrue(is_authenticated())

    @patch('usage_monitor_for_copilot.api._CLIENT')
    def test_server_error_means_not_authenticated(self, client):
        client.request.side_effect = CopilotServerError('AUTHENTICATION_REQUIRED', code=-32001)
        self.assertFalse(is_authenticated())


class TestCompatibilityHooks(unittest.TestCase):
    def test_fetch_profile_always_returns_none(self):
        self.assertIsNone(fetch_profile())

    def test_fetch_prepaid_credits_is_a_no_op(self):
        self.assertIsNone(fetch_prepaid_credits('org-uuid'))


if __name__ == '__main__':
    unittest.main()
