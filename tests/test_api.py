"""Tests for the Codex App Server transport and response normalization."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from usage_monitor_for_codex.api import (
    CodexAppServerClient,
    CodexAppServerError,
    fetch_profile,
    fetch_usage,
    normalize_rate_limits,
)


def _snapshot() -> dict:
    return {
        'accountId': 'account-1',
        'rateLimits': {
            'primary': {
                'usedPercent': 24,
                'windowDurationMins': 300,
                'resetsAt': 1_800_000_000,
            },
            'secondary': {
                'usedPercent': 61.5,
                'windowDurationMins': 10_080,
                'resetsAt': 1_800_604_800,
            },
            'credits': {'hasCredits': True, 'unlimited': False, 'balance': 12.5},
            'rateLimitReachedType': None,
        },
    }


class TestNormalizeRateLimits(unittest.TestCase):
    def test_maps_standard_codex_windows(self):
        result = normalize_rate_limits(_snapshot())

        self.assertEqual(result['five_hour']['utilization'], 24.0)
        self.assertEqual(result['seven_day']['utilization'], 61.5)
        self.assertEqual(
            result['five_hour']['resets_at'],
            datetime.fromtimestamp(1_800_000_000, tz=timezone.utc).isoformat(),
        )
        self.assertEqual(result['_credits']['balance'], 12.5)
        self.assertEqual(result['_account_id'], 'account-1')

    def test_prefers_named_rate_limit_buckets(self):
        payload = {
            'rateLimitsByLimitId': {
                'codex': _snapshot()['rateLimits'],
                'review': {
                    'limitId': 'code-review',
                    'limitName': 'Code Review',
                    'primary': {'usedPercent': 10, 'windowDurationMins': 60},
                },
            },
        }

        result = normalize_rate_limits(payload)

        self.assertIn('five_hour', result)
        self.assertEqual(result['one_hour_code_review']['utilization'], 10.0)

    def test_invalid_windows_are_ignored(self):
        result = normalize_rate_limits({
            'rateLimits': {
                'primary': {'usedPercent': True, 'windowDurationMins': 300},
                'secondary': {'usedPercent': '20', 'windowDurationMins': 10_080},
            },
        })

        self.assertNotIn('five_hour', result)
        self.assertNotIn('seven_day', result)

    def test_unknown_duration_uses_position_name(self):
        result = normalize_rate_limits({
            'rateLimits': {'primary': {'usedPercent': 7, 'windowDurationMins': 17}},
        })
        self.assertEqual(result['primary_limit']['utilization'], 7.0)

    def test_non_mapping_payload_is_empty(self):
        self.assertEqual(normalize_rate_limits(None), {})


class TestFetchProfile(unittest.TestCase):
    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_normalizes_chatgpt_account(self, client):
        client.request.return_value = {
            'account': {'type': 'chatgpt', 'email': 'user@example.test', 'planType': 'plus'},
        }

        profile = fetch_profile()

        assert profile is not None
        self.assertEqual(profile['account']['auth_type'], 'chatgpt')
        self.assertEqual(profile['account']['email'], 'user@example.test')
        self.assertEqual(profile['organization']['organization_type'], 'plus')
        self.assertEqual(len(profile['account']['uuid']), 20)
        client.note_account.assert_called_once()

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_signed_out_returns_none(self, client):
        client.request.return_value = {'account': None}
        self.assertIsNone(fetch_profile())

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_transport_failure_returns_none(self, client):
        client.request.side_effect = CodexAppServerError('stopped')
        self.assertIsNone(fetch_profile())


class TestFetchUsage(unittest.TestCase):
    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_fetches_rate_limits_for_chatgpt_login(self, client):
        client.request.side_effect = [
            {'account': {'type': 'chatgpt', 'planType': 'plus'}},
            _snapshot(),
        ]

        result = fetch_usage()

        self.assertEqual(result['five_hour']['utilization'], 24.0)
        self.assertEqual(client.request.call_args_list[1].args[0], 'account/rateLimits/read')

    @patch('usage_monitor_for_codex.api.time.sleep')
    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_retries_transient_backend_failure(self, client, sleep):
        client.request.side_effect = [
            {'account': {'type': 'chatgpt', 'planType': 'plus'}},
            CodexAppServerError('error sending request for url', code=-32603),
            _snapshot(),
        ]

        result = fetch_usage()

        self.assertEqual(result['five_hour']['utilization'], 24.0)
        sleep.assert_called_once_with(0.25)

    @patch('usage_monitor_for_codex.api.time.sleep')
    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_hides_internal_url_after_transient_retries(self, client, sleep):
        client.request.side_effect = [
            {'account': {'type': 'chatgpt'}},
            *[CodexAppServerError(
                'failed to fetch codex rate limits: error sending request for url '
                '(https://chatgpt.com/backend-api/wham/usage)',
                code=-32603,
            ) for _ in range(3)],
        ]

        result = fetch_usage()

        self.assertNotIn('chatgpt.com', result['error'])
        self.assertNotIn('wham', result['error'])
        self.assertEqual(sleep.call_count, 2)

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_signed_out_is_an_auth_error(self, client):
        client.request.return_value = {'account': None}
        self.assertTrue(fetch_usage()['auth_error'])

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_api_key_login_is_explicitly_unsupported(self, client):
        client.request.return_value = {'account': {'type': 'apiKey'}}
        result = fetch_usage()
        self.assertTrue(result['auth_error'])
        self.assertIn('ChatGPT', result['error'])

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_empty_rate_limits_are_reported(self, client):
        client.request.side_effect = [
            {'account': {'type': 'chatgpt'}},
            {'rateLimits': {}},
        ]
        self.assertIn('no rate-limit windows', fetch_usage()['error'])

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_app_server_auth_error_is_classified(self, client):
        client.request.side_effect = CodexAppServerError('Please login again', code=-32000)
        result = fetch_usage()
        self.assertTrue(result['auth_error'])

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_app_server_rate_limit_error_is_classified(self, client):
        client.request.side_effect = CodexAppServerError('Rate limit exceeded', code=429)
        result = fetch_usage()
        self.assertTrue(result['rate_limited'])

    @patch('usage_monitor_for_codex.api._CLIENT')
    def test_generic_rate_limits_fetch_failure_is_not_a_429(self, client):
        client.request.side_effect = CodexAppServerError('failed to fetch Codex rate limits')
        result = fetch_usage()
        self.assertNotIn('rate_limited', result)


class TestAppServerClient(unittest.TestCase):
    def test_account_marker_is_stable_and_contains_no_identity(self):
        client = CodexAppServerClient('codex')
        account = {'type': 'chatgpt', 'email': 'secret@example.test', 'planType': 'plus'}
        client.note_account(account)
        first = client.account_marker
        client.note_account(account)

        self.assertEqual(client.account_marker, first)
        self.assertNotIn('secret@example.test', first or '')

        client.note_account({**account, 'email': 'other@example.test'})
        self.assertNotEqual(client.account_marker, first)

    def test_serializes_jsonl_request_and_returns_matching_response(self):
        client = CodexAppServerClient('codex')
        process = MagicMock()
        process.poll.return_value = None
        process.stdin = MagicMock()
        client._process = process
        client._messages.put({'method': 'account/rateLimits/updated', 'params': {}})
        client._messages.put({'id': 1, 'result': {'ok': True}})

        result = client._request_locked('test/read', {'value': 1}, timeout=0.1)

        self.assertEqual(result, {'ok': True})
        written = process.stdin.write.call_args.args[0]
        self.assertEqual(json.loads(written), {'id': 1, 'method': 'test/read', 'params': {'value': 1}})

    def test_json_rpc_error_preserves_numeric_code(self):
        client = CodexAppServerClient('codex')
        process = MagicMock()
        process.poll.return_value = None
        process.stdin = MagicMock()
        client._process = process
        client._messages.put({'id': 1, 'error': {'code': 429, 'message': 'limited'}})

        with self.assertRaises(CodexAppServerError) as raised:
            client._request_locked('test/read', None, timeout=0.1)
        self.assertEqual(raised.exception.code, 429)


if __name__ == '__main__':
    unittest.main()
