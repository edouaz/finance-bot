import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from finance.connections import connection_status
from finance.core import Settings, FinanceError
import finance_mcp_v2 as api


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings = Settings(self.root, self.root / 'storage', 'app', self.root / 'key', self.root)
        self.now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
        self.config = patch.object(api.Settings, 'load', return_value=self.settings)
        self.config.start(); self.addCleanup(self.config.stop)
        self.clock = patch('finance.connections.datetime', wraps=datetime)
        clock = self.clock.start(); clock.now.return_value = self.now
        self.addCleanup(self.clock.stop)
        api._calls.clear(); api._notice_sent.clear()
        self.addCleanup(api._calls.clear); self.addCleanup(api._notice_sent.clear)

    def save(self, bank, delta):
        path = self.root / f'{bank}_session.json'
        path.write_text(json.dumps({'session_id': 'never-expose-this-secret', 'access': {
            'valid_until': (self.now + delta).isoformat()}}))
        path.chmod(0o600)
        return path

    def test_future_soon_expired_and_threshold_boundaries(self):
        for delta, soon, expired, days in [(timedelta(days=180), False, False, 180),
                                           (timedelta(days=7, seconds=1), False, False, 8),
                                           (timedelta(days=7), True, False, 7),
                                           (timedelta(seconds=1), True, False, 1),
                                           (timedelta(0), False, True, 0),
                                           (timedelta(days=-2), False, True, 0)]:
            self.save('bnp', delta)
            result = connection_status(self.settings, self.now)['bnp']
            self.assertEqual((result['expires_soon'], result['reauthorization_required'], result['days_remaining']),
                             (soon, expired, days))
            self.assertFalse(result['live_verified'])
            self.assertNotIn('never-expose', json.dumps(result))

    def test_missing_corrupt_unsafe_and_naive_expirations_do_not_leak(self):
        for data in ('not-json secret-code', '{}', '[]', '{"access":{"valid_until":"2099-01-01"}}',
                     '{"access":{"valid_until":"secret-password"}}'):
            path = self.root / 'bnp_session.json'
            path.write_text(data); path.chmod(0o600)
            result = connection_status(self.settings, self.now)
            self.assertEqual(result['bnp'], {'status': 'session_unavailable', 'live_verified': False})
            self.assertNotIn('secret', json.dumps(result))
        path = self.save('bnp', timedelta(days=2)); path.chmod(0o644)
        self.assertEqual(connection_status(self.settings, self.now)['bnp']['status'], 'session_unavailable')
        path.unlink()
        self.assertEqual(connection_status(self.settings, self.now)['bnp']['status'], 'session_unavailable')

    def test_notices_are_delivered_on_demand_at_most_once_per_day(self):
        self.save('bnp', timedelta(days=6))
        self.save('revolut', timedelta(days=180))
        query = api.guarded(lambda: {'amount': '123'})
        with patch('finance.core.Client.get') as provider, patch.object(api.time, 'monotonic', return_value=100):
            first = query()
            self.assertEqual(first['amount'], '123')
            self.assertEqual([n['bank'] for n in first['connection_notices']], ['bnp'])
            self.assertNotIn('connection_notices', query())
            provider.assert_not_called()
        with patch.object(api.time, 'monotonic', return_value=100 + 86400):
            self.assertIn('connection_notices', query())
        self.assertNotIn('never-expose', json.dumps(first))
        self.assertFalse(first['connection_notices'][0]['live_verified'])

    def test_expiry_transition_not_suppressed_by_upcoming_reminder(self):
        self.save('bnp', timedelta(days=1))
        self.assertFalse(api.connection_notices()[0]['reauthorization_required'])
        self.save('bnp', timedelta(days=-1))
        self.assertTrue(api.connection_notices()[0]['reauthorization_required'])

    def test_successful_renewal_silences_notices_and_new_expiry_can_warn(self):
        self.save('bnp', timedelta(days=2))
        self.assertEqual(len(api.connection_notices()), 1)
        self.save('bnp', timedelta(days=180))
        self.assertEqual(api.connection_notices(), [])
        self.save('bnp', timedelta(days=3))
        self.assertEqual(len(api.connection_notices()), 1)

    def test_notice_includes_private_shortcut_when_configured(self):
        import os
        self.save('revolut', timedelta(days=2))
        with patch.dict(os.environ, {'FINANCE_AUTH_REDIRECT_URL': 'https://private.example/callback'}):
            notice = api.connection_notices()[0]
        self.assertEqual(notice['renewal_url'], 'https://private.example/?bank=revolut')
        self.assertNotIn('never-expose', json.dumps(notice))

    def test_concurrent_queries_emit_one_notice(self):
        self.save('bnp', timedelta(days=2))
        query = api.guarded(lambda: {'ok': True})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: query(), range(4)))
        self.assertEqual(sum('connection_notices' in r for r in results), 1)

    def test_query_errors_can_carry_a_notice_and_notice_failures_preserve_query(self):
        self.save('revolut', timedelta(days=-1))
        def failed(): raise FinanceError('reauthorization_required')
        result = api.guarded(failed)()
        self.assertEqual(result['error'], 'reauthorization_required')
        self.assertEqual(result['connection_notices'][0]['bank'], 'revolut')
        with patch.object(api, 'connection_notices', side_effect=OSError('private-detail')):
            self.assertEqual(api.guarded(lambda: {'ok': True})(), {'ok': True})

    def test_composed_tools_keep_notices_at_top_level(self):
        self.save('bnp', timedelta(days=2))
        service = Mock()
        service.analysis_rows.return_value = []
        service.coverage.return_value = {}
        with patch.object(api, 'service', return_value=service):
            result = api.compare_periods('2026-10-01', '2026-10-02', '2026-09-01', '2026-09-02')
        self.assertIn('connection_notices', result)
        self.assertNotIn('connection_notices', result['current'])
        self.assertNotIn('connection_notices', result['previous'])

    def test_oversized_result_still_delivers_due_notice(self):
        self.save('bnp', timedelta(days=1))
        result = api.guarded(lambda: {'data': 'x' * 98304})()
        self.assertEqual(result['error'], 'response_limit_narrow_date_range_or_filters')
        self.assertIn('connection_notices', result)

    def test_connection_status_is_always_inspectable_even_when_notice_throttled(self):
        self.save('bnp', timedelta(days=3))
        first = api.get_connection_status()
        second = api.get_connection_status()
        self.assertTrue(second['bnp']['expires_soon'])
        self.assertIn('connection_notices', first)
        self.assertNotIn('connection_notices', second)


if __name__ == '__main__': unittest.main()
